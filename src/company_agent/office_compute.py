"""Batch aggregation sandbox adapter (the run_compute port, §4.9).

Contract: ``company_office_compute`` (``company.office/2.0``, ``office.compute``).
The tool is the parent of the child runner in ``office_compute_child``:

- the machine-level switch ``COMPANY_AGENT_COMPUTE_ALLOW`` must equal ``1`` or
  ``true`` - without it the call refuses, high-security deployments stay
  inert, and no environment variable fakes it in;
- the child process is spawned per call with a whitelisted environment (the
  P0 minimal env PLUS the workspace root identity), a 30s ceiling and a
  bounded stdout, cwd outside the workspace; the source and the project name
  travel through stdin, never through argv;
- the receipt is re-verified against the disk: every written path must still
  exist inside the project tree, the re-read sha256/size replaces whatever
  the child reported, and charts must exist (json+svg);
- trust is untrusted end to end: the child answers one JSON line, anything
  else - multiple lines, missing fields, non-JSON, oversized - is an honest
  refusal, never a guess;
- elapsed time is measured by the parent because the child cannot be trusted
  with its own clock.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from company_agent import office_compute_child, office_convert, office_purpose, workspace_files

ENV_ALLOW = "COMPANY_AGENT_COMPUTE_ALLOW"
WORKSPACE_ENV = workspace_files.WORKSPACE_ENV

MAX_SOURCE = 80_000
STDOUT_CAP = 52_000
RUN_TIMEOUT = 30


class OfficeComputeError(ValueError):
    """Refusal that names the boundary hit without echoing paths outside the root."""


def compute(args: dict) -> dict:
    """Contract entry point: run one whitelisted sandbox program."""

    purpose = office_purpose.take(args)
    root = workspace_files.root()
    project = args.get("project")
    if not isinstance(project, str) or not project.strip() or project != project.strip():
        raise OfficeComputeError("project is invalid")
    compound = f"{project}"
    workspace_files._lexical(compound)
    project_dir = root / project
    if not project_dir.is_dir():
        raise OfficeComputeError(f"project 目录 {project!r} 不存在:请先用 create 建立工作区文件")
    if not _allowed():
        raise OfficeComputeError(
            f"本地计算沙箱未启用:{ENV_ALLOW}=1 才可执行代码评估;"
            "高安全部署保持关闭是设计行为,不是故障"
        )
    source = args.get("source")
    if not isinstance(source, str) or not source.strip():
        raise OfficeComputeError("source 必须是非空程序文本")
    if len(source) > MAX_SOURCE:
        raise OfficeComputeError(f"source {len(source)} 字符超过 {MAX_SOURCE} 上限,拒绝")

    started = time.monotonic()
    stdout = _run_child(root, project, source)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    receipt = _receipt(stdout)
    if receipt.get("ok") is not True:
        message = str(receipt.get("message") or "沙箱失败:无消息")
        raise OfficeComputeError(message[:200])
    verified = _verified(root, project, receipt, elapsed_ms)
    office_purpose.audit(
        "office_compute", purpose, {"project": project, "source_chars": len(source)}
    )
    return verified


def _allowed() -> bool:
    raw = str(os.environ.get(ENV_ALLOW) or "").strip().casefold()
    return raw in {"1", "true", "yes"}


def _run_child(root: Path, project: str, source: str) -> str:
    child = Path(office_compute_child.__file__)
    env = office_convert._minimal_env()
    env[WORKSPACE_ENV] = str(root)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        with tempfile.TemporaryDirectory(prefix="office-compute-") as scratch:
            finished = subprocess.run(
                [sys.executable, str(child), str(root)],
                cwd=scratch,
                env=env,
                input=json.dumps({"project": project, "source": source}, ensure_ascii=False).encode("utf-8"),
                capture_output=True,
                timeout=RUN_TIMEOUT,
            )
    except subprocess.TimeoutExpired as exc:
        raise OfficeComputeError(f"沙箱执行超过 {RUN_TIMEOUT} 秒被终止:产物作废") from exc
    except OSError as exc:
        raise OfficeComputeError(f"沙箱子进程无法启动:{str(exc)[:120]}") from exc
    output = finished.stdout or b""
    if len(output) > STDOUT_CAP:
        raise OfficeComputeError(f"沙箱输出超过 {STDOUT_CAP} 字节上限:如实拒绝")
    try:
        return output.decode("utf-8")
    except UnicodeError as exc:
        raise OfficeComputeError("沙箱输出不是 UTF-8:如实拒绝") from exc


def _receipt(text: str) -> dict[str, Any]:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    if len(lines) != 1:
        raise OfficeComputeError(f"沙箱输出应为一行 JSON,实得 {len(lines)} 行:如实拒绝")
    try:
        payload = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise OfficeComputeError("沙箱输出不是合法 JSON:如实拒绝") from exc
    if not isinstance(payload, dict):
        raise OfficeComputeError("沙箱输出不是 JSON 对象:如实拒绝")
    return payload


def _verified(root: Path, project: str, receipt: dict[str, Any], elapsed_ms: int) -> dict:
    writes = receipt.get("writes")
    if not isinstance(writes, list) or len(writes) > 200:
        raise OfficeComputeError("沙箱 writes 回执缺失或超 200 条:如实拒绝")
    verified_rows: list[dict[str, Any]] = []
    fingerprints: list[str] = []
    charts = receipt.get("charts")
    if not isinstance(charts, list) or len(charts) > 64:
        raise OfficeComputeError("沙箱 charts 回执缺失或超 64 条:如实拒绝")
    for row in writes:
        path_value = row.get("path") if isinstance(row, dict) else None
        if not isinstance(path_value, str) or not path_value.strip():
            raise OfficeComputeError("沙箱 write 回执缺 path:如实拒绝")
        compound = f"{project}/{path_value.strip()}"
        try:
            fingerprint = workspace_files.fingerprint(root, compound)
            resolved = workspace_files.resolve(root, compound)
            project_root = (root / project).resolve()
            if not resolved.is_relative_to(project_root):
                raise OfficeComputeError(f"沙箱写入越出项目目录:{path_value[:64]},如实拒绝")
        except (workspace_files.WorkspaceFileError, OSError) as exc:
            raise OfficeComputeError(
                f"沙箱声称写入但磁盘不符({str(exc)[:120]}):如实拒绝"
            ) from exc
        reported_bytes = row.get("bytes")
        if isinstance(reported_bytes, int) and reported_bytes != fingerprint["bytes"]:
            raise OfficeComputeError(
                f"沙箱回执 bytes 与磁盘不符:{path_value[:64]},如实拒绝"
            )
        verified_rows.append(
            {"path": fingerprint["path"], "bytes": fingerprint["bytes"], "sha256": fingerprint["sha256"]}
        )
        fingerprints.append(fingerprint["sha256"])
    for chart_path in charts:
        if not isinstance(chart_path, str) or not chart_path.strip():
            raise OfficeComputeError("沙箱 chart 回执缺路径:如实拒绝")
        try:
            fingerprint = workspace_files.fingerprint(root, f"{project}/{chart_path.strip()}")
            _ = fingerprint
        except (workspace_files.WorkspaceFileError, OSError) as exc:
            raise OfficeComputeError(f"沙箱 chart 磁盘不符:{str(exc)[:120]}") from exc
    prints = receipt.get("prints")
    if not isinstance(prints, list) or len(prints) > 40:
        raise OfficeComputeError("沙箱 prints 回执缺失或超 40 条:如实拒绝")
    prints = [str(row)[:400] for row in prints]
    if not isinstance(receipt.get("result"), dict):
        raise OfficeComputeError("沙箱 result 不是对象:如实拒绝")
    return {
        "result": receipt["result"],
        "written": verified_rows,
        "charts": [str(row) for row in charts],
        "prints": prints,
        "prints_truncated": receipt.get("prints_truncated") is True,
        "elapsed_ms": elapsed_ms,
        "sha256_writes": fingerprints,
        "trust": "untrusted_reference_data",
    }
