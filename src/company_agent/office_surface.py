"""Read and dispose of docx revision marks without inventing colors in the file (§4.11)."""
from __future__ import annotations

import contextlib
import hashlib
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

from company_agent import audit_chain, workspace_files
from company_agent import office_create as _oc
from company_agent import office_files as _files

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{_W_NS}}}"
_COLORS = ("#C00000", "#0070C0", "#00B050", "#FFC000", "#7030A0", "#00B0F0")
_DISPOSITION = "word/company-disposition.xml"
_LEGACY_DISPOSITION = "word/lawmind-disposition.xml"
_NS = {"w": _W_NS}


class OfficeSurfaceError(ValueError):
    """Refusal that names the boundary hit."""


def surface(args: dict) -> dict:
    workspace = workspace_files.root()
    purpose = _files._purpose(args)
    compound = _oc._compound(args)
    resolved = workspace_files.resolve(workspace, compound)
    if resolved.suffix.casefold() != ".docx":
        raise OfficeSurfaceError("审阅面只支持 .docx")
    action = args.get("action")
    if action not in {"read", "accept", "reject"}:
        raise OfficeSurfaceError("action 必须是 read、accept 或 reject")
    data = resolved.read_bytes()
    revisions = _revisions(data)
    self_author = str(args.get("author") or "company-agent")
    if action == "read":
        return _receipt(compound, data, revisions, purpose, changed=False)
    revision_id = args.get("revision_id")
    if not isinstance(revision_id, str) or not revision_id:
        raise OfficeSurfaceError("revision_id 必须是修订 id")
    match = next((row for row in revisions if row["id"] == revision_id), None)
    if match is None:
        raise OfficeSurfaceError("revision_id 不存在")
    if match["author"] != self_author:
        raise OfficeSurfaceError("他人的修订只读")
    if action == "accept":
        updated = _write_disposition(data, revision_id, "accept")
    else:
        updated = _reject(data, revision_id, match["kind"])
    existed, target = _oc._resolve_target(workspace, compound, True)
    _oc._write_atomic(target, updated, existed)
    _oc._verify_written(target, updated)
    with contextlib.suppress(audit_chain.AuditChainError):
        audit_chain.append(
            "office_surface",
            {
                "purpose": purpose,
                "path": compound,
                "action": action,
                "revision_id": revision_id,
            },
        )
    return _receipt(compound, updated, _revisions(updated), purpose, changed=True)


def _revisions(data: bytes) -> list[dict[str, Any]]:
    try:
        package = zipfile.ZipFile(io.BytesIO(data))
        root = ET.fromstring(package.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise OfficeSurfaceError("docx 数据包损坏") from exc
    accepted = _accepted_ids(package)
    authors: list[str] = []
    rows: list[dict[str, Any]] = []
    for kind, tag in (("ins", "ins"), ("del", "del")):
        for node in root.iter(f"{_W}{tag}"):
            author = node.get(f"{_W}author") or ""
            if author not in authors:
                authors.append(author)
            text = "".join(item.text or "" for item in node.iter(f"{_W}t"))
            text += "".join(item.text or "" for item in node.iter(f"{_W}delText"))
            revision_id = node.get(f"{_W}id") or ""
            rows.append(
                {
                    "id": revision_id,
                    "author": author,
                    "kind": kind,
                    "text": text[:200],
                    "color": _COLORS[authors.index(author) % len(_COLORS)],
                    "folded": revision_id in accepted,
                }
            )
    return rows


def _accepted_ids(package: zipfile.ZipFile) -> set[str]:
    """Only the current part counts. A legacy part is read and ignored."""

    with contextlib.suppress(KeyError):
        package.read(_LEGACY_DISPOSITION)
    try:
        text = package.read(_DISPOSITION).decode("utf-8")
    except KeyError:
        return set()
    return {
        match.group(1)
        for match in re.finditer(r'<item id="([^"]+)" decision="accept"/>', text)
    }


def _write_disposition(data: bytes, revision_id: str, decision: str) -> bytes:
    package = zipfile.ZipFile(io.BytesIO(data))
    name = _DISPOSITION
    try:
        previous = package.read(name).decode("utf-8")
    except KeyError:
        previous = "<dispositions></dispositions>"
    if f'id="{revision_id}"' not in previous:
        previous = previous.replace(
            "</dispositions>",
            f'<item id="{revision_id}" decision="{decision}"/></dispositions>',
        )
    return _repackage(package, {name: previous.encode("utf-8")})


def _reject(data: bytes, revision_id: str, kind: str) -> bytes:
    package = zipfile.ZipFile(io.BytesIO(data))
    root = ET.fromstring(package.read("word/document.xml"))
    target = None
    for node in root.iter(f"{_W}{kind}"):
        if node.get(f"{_W}id") == revision_id:
            target = node
            break
    if target is None:
        raise OfficeSurfaceError("revision_id 不存在")
    parent = _parent(root, target)
    if parent is None:
        raise OfficeSurfaceError("修订节点没有父节点")
    index = list(parent).index(target)
    if kind == "ins":
        parent.remove(target)
    else:
        parent.remove(target)
        for child in list(target):
            parent.insert(index, child)
            index += 1
    ET.register_namespace("w", _W_NS)
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    updated = _repackage(package, {"word/document.xml": xml})
    return _write_disposition(updated, revision_id, "reject")


def _parent(root: ET.Element, node: ET.Element) -> ET.Element | None:
    for parent in root.iter():
        if node in list(parent):
            return parent
    return None


def _repackage(package: zipfile.ZipFile, edited: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as output:
        names = set(package.namelist())
        for info in package.infolist():
            output.writestr(info, edited.get(info.filename, package.read(info.filename)))
        for name, payload in edited.items():
            if name not in names:
                output.writestr(name, payload)
    return buffer.getvalue()


def _receipt(
    compound: str,
    data: bytes,
    revisions: list[dict[str, str]],
    purpose: str,
    *,
    changed: bool,
) -> dict:
    return {
        "path": compound,
        "changed": changed,
        "revisions": revisions[:64],
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "purpose": purpose,
        "trust": "untrusted_reference_data",
    }
