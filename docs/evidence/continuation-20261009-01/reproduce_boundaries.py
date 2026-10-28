"""Synthetic probes for release verification order and local acceptance selection."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import release_manifest as release  # noqa: E402
import verify_acceptance as acceptance  # noqa: E402


def main():
    events = []

    def verify(*_args, **_kwargs):
        events.append("content_and_executable_version_probe")
        return {"contract_digest": "sha256:" + "1" * 64, "lock_digest": "sha256:" + "2" * 64,
                "immutable_required": True}

    def bad_signature(*_args, **_kwargs):
        events.append("signature_rejected")
        raise release.ManifestError("synthetic invalid signature")

    with patch.object(release, "verify_manifest", verify), patch.object(
        release, "verify_attestation", bad_signature
    ):
        code = release.main(["verify", "--manifest", "/synthetic/manifest.json", "--attestation",
                             "/synthetic/attestation.json", "--trust-config", "/synthetic/trust.json"])
    with patch.dict(os.environ, {"PYTEST_ADDOPTS": "-k test_one", "PYTEST_PLUGINS": "synthetic_plugin"}):
        env = acceptance.offline_environment()
        retained = {name: name in env for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS")}
    empty = acceptance.run_gate("tests", [sys.executable, "-I", "-c", "print('no test summary')"])
    print(json.dumps({"scope": "synthetic_no_runtime_or_service", "signature_exit": code,
                      "verification_order": events, "pytest_override_retained": retained,
                      "empty_successful_process_status": empty["status"]}, sort_keys=True))


if __name__ == "__main__":
    main()
