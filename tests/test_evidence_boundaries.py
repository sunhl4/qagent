"""Bound administrative JSON inputs without consuming credentials or starting services."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=[("release_manifest", "ManifestError"), ("verify_manual_evidence", "EvidenceError")])
def parser(request):
    module = script(request.param[0])
    return module, getattr(module, request.param[1])


@pytest.mark.parametrize("raw", [
    '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{"x":1e999}',
    '{"x":9007199254740992}', '{"x":1,"x":2}',
    '[' * 1500 + '0' + ']' * 1500, '{"x":"\\ud800"}',
    '{"x":' + '9' * 5000 + '}',
])
def test_strict_json_rejects_extensions_and_unbounded_values(parser, tmp_path, raw):
    module, error = parser
    path = tmp_path / "untrusted.json"
    path.write_text(raw)
    with pytest.raises(error, match="JSON"):
        module.load_json(path)


def test_json_size_depth_and_node_budgets(parser, tmp_path, monkeypatch):
    module, error = parser
    path = tmp_path / "oversize.json"
    monkeypatch.setattr(module, "MAX_JSON_BYTES", 128)
    path.write_bytes(b" " * 129)
    with pytest.raises(error):
        module.load_json(path)
    monkeypatch.setattr(module, "MAX_JSON_BYTES", 4096)
    path.write_text('[' * (module.MAX_JSON_DEPTH + 1) + '0' + ']' * (module.MAX_JSON_DEPTH + 1))
    with pytest.raises(error):
        module.load_json(path)
    monkeypatch.setattr(module, "MAX_JSON_NODES", 8)
    path.write_text(json.dumps(list(range(9))))
    with pytest.raises(error):
        module.load_json(path)
    path.write_text('{"value":[1,true,null,"文本"]}')
    assert module.load_json(path) == {"value": [1, True, None, "文本"]}


@pytest.mark.parametrize("kind", ["link", "fifo", "directory"])
def test_json_reader_rejects_nonregular_inputs_without_blocking(parser, tmp_path, kind, make_symlink):
    module, error = parser
    path = tmp_path / "input"
    if kind == "link":
        target = tmp_path / "target.json"
        target.write_text("{}")
        make_symlink(target, path)
    elif kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("mkfifo unavailable on this host")
        os.mkfifo(path)
    else:
        path.mkdir()
    with pytest.raises(error):
        module.load_json(path)


def test_cli_errors_are_short_and_do_not_echo_untrusted_json(parser, tmp_path, capsys):
    module, _ = parser
    path = tmp_path / "input.json"
    path.write_text('{"private-synthetic-input":NaN}')
    path.chmod(0o600)
    args = ["verify", "--manifest", str(path)] if hasattr(module, "ManifestError") else [
        "--evidence", str(path)
    ]
    assert module.main(args) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert len(captured.err) < 200
    assert "private-synthetic-input" not in captured.err and "Traceback" not in captured.err
