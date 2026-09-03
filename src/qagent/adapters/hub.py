from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from qagent.adapters.contracts import CONTRACTS

_FACE = CONTRACTS / "hub" / "catalog_face.json"
_FORBIDDEN_OUT = frozenset({"qasm3", "body", "twin_id", "token", "secret", "password"})
_SELECTABLE = frozenset({"algorithm", "runtime", "compiler", "workflow"})


def _public_asset(row: Mapping[str, Any]) -> dict[str, Any]:
    out = {
        "id": str(row.get("id") or ""),
        "kind": str(row.get("kind") or ""),
        "title": str(row.get("title") or row.get("id") or ""),
        "maturity": str(row.get("maturity") or ""),
        "summary": str(row.get("summary") or ""),
    }
    native = row.get("native_format")
    if native:
        out["native_format"] = str(native)
    when = row.get("choose_when")
    if isinstance(when, list) and when:
        out["choose_when"] = [str(item) for item in when]
    not_when = row.get("do_not_choose_when")
    if isinstance(not_when, list) and not_when:
        out["do_not_choose_when"] = [str(item) for item in not_when]
    leaked = _FORBIDDEN_OUT & set(out)
    if leaked:
        raise RuntimeError(f"hub face leaked {sorted(leaked)}")
    return out


def load_hub_face() -> dict[str, Any]:
    """Bundled face, optionally replaced by a live algo-hub index."""
    bundled = json.loads(_FACE.read_text(encoding="utf-8"))
    live = _try_live_index()
    if live:
        return live
    return bundled


def _try_live_index() -> dict[str, Any] | None:
    home = os.environ.get("QAGENT_ALGO_HUB_HOME", "").strip()
    if not home:
        return None
    index = Path(home) / "catalog" / "index.yaml"
    if not index.is_file():
        return None
    try:
        import yaml  # type: ignore
    except ImportError:
        return None
    raw = yaml.safe_load(index.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    assets = []
    for row in raw.get("assets") or []:
        if isinstance(row, dict) and row.get("id"):
            assets.append(_public_asset(row))
    if not assets:
        return None
    bundled = json.loads(_FACE.read_text(encoding="utf-8"))
    return {
        "api_version": "hub/v1",
        "source": "live",
        "choose": bundled.get("choose") or {},
        "assets": assets,
    }


class NativeHub:
    """Read-only algo-hub face. Does not import science packages. Does not run."""

    def list_assets(self, args: Mapping[str, Any]) -> dict[str, Any]:
        face = load_hub_face()
        kind = str(args.get("kind") or "").strip()
        rows = [_public_asset(row) for row in face.get("assets") or []]
        if kind:
            rows = [row for row in rows if row.get("kind") == kind]
        return {
            "assets": rows,
            "count": len(rows),
            "source": str(face.get("source") or "bundled"),
        }

    def describe(self, args: Mapping[str, Any]) -> dict[str, Any]:
        asset_id = str(args.get("id") or args.get("algorithm_id") or "").strip()
        if not asset_id:
            raise ValueError("id is required")
        face = load_hub_face()
        for row in face.get("assets") or []:
            if str(row.get("id") or "") == asset_id:
                payload = _public_asset(row)
                payload["selectable"] = payload.get("kind") in _SELECTABLE
                return payload
        raise KeyError(f"unknown id {asset_id!r}")

    def choose(self, args: Mapping[str, Any]) -> dict[str, Any]:
        face = load_hub_face()
        rules = face.get("choose") if isinstance(face.get("choose"), dict) else {}
        if "has_molecule" in args:
            has_molecule = bool(args.get("has_molecule"))
            key = "has_molecule" if has_molecule else "no_molecule"
            algorithm_id = str(rules.get(key) or ("org.chem.vqe" if has_molecule else "org.algo.vqe.hea"))
            reason = "molecule / geometry / basis" if has_molecule else "Pauli Hamiltonian, no molecule"
            return {"algorithm_id": algorithm_id, "reason": reason}
        hint = str(args.get("hint") or "").lower()
        if any(token in hint for token in ("maxcut", "qaoa", "组合")):
            return {"algorithm_id": "org.algo.qaoa.maxcut", "reason": "combinatorial / MaxCut"}
        if any(token in hint for token in ("pauli", "hamiltonian", "sparsepauli")):
            return {"algorithm_id": "org.algo.vqe.hea", "reason": "Pauli Hamiltonian"}
        if any(token in hint for token in ("分子", "molecule", "geometry", "basis", "active space")):
            return {"algorithm_id": "org.chem.vqe", "reason": "chemistry molecule"}
        return {"algorithm_id": "org.chem.vqe", "reason": "default chemistry track"}

    def validate(self, args: Mapping[str, Any]) -> dict[str, Any]:
        config = args.get("config")
        if not isinstance(config, dict):
            raise ValueError("config mapping is required")
        errors: list[str] = []
        if config.get("api_version") != "hub/v1":
            errors.append("api_version must be hub/v1")
        algorithm_id = config.get("algorithm_id")
        if not isinstance(algorithm_id, str) or not algorithm_id:
            errors.append("algorithm_id is required")
            return {"ok": False, "errors": errors}
        face = load_hub_face()
        card = next((row for row in face.get("assets") or [] if row.get("id") == algorithm_id), None)
        if card is None:
            errors.append(f"unknown algorithm_id {algorithm_id!r}")
            return {"ok": False, "errors": errors, "algorithm_id": algorithm_id}
        algorithm = config.get("algorithm") if isinstance(config.get("algorithm"), dict) else {}
        if not algorithm:
            errors.append("algorithm object is required")
        native = algorithm.get("native_format")
        expected = card.get("native_format")
        if native and expected and native != expected:
            errors.append(f"native_format {native!r} does not match card {expected!r}")
        return {
            "ok": not errors,
            "errors": errors,
            "algorithm_id": algorithm_id,
        }

    def translate(self, args: Mapping[str, Any]) -> dict[str, Any]:
        """Map company-pack or foreign JSON onto hub/v1. Does not run. No qasm3 on the face."""
        from qagent.services.translate import translate_config
        from qagent.services.uploads import parse_config_text

        config = args.get("config")
        if not isinstance(config, dict):
            text = args.get("text")
            if isinstance(text, str) and text.strip():
                config = parse_config_text(text)
            else:
                raise ValueError("config mapping is required")
        face = translate_config(config)
        out: dict[str, Any] = {
            "ok": bool(face.get("ok")),
            "origin": str(face.get("origin") or ""),
            "from_kind": str(face.get("from_kind") or ""),
            "errors": list(face.get("errors") or []),
        }
        algorithm_id = str(face.get("algorithm_id") or "")
        if algorithm_id:
            out["algorithm_id"] = algorithm_id
        leaked = _FORBIDDEN_OUT & set(out)
        if leaked:
            raise RuntimeError(f"hub translate leaked {sorted(leaked)}")
        return out
