"""Local OCR for empty text layers and images (§4.6).

The command is ``COMPANY_AGENT_OCR_CMD`` (an absolute tesseract binary). PDF
pages are rasterized with ``pdftoppm`` from ``COMPANY_AGENT_PDFTOPPM`` or
PATH. Nothing is uploaded. A missing binary or a failed run is a refusal,
never an empty stand-in string.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ENV_OCR = "COMPANY_AGENT_OCR_CMD"
ENV_PDFTOPPM = "COMPANY_AGENT_PDFTOPPM"
OCR_BUDGET_SECONDS = 90
OCR_MAX_PAGES = 12
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}


class OfficeOcrError(ValueError):
    """OCR was required and did not produce text."""


def image_suffixes() -> set[str]:
    return set(_IMAGE_SUFFIXES)


def configured() -> bool:
    return bool(str(os.environ.get(ENV_OCR) or "").strip())


def read_image(data: bytes, suffix: str) -> str:
    if suffix.casefold() not in _IMAGE_SUFFIXES:
        raise OfficeOcrError(f"{suffix} 不是可 OCR 的图片")
    if not configured():
        raise OfficeOcrError(f"{suffix} 图片 OCR 未配置:明确拒绝,不返回空文本")
    return _run_bytes(data, suffix if suffix.startswith(".") else f".{suffix}")


def read_pdf_pages(data: bytes) -> list[str]:
    """OCR the first 12 rendered pages. Requires tesseract and pdftoppm."""

    if not configured():
        raise OfficeOcrError("PDF 文本层为空且 OCR 未配置:明确拒绝,不返回空文本")
    raster = _pdftoppm()
    if raster is None:
        raise OfficeOcrError("PDF 文本层为空,缺少 pdftoppm 栅格化:明确拒绝,不返回空文本")
    with tempfile.TemporaryDirectory(prefix="office-ocr-") as staging:
        source = Path(staging) / "page.pdf"
        source.write_bytes(data)
        prefix = str(Path(staging) / "page")
        try:
            subprocess.run(
                [raster, "-png", "-f", "1", "-l", str(OCR_MAX_PAGES), str(source), prefix],
                cwd=staging,
                env=_minimal_env(),
                capture_output=True,
                timeout=OCR_BUDGET_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OfficeOcrError("PDF 栅格化失败:明确拒绝") from exc
        images = sorted(Path(staging).glob("page-*.png"))
        if not images:
            raise OfficeOcrError("PDF 栅格化没有产出页面:明确拒绝")
        pages: list[str] = []
        for image in images[:OCR_MAX_PAGES]:
            pages.append(_run_file(image))
        return pages


def _run_bytes(data: bytes, suffix: str) -> str:
    with tempfile.TemporaryDirectory(prefix="office-ocr-") as staging:
        target = Path(staging) / f"image{suffix}"
        target.write_bytes(data)
        return _run_file(target)


def _run_file(path: Path) -> str:
    command = str(os.environ.get(ENV_OCR) or "").strip()
    binary = Path(command)
    if not binary.is_file():
        raise OfficeOcrError("COMPANY_AGENT_OCR_CMD 不是可执行文件:明确拒绝")
    try:
        finished = subprocess.run(
            [str(binary), str(path), "stdout", "-l", "chi_sim+eng"],
            cwd=str(path.parent),
            env=_minimal_env(),
            capture_output=True,
            timeout=OCR_BUDGET_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OfficeOcrError("OCR 进程失败或超时:明确拒绝,不返回空文本") from exc
    if finished.returncode != 0:
        raise OfficeOcrError(f"OCR 退出码 {finished.returncode}:明确拒绝,不返回空文本")
    text = (finished.stdout or b"").decode("utf-8", errors="replace").strip()
    if not text:
        raise OfficeOcrError("OCR 没有识别出文本:明确拒绝,不返回空文本")
    return text


def _pdftoppm() -> str | None:
    configured_path = str(os.environ.get(ENV_PDFTOPPM) or "").strip()
    if configured_path:
        return configured_path if Path(configured_path).is_file() else None
    return shutil.which("pdftoppm")


def _minimal_env() -> dict[str, str]:
    minimal: dict[str, str] = {}
    for key in ("PATH", "SystemRoot", "SystemDrive", "TEMP", "TMP", "COMSPEC", "PATHEXT"):
        value = os.environ.get(key)
        if isinstance(value, str) and value:
            minimal[key] = value
    return minimal
