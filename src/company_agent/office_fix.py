"""Apply format-audit fixes without changing sentence text (§4.12)."""
from __future__ import annotations

import contextlib
import hashlib
import io
import xml.etree.ElementTree as ET
import zipfile

from company_agent import audit_chain, office_audit, workspace_files
from company_agent import office_create as _oc
from company_agent import office_files as _files

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{_W_NS}}}"


class OfficeFixError(ValueError):
    """Refusal that names the boundary hit."""


def fix(args: dict) -> dict:
    """Set page geometry and default font. Visible paragraph text is preserved."""

    workspace = workspace_files.root()
    purpose = _files._purpose(args)
    compound = _oc._compound(args)
    resolved = workspace_files.resolve(workspace, compound)
    if resolved.suffix.casefold() != ".docx":
        raise OfficeFixError("格式修复只支持 .docx")
    original = resolved.read_bytes()
    before_text = _visible(original)
    before = office_audit.audit({"project": args["project"], "path": args["path"], "mode": "retemplate"})
    data = _patch(original)
    existed, target = _oc._resolve_target(workspace, compound, True)
    _oc._write_atomic(target, data, existed)
    _oc._verify_written(target, data)
    if _visible(target.read_bytes()) != before_text:
        _oc._write_atomic(target, original, True)
        raise OfficeFixError("格式修复改变了正文,已拒绝")
    after = office_audit.audit(
        {"project": args["project"], "path": args["path"], "mode": "retemplate"}
    )
    with contextlib.suppress(audit_chain.AuditChainError):
        audit_chain.append(
            "office_fix",
            {
                "purpose": purpose,
                "path": compound,
                "before": len(before["issues"]),
                "after": len(after["issues"]),
            },
        )
    return {
        "path": compound,
        "before_issues": len(before["issues"]),
        "after_issues": len(after["issues"]),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "trust": "untrusted_reference_data",
    }


def _patch(data: bytes) -> bytes:
    try:
        package = zipfile.ZipFile(io.BytesIO(data))
        document = ET.fromstring(package.read("word/document.xml"))
        styles = ET.fromstring(package.read("word/styles.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise OfficeFixError("docx 数据包损坏,拒绝修复") from exc
    _ensure_sect(document)
    _ensure_defaults(styles)
    ET.register_namespace("w", _W_NS)
    edited = {
        "word/document.xml": ET.tostring(document, encoding="utf-8", xml_declaration=True),
        "word/styles.xml": ET.tostring(styles, encoding="utf-8", xml_declaration=True),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as output:
        for info in package.infolist():
            payload = edited.get(info.filename, package.read(info.filename))
            output.writestr(info, payload)
    return buffer.getvalue()


def _ensure_sect(document: ET.Element) -> None:
    body = document.find(f"{_W}body")
    if body is None:
        raise OfficeFixError("docx 没有正文")
    sect = body.find(f"{_W}sectPr")
    if sect is None:
        sect = ET.SubElement(body, f"{_W}sectPr")
    if sect.find(f"{_W}pgSz") is None:
        size = ET.SubElement(sect, f"{_W}pgSz")
        size.set(f"{_W}w", "11906")
        size.set(f"{_W}h", "16838")
    if sect.find(f"{_W}pgMar") is None:
        margins = ET.SubElement(sect, f"{_W}pgMar")
        margins.set(f"{_W}top", "1418")
        margins.set(f"{_W}right", "1474")
        margins.set(f"{_W}bottom", "993")
        margins.set(f"{_W}left", "2098")


def _ensure_defaults(styles: ET.Element) -> None:
    defaults = styles.find(f"{_W}docDefaults")
    if defaults is None:
        defaults = ET.Element(f"{_W}docDefaults")
        styles.insert(0, defaults)
    rpr_default = defaults.find(f"{_W}rPrDefault")
    if rpr_default is None:
        rpr_default = ET.SubElement(defaults, f"{_W}rPrDefault")
    rpr = rpr_default.find(f"{_W}rPr")
    if rpr is None:
        rpr = ET.SubElement(rpr_default, f"{_W}rPr")
    fonts = rpr.find(f"{_W}rFonts")
    if fonts is None:
        fonts = ET.SubElement(rpr, f"{_W}rFonts")
    fonts.set(f"{_W}ascii", "FangSong")
    fonts.set(f"{_W}eastAsia", "仿宋")
    size = rpr.find(f"{_W}sz")
    if size is None:
        size = ET.SubElement(rpr, f"{_W}sz")
    size.set(f"{_W}val", "32")


def _visible(data: bytes) -> list[str]:
    try:
        package = zipfile.ZipFile(io.BytesIO(data))
        root = ET.fromstring(package.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise OfficeFixError("docx 正文不可读") from exc
    return [
        "".join(node.text or "" for node in paragraph.iter(f"{_W}t"))
        for paragraph in root.iter(f"{_W}p")
    ]
