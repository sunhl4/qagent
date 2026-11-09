"""South-bound SSH adapter for the compute.hpc capability.

The company-agent kernel reaches every provider through the
``company-agent-provider/1.0`` HTTP envelope, so this adapter exposes that
envelope locally and bridges it to the authorized SLURM login node over an
openSSH key-authenticated channel (``BatchMode``; no passwords are read).

Fail-closed rules implemented here:

- The HTTP endpoint accepts exactly one path, one method, one protocol
  version, and bounded JSON payloads.
- The SSH target must be configured through ``COMPANY_AGENT_HPC_USER`` and
  ``COMPANY_AGENT_HPC_HOST`` and must match strict character classes; when
  either is missing every request fails closed.
- A configured shared bearer token is required on every request; missing
  credentials fail closed. The value is compared in constant time and never echoed.
- Only ``hpc.queue`` (read-only ``squeue`` probe), ``hpc.submit`` (``sbatch``),
  and five read-only-classified probes/operations are implemented:
  ``hpc.job-status`` (one job in the live queue then accounting history),
  ``hpc.script-exists`` (``test -f``), ``hpc.resources`` (aggregated ``sinfo``
  inventory rows plus the per-account ``staging_root`` derived from the SSH
  login account's own home directory), ``hpc.file-list`` (one-directory
  listing), and
  ``hpc.file-fetch`` (gateway file downloaded into the DSH workspace under
  ``gateway/<basename>``; the workspace header is required and the file bytes
  never pass through the model context), ``hpc.job-cancel`` (``scancel`` of
  one job), ``hpc.dir-create`` (``mkdir -p``), and ``hpc.file-remove``
  (bounded ``rm`` of one regular file with an honest missing-skip receipt).
  ``hpc.stage-file`` and the gateway mutations are the controlled writes
  (workspace file to one gateway path; human approval is
  enforced by the kernel policy contract; an existing gateway file is only
  touched with an explicit overwrite flag, otherwise an honest skipped
  receipt is returned). Gateway files are limited to bounded UTF-8 text.
  All remote
  arguments are revalidated against the same character classes as the tool
  contract before they are shell quoted into the remote command, so the local
  side never spawns a shell and remote expansion is bounded by quoting.
- Results are short receipts or short queue rows. Errors stay generic and
  never include host names, stderr text, or configuration values.

Run: ``python -m company_agent.hpc_ssh --port 8791`` and point the provider
contract's ``COMPANY_AGENT_HPC_INVOKE_URL`` at ``http://127.0.0.1:8791/invoke``.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shlex
import signal
import stat
import subprocess
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from company_agent.workspace_files import WorkspaceFileError, open_file, resolve as resolve_workspace

PROVIDER_ID = "hpc-slurm-ssh"
PROTOCOL = "company-agent-provider/1.0"
QUEUE_OPERATION = "hpc.queue"
SUBMIT_OPERATION = "hpc.submit"
STATUS_OPERATION = "hpc.job-status"
SCRIPT_OPERATION = "hpc.script-exists"
RESOURCES_OPERATION = "hpc.resources"
LIST_OPERATION = "hpc.file-list"
FETCH_OPERATION = "hpc.file-fetch"
STAGE_OPERATION = "hpc.stage-file"
CANCEL_OPERATION = "hpc.job-cancel"
DIR_OPERATION = "hpc.dir-create"
REMOVE_OPERATION = "hpc.file-remove"

_MAX_REQUEST_BYTES = 1_000_000
_SSH_CONNECT_TIMEOUT = 8
_QUEUE_TIMEOUT = 20
_SUBMIT_TIMEOUT = 30
_STATUS_TIMEOUT = 20
_MAX_QUEUE_ROWS = 16
_MAX_RESULT_BYTES = 64_000
_ENVELOPE_KEYS_OK = frozenset({"protocol", "ok", "provider", "request_id", "result"})
_ENVELOPE_KEYS_ERROR = frozenset({"protocol", "ok", "provider", "request_id", "error"})

_USER_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_HOST_PATTERN = re.compile(r"^[A-Za-z0-9.:_-]{1,253}$")
_JOB_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_SCRIPT_PATTERN = re.compile(r"^/[A-Za-z0-9_./-]{1,255}$")
_PARTITION_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_WALLTIME_PATTERN = re.compile(r"^[0-9]{1,3}:[0-9]{2}:[0-9]{2}$")
_REQUEST_ID_PATTERN = re.compile(r"^req_[0-9a-f]{32}$")
_SLURM_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,31}$")
_SLURM_JOB_PATTERN = re.compile(r"^[0-9]{1,32}$")
_QUEUE_FIELD_DELIMITER = "\t"
_INVALID_FIELD = re.compile(r"[\t\r\n]")
_GENERIC_ERROR = "hpc gateway is unavailable"

# resources_result folds a single home echo into the sinfo call so the
# per-account staging root is derived from the authorized login account itself:
# whatever identity was provisioned, its writable home reports
# <home>/company_agent; no account-specific path is ever stored in this repo.
# The dollars are escaped because the desktop runs ssh through wsl.exe, and
# wsl.exe expands $HOME (and $?) in the argument to the Windows-side Linux
# home before ssh ever reaches the cluster.
_STAGING_MARKER = "company-agent-home"
_STAGING_DIRNAME = "company_agent"


class AdapterError(RuntimeError):
    """Raised when a request cannot be served under the fail-closed contract."""


@dataclass(frozen=True)
class SshTarget:
    user: str
    host: str


@dataclass(frozen=True)
class SshResult:
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool


def ssh_target() -> SshTarget | None:
    user = str(os.environ.get("COMPANY_AGENT_HPC_USER") or "").strip()
    host = str(os.environ.get("COMPANY_AGENT_HPC_HOST") or "").strip()
    if not _USER_PATTERN.fullmatch(user) or not _HOST_PATTERN.fullmatch(host):
        return None
    return SshTarget(user=user, host=host)


def run_ssh(target: SshTarget, remote_command: str, *, timeout: int,
            stdin_text: str | None = None) -> SshResult:
    argv = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={_SSH_CONNECT_TIMEOUT}",
        "-o", "StrictHostKeyChecking=yes",
        f"{target.user}@{target.host}",
        remote_command,
    ]
    # The company SSH key and known_hosts live in the WSL home. Windows ssh
    # cannot see them, so the desktop opts in and runs that same ssh.
    if os.environ.get("COMPANY_AGENT_HPC_VIA_WSL") == "1" and os.name == "nt":
        distro = os.environ.get("COMPANY_AGENT_WSL_DISTRO", "Ubuntu").strip() or "Ubuntu"
        if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", distro):
            root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT") or r"C:\Windows"
            wsl = Path(root) / "System32" / "wsl.exe"
            if wsl.is_file():
                argv = [str(wsl), "-d", distro, "--", *argv]
    try:
        # Bytes in, bytes out. Text mode on Windows rewrites \n to \r\n, and
        # sbatch then rejects the staged script for DOS line breaks.
        completed = subprocess.run(
            argv,
            capture_output=True,
            input=None if stdin_text is None else stdin_text.encode("utf-8"),
            timeout=timeout,
            check=False,
        )
        stdout = completed.stdout.decode("utf-8", "replace") if isinstance(completed.stdout, bytes) else (completed.stdout or "")
        stderr = completed.stderr.decode("utf-8", "replace") if isinstance(completed.stderr, bytes) else (completed.stderr or "")
        return SshResult(
            stdout=stdout,
            stderr=stderr,
            returncode=int(completed.returncode if completed.returncode is not None else -1),
            timed_out=False,
        )
    except subprocess.TimeoutExpired:
        return SshResult(stdout="", stderr="", returncode=-1, timed_out=True)
    except OSError:
        return SshResult(stdout="", stderr="", returncode=-1, timed_out=False)


def _clean(value: str, limit: int) -> str:
    value = value.strip()[:limit]
    return _INVALID_FIELD.sub("", value)


_QUEUE_FIELDS_FORMAT = "%.20i\t%.120j\t%.60P\t%.30T\t%.16N\t%.16M"
_HISTORY_FIELDS = "JobID%28,State%32,Elapsed%16,JobName%120"
_SINFO_FIELDS = "%P|%a|%D|%t|%C"


def _parse_queue_rows(stdout: str) -> list[dict[str, str]]:
    jobs: list[dict[str, str]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        fields = line.split(_QUEUE_FIELD_DELIMITER)
        if len(fields) != 6:
            continue
        slurm_number = fields[0].strip()
        if not slurm_number.isdigit():
            continue
        state = _clean(fields[3], 32)
        if not state:
            continue
        jobs.append(
            {
                "slurm_number": slurm_number[:32],
                "name": _clean(fields[1], 128),
                "partition": _clean(fields[2], 64),
                "state": state,
                "nodes": _clean(fields[4], 16),
                "elapsed": _clean(fields[5], 16),
            }
        )
        if len(jobs) >= _MAX_QUEUE_ROWS:
            break
    return jobs


def queue_result() -> dict[str, object]:
    target = ssh_target()
    if target is None:
        raise AdapterError(_GENERIC_ERROR)
    result = run_ssh(
        target,
        f"squeue -u {target.user} -h -o '{_QUEUE_FIELDS_FORMAT}'",
        timeout=_QUEUE_TIMEOUT,
    )
    if result.timed_out or result.returncode != 0:
        raise AdapterError(_GENERIC_ERROR)
    jobs = _parse_queue_rows(result.stdout)
    return {"provider": PROVIDER_ID, "jobs": jobs, "status": "completed"}


def _validated_submit_arguments(payload: dict[str, object]) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise AdapterError("invalid submit arguments")
    if set(payload) - {"job_name", "script", "partition", "nodes", "walltime"}:
        raise AdapterError("invalid submit arguments")
    job_name = payload.get("job_name")
    script = payload.get("script")
    partition = payload.get("partition")
    nodes = payload.get("nodes")
    walltime = payload.get("walltime")
    if not isinstance(job_name, str) or not _JOB_NAME_PATTERN.fullmatch(job_name):
        raise AdapterError("invalid submit arguments")
    if not isinstance(script, str) or not _SCRIPT_PATTERN.fullmatch(script):
        raise AdapterError("invalid submit arguments")
    if ".." in script.split("/") or script.endswith("/"):
        raise AdapterError("invalid submit arguments")
    argument_list = [f"-J {shlex.quote(job_name)}"]
    if partition is not None:
        if not isinstance(partition, str) or not _PARTITION_PATTERN.fullmatch(partition):
            raise AdapterError("invalid submit arguments")
        argument_list.append(f"-p {shlex.quote(partition)}")
    if nodes is not None:
        if isinstance(nodes, bool) or not isinstance(nodes, int) or not 1 <= nodes <= 64:
            raise AdapterError("invalid submit arguments")
        argument_list.append(f"-N {nodes}")
    if walltime is not None:
        if (not isinstance(walltime, str) or not _WALLTIME_PATTERN.fullmatch(walltime)
            or any(int(part) > 59 for part in walltime.split(":")[1:])):
            raise AdapterError("invalid submit arguments")
        argument_list.append(f"-t {shlex.quote(walltime)}")
    argument_list.append(shlex.quote(script))
    return {"command": "sbatch --parsable " + " ".join(argument_list), "fields": payload}


def submit_result(payload: dict[str, object]) -> dict[str, object]:
    validated = _validated_submit_arguments(payload)
    target = ssh_target()
    if target is None:
        raise AdapterError(_GENERIC_ERROR)
    result = run_ssh(target, validated["command"], timeout=_SUBMIT_TIMEOUT)
    if result.timed_out or result.returncode != 0:
        raise AdapterError(_GENERIC_ERROR)
    line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    line = line.split(";", 1)[0]  # sbatch --parsable returns number[;cluster].
    if not re.fullmatch(r"[0-9]{1,32}", line):
        raise AdapterError(_GENERIC_ERROR)
    fields = dict(validated["fields"])
    output: dict[str, object] = {
        "provider": PROVIDER_ID,
        "slurm_number": line,
        "job_name": fields["job_name"],
        "state": "pending",
    }
    if isinstance(fields.get("partition"), str):
        output["partition"] = fields["partition"]
    return output


def operation_result(operation: str, payload: dict[str, object], workspace: str = "") -> dict[str, object]:
    if operation == QUEUE_OPERATION:
        if payload:
            raise AdapterError("queue probe accepts no arguments")
        return queue_result()
    if operation == SUBMIT_OPERATION:
        return submit_result(payload)
    if operation == STATUS_OPERATION:
        return status_result(payload)
    if operation == SCRIPT_OPERATION:
        return script_exists_result(payload)
    if operation == RESOURCES_OPERATION:
        if payload:
            raise AdapterError("resources probe accepts no arguments")
        return resources_result()
    if operation == LIST_OPERATION:
        return file_list_result(payload)
    if operation == FETCH_OPERATION:
        return file_fetch_result(payload, workspace)
    if operation == STAGE_OPERATION:
        return stage_file_result(payload, workspace)
    if operation == CANCEL_OPERATION:
        return job_cancel_result(payload)
    if operation == DIR_OPERATION:
        return dir_create_result(payload)
    if operation == REMOVE_OPERATION:
        return file_remove_result(payload)
    raise AdapterError("unknown operation")


def _validated_job_number_argument(payload: object) -> str:
    number = payload.get("slurm_number") if isinstance(payload, dict) else None
    if not isinstance(number, str) or not _SLURM_JOB_PATTERN.fullmatch(number):
        raise AdapterError("invalid cancel arguments")
    return number


def job_cancel_result(payload: dict[str, object]) -> dict[str, object]:
    number = _validated_job_number_argument(payload)
    target = ssh_target()
    if target is None:
        raise AdapterError(_GENERIC_ERROR)
    result = run_ssh(
        target,
        "scancel " + shlex.quote(number),
        timeout=_SUBMIT_TIMEOUT,
    )
    if result.timed_out:
        raise AdapterError(_GENERIC_ERROR)
    return {
        "provider": PROVIDER_ID,
        "slurm_number": number,
        "cancelled": result.returncode == 0,
    }


def _account_home(target: SshTarget) -> str:
    """Cluster login home, cached for this process.

    wsl.exe expands an unescaped ``$HOME`` before ssh runs, so a desktop that
    learned its staging root from that expansion holds the Linux distro home.
    The escaped form is expanded by the cluster shell instead.
    """
    cached = getattr(_account_home, "value", None)
    if isinstance(cached, str):
        return cached
    result = run_ssh(target, "printf '%s' \\$HOME", timeout=_STATUS_TIMEOUT)
    home = result.stdout.strip()
    if (result.timed_out or result.returncode != 0
            or not _SCRIPT_PATTERN.fullmatch(home)
            or ".." in home.split("/") or home.endswith("/")):
        raise AdapterError(_GENERIC_ERROR)
    _account_home.value = home
    return home


def _place_staging_path(path: str, target: SshTarget) -> str:
    """Move a company_agent path onto the cluster account home.

    Callers that cached the WSL home keep sending ``/home/.../company_agent``.
    That directory is not the login account's writable staging root. Paths
    that already sit on the account home, and paths outside company_agent,
    stay unchanged.
    """
    if os.environ.get("COMPANY_AGENT_HPC_VIA_WSL") != "1":
        return path
    home = _account_home(target)
    if path == home or path.startswith(home + "/"):
        return path
    marker = "/" + _STAGING_DIRNAME
    if path.endswith(marker):
        index = len(path) - len(marker)
    else:
        index = path.find(marker + "/")
    if index < 0:
        return path
    placed = home + path[index:]
    if (not _SCRIPT_PATTERN.fullmatch(placed) or ".." in placed.split("/")
            or placed.endswith("/")):
        raise AdapterError(_GENERIC_ERROR)
    return placed


def dir_create_result(payload: dict[str, object]) -> dict[str, object]:
    path = _validated_path_argument(payload, "path")
    target = ssh_target()
    if target is None:
        raise AdapterError(_GENERIC_ERROR)
    path = _place_staging_path(path, target)
    exists_dir = run_ssh(
        target,
        "test -d " + shlex.quote(path),
        timeout=_STATUS_TIMEOUT,
    )
    if exists_dir.timed_out or exists_dir.returncode not in (0, 1):
        raise AdapterError(_GENERIC_ERROR)
    if exists_dir.returncode == 0:
        return {"provider": PROVIDER_ID, "path": path, "created": False, "mode": "exists"}
    created = run_ssh(
        target,
        "mkdir -p " + shlex.quote(path),
        timeout=_SUBMIT_TIMEOUT,
    )
    if created.timed_out or created.returncode != 0:
        raise AdapterError(_GENERIC_ERROR)
    return {"provider": PROVIDER_ID, "path": path, "created": True, "mode": "created"}


def file_remove_result(payload: dict[str, object]) -> dict[str, object]:
    path = _validated_path_argument(payload, "path")
    target = ssh_target()
    if target is None:
        raise AdapterError(_GENERIC_ERROR)
    exists_file = run_ssh(
        target,
        "test -f " + shlex.quote(path),
        timeout=_STATUS_TIMEOUT,
    )
    if exists_file.timed_out or exists_file.returncode not in (0, 1):
        raise AdapterError(_GENERIC_ERROR)
    if exists_file.returncode == 1:
        return {
            "provider": PROVIDER_ID,
            "path": path,
            "removed": False,
            "mode": "skipped_missing",
        }
    removed = run_ssh(
        target,
        "rm -- " + shlex.quote(path),
        timeout=_SUBMIT_TIMEOUT,
    )
    if removed.timed_out or removed.returncode != 0:
        raise AdapterError(_GENERIC_ERROR)
    return {"provider": PROVIDER_ID, "path": path, "removed": True, "mode": "removed"}


def _clean_node_state(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z]", "", value)
    cleaned = cleaned.strip()[:16]
    return cleaned


def resources_result() -> dict[str, object]:
    target = ssh_target()
    if target is None:
        raise AdapterError(_GENERIC_ERROR)
    result = run_ssh(
        target,
        f"sinfo -h -o '{_SINFO_FIELDS}' ; sinfo_status=\\$? ; "
        f"printf '{_STAGING_MARKER}\\t%s\\n' \\$HOME ; exit \\$sinfo_status",
        timeout=_STATUS_TIMEOUT,
    )
    if result.timed_out or result.returncode != 0:
        raise AdapterError(_GENERIC_ERROR)
    partitions: dict[str, dict[str, object]] = {}
    home: str | None = None
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        if line.startswith(f"{_STAGING_MARKER}\t"):
            candidate = line[len(_STAGING_MARKER) + 1 :]
            if home is not None or _SCRIPT_PATTERN.fullmatch(candidate) is None:
                raise AdapterError(_GENERIC_ERROR)
            if ".." in candidate.split("/") or candidate.endswith("/") or candidate == "/":
                raise AdapterError(_GENERIC_ERROR)
            home = candidate
            continue
        fields = line.split("|")
        if len(fields) != 5:
            continue
        partition = _clean(fields[0], 64)
        state_group = _clean_node_state(fields[3])
        nodes_group_raw = fields[2].strip()
        if not partition or not state_group or not nodes_group_raw.isdigit():
            continue
        core_fields = fields[4].strip().split("/")
        if len(core_fields) != 4 or any(not value.isdigit() for value in core_fields):
            continue
        if partition not in partitions:
            partitions[partition] = {
                "partition": partition,
                "availability": _clean(fields[1], 32),
                "nodes_total": 0,
                "nodes_by_state": [],
                "cores_allocated": 0,
                "cores_idle": 0,
                "cores_other": 0,
                "cores_total": 0,
            }
        row = partitions[partition]
        row["nodes_total"] = int(row["nodes_total"]) + int(nodes_group_raw)
        row["nodes_by_state"].append(f"{state_group}={nodes_group_raw}")
        row["cores_allocated"] += int(core_fields[0])
        row["cores_idle"] += int(core_fields[1])
        row["cores_other"] += int(core_fields[2])
        row["cores_total"] += int(core_fields[3])
    if home is None:
        # The account staging root is a required contract output: when the login
        # account's home cannot be reported, the probe must fail closed instead
        # of letting callers fall back to shared directories.
        raise AdapterError(_GENERIC_ERROR)
    rows: list[dict[str, object]] = []
    for row in partitions.values():
        row["nodes_by_state"] = ",".join(row["nodes_by_state"])[:64]
        if row["nodes_by_state"]:
            rows.append(row)
    return {"provider": PROVIDER_ID, "partitions": rows, "staging_root": home + "/" + _STAGING_DIRNAME}


_MAX_GATEWAY_TEXT_BYTES = 48_000
_LIST_FIELDS_FORMAT = "%s\\t%T@\\t%f\\n"


def _workspace_root(header: str) -> Path:
    try:
        workspace = base64.b64decode(header, altchars=b"-_", validate=True).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise AdapterError(_GENERIC_ERROR) from exc
    root = Path(workspace)
    if not workspace or not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise AdapterError(_GENERIC_ERROR)
    try:
        return root.resolve(strict=True)
    except OSError as exc:
        raise AdapterError(_GENERIC_ERROR) from exc


def _workspace_file_bytes(root: Path, relative: str) -> bytes:
    try:
        resolve_workspace(root, relative)
        with open_file(root, relative) as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_GATEWAY_TEXT_BYTES:
                raise AdapterError(_GENERIC_ERROR)
            data = stream.read(_MAX_GATEWAY_TEXT_BYTES + 1)
            after = os.fstat(stream.fileno())
            first = (before.st_dev, before.st_ino, before.st_size,
                     before.st_mtime_ns, before.st_ctime_ns)
            second = (after.st_dev, after.st_ino, after.st_size,
                      after.st_mtime_ns, after.st_ctime_ns)
            if first != second or len(data) > _MAX_GATEWAY_TEXT_BYTES:
                raise AdapterError(_GENERIC_ERROR)
            return data
    except (WorkspaceFileError, OSError) as exc:
        raise AdapterError(_GENERIC_ERROR) from exc


def _workspace_destination(root: Path, relative: str) -> Path:
    try:
        return resolve_workspace(root, relative)
    except (WorkspaceFileError, OSError) as exc:
        raise AdapterError(_GENERIC_ERROR) from exc
def _validated_path_argument(payload: dict[str, object], field: str) -> str:
    value = payload.get(field) if isinstance(payload, dict) else None
    if not isinstance(value, str) or not _SCRIPT_PATTERN.fullmatch(value):
        raise AdapterError("invalid file arguments")
    if ".." in value.split("/") or value.endswith("/"):
        raise AdapterError("invalid file arguments")
    return value


def _workspace_relative(payload: dict[str, object]) -> str:
    value = payload.get("workspace_path") if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value or value.startswith("/") or len(value) > 255:
        raise AdapterError("invalid file arguments")
    if ".." in Path(value).parts or "\x00" in value or "\r" in value or "\n" in value:
        raise AdapterError("invalid file arguments")
    if any(character.isspace() for character in value):
        raise AdapterError("invalid file arguments")
    return value


def file_list_result(payload: dict[str, object]) -> dict[str, object]:
    path = _validated_path_argument(payload, "path")
    target = ssh_target()
    if target is None:
        raise AdapterError(_GENERIC_ERROR)
    result = run_ssh(
        target,
        "find " + shlex.quote(path) + " -maxdepth 1 -mindepth 1 -type f -printf '"
        + _LIST_FIELDS_FORMAT + "' | head -33",
        timeout=_STATUS_TIMEOUT,
    )
    if result.timed_out or result.returncode != 0:
        raise AdapterError(_GENERIC_ERROR)
    entries: list[dict[str, object]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        fields = line.split(_QUEUE_FIELD_DELIMITER)
        if len(fields) != 3:
            continue
        name = _clean(fields[2], 128)
        if not name or any(character in name for character in "\t\r\n"):
            continue
        if not fields[0].isdigit() or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", fields[1]):
            continue
        entries.append({
            "name": name,
            "bytes": int(fields[0]),
            "mtime": min(int(float(fields[1])), 4_000_000_000),
        })
        if len(entries) >= 32:
            break
    return {"provider": PROVIDER_ID, "path": path, "entries": entries}


def file_fetch_result(payload: dict[str, object], workspace: str) -> dict[str, object]:
    path = _validated_path_argument(payload, "path")
    root = _workspace_root(workspace)
    target = ssh_target()
    if target is None:
        raise AdapterError(_GENERIC_ERROR)
    # Existence is checked in its own call: in a `|` pipeline the channel would
    # otherwise only report the last (base64) status and a missing remote file
    # would surface as an honest-looking but wrong `0 bytes` fetch.
    exists_check = run_ssh(
        target,
        "test -f " + shlex.quote(path),
        timeout=_STATUS_TIMEOUT,
    )
    if exists_check.timed_out or exists_check.returncode not in (0, 1):
        raise AdapterError(_GENERIC_ERROR)
    if exists_check.returncode == 1:
        raise AdapterError("remote file is unavailable")
    result = run_ssh(
        target,
        "head -c " + str(_MAX_GATEWAY_TEXT_BYTES) + " " + shlex.quote(path) + " | base64 -w0",
        timeout=_STATUS_TIMEOUT,
    )
    if result.timed_out or result.returncode != 0:
        raise AdapterError(_GENERIC_ERROR)
    encoded = result.stdout.strip()
    if len(encoded) >= 4 * ((47_999 + 2) // 3):
        raise AdapterError(_GENERIC_ERROR)
    try:
        data = base64.b64decode(encoded, validate=True)
        text = data.decode("utf-8", errors="strict").replace("\r\n", "\n").replace("\r", "\n")
        if data != text.encode("utf-8"):
            raise UnicodeError("round-trip")
    except (ValueError, UnicodeError) as exc:
        raise AdapterError(_GENERIC_ERROR) from exc
    filename = Path(path).name
    if not filename or any(character in filename for character in "\t\r\n\\"):
        raise AdapterError(_GENERIC_ERROR)
    gateway_dir = root / "gateway"
    if not gateway_dir.exists():
        os.mkdir(gateway_dir, mode=0o700)
    if not gateway_dir.is_dir() or gateway_dir.is_symlink():
        raise AdapterError(_GENERIC_ERROR)
    destination = gateway_dir / filename
    if destination.exists() and (destination.is_symlink() or not stat.S_ISREG(destination.stat().st_mode)):
        raise AdapterError(_GENERIC_ERROR)
    import tempfile

    os.chmod(gateway_dir, 0o700)
    temporary_fd, temporary_name = tempfile.mkstemp(dir=gateway_dir, prefix=".fetch-")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(temporary_fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(temporary, destination)
        except OSError:
            # Windows may reject replace while the destination has an open handle;
            # both paths are already inside the verified gateway directory.
            with open(temporary, "rb") as source_stream, open(destination, "wb") as destination_stream:
                destination_stream.write(source_stream.read())
                destination_stream.flush()
                os.fsync(destination_stream.fileno())
            temporary.unlink(missing_ok=True)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return {
        "provider": PROVIDER_ID,
        "gateway_path": path,
        "saved_to": "gateway/" + filename,
        "bytes": len(data),
    }


def stage_file_result(payload: dict[str, object], workspace: str) -> dict[str, object]:
    gateway_path = _validated_path_argument(payload, "gateway_path")
    workspace_relative = _workspace_relative(payload)
    overwrite = payload.get("overwrite", False) if isinstance(payload, dict) else False
    if not isinstance(overwrite, bool):
        raise AdapterError("invalid file arguments")
    root = _workspace_root(workspace)
    data = _workspace_file_bytes(root, workspace_relative)
    try:
        text = data.decode("utf-8", errors="strict").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeError as exc:
        raise AdapterError(_GENERIC_ERROR) from exc
    target = ssh_target()
    if target is None:
        raise AdapterError(_GENERIC_ERROR)
    gateway_path = _place_staging_path(gateway_path, target)
    exists_check = run_ssh(
        target,
        "test -f " + shlex.quote(gateway_path),
        timeout=_STATUS_TIMEOUT,
    )
    if exists_check.timed_out or exists_check.returncode not in (0, 1):
        raise AdapterError(_GENERIC_ERROR)
    if exists_check.returncode == 0 and not overwrite:
        return {
            "provider": PROVIDER_ID,
            "gateway_path": gateway_path,
            "written": False,
            "mode": "skipped_exists",
        }
    written = run_ssh(
        target,
        "cat > " + shlex.quote(gateway_path),
        timeout=_SUBMIT_TIMEOUT,
        stdin_text=text,
    )
    if written.timed_out or written.returncode != 0:
        raise AdapterError(_GENERIC_ERROR)
    mode = "overwritten" if exists_check.returncode == 0 else "created"
    return {
        "provider": PROVIDER_ID,
        "gateway_path": gateway_path,
        "written": True,
        "mode": mode,
        "bytes": len(data),
    }


def _validated_script_arguments(payload: object, *fields: str) -> dict[str, str]:
    if not isinstance(payload, dict) or set(payload) != set(fields):
        raise AdapterError("invalid script arguments")
    values: dict[str, str] = {}
    for name in fields:
        value = payload[name]
        if not isinstance(value, str) or not _SCRIPT_PATTERN.fullmatch(value):
            raise AdapterError("invalid script arguments")
        if ".." in value.split("/") or value.endswith("/"):
            raise AdapterError("invalid script arguments")
        values[name] = value
    return values


def script_exists_result(payload: dict[str, object]) -> dict[str, object]:
    fields = _validated_script_arguments(payload, "script")
    target = ssh_target()
    if target is None:
        raise AdapterError(_GENERIC_ERROR)
    result = run_ssh(
        target,
        "test -f " + shlex.quote(fields["script"]),
        timeout=_STATUS_TIMEOUT,
    )
    if result.timed_out or result.returncode not in (0, 1):
        raise AdapterError(_GENERIC_ERROR)
    return {
        "provider": PROVIDER_ID,
        "script": fields["script"],
        "exists": result.returncode == 0,
    }


def _validated_job_number(payload: dict[str, object]) -> str:
    if not isinstance(payload, dict) or set(payload) != {"slurm_number"}:
        raise AdapterError("invalid status arguments")
    number = payload.get("slurm_number")
    if not isinstance(number, str) or not _SLURM_JOB_PATTERN.fullmatch(number):
        raise AdapterError("invalid status arguments")
    return number


def _history_rows(numbers: str) -> list[dict[str, str]]:
    target = ssh_target()
    if target is None:
        raise AdapterError(_GENERIC_ERROR)
    result = run_ssh(
        target,
        "sacct --parsable2 -n -j " + shlex.quote(numbers)
        + " -o " + shlex.quote(_HISTORY_FIELDS),
        timeout=_STATUS_TIMEOUT,
    )
    if result.timed_out or result.returncode != 0:
        raise AdapterError(_GENERIC_ERROR)
    rows: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) < 4:
            continue
        job_number = fields[0].strip()
        if not job_number.isdigit():
            continue
        state = _clean(fields[1], 32)
        if not state:
            continue
        rows.append(
            {
                "slurm_number": job_number[:32],
                "state": state,
                "elapsed": _clean(fields[2], 16),
                "name": _clean(fields[3], 128),
            }
        )
    return rows


def status_result(payload: dict[str, object]) -> dict[str, object]:
    number = _validated_job_number(payload)
    target = ssh_target()
    if target is None:
        raise AdapterError(_GENERIC_ERROR)
    queue = run_ssh(
        target,
        f"squeue -j {shlex.quote(number)} -h -o '{_QUEUE_FIELDS_FORMAT}'",
        timeout=_STATUS_TIMEOUT,
    )
    if queue.timed_out or queue.returncode != 0:
        raise AdapterError(_GENERIC_ERROR)
    rows = _parse_queue_rows(queue.stdout)
    if rows:
        return {"provider": PROVIDER_ID, **rows[0], "slurm_number": number, "source": "queue"}
    history = _history_rows(number)
    if history:
        return {"provider": PROVIDER_ID, **history[0], "slurm_number": number, "source": "history"}
    return {
        "provider": PROVIDER_ID,
        "slurm_number": number,
        "state": "not_found",
        "source": "none",
    }


def _response_envelope(
    *, ok: bool, request_id: str = "", result: dict[str, object] | None = None, error: str | None = None
) -> bytes:
    envelope: dict[str, object] = {
        "protocol": PROTOCOL,
        "ok": ok,
        "provider": PROVIDER_ID,
        "request_id": request_id,
    }
    if ok:
        envelope["result"] = result
    else:
        envelope["error"] = error
    return json.dumps(envelope, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def handle_request(body: bytes, authorization: str | None, workspace_header: str = "") -> tuple[int, bytes]:
    from company_agent.gateway import dispatch

    if ssh_target() is None:
        return HTTPStatus.SERVICE_UNAVAILABLE.value, _response_envelope(
            ok=False, error=_GENERIC_ERROR
        )
    return dispatch(body, authorization, provider=PROVIDER_ID, token_env="COMPANY_AGENT_HPC_TOKEN",
                    operations={QUEUE_OPERATION, SUBMIT_OPERATION, STATUS_OPERATION, SCRIPT_OPERATION,
                                RESOURCES_OPERATION, LIST_OPERATION, FETCH_OPERATION, STAGE_OPERATION,
                                CANCEL_OPERATION, DIR_OPERATION, REMOVE_OPERATION},
                    workspace=workspace_header,
                    execute=lambda operation, payload, workspace: operation_result(
                        operation, payload, workspace))


class _Handler(BaseHTTPRequestHandler):
    server_version = "company-agent-hpc-ssh/1.0"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        if self.path != "/invoke":
            self._respond(HTTPStatus.NOT_FOUND.value, _response_envelope(
                ok=False, request_id="", error=_GENERIC_ERROR
            ))
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = -1
        if not 0 < length <= _MAX_REQUEST_BYTES:
            self._respond(HTTPStatus.BAD_REQUEST.value, _response_envelope(
                ok=False, request_id="", error=_GENERIC_ERROR
            ))
            return
        body = self.rfile.read(length)
        status, payload = handle_request(
            body,
            self.headers.get("Authorization"),
            self.headers.get("X-Company-Workspace") or "",
        )
        self._respond(status, payload)

    def _respond(self, status: int, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - http.server API
        del format, args  # keep stderr quiet; diagnostics stay generic


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="company-agent.hpc_ssh")
    parser.add_argument("--port", type=int, default=8791)
    ns = parser.parse_args(args=argv)
    if not 1 <= ns.port <= 65535:
        parser.error("port must be 1-65535")
    server = ThreadingHTTPServer(("127.0.0.1", ns.port), _Handler)
    server.daemon_threads = True

    def _shutdown(_signum: object, _frame: object) -> None:
        server.shutdown()

    try:
        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)
    except (ValueError, OSError):
        pass
    server.serve_forever(poll_interval=0.5)
    server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
