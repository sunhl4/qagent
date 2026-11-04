"""Local office conversion for the WPS-suite porting (§4.6/§4.7, L6 exit).

The MeWork stack kept ``ConvertDocToDocx`` in the cloud; the deepseekharness
port must compute locally, and the reference implementation's answer is a
local LibreOffice headless run with a resource lease. Same behavior here:

- ``.docx`` becomes a sibling ``.pdf``; ``.doc`` becomes a sibling ``.docx``;
  other suffixes refuse;
- the engine order is Word/WPS save-as first (``COMPANY_AGENT_WORD_CMD``),
  then on macOS an AppleScript save into the Word container, then a registered
  Word/WPS COM progid, then ``COMPANY_AGENT_SOFFICE`` / ``soffice`` /
  ``libreoffice``; with neither engine the call is a hard, honest failure -
  the port never fakes a converted artifact nor uploads anything;
- the conversion holds a bounded lease (``%TEMP%`` lock file keyed by the
  workspace root) so two tasks cannot fight over the same soffice; a lock
  older than 600 seconds is assumed dead and broken;
- the child process runs arrayed arguments with a whitelisted environment
  (no full ``process.env`` inheritance), bounded stdout and a 120s ceiling;
- the product must pass the three-way check: exists, non-empty, matching
  magic bytes (``%PDF-`` or a zip package carrying ``word/document.xml``);
- naming stays next to the source: ``<stem>.<ext>``, then
  ``<stem>_01.._99``; with ``overwrite=true`` the first same-name sibling is
  replaced, the source file itself never is;
- 20MB input cap with honest refusal.
"""
from __future__ import annotations

import contextlib
import errno
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from company_agent import office_create as _oc
from company_agent import office_ingest as _ingest
from company_agent import office_purpose, workspace_files

ENV_SOFFICE = "COMPANY_AGENT_SOFFICE"
ENV_WORD = "COMPANY_AGENT_WORD_CMD"

MAX_FILE_BYTES = _ingest.MAX_FILE_BYTES
STDOUT_CAP = 256_000
RUN_TIMEOUT = 120
LEASE_TIMEOUT = 120
LEASE_STALE_SECONDS = 600
_OUTPUT_MAGIC = {"pdf": b"%PDF-", "docx": b"PK\x03\x04"}
_SOURCE_MAGIC = {".docx": b"PK\x03\x04", ".doc": b"\xd0\xcf\x11\xe0"}
_CONVERSION = {".docx": ("pdf", "pdf"), ".doc": ("docx", "docx")}
_ENV_KEYS = ("PATH", "SystemRoot", "SystemDrive", "TEMP", "TMP", "COMSPEC", "PATHEXT")


class OfficeConvertError(ValueError):
    """Refusal that names the boundary hit without echoing paths outside the root."""


def convert(args: dict) -> dict:
    """Contract entry point: bounded local conversion with a lease."""

    purpose = office_purpose.take(args)
    root = workspace_files.root()
    compound = _oc._compound(args)
    resolved = workspace_files.resolve(root, compound)
    if not resolved.is_file():
        raise OfficeConvertError("workspace path is not a file")
    suffix = resolved.suffix.casefold()
    target_ext, fmt = _CONVERSION.get(suffix, ("", ""))
    if not target_ext:
        raise OfficeConvertError(f"{suffix or '(无后缀)'} 不是可转换类型;支持 .docx→pdf 与 .doc→docx")
    data = _read_bounded(root, compound)
    _check_magic(suffix, data)
    project = compound.split("/", 1)[0]
    try:
        from company_agent import office_validate

        office_validate.require_passed(project, args)
    except office_validate.OfficeValidateError as exc:
        raise OfficeConvertError(str(exc)) from exc

    engine, kind = _resolve_engine()
    lease_name = "soffice-" + hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:12] + ".lock"
    with tempfile.TemporaryDirectory(prefix="office-convert-") as staging:
        staging_path = Path(staging)
        with _lease(Path(tempfile.gettempdir()) / lease_name):
            if kind == "com":
                _com_save(engine, resolved, staging_path, fmt)
            elif kind == "apple":
                script_path = staging_path / "save-as.applescript"
                script_path.write_text(
                    _apple_script(resolved, staging_path, fmt), encoding="utf-8"
                )
                code, _output = _run(["osascript", str(script_path)], cwd=str(staging_path))
                if code != 0:
                    raise OfficeConvertError(f"apple 退出码 {code}:产物未生成,如实失败")
            else:
                if kind == "word":
                    command = [engine, "--save-as", fmt, str(staging_path), str(resolved)]
                else:
                    command = [
                        engine,
                        "--headless",
                        "--nologo",
                        "--nolockcheck",
                        "--convert-to",
                        fmt,
                        "--outdir",
                        str(staging_path),
                        str(resolved),
                    ]
                code, _output = _run(command, cwd=str(staging_path))
                if code != 0:
                    raise OfficeConvertError(f"{kind} 退出码 {code}:产物未生成,如实失败")
        product = staging_path / f"{resolved.stem}.{target_ext}"
        _verify_product(product, target_ext)
        data = product.read_bytes()
    target, overwrote = _next_free_name(resolved, target_ext, _overwrite(args))
    _oc._write_atomic(target, data, target.exists())
    _oc._verify_written(target, data)
    if target.read_bytes() != data:
        raise OfficeConvertError("交付落盘复验失败:磁盘字节与验证字节不一致,如实失败")
    office_purpose.audit(
        "office_convert", purpose, {"path": compound, "convert": target_ext, "engine": kind}
    )
    return {
        "convert": target_ext,
        "source": compound,
        "path": _compound_of(root, target),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "engine": _basename(engine),
        "overwrote": overwrote,
    }


# ---------------------------------------------------------------- engine


_COM_PROGIDS = ("Word.Application", "KWPS.Application", "wps.Application")


def _resolve_engine() -> tuple[str, str]:
    word = str(os.environ.get(ENV_WORD) or "").strip()
    if word:
        found = Path(word)
        if not found.is_file():
            raise OfficeConvertError("COMPANY_AGENT_WORD_CMD 配置的路径不是文件")
        return str(found), "word"
    if _platform() == "darwin":
        return "osascript", "apple"
    progid = _com_progid()
    if progid:
        return progid, "com"
    configured = str(os.environ.get(ENV_SOFFICE) or "").strip()
    if configured:
        found = Path(configured)
        if not found.is_file():
            raise OfficeConvertError("COMPANY_AGENT_SOFFICE 配置的路径不是文件:请核对无头引擎安装位置")
        return str(found), "soffice"
    for name in ("soffice", "libreoffice"):
        found = _which(name)
        if found:
            return found, "soffice"
    raise OfficeConvertError(
        "本机未找到 Word/WPS 另存引擎,也未找到无头转换引擎(LibreOffice):"
        "请安装 Word/WPS 或 LibreOffice,"
        "或用 COMPANY_AGENT_WORD_CMD / COMPANY_AGENT_SOFFICE 指向绝对路径;如实失败,不出替身产物"
    )


def _platform() -> str:
    """sys.platform seam so the macOS script can be tested on Windows."""

    return sys.platform


def _apple_script(source: Path, staging: Path, fmt: str) -> str:
    """Copy into the Word container, then save. Never activates Word."""

    dest = staging / f"{source.stem}.{fmt}"
    container = "~/Library/Containers/com.microsoft.Word/Data/Documents"
    return (
        f'set containerDir to "{container}"\n'
        "display alerts to alerts none\n"
        f'set srcPosix to "{source}"\n'
        f'set dstPosix to "{dest}"\n'
        "do shell script \"cp \" & quoted form of srcPosix & \" \" & quoted form of containerDir\n"
        "tell application \"Microsoft Word\"\n"
        "open POSIX file srcPosix\n"
        "save as active document file name dstPosix\n"
        "close active document saving no\n"
        "end tell\n"
    )


def _com_progid() -> str | None:
    """Registered Word or WPS automation id, or None when this host has neither."""

    if os.name != "nt":
        return None
    import winreg  # noqa: PLC0415 -- Windows-only lookup

    for progid in _COM_PROGIDS:
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + r"\CLSID"):
                return progid
        except OSError:
            continue
    return None


def _com_save(progid: str, source: Path, staging: Path, fmt: str) -> None:
    """Save a copy through Word/WPS COM. The live file is not the destination."""

    if progid not in _COM_PROGIDS:
        raise OfficeConvertError("COM 程序标识不在允许列表,拒绝转换")
    if fmt not in {"pdf", "docx"}:
        raise OfficeConvertError("COM 另存只支持 pdf 与 docx")
    dest = staging / f"{source.stem}.{fmt}"
    file_format = "17" if fmt == "pdf" else "16"
    script = staging / "save-as.ps1"
    script.write_text(
        "param([string]$src,[string]$dst,[int]$fmt,[string]$id)\n"
        "$app = New-Object -ComObject $id\n"
        "$app.Visible = $false\n"
        "$app.DisplayAlerts = 0\n"
        "$doc = $app.Documents.Open($src)\n"
        "$doc.SaveAs([ref]$dst, [ref]$fmt)\n"
        "$doc.Close($false)\n"
        "$app.Quit()\n",
        encoding="utf-8",
    )
    code, _output = _run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(script),
            str(source),
            str(dest),
            file_format,
            progid,
        ],
        cwd=str(staging),
    )
    if code != 0:
        raise OfficeConvertError(f"word 退出码 {code}:产物未生成,如实失败")


def _which(name: str) -> str | None:
    return shutil.which(name)


def _run(command: list[str], cwd: str) -> tuple[int, bytes]:
    try:
        finished = subprocess.run(
            command,
            cwd=cwd,
            env=_minimal_env(),
            capture_output=True,
            timeout=RUN_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise OfficeConvertError("转换引擎可执行文件消失,如实失败") from exc
    except subprocess.TimeoutExpired as exc:
        raise OfficeConvertError(f"转换超过 {RUN_TIMEOUT} 秒被终止,产物不可信") from exc
    output = finished.stdout or b""
    if len(output) > STDOUT_CAP:
        output = output[:STDOUT_CAP]
    return int(finished.returncode or 0), output


def _minimal_env() -> dict[str, str]:
    minimal: dict[str, str] = {}
    for key in _ENV_KEYS:
        value = os.environ.get(key)
        if isinstance(value, str) and value:
            minimal[key] = value
    return minimal


def _basename(engine: str) -> str:
    stem = Path(engine).name
    return stem[:64] or "soffice"


# ---------------------------------------------------------------- lease


class _lease:
    """Cross-process, bounded, self-healing lock file for one converter."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fd: int | None = None

    def _acquire(self) -> bool:
        try:
            self._fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self._fd, str(os.getpid()).encode("ascii"))
            return True
        except FileExistsError:
            return False
        except OSError as exc:
            if exc.errno == errno.EACCES:
                raise OfficeConvertError("转换租约文件不可写,如实失败") from exc
            return False

    def _break(self) -> None:
        try:
            age = time.time() - self._path.stat().st_mtime
        except OSError:
            return
        if age > LEASE_STALE_SECONDS:
            with contextlib.suppress(OSError):
                self._path.unlink()

    def _wait(self) -> None:
        deadline = time.monotonic() + LEASE_TIMEOUT
        while time.monotonic() < deadline:
            if self._acquire():
                return
            self._break()
            time.sleep(0.25)
        raise OfficeConvertError(f"转换器被其他任务占用超过 {LEASE_TIMEOUT} 秒:租约未释放,拒绝无限等待")

    def __enter__(self) -> _lease:
        self._wait()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
            with contextlib.suppress(OSError):
                self._path.unlink()


# ---------------------------------------------------------------- naming


def _next_free_name(resolved: Path, target_ext: str, overwrite: bool) -> tuple[Path, bool]:
    first = resolved.with_name(resolved.stem + "." + target_ext)
    if not first.exists():
        return first, False
    if overwrite:
        return first, True
    for index in range(1, 100):
        candidate = resolved.with_name(f"{resolved.stem}_{index:02d}.{target_ext}")
        if not candidate.exists():
            return candidate, False
    raise OfficeConvertError("交付名 99 个序号都已占用:请清理或换目录,如实拒绝")


def _compound_of(root: Path, target: Path) -> str:
    return target.resolve(strict=True).relative_to(root.resolve()).as_posix()


# ---------------------------------------------------------------- verification


def _check_magic(suffix: str, data: bytes) -> None:
    expected = _SOURCE_MAGIC[suffix]
    if data[: len(expected)] != expected:
        raise OfficeConvertError("源文件字节与其扩展名不符(可能损坏或扩展名被装错),如实拒绝")


def _verify_product(target: Path, target_ext: str) -> None:
    if not target.is_file():
        raise OfficeConvertError("产物未生成:引擎退出码为 0 但没有写出目标文件")
    data = target.read_bytes()
    if not data:
        raise OfficeConvertError("产物为空:三重校验不通过,如实失败")
    if data[: len(_OUTPUT_MAGIC[target_ext])] != _OUTPUT_MAGIC[target_ext]:
        raise OfficeConvertError("产物 magic 与目标格式不符:三重校验不通过,如实失败")
    if target_ext == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as package:
                _ = package.read("word/document.xml")
        except (zipfile.BadZipFile, KeyError) as exc:
            raise OfficeConvertError("产物不是可打开的 docx 包:三重校验不通过,如实失败") from exc


def _overwrite(args: dict) -> bool:
    raw = args.get("overwrite")
    if raw is None:
        return False
    if not isinstance(raw, bool):
        raise OfficeConvertError("overwrite 必须是布尔值")
    return raw


def _read_bounded(root, relative: str) -> bytes:
    try:
        oversized = workspace_files.resolve(root, relative).stat().st_size > MAX_FILE_BYTES
    except OSError as exc:
        raise OfficeConvertError("workspace file is not available") from exc
    if oversized:
        raise OfficeConvertError("文件超过 20MB 转换上限:该文件被拒绝(明示拒收,不出替身)")
    with workspace_files.open_file(root, relative) as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise OfficeConvertError("文件超过 20MB 转换上限:该文件被拒绝(明示拒收,不出替身)")
    return data
