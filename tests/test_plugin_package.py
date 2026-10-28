from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_quantum_plugin_installs_with_its_core_dependency(tmp_path: Path) -> None:
    manifest = {
        "name": "company-agent-package-check",
        "private": True,
        "type": "module",
        "dependencies": {
            "@unitqc/company-agent-quantum": f"file:{ROOT / 'packages/company-agent-quantum'}",
            "@unitqc/company-agent-latex": f"file:{ROOT / 'packages/company-agent-latex'}",
        },
    }
    (tmp_path / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    subprocess.run(
        ["corepack", "pnpm", "install", "--prod", "--ignore-scripts", "--offline", "--reporter=silent"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    env = os.environ.copy()
    env["COMPANY_AGENT_PYTHONPATH"] = str(ROOT / "src")
    for module, expected_name in (
        ("@unitqc/company-agent-quantum", "company-agent-quantum"),
        ("@unitqc/company-agent-latex", "company-agent-latex"),
    ):
        result = subprocess.run(
            [
                "node",
                "--input-type=module",
                "-e",
                f"import({json.dumps(module)}).then(m => console.log(m.name))",
            ],
            cwd=tmp_path,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == expected_name
    assert (tmp_path / "node_modules/.pnpm/node_modules/@unitqc/company-agent-core").exists()
