from __future__ import annotations

from typing import Any

from qagent.adapters.contracts import ROOT
from qagent.adapters.gov_store import (
    now_iso,
    read_json,
    safe_mode_path,
    savepoint_dir,
    write_json,
)
from qagent.adapters.preset import PRESET_BOOT, active_preset, set_active_preset
from qagent.adapters.support import new_id
from qagent.adapters.workplace_store import WorkplaceStore
from qagent.services.workplace import save_workplace

_PLUGIN_MARK = 'name: "@qccd/'


def plugin_names(profile: str = "qagent") -> list[str]:
    path = ROOT / "profiles" / profile / "cordis.patch.yml"
    if not path.is_file():
        return []
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if _PLUGIN_MARK in line:
            names.append(line.split(_PLUGIN_MARK, 1)[1].strip().strip('"'))
    return names


def snapshot(note: str = "") -> dict[str, Any]:
    """Public workplace + preset + plugin names. Never copies secrets."""
    public = WorkplaceStore().load()[0].to_public()
    row = {
        "savepoint_id": new_id("sp"),
        "ts": now_iso(),
        "note": note,
        "preset": active_preset(),
        "workplace": {
            key: public[key]
            for key in public
            if not str(key).startswith("has_") and key != "ready"
        },
        "plugins": plugin_names(),
    }
    write_json(savepoint_dir() / f"{row['savepoint_id']}.json", row)
    return row


def restore(savepoint_id: str) -> dict[str, Any]:
    row = read_json(savepoint_dir() / f"{savepoint_id}.json")
    if not row:
        raise ValueError(f"unknown savepoint_id {savepoint_id!r}")
    workplace = row.get("workplace") if isinstance(row.get("workplace"), dict) else {}
    save_workplace(workplace, None)
    if row.get("preset"):
        set_active_preset(str(row["preset"]))
    _clear_safe_mode()
    return {"ok": True, "savepoint_id": savepoint_id, "preset": active_preset()}


def enter_safe_mode() -> dict[str, Any]:
    """Policy-visible SAFE MODE: boot preset. TwinRun is not in the allowed set."""
    snap = snapshot(note="safe-mode")
    set_active_preset(PRESET_BOOT)
    flag = safe_mode_path()
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(str(snap["savepoint_id"]) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "safe_mode": True,
        "preset": PRESET_BOOT,
        "savepoint_id": snap["savepoint_id"],
    }


def safe_mode_on() -> bool:
    return safe_mode_path().is_file()


def _clear_safe_mode() -> None:
    path = safe_mode_path()
    if path.is_file():
        path.unlink()
