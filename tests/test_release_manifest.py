from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Every fixture in this module expresses protection through POSIX chmod
# semantics (0444/0555 release shapes, 0600 private, 0666 unsafe); Windows
# cannot express those bits, so the module is honest-skipped there and stays
# fully enforced on the Ubuntu release host.
pytestmark = pytest.mark.posix_permissions


def load_script(name: str):
    path = ROOT / f"scripts/{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RELEASE = load_script("release_manifest")


def copy_release(tmp_path: Path) -> Path:
    root = tmp_path / "release"
    for relative in RELEASE.MANAGED_ROOTS:
        shutil.copytree(
            ROOT / relative, root / relative, ignore=shutil.ignore_patterns("node_modules", "__pycache__")
        )
    for relative in RELEASE.MANAGED_FILES:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    for relative in (
        "profiles/company-agent/pnpm-lock.yaml",
        "profiles/company-agent-minimal/pnpm-lock.yaml",
    ):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    for path in [root, *root.rglob("*")]:
        if path.is_dir():
            path.chmod(0o755)
        elif path.is_file():
            path.chmod(0o644)
    return root


def fake_runtime(tmp_path: Path, *, node_version: str = "22.22.0", dsh_version: str = "0.1.5-rc.2") -> Path:
    runtime = tmp_path / "runtime"
    node = runtime / "node_modules/node/bin/node"
    entry = runtime / "node_modules/@deepseek-ai/dsh/lib/bin.js"
    package = runtime / "node_modules/@deepseek-ai/dsh/package.json"
    node.parent.mkdir(parents=True)
    entry.parent.mkdir(parents=True)
    node.write_text(
        "#!/bin/sh\n"
        f"if [ \"$1\" = --version ]; then printf 'v{node_version}\\n'; exit 0; fi\n"
        f"printf '{dsh_version}'\n",
        encoding="utf-8",
    )
    entry.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    package.write_text(json.dumps({"version": dsh_version}), encoding="utf-8")
    node.chmod(0o755)
    entry.chmod(0o755)
    package.chmod(0o644)
    for path in [runtime, *runtime.rglob("*")]:
        if path.is_dir():
            path.chmod(0o755)
    return runtime


def write_manifest(tmp_path: Path, root: Path, runtime: Path) -> tuple[Path, dict]:
    manifest = RELEASE.build_manifest(root, runtime, immutable=False)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    path.chmod(0o600)
    return path, manifest


def test_manifest_round_trip_and_exact_managed_roots(tmp_path: Path) -> None:
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    path, manifest = write_manifest(tmp_path, root, runtime)
    verified = RELEASE.verify_manifest(path, expected_root=root, expected_runtime=runtime)
    assert verified["content_digest"] == manifest["content_digest"]
    assert verified["versions"] == {"node": "22.22.0", "dsh": "0.1.5-rc.2"}
    assert verified["contract_digest"].startswith("sha256:")
    assert verified["lock_digest"].startswith("sha256:")
    assert [row["path"] for row in verified["source_entries"]] == sorted(
        row["path"] for row in verified["source_entries"]
    )


@pytest.mark.parametrize("change", ["tamper", "addition", "deletion"])
def test_manifest_fails_closed_for_content_set_changes(tmp_path: Path, change: str) -> None:
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    path, _ = write_manifest(tmp_path, root, runtime)
    if change == "tamper":
        (root / "contracts/tools.json").write_text("{}", encoding="utf-8")
    elif change == "addition":
        (root / "src/company_agent/unlisted.py").write_text("value = 1\n", encoding="utf-8")
    else:
        (root / "src/company_agent/__init__.py").unlink()
    with pytest.raises(RELEASE.ManifestError):
        RELEASE.verify_manifest(path, expected_root=root, expected_runtime=runtime)


def test_manifest_rejects_symlink_and_unsafe_permissions(tmp_path: Path) -> None:
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    target = root / "src/company_agent/__init__.py"
    target.unlink()
    target.symlink_to(root / "pins.json")
    with pytest.raises(RELEASE.ManifestError, match="symlink"):
        RELEASE.build_manifest(root, runtime, immutable=False)
    target.unlink()
    target.write_text("", encoding="utf-8")
    target.chmod(0o666)
    with pytest.raises(RELEASE.ManifestError, match="writable"):
        RELEASE.build_manifest(root, runtime, immutable=False)


def test_runtime_real_path_and_version_are_bound(tmp_path: Path) -> None:
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    path, manifest = write_manifest(tmp_path, root, runtime)
    manifest["runtime_entries"][0]["real_path"] = str(runtime / "forged-node")
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RELEASE.ManifestError, match="real path"):
        RELEASE.verify_manifest(path, expected_root=root, expected_runtime=runtime)
    bad_runtime = fake_runtime(tmp_path / "bad", node_version="99.0.0")
    with pytest.raises(RELEASE.ManifestError, match="Node version mismatch"):
        RELEASE.build_manifest(root, bad_runtime, immutable=False)


def test_production_requires_read_only_release_not_writable_workspace(tmp_path: Path) -> None:
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    with pytest.raises(RELEASE.ManifestError, match="release root is writable"):
        RELEASE.build_manifest(root, runtime, immutable=True)
    assert stat.S_IMODE(ROOT.stat().st_mode) & 0o222


def test_attestation_is_external_and_tamper_evident(tmp_path: Path) -> None:
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    path, manifest = write_manifest(tmp_path, root, runtime)
    key = bytes.fromhex("42" * 32)
    trust = {"format": RELEASE.TRUST_FORMAT, "key_id": "operator-key", "hmac_sha256_key_hex": key.hex()}
    trust_path = tmp_path / "trust.json"
    trust_path.write_text(json.dumps(trust), encoding="utf-8")
    trust_path.chmod(0o600)
    signed = {
        "format": RELEASE.ATTESTATION_FORMAT,
        "key_id": "operator-key",
        "manifest_sha256": RELEASE.manifest_digest(manifest),
        "release_root": str(root.resolve()),
        "runtime_root": str(runtime.resolve()),
    }
    attestation = {
        **signed,
        "signature": "hmac-sha256:"
        + hmac.new(key, RELEASE.canonical_bytes(signed), hashlib.sha256).hexdigest(),
    }
    attestation_path = tmp_path / "attestation.json"
    attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
    attestation_path.chmod(0o600)
    assert RELEASE.verify_attestation(manifest, attestation_path, trust_path)["key_id"] == "operator-key"
    attestation["manifest_sha256"] = "sha256:" + "0" * 64
    attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
    with pytest.raises(RELEASE.ManifestError, match="linkage"):
        RELEASE.verify_attestation(manifest, attestation_path, trust_path)
    assert RELEASE.verify_manifest(path)["format"] == RELEASE.FORMAT


def test_manifest_binds_all_runtime_dependencies_and_builtin_knowledge(tmp_path: Path) -> None:
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    dependency = runtime / "node_modules/dependency/index.js"
    dependency.parent.mkdir()
    dependency.write_text("export default 1;\n", encoding="utf-8")
    dependency.chmod(0o644)
    path, manifest = write_manifest(tmp_path, root, runtime)
    assert any(row["path"].startswith("knowledge/") for row in manifest["source_entries"])
    dependency.write_text("export default 2;\n", encoding="utf-8")
    with pytest.raises(RELEASE.ManifestError, match="dependency tree mismatch"):
        RELEASE.verify_manifest(path)


def test_start_script_separates_development_and_production() -> None:
    text = (ROOT / "scripts/start_runtime.sh").read_text(encoding="utf-8")
    assert "COMPANY_AGENT_DEPLOYMENT_MODE:-development" in text
    assert "mutable workspace is not a production deployment" in text
    assert "--require-immutable" in text
    assert "COMPANY_AGENT_RELEASE_MANIFEST" in text
    assert "COMPANY_AGENT_RELEASE_ATTESTATION" in text
    assert "COMPANY_AGENT_RELEASE_TRUST_CONFIG" in text
    assert "COMPANY_AGENT_PRODUCTION_VERIFIED=1" in text
    assert "chmod -R" not in text
    assert 'cp -R "${RUNTIME}' not in text
    assert os.access(ROOT / "scripts/start_runtime.sh", os.R_OK)


def populate_profile_dependencies(root: Path) -> None:
    for name in ("company-agent", "company-agent-minimal"):
        modules = root / "profiles" / name / "node_modules"
        package = modules / ".pnpm/fixture/node_modules/fixture"
        package.mkdir(parents=True)
        (package / "index.js").write_text("export default 1;\n", encoding="utf-8")
        (modules / "fixture").symlink_to(".pnpm/fixture/node_modules/fixture", target_is_directory=True)


def readonly_tree(root: Path, readonly: bool) -> None:
    # Only temporary fixtures are changed. Skip links to avoid touching external targets.
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            continue
        executable = path.is_dir() or bool(path.stat().st_mode & 0o111)
        path.chmod((0o555 if executable else 0o444) if readonly else (0o755 if executable else 0o644))


def signed_manifest(tmp_path: Path, manifest: dict) -> tuple[Path, Path]:
    key = bytes.fromhex("42" * 32)
    trust = {"format": RELEASE.TRUST_FORMAT, "key_id": "synthetic", "hmac_sha256_key_hex": key.hex()}
    signed = {
        "format": RELEASE.ATTESTATION_FORMAT, "key_id": "synthetic",
        "manifest_sha256": RELEASE.manifest_digest(manifest),
        "release_root": manifest["release_root"], "runtime_root": manifest["runtime_root"],
    }
    attestation = {**signed, "signature": "hmac-sha256:" + hmac.new(
        key, RELEASE.canonical_bytes(signed), hashlib.sha256
    ).hexdigest()}
    paths = tmp_path / "attestation.json", tmp_path / "trust.json"
    for path, data in zip(paths, (attestation, trust), strict=True):
        path.write_text(json.dumps(data))
        path.chmod(0o600)
    return paths


def test_readonly_release_round_trip_with_external_attestation(tmp_path):
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    populate_profile_dependencies(root)
    try:
        readonly_tree(root, True)
        readonly_tree(runtime, True)
        manifest = RELEASE.build_manifest(root, runtime, immutable=True)
        path = tmp_path / "manifest.json"
        RELEASE._write_new_json(path, manifest)
        attestation, trust = signed_manifest(tmp_path, manifest)
        assert RELEASE.verify_manifest(path, expected_root=root, expected_runtime=runtime,
                                       require_immutable=True, attestation_path=attestation,
                                       trust_path=trust) == manifest
        assert RELEASE.verify_attestation(manifest, attestation, trust)["key_id"] == "synthetic"
        assert all(manifest["profile_dependency_digests"].values())
        with pytest.raises(RELEASE.ManifestError, match="new absolute"):
            RELEASE._write_new_json(path, manifest)
    finally:
        readonly_tree(root, False)
        readonly_tree(runtime, False)


@pytest.mark.parametrize("name", ["company-agent", "company-agent-minimal"])
@pytest.mark.parametrize("mutation", ["content", "mode", "missing", "escape", "broken"])
def test_profile_dependency_mutation_fails_closed(tmp_path, name, mutation):
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    populate_profile_dependencies(root)
    path, _ = write_manifest(tmp_path, root, runtime)
    modules = root / "profiles" / name / "node_modules"
    target = modules / ".pnpm/fixture/node_modules/fixture/index.js"
    if mutation == "content":
        target.write_text("export default 2;\n")
    elif mutation == "mode":
        target.chmod(0o666)
    elif mutation == "missing":
        shutil.rmtree(modules)
    else:
        link = modules / "fixture"
        link.unlink()
        link.symlink_to(tmp_path if mutation == "escape" else modules / "missing")
    with pytest.raises(RELEASE.ManifestError):
        RELEASE.verify_manifest(path)


@pytest.mark.parametrize("mutation", ["mode", "missing", "escape", "broken"])
def test_runtime_tree_mutation_fails_closed(tmp_path, mutation):
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    path, _ = write_manifest(tmp_path, root, runtime)
    entry = runtime / "node_modules/@deepseek-ai/dsh/lib/bin.js"
    if mutation == "mode":
        entry.chmod(0o777)
    elif mutation == "missing":
        entry.unlink()
    else:
        link = runtime / "node_modules/injected"
        link.symlink_to(tmp_path if mutation == "escape" else runtime / "node_modules/missing")
    with pytest.raises(RELEASE.ManifestError):
        RELEASE.verify_manifest(path)


@pytest.mark.parametrize("missing", ["company-agent", "company-agent-minimal"])
def test_immutable_release_requires_both_profile_trees(tmp_path, missing):
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    populate_profile_dependencies(root)
    shutil.rmtree(root / "profiles" / missing / "node_modules")
    try:
        readonly_tree(root, True)
        readonly_tree(runtime, True)
        with pytest.raises(RELEASE.ManifestError, match="dependencies are missing"):
            RELEASE.build_manifest(root, runtime, immutable=True)
    finally:
        readonly_tree(root, False)
        readonly_tree(runtime, False)


@pytest.mark.parametrize("inside", ["release", "runtime"])
@pytest.mark.parametrize("kind", ["attestation", "trust"])
def test_attestation_and_trust_must_be_external(tmp_path, inside, kind):
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    _, manifest = write_manifest(tmp_path, root, runtime)
    attestation, trust = signed_manifest(tmp_path, manifest)
    original = attestation if kind == "attestation" else trust
    internal = (root if inside == "release" else runtime) / original.name
    shutil.copy2(original, internal)
    with pytest.raises(RELEASE.ManifestError, match="must be external"):
        RELEASE.verify_attestation(manifest, internal if kind == "attestation" else attestation,
                                   internal if kind == "trust" else trust)


@pytest.mark.parametrize(
    "mutation", ["signature", "linkage", "trust", "missing_trust", "missing_attestation"]
)
def test_attested_verification_rejects_before_any_executable_probe(tmp_path, monkeypatch, mutation):
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    path, manifest = write_manifest(tmp_path, root, runtime)
    attestation, trust = signed_manifest(tmp_path, manifest)
    if mutation in {"signature", "linkage"}:
        value = json.loads(attestation.read_text())
        field = "signature" if mutation == "signature" else "manifest_sha256"
        value[field] = ("hmac-sha256:" if field == "signature" else "sha256:") + "0" * 64
        attestation.write_text(json.dumps(value))
    elif mutation == "trust":
        trust.chmod(0o644)
    probes = []

    def forbidden_probe(*args, **kwargs):
        probes.append(args)
        raise AssertionError("untrusted release must not execute a version probe")

    monkeypatch.setattr(RELEASE, "_probe", forbidden_probe)
    with pytest.raises(RELEASE.ManifestError):
        RELEASE.verify_manifest(
            path, expected_root=root, expected_runtime=runtime,
            attestation_path=None if mutation == "missing_attestation" else attestation,
            trust_path=None if mutation == "missing_trust" else trust,
        )
    assert probes == []


@pytest.mark.parametrize("tampered", ["source", "runtime"])
def test_valid_attestation_does_not_allow_tampered_content_to_execute(tmp_path, monkeypatch, tampered):
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    path, manifest = write_manifest(tmp_path, root, runtime)
    attestation, trust = signed_manifest(tmp_path, manifest)
    target = root / "src/company_agent/__init__.py" if tampered == "source" else (
        runtime / "node_modules/node/bin/node"
    )
    target.write_text(target.read_text() + "\n# changed after signing\n")

    def forbidden_probe(*_args, **_kwargs):
        raise AssertionError("tampered content must not execute a version probe")

    monkeypatch.setattr(RELEASE, "_probe", forbidden_probe)
    with pytest.raises(RELEASE.ManifestError, match="mismatch"):
        RELEASE.verify_manifest(path, attestation_path=attestation, trust_path=trust)


def test_attested_verification_loads_manifest_once_then_checks_content(tmp_path, monkeypatch):
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    path, manifest = write_manifest(tmp_path, root, runtime)
    attestation, trust = signed_manifest(tmp_path, manifest)
    original_load = RELEASE.load_json
    original_verify = RELEASE.verify_attestation
    loads = []

    def tracked_load(candidate):
        if candidate == path:
            loads.append(candidate)
        return original_load(candidate)

    def replace_after_authentication(value, attestation_path, trust_path):
        result = original_verify(value, attestation_path, trust_path)
        path.write_text("{}")
        return result

    monkeypatch.setattr(RELEASE, "load_json", tracked_load)
    monkeypatch.setattr(RELEASE, "verify_attestation", replace_after_authentication)
    assert RELEASE.verify_manifest(path, attestation_path=attestation, trust_path=trust) == manifest
    assert loads == [path]


@pytest.mark.parametrize("valid", [True, False])
def test_production_launcher_stops_at_verification_or_enters_only_stub(tmp_path, valid):
    root = copy_release(tmp_path)
    runtime = fake_runtime(tmp_path)
    populate_profile_dependencies(root)
    # Synthetic Node implements version probes and records the launch branch, never DSH.
    node = runtime / "node_modules/node/bin/node"
    probe_marker = tmp_path / "version-probe-marker"
    node.write_text(
        "#!/bin/sh\n"
        f"printf 'probe\\n' >> {shlex.quote(str(probe_marker))}\n"
        "if [ \"$1\" = --version ]; then printf 'v22.22.0\\n'; exit 0; fi\n"
        "if [ \"$1\" = -e ]; then printf '0.1.5-rc.2'; exit 0; fi\n"
        "test -z \"${NODE_OPTIONS:-}\" && test -z \"${PYTHONPATH:-}\" || exit 90\n"
        "test -z \"${COMPANY_AGENT_APPROVAL_CONTEXT:-}\" || exit 91\n"
        "test \"$COMPANY_AGENT_PRODUCTION_VERIFIED\" = 1 || exit 92\n"
        "test \"$COMPANY_AGENT_PYTHON\" = /usr/bin/python3 || exit 93\n"
        "printf 'synthetic-launch-only' > \"$COMPANY_AGENT_DSH_HOME/launch-marker\"\n"
    )
    home = tmp_path / "home"
    (home / "profiles").mkdir(parents=True)
    (home / "profiles/company-agent").symlink_to(root / "profiles/company-agent", target_is_directory=True)
    try:
        readonly_tree(root, True)
        readonly_tree(runtime, True)
        manifest = RELEASE.build_manifest(root, runtime, immutable=True)
        path = tmp_path / "manifest.json"
        RELEASE._write_new_json(path, manifest)
        attestation, trust = signed_manifest(tmp_path, manifest)
        if not valid:
            data = json.loads(attestation.read_text())
            data["signature"] = "hmac-sha256:" + "0" * 64
            attestation.write_text(json.dumps(data))
        probe_marker.unlink()
        env = {
            "PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
            "COMPANY_AGENT_DSH_HOME": str(home), "COMPANY_AGENT_RUNTIME_DIR": str(runtime),
            "COMPANY_AGENT_DEPLOYMENT_MODE": "production", "COMPANY_AGENT_PROFILE": "company-agent",
            "COMPANY_AGENT_PRESET": "lab", "COMPANY_AGENT_RELEASE_MANIFEST": str(path),
            "COMPANY_AGENT_RELEASE_ATTESTATION": str(attestation),
            "COMPANY_AGENT_RELEASE_TRUST_CONFIG": str(trust),
            "NODE_OPTIONS": "--require=/synthetic/invalid", "PYTHONPATH": "/synthetic/invalid",
            "COMPANY_AGENT_APPROVAL_CONTEXT": "synthetic-forbidden",
        }
        result = subprocess.run(["bash", str(root / "scripts/start_runtime.sh")], env=env,
                                capture_output=True, text=True, timeout=30, check=False)
        assert (result.returncode == 0) == valid, result.stderr
        assert (home / "launch-marker").exists() == valid
        assert probe_marker.exists() == valid
        if not valid:
            assert not (home / ".agent-presets").exists()
    finally:
        readonly_tree(root, False)
        readonly_tree(runtime, False)
