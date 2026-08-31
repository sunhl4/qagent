from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from qagent.adapters.contracts import ROOT as PACKAGE_ROOT
from qagent.adapters.homes import qdata_bin, qdata_url
from qagent.adapters.support import (
    http_json_url,
    json_headers,
    load_json,
    new_id,
    resolve_user_store,
)
from qagent.models.handles import B3_INCONCLUSIVE, B3_QUANTUM_WINS, B3_VERDICTS, HANDLE_ASSET

_ALLOWED = (
    "a1_closed_loop",
    "a2_spin_shadow",
    "a2_chem_pes",
    "a3_sensitivity",
    "qem_triad",
)
_JOB_KINDS = ("sample-to-solver", "shadow-predict", "surrogate")
_SOUTHBOUND = (
    "ionstack",
    "execute_twin_run",
    "urllib.request",
    "urllib",
    "socket",
    "http.client",
    "requests",
    "qdata.serve",
)
_FORBIDDEN_OUT = frozenset({"bitstrings", "rows", "pauli_terms", "counts_full", "result_full"})
_JOB_OUT_ORDER = ("status", "summary", "asset_id")
_JOB_OUT = frozenset(_JOB_OUT_ORDER)
_HTTP_FAIL = (urllib.error.URLError, TimeoutError, OSError, ValueError)
_CATALOG_CAP = 20
_NAME_CAP = 80
_KNOWLEDGE_SLOT = 5
_CATALOG_TEXT = (".md", ".txt")
_ROW_KEYS = ("kind", "name", HANDLE_ASSET, "recipe")


def _db(args: Mapping[str, Any]) -> Any:
    root = resolve_user_store(dict(args))
    path = root / "qdata.json"
    data = load_json(path, {"assets": {}, "jobs": {}, "records": {}})
    return path, data


def _persist(path, data) -> None:
    # Insertion order must survive reload so _card_rows can keep the newest tail.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _short(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in _FORBIDDEN_OUT}


def _clip_name(value: object) -> str:
    return " ".join(str(value or "").split())[:_NAME_CAP]


def _catalog_row(kind: str, name: str, asset_id: str = "", recipe: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {"kind": kind, "name": _clip_name(name)}
    if asset_id:
        row[HANDLE_ASSET] = str(asset_id)
    if recipe:
        row["recipe"] = _clip_name(recipe)
    return {key: row[key] for key in _ROW_KEYS if key in row}


def _knowledge_roots() -> list[Path]:
    roots = [PACKAGE_ROOT / "handbooks"]
    raw = os.environ.get("QAGENT_KNOWLEDGE_PATH") or ""
    for item in raw.split(os.pathsep):
        text = item.strip()
        if text:
            roots.append(Path(text))
    return roots


def _knowledge_names(limit: int) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for folder in _knowledge_roots():
        if not folder.is_dir():
            continue
        files = sorted(path for path in folder.rglob("*") if path.is_file())
        for path in files:
            if path.suffix.lower() not in _CATALOG_TEXT:
                continue
            try:
                rel = str(path.relative_to(folder))
            except ValueError:
                rel = path.name
            name = _clip_name(rel)
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
            if len(names) >= limit:
                return names
    return names


def _card_rows(data: Mapping[str, Any], limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    assets = data.get("assets") if isinstance(data.get("assets"), dict) else {}
    items = list(assets.items())[-limit:] if limit > 0 else []
    for key, raw in items:
        row = raw if isinstance(raw, dict) else {}
        asset_id = str(row.get(HANDLE_ASSET) or key)
        recipe = _clip_name(row.get("recipe") or "")
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        name = recipe or _clip_name(summary.get("recipe") or summary.get("kind") or asset_id)
        rows.append(_catalog_row("card", name, asset_id=asset_id, recipe=recipe))
    return rows


def _qdata_http_list(url: str) -> list[Any]:
    try:
        request = urllib.request.Request(
            url,
            method="GET",
            headers=json_headers(url),
        )
        with urllib.request.urlopen(request, timeout=8) as resp:
            raw = resp.read().decode("utf-8")
        parsed = json.loads(raw) if raw else []
    except (_HTTP_FAIL + (json.JSONDecodeError,)) as exc:
        raise RuntimeError(f"qdata HTTP is not reachable ({url})") from exc
    if not isinstance(parsed, list):
        raise RuntimeError(f"qdata HTTP assets must be a list ({url})")
    return parsed


def _remote_card_rows(limit: int) -> list[dict[str, Any]]:
    base = qdata_url()
    if not base or limit <= 0:
        return []
    ranked: list[tuple[str, dict[str, Any]]] = []
    for item in _qdata_http_list(f"{base}/v1/assets"):
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get(HANDLE_ASSET) or "").strip()
        if not asset_id:
            continue
        kind = _clip_name(item.get("kind") or "")
        recipe = kind if kind in _ALLOWED else ""
        ranked.append(
            (
                str(item.get("created_utc") or ""),
                _catalog_row("card", kind or asset_id, asset_id=asset_id, recipe=recipe),
            )
        )
    ranked.sort(key=lambda pair: pair[0])
    return [row for _stamp, row in ranked[-limit:]]


def _qdata_http(
    url: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        return http_json_url(url, method, body, timeout=8)
    except _HTTP_FAIL as exc:
        raise RuntimeError(f"qdata HTTP is not reachable ({url})") from exc


def _public_job(raw: Mapping[str, Any]) -> dict[str, Any]:
    summary = raw.get("summary")
    if not isinstance(summary, dict):
        result = raw.get("result")
        summary = result if isinstance(result, dict) else {}
    asset_id = raw.get("asset_id")
    if not asset_id and isinstance(raw.get("result"), dict):
        asset_id = raw["result"].get("asset_id")
    payload: dict[str, Any] = {
        "status": str(raw.get("status") or "unknown"),
        "summary": {key: value for key, value in summary.items() if key not in _FORBIDDEN_OUT},
    }
    if asset_id:
        payload[HANDLE_ASSET] = str(asset_id)
    return {key: payload[key] for key in _JOB_OUT_ORDER if key in payload}


def _verdict_for(asset: dict[str, Any]) -> str:
    recipe = asset.get("recipe")
    if recipe == "qem_triad" and not asset.get("qem_contract_ok"):
        return B3_INCONCLUSIVE
    stored = asset.get("verdict")
    if stored in B3_VERDICTS:
        if stored == B3_QUANTUM_WINS and recipe == "qem_triad" and not asset.get("qem_contract_ok"):
            return B3_INCONCLUSIVE
        return stored
    return B3_INCONCLUSIVE


class WiredQData:
    """Contract store + allowlist. Does not import the qdata package."""

    def list_providers(self, _args: Mapping[str, Any]) -> dict[str, Any]:
        return {"providers": [{"name": _clip_name(name)} for name in _ALLOWED]}

    def run_recipe(self, args: Mapping[str, Any]) -> dict[str, Any]:
        name = str(args.get("name") or "")
        if name not in _ALLOWED:
            raise ValueError(f"recipe {name!r} is not on the allowlist")
        live = _run_qdata_cli(name, args)
        if live is not None:
            return live
        path, data = _db(args)
        asset_id = "asset_" + hashlib.sha256(f"{name}:{new_id('r')}".encode()).hexdigest()[:12]
        record_id = new_id("run")
        params = args.get("params") if isinstance(args.get("params"), dict) else {}
        asset = {
            "asset_id": asset_id,
            "recipe": name,
            "summary": {"recipe": name, "shots": args.get("shots")},
            "run_record_id": record_id,
            "qem_contract_ok": bool(params.get("qem_contract_ok")),
            "verdict": B3_INCONCLUSIVE,
        }
        data["assets"][asset_id] = asset
        data["records"][record_id] = {
            "run_record_id": record_id,
            "asset_id": asset_id,
            "summary": {"recipe": name},
        }
        _persist(path, data)
        return _short(
            {
                HANDLE_ASSET: asset_id,
                "summary": {**asset["summary"], "source": "qagent-local-card"},
                "run_record_id": record_id,
            }
        )

    def submit_job(self, args: Mapping[str, Any]) -> dict[str, Any]:
        kind = str(args.get("kind") or "")
        if kind not in _JOB_KINDS:
            raise ValueError(f"unknown job kind {kind!r}")
        base = qdata_url()
        if base:
            payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
            live = _qdata_http(f"{base}/v1/jobs/{kind}", "POST", payload)
            job_id = live.get("job_id")
            if not job_id:
                raise RuntimeError("qdata HTTP did not return job_id")
            return {"job_id": str(job_id)}
        path, data = _db(args)
        job_id = new_id("job")
        asset_id = new_id("asset")
        data["jobs"][job_id] = {
            "job_id": job_id,
            "kind": kind,
            "status": "local-card",
            "asset_id": asset_id,
            "summary": {"kind": kind, "source": "qagent-local-card"},
            "bitstrings": ["00"],
            "rows": [1],
        }
        data["assets"][asset_id] = {
            "asset_id": asset_id,
            "recipe": None,
            "summary": {"kind": kind},
            "run_record_id": None,
            "qem_contract_ok": False,
            "verdict": B3_INCONCLUSIVE,
        }
        _persist(path, data)
        return {"job_id": job_id}

    def get_job(self, args: Mapping[str, Any]) -> dict[str, Any]:
        job_id = str(args.get("job_id") or "")
        base = qdata_url()
        if base:
            return _public_job(_qdata_http(f"{base}/v1/jobs/{job_id}"))
        path, data = _db(args)
        job = data["jobs"].get(job_id)
        if not job:
            raise KeyError(f"unknown job_id {job_id!r}")
        return _public_job(job)

    def list_assets(self, args: Mapping[str, Any]) -> dict[str, Any]:
        _path, data = _db(args)
        recipes = [_catalog_row("recipe", name, recipe=name) for name in _ALLOWED]
        knowledge = [_catalog_row("knowledge", name) for name in _knowledge_names(_KNOWLEDGE_SLOT)]
        budget = max(0, _CATALOG_CAP - len(recipes) - len(knowledge))
        cards = _card_rows(data, budget)
        seen = {row.get(HANDLE_ASSET) for row in cards if row.get(HANDLE_ASSET)}
        for row in _remote_card_rows(budget):
            asset_id = row.get(HANDLE_ASSET)
            if not asset_id or asset_id in seen:
                continue
            if len(cards) >= budget:
                break
            cards.append(row)
            seen.add(asset_id)
        return {"assets": [*recipes, *cards, *knowledge][:_CATALOG_CAP]}

    def get_run_record(self, args: Mapping[str, Any]) -> dict[str, Any]:
        record_id = str(args.get("run_record_id") or "")
        _path, data = _db(args)
        record = data["records"].get(record_id)
        if not record:
            raise KeyError(f"unknown run_record_id {record_id!r}")
        return {
            "run_record_id": record_id,
            "summary": record.get("summary") or {},
            HANDLE_ASSET: record.get("asset_id"),
        }

    def dequant_gate(self, args: Mapping[str, Any]) -> dict[str, Any]:
        asset_id = str(args.get("asset_id") or "")
        path, data = _db(args)
        asset = data["assets"].get(asset_id)
        if not asset:
            raise KeyError(f"unknown asset_id {asset_id!r}")
        verdict = _verdict_for(asset)
        if args.get("force_verdict") == B3_QUANTUM_WINS and not asset.get("qem_contract_ok"):
            raise ValueError("cannot_write quantum_wins unless qem_contract_ok")
        asset["verdict"] = verdict
        _persist(path, data)
        ok = bool(asset.get("qem_contract_ok"))
        return {"b3": {"verdict": verdict, "qem_contract_ok": ok}, "qem_contract_ok": ok}

    def sandbox_exec(self, args: Mapping[str, Any]) -> dict[str, Any]:
        code = str(args.get("code") or "")
        if _southbound_source(code):
            return {"ok": False, "stdout": "southbound blocked", "rest_called": False}
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return {"ok": False, "stdout": str(exc), "rest_called": False}
        if _southbound_ast(tree):
            return {"ok": False, "stdout": "southbound blocked", "rest_called": False}
        try:
            exec(  # noqa: S102 — restricted builtins, no import
                compile(tree, "<qagent-sandbox>", "exec"),
                {"__builtins__": {"print": print, "range": range, "len": len, "str": str}},
                {},
            )
        except Exception as exc:  # noqa: BLE001 — surface sandbox failure
            return {"ok": False, "stdout": str(exc), "rest_called": False}
        return {"ok": True, "stdout": "", "rest_called": False}


def _run_qdata_cli(name: str, args: Mapping[str, Any]) -> dict[str, Any] | None:
    exe = qdata_bin()
    if not exe:
        return None
    out = resolve_user_store(dict(args)) / "qdata-runs" / name / new_id("out")
    out.mkdir(parents=True, exist_ok=True)
    argv = [exe, "run", name, "--out", str(out), "--no-figure"]
    if args.get("shots") is not None:
        argv.extend(["--shots", str(int(args["shots"]))])
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"qdata CLI failed: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "qdata run failed").strip())
    try:
        summary = json.loads((proc.stdout or "").strip() or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("qdata CLI did not print a JSON summary") from exc
    if not isinstance(summary, dict):
        raise RuntimeError("qdata CLI summary must be an object")
    path, data = _db(args)
    asset_id = str(summary.get("asset_id") or "asset_" + hashlib.sha256(str(out).encode()).hexdigest()[:12])
    record_id = new_id("run")
    asset = {
        "asset_id": asset_id,
        "recipe": name,
        "summary": {**summary, "recipe": name, "source": "qdata-cli"},
        "run_record_id": record_id,
        "qem_contract_ok": bool(summary.get("qem_contract_ok")),
        "verdict": B3_INCONCLUSIVE,
    }
    data["assets"][asset_id] = asset
    data["records"][record_id] = {
        "run_record_id": record_id,
        "asset_id": asset_id,
        "summary": {"recipe": name, "source": "qdata-cli"},
    }
    _persist(path, data)
    return _short({HANDLE_ASSET: asset_id, "summary": asset["summary"], "run_record_id": record_id})


def _job_from_live(live: Mapping[str, Any]) -> dict[str, Any]:
    return _public_job(live)


def _southbound_source(code: str) -> bool:
    if any(token in code for token in _SOUTHBOUND):
        return True
    return bool(re.search(r"\bexecute_twin_run\b", code))


def _southbound_ast(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(alias.name == root or alias.name.startswith(root + ".") for root in _SOUTHBOUND):
                    return True
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if any(module == root or module.startswith(root + ".") for root in _SOUTHBOUND):
                return True
            if any(alias.name == "execute_twin_run" for alias in node.names):
                return True
        if isinstance(node, ast.Name) and node.id == "execute_twin_run":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "execute_twin_run":
            return True
    return False
