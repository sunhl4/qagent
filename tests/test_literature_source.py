from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from company_agent.literature_source import (
    LiteratureSourceError,
    copy_source_tree,
    inspect_archive,
    index_tex,
)

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "literature"


def test_index_tex_keeps_approximation_and_marks_unexpanded_macros() -> None:
    indexed = index_tex(
        (FIXTURE / "main.tex").read_text(encoding="utf-8"),
        paper_id="demo1",
        version="v1",
    )
    by_anchor = {entry["anchor"]: entry for entry in indexed["formulas"]}
    assert set(by_anchor) == {"eq:energy", "eq:bound", "eq:macro"}
    assert "\\approx" in by_anchor["eq:energy"]["tex"]
    assert by_anchor["eq:energy"]["fidelity"] == "copied"
    assert "\\lesssim" in by_anchor["eq:bound"]["tex"]
    assert by_anchor["eq:bound"]["fidelity"] == "copied"
    assert by_anchor["eq:bound"]["role"] == "constraint"
    assert by_anchor["eq:macro"]["fidelity"] == "macro_unexpanded"
    assert indexed["figures"] == ["figures/schematic.pdf"]
    assert indexed["code_urls"] == ["https://github.com/example/demo"]
    assert indexed["supplements"] == ["supplement.tex"]


def test_archive_rejects_escape_link_suffix_and_file_count(tmp_path: Path) -> None:
    with pytest.raises(LiteratureSourceError):
        inspect_archive(_tar({"../escape.tex": b"nope"}))
    with pytest.raises(LiteratureSourceError):
        inspect_archive(_tar_link())
    with pytest.raises(LiteratureSourceError):
        inspect_archive(_tar({"notes.exe": b"nope"}))
    with pytest.raises(LiteratureSourceError):
        inspect_archive(_tar({f"note-{index}.txt": b"x" for index in range(41)}))
    copied = copy_source_tree(FIXTURE, tmp_path / "copy")
    assert copied["files"] >= 3
    assert (tmp_path / "copy" / "main.tex").is_file()


def _tar(files: dict[str, bytes]) -> bytes:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return payload.getvalue()


def _tar_link() -> bytes:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        info = tarfile.TarInfo("link.tex")
        info.type = tarfile.SYMTYPE
        info.linkname = "main.tex"
        archive.addfile(info)
    return payload.getvalue()
