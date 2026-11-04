"""In-process OLE readers for legacy Word and Excel (§4.7).

``.doc`` text comes from the Word 97 FIB plus the piece table in the table
stream. Encrypted files, Word 6/95, and truncated compound files raise
``doc_needs_docx`` instead of returning empty text. ``.xls`` reads cached
BIFF cell values only; formulas are reported as unevaluated. ``.ppt`` is not
parsed here.
"""
from __future__ import annotations

import struct
from datetime import datetime

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ENDOFCHAIN = 0xFFFFFFFE
_FREESECT = 0xFFFFFFFF
_FATSECT = 0xFFFFFFFD
_NOSTREAM = 0xFFFFFFFF

_SPRM_AUTHOR = 0x4804
_SPRM_WHEN = 0x6805
_SPRM_AUTHOR_DEL = 0x4863
_SPRM_WHEN_DEL = 0x6864
_SPRA_LEN = {0: 1, 1: 1, 2: 2, 3: 4, 4: 2, 5: 2, 6: None, 7: 3}


class OfficeBinaryError(ValueError):
    """Honest refusal for a legacy binary this reader will not invent text for."""


def read_doc(data: bytes) -> dict[str, object]:
    """Return main-document text and any revision marks found in the CLX."""

    streams = _streams(data)
    word = streams.get("WordDocument")
    if word is None or len(word) < 0x1A8:
        raise OfficeBinaryError("doc_needs_docx")
    ident, nfib = struct.unpack_from("<HH", word, 0)
    flags = struct.unpack_from("<H", word, 0x0A)[0]
    if ident != 0xA5EC or nfib < 0x00C1:
        raise OfficeBinaryError("doc_needs_docx")
    if flags & 0x0100:
        raise OfficeBinaryError("doc_needs_docx")
    which = "1Table" if flags & 0x0200 else "0Table"
    table = streams.get(which)
    if table is None:
        raise OfficeBinaryError("doc_needs_docx")
    fc_clx, lcb_clx = struct.unpack_from("<II", word, 0x01A2)
    if lcb_clx < 16 or fc_clx + lcb_clx > len(table):
        raise OfficeBinaryError("doc_needs_docx")
    ccp_text = struct.unpack_from("<I", word, 0x004C)[0]
    clx = table[fc_clx : fc_clx + lcb_clx]
    revisions = _revisions(clx)
    text = _piece_text(word, clx, ccp_text)
    if not text and not revisions:
        raise OfficeBinaryError("doc_needs_docx")
    return {"text": text, "revisions": revisions}


def read_xls(data: bytes) -> list[tuple[str, list[list[str]]]]:
    """Return ``(sheet name, rows of cached values)`` from a BIFF8 workbook."""

    streams = _streams(data)
    book = streams.get("Workbook") or streams.get("Book")
    if book is None:
        raise OfficeBinaryError("xls 工作簿流不存在:明确拒绝")
    return _biff_sheets(book)


def compound_file(streams: dict[str, bytes]) -> bytes:
    """Build a version-3 compound file. Test fixture helper, cutoff 0."""

    names = list(streams)
    sector = 512
    directory_sectors = max(1, (1 + len(names) + 3) // 4)
    data_sectors: list[tuple[str, list[int]]] = []
    next_sid = 1 + directory_sectors
    for name in names:
        blob = streams[name]
        count = max(1, (len(blob) + sector - 1) // sector)
        sids = list(range(next_sid, next_sid + count))
        next_sid += count
        data_sectors.append((name, sids))
    total = next_sid
    if total > 128:
        raise OfficeBinaryError("测试复合文档超过一个 FAT 扇区")
    fat = [_FREESECT] * 128
    fat[0] = _FATSECT
    for sid in range(1, 1 + directory_sectors):
        fat[sid] = sid + 1 if sid + 1 < 1 + directory_sectors else _ENDOFCHAIN
    for _name, sids in data_sectors:
        for index, sid in enumerate(sids):
            fat[sid] = sids[index + 1] if index + 1 < len(sids) else _ENDOFCHAIN
    header = bytearray(sector)
    header[0:8] = OLE_MAGIC
    struct.pack_into("<HHHHH", header, 0x18, 0x003E, 0x0003, 0xFFFE, 9, 6)
    struct.pack_into("<I", header, 0x2C, 1)
    struct.pack_into("<I", header, 0x30, 1)
    struct.pack_into("<I", header, 0x38, 0)
    struct.pack_into("<I", header, 0x3C, _ENDOFCHAIN)
    struct.pack_into("<I", header, 0x44, _ENDOFCHAIN)
    struct.pack_into("<I", header, 0x4C, 0)
    for index in range(1, 109):
        struct.pack_into("<I", header, 0x4C + index * 4, _FREESECT)
    fat_bytes = b"".join(struct.pack("<I", value) for value in fat)
    directory = _directory(names, data_sectors, streams)
    directory += b"\x00" * (directory_sectors * sector - len(directory))
    body = bytearray()
    body += fat_bytes
    body += directory
    for name, sids in data_sectors:
        blob = streams[name]
        padded = blob + b"\x00" * (len(sids) * sector - len(blob))
        body += padded
    return bytes(header) + bytes(body)


def _directory(names: list[str], layout: list[tuple[str, list[int]]], streams: dict[str, bytes]) -> bytes:
    entries = [_dir_entry("Root Entry", 5, _NOSTREAM, 0, child=1 if names else _NOSTREAM)]
    for index, name in enumerate(names):
        right = index + 2 if index + 1 < len(names) else _NOSTREAM
        start = layout[index][1][0]
        entries.append(_dir_entry(name, 2, start, len(streams[name]), right=right))
    return b"".join(entries)


def _dir_entry(
    name: str, kind: int, start: int, size: int, *, child: int = _NOSTREAM, right: int = _NOSTREAM
) -> bytes:
    raw = name.encode("utf-16-le")
    if len(raw) > 62:
        raise OfficeBinaryError("复合文档流名过长")
    entry = bytearray(128)
    entry[0 : len(raw)] = raw
    struct.pack_into("<H", entry, 0x40, len(raw) + 2)
    entry[0x42] = kind
    entry[0x43] = 1
    struct.pack_into("<III", entry, 0x44, _NOSTREAM, right, child)
    struct.pack_into("<I", entry, 0x74, start)
    struct.pack_into("<Q", entry, 0x78, size)
    return bytes(entry)


def _streams(data: bytes) -> dict[str, bytes]:
    if len(data) < 512 or data[:8] != OLE_MAGIC:
        raise OfficeBinaryError("doc_needs_docx")
    _minor, major, _order, sector_shift, _mini_shift = struct.unpack_from("<HHHHH", data, 0x18)
    if major not in {3, 4}:
        raise OfficeBinaryError("doc_needs_docx")
    sector = 1 << sector_shift
    if sector not in {512, 4096} or len(data) < sector * 2:
        raise OfficeBinaryError("doc_needs_docx")
    fat_count = struct.unpack_from("<I", data, 0x2C)[0]
    dir_start = struct.unpack_from("<I", data, 0x30)[0]
    difat = list(struct.unpack_from("<109I", data, 0x4C))
    fat: list[int] = []
    for sid in difat:
        if sid >= 0xFFFFFFFA:
            break
        blob = _sector(data, sector, sid)
        fat.extend(struct.unpack("<" + "I" * (sector // 4), blob))
        if fat_count and len(fat) >= fat_count * (sector // 4):
            break
    if not fat:
        raise OfficeBinaryError("doc_needs_docx")
    directory = b"".join(_sector(data, sector, sid) for sid in _chain(fat, dir_start))
    found: dict[str, bytes] = {}
    for offset in range(0, len(directory), 128):
        entry = directory[offset : offset + 128]
        if len(entry) < 128:
            break
        kind = entry[0x42]
        if kind != 2:
            continue
        name_len = struct.unpack_from("<H", entry, 0x40)[0]
        if name_len < 2 or name_len > 64:
            continue
        name = entry[: name_len - 2].decode("utf-16-le", errors="replace")
        start, size = struct.unpack_from("<IQ", entry, 0x74)
        blob = b"".join(_sector(data, sector, sid) for sid in _chain(fat, start))[:size]
        found[name] = blob
    return found


def _sector(data: bytes, sector: int, sid: int) -> bytes:
    start = (sid + 1) * sector
    return data[start : start + sector]


def _chain(fat: list[int], start: int) -> list[int]:
    sid = start
    seen: set[int] = set()
    chain: list[int] = []
    while sid < 0xFFFFFFFA and sid not in seen and sid < len(fat):
        seen.add(sid)
        chain.append(sid)
        sid = fat[sid]
        if len(chain) > 100_000:
            break
    return chain


def _piece_text(word: bytes, clx: bytes, ccp_text: int) -> str:
    cursor = 0
    while cursor < len(clx) and clx[cursor] == 0x01:
        if cursor + 3 > len(clx):
            raise OfficeBinaryError("doc_needs_docx")
        cb = struct.unpack_from("<H", clx, cursor + 1)[0]
        cursor += 3 + cb
    if cursor >= len(clx) or clx[cursor] != 0x02:
        raise OfficeBinaryError("doc_needs_docx")
    lcb = struct.unpack_from("<I", clx, cursor + 1)[0]
    plc = clx[cursor + 5 : cursor + 5 + lcb]
    if len(plc) < 16 or (len(plc) - 4) % 12 != 0:
        raise OfficeBinaryError("doc_needs_docx")
    count = (len(plc) - 4) // 12
    cps = list(struct.unpack_from("<" + "I" * (count + 1), plc, 0))
    pieces: list[str] = []
    for index in range(count):
        fc = struct.unpack_from("<I", plc, 4 * (count + 1) + index * 8 + 2)[0]
        chars = cps[index + 1] - cps[index]
        if chars < 0 or chars > 2_000_000:
            raise OfficeBinaryError("doc_needs_docx")
        if fc & 0x40000000:
            start = (fc & 0x3FFFFFFF) // 2
            raw = word[start : start + chars]
            pieces.append(raw.decode("cp1252", errors="replace"))
        else:
            start = fc
            raw = word[start : start + chars * 2]
            pieces.append(raw.decode("utf-16-le", errors="replace"))
    text = "".join(pieces)
    if ccp_text and ccp_text < len(text):
        text = text[:ccp_text]
    if text.endswith("\r"):
        text = text[:-1]
    return text.replace("\r", "\n").replace("\x07", "")


def _revisions(clx: bytes) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    cursor = 0
    while cursor + 3 <= len(clx) and clx[cursor] == 0x01:
        cb = struct.unpack_from("<H", clx, cursor + 1)[0]
        grp = clx[cursor + 3 : cursor + 3 + cb]
        rows.extend(_sprms(grp))
        cursor += 3 + cb
    return rows[:32]


def _sprms(grp: bytes) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pending: dict[str, str] = {}
    cursor = 0
    while cursor + 2 <= len(grp):
        sprm = struct.unpack_from("<H", grp, cursor)[0]
        cursor += 2
        spra = (sprm >> 13) & 0x7
        size = _SPRA_LEN[spra]
        if size is None:
            if cursor >= len(grp):
                break
            size = grp[cursor]
            cursor += 1
        operand = grp[cursor : cursor + size]
        cursor += size
        if len(operand) < size:
            break
        if sprm in {_SPRM_AUTHOR, _SPRM_AUTHOR_DEL} and len(operand) >= 2:
            pending = {
                "author": f"author-{struct.unpack_from('<H', operand)[0]}",
                "kind": "del" if sprm == _SPRM_AUTHOR_DEL else "ins",
            }
        elif sprm in {_SPRM_WHEN, _SPRM_WHEN_DEL} and len(operand) >= 4 and pending:
            when = _dttm(struct.unpack_from("<I", operand)[0])
            if when:
                pending["when"] = when
                rows.append(pending)
            pending = {}
    return rows


def _dttm(value: int) -> str:
    minute = value & 0x3F
    hour = (value >> 6) & 0x1F
    day = (value >> 11) & 0x1F
    month = (value >> 16) & 0x0F
    year = 1900 + ((value >> 20) & 0x1FF)
    if not (1 <= month <= 12 and 1 <= day <= 31 and hour <= 23 and minute <= 59):
        return ""
    return datetime(year, month, day, hour, minute).strftime("%Y-%m-%dT%H:%M:%SZ")


def _biff_sheets(book: bytes) -> list[tuple[str, list[list[str]]]]:
    records = _records(book)
    strings = _sst(records)
    sheets: list[tuple[str, list[list[str]]]] = []
    current: list[list[str]] | None = None
    for opcode, payload in records:
        if opcode == 0x0085 and current is None:
            sheets.append((_boundsheet_name(payload), []))
        elif opcode == 0x0809 and len(payload) >= 4:
            dt = struct.unpack_from("<H", payload, 2)[0]
            if dt == 0x0010:
                if not sheets:
                    sheets.append(("Sheet1", []))
                current = sheets[-1][1]
        elif current is not None and opcode == 0x000A:
            current = None
        elif current is not None:
            cell = _cell(opcode, payload, strings)
            if cell is not None:
                _put(current, cell[0], cell[1], cell[2])
    if not sheets:
        raise OfficeBinaryError("xls 没有工作表:明确拒绝")
    return sheets


def _records(book: bytes) -> list[tuple[int, bytes]]:
    rows: list[tuple[int, bytes]] = []
    cursor = 0
    while cursor + 4 <= len(book):
        opcode, size = struct.unpack_from("<HH", book, cursor)
        cursor += 4
        payload = book[cursor : cursor + size]
        cursor += size
        if opcode == 0x003C and rows:
            prev, body = rows[-1]
            rows[-1] = (prev, body + payload)
        else:
            rows.append((opcode, payload))
    return rows


def _sst(records: list[tuple[int, bytes]]) -> list[str]:
    for opcode, payload in records:
        if opcode != 0x00FC or len(payload) < 8:
            continue
        strings: list[str] = []
        cursor = 8
        while cursor + 3 <= len(payload):
            cch, flags = struct.unpack_from("<HB", payload, cursor)
            cursor += 3
            if flags & 0x08 and cursor + 2 <= len(payload):
                cursor += 2
            if flags & 0x04 and cursor + 4 <= len(payload):
                cursor += 4
            width = 2 if flags & 0x01 else 1
            raw = payload[cursor : cursor + cch * width]
            cursor += cch * width
            if flags & 0x01:
                strings.append(raw.decode("utf-16-le", errors="replace"))
            else:
                strings.append(raw.decode("latin-1", errors="replace"))
        return strings
    return []


def _boundsheet_name(payload: bytes) -> str:
    if len(payload) < 8:
        return "Sheet"
    cch = payload[6]
    flags = payload[7]
    raw = payload[8 : 8 + cch * (2 if flags & 1 else 1)]
    if flags & 1:
        return raw.decode("utf-16-le", errors="replace") or "Sheet"
    return raw.decode("latin-1", errors="replace") or "Sheet"


def _cell(opcode: int, payload: bytes, strings: list[str]) -> tuple[int, int, str] | None:
    if opcode == 0x00FD and len(payload) >= 10:
        row, col, _xf, index = struct.unpack_from("<HHHI", payload)
        text = strings[index] if index < len(strings) else ""
        return row, col, text
    if opcode == 0x0203 and len(payload) >= 14:
        row, col, _xf = struct.unpack_from("<HHH", payload)
        value = struct.unpack_from("<d", payload, 6)[0]
        return row, col, _num(value)
    if opcode == 0x027E and len(payload) >= 10:
        row, col, _xf, rk = struct.unpack_from("<HHHI", payload)
        return row, col, _num(_rk(rk))
    if opcode == 0x0204 and len(payload) >= 8:
        row, col, _xf, cch = struct.unpack_from("<HHHH", payload)
        flags = payload[8] if len(payload) > 8 else 0
        raw = payload[9 : 9 + cch * (2 if flags & 1 else 1)]
        text = raw.decode("utf-16-le" if flags & 1 else "latin-1", errors="replace")
        return row, col, text
    if opcode == 0x0006 and len(payload) >= 14:
        row, col = struct.unpack_from("<HH", payload)
        return row, col, "[公式未求值]"
    return None


def _rk(value: int) -> float:
    number = value >> 2
    if value & 0x02:
        decoded: float = float(number if not value & 0x80000000 else number - 0x40000000)
    else:
        decoded = struct.unpack("<d", struct.pack("<Q", number << 34))[0]
    if value & 0x01:
        decoded /= 100.0
    return decoded


def _num(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return repr(value)


def _put(rows: list[list[str]], row: int, col: int, text: str) -> None:
    if row >= 5000 or col >= 64:
        return
    while len(rows) <= row:
        rows.append([])
    line = rows[row]
    while len(line) <= col:
        line.append("")
    line[col] = text
