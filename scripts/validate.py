#!/usr/bin/env python3
"""工程自检脚本。

检查内容：
1. 所有 JSON schema 可解析。
2. 若安装了 jsonschema，则检查 schema 自身合法。
3. 所有 YAML 示例可解析（需要 PyYAML）。
4. 若安装了 jsonschema 与 PyYAML，则用对应 schema 校验示例。
5. Canvas 文件存在且包含 default export。

不依赖第三方库也能运行，只是跳过需要库的检查。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILURES: list[str] = []
NOTES: list[str] = []


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"JSON 解析失败: {path.relative_to(ROOT)}: {exc}")
        return None


def _walk(node, path, failures):
    """Recursively check structural invariants without third-party libs."""
    if not isinstance(node, dict):
        return
    if node.get("type") == "object" or "properties" in node:
        props = node.get("properties", {})
        for name in node.get("required", []):
            if name not in props:
                failures.append(f"{path}: required 字段 {name} 未在 properties 中定义")
        for name, child in props.items():
            _walk(child, f"{path}.{name}", failures)
    if node.get("type") == "array":
        items = node.get("items")
        if isinstance(items, dict):
            _walk(items, f"{path}[]", failures)
    for key in ("oneOf", "anyOf", "allOf"):
        for index, child in enumerate(node.get(key, []) or []):
            _walk(child, f"{path}.{key}[{index}]", failures)
    if "enum" in node:
        values = node["enum"]
        if len(values) != len(set(map(str, values))):
            failures.append(f"{path}: enum 存在重复值")


def check_schemas() -> dict[str, dict]:
    loaded: dict[str, dict] = {}
    schema_dirs = [ROOT / "schemas", ROOT / "contracts" / "schemas"]
    files: list[Path] = []
    for directory in schema_dirs:
        if not directory.is_dir():
            FAILURES.append(f"缺少 {directory.relative_to(ROOT)}/ 目录")
            continue
        files.extend(sorted(directory.glob("*.json")))

    if not files:
        FAILURES.append("没有任何 JSON schema")
        return loaded

    for path in files:
        data = load_json(path)
        if data is None:
            continue
        for key in ("$schema", "$id", "title", "type"):
            if key not in data:
                FAILURES.append(f"{path.name} 缺少 {key}")
        _walk(data, str(path.relative_to(ROOT)), FAILURES)
        loaded[path.name] = data

    try:
        import jsonschema  # type: ignore
    except Exception:  # noqa: BLE001
        NOTES.append("未安装 jsonschema，跳过官方 schema 合法性检查")
        return loaded

    for name, data in loaded.items():
        try:
            jsonschema.Draft202012Validator.check_schema(data)
        except Exception as exc:  # noqa: BLE001
            FAILURES.append(f"{name} schema 非法: {exc}")
    return loaded


def check_yaml() -> list[Path]:
    yaml_files = sorted(ROOT.glob("configs/*.y*ml")) + sorted(ROOT.glob("examples/*.y*ml"))
    yaml_files += sorted(ROOT.glob("contracts/conformance/*.y*ml"))
    if not yaml_files:
        NOTES.append("未找到 YAML 示例")
        return []

    try:
        import yaml  # type: ignore
    except Exception:  # noqa: BLE001
        NOTES.append("未安装 PyYAML，跳过 YAML 解析检查")
        return yaml_files

    for path in yaml_files:
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            FAILURES.append(f"YAML 解析失败: {path.relative_to(ROOT)}: {exc}")
    return yaml_files


def check_examples(schemas: dict[str, dict], yaml_files: list[Path]) -> None:
    try:
        import yaml  # type: ignore
    except Exception:  # noqa: BLE001
        NOTES.append("缺少 PyYAML，跳过示例检查")
        return

    mapping = {
        "examples/experiment-spec.example.yaml": "experiment-spec.schema.json",
    }

    # 不依赖 jsonschema 也能做的顶层键检查
    for rel, schema_name in mapping.items():
        path = ROOT / rel
        if not path.exists():
            NOTES.append(f"示例不存在，跳过: {rel}")
            continue
        schema = schemas.get(schema_name)
        if schema is None:
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            FAILURES.append(f"{rel} 顶层不是对象")
            continue
        props = schema.get("properties", {})
        for key in data:
            if key not in props:
                FAILURES.append(f"{rel} 含未知字段: {key}")
        for key in schema.get("required", []):
            if key not in data:
                FAILURES.append(f"{rel} 缺少必填字段: {key}")

    try:
        import jsonschema  # type: ignore
    except Exception:  # noqa: BLE001
        NOTES.append("未安装 jsonschema，跳过示例的完整 schema 校验")
        return

    for rel, schema_name in mapping.items():
        path = ROOT / rel
        schema = schemas.get(schema_name)
        if not path.exists() or schema is None:
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            jsonschema.Draft202012Validator(schema).validate(data)
        except Exception as exc:  # noqa: BLE001
            FAILURES.append(f"{rel} 不符合 {schema_name}: {exc}")


def check_conformance_cases() -> None:
    path = ROOT / "contracts" / "conformance" / "cases.yaml"
    if not path.exists():
        FAILURES.append("缺少 contracts/conformance/cases.yaml")
        return
    try:
        import yaml  # type: ignore
    except Exception:  # noqa: BLE001
        NOTES.append("未安装 PyYAML，跳过一致性用例检查")
        return

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        FAILURES.append("cases.yaml 顶层不是对象")
        return
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        FAILURES.append("cases.yaml 缺少 cases 数组")
        return

    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            FAILURES.append(f"cases[{index}] 不是对象")
            continue
        for key in ("id", "port", "level", "title", "given", "when", "then"):
            if key not in case:
                FAILURES.append(f"cases[{index}] 缺少 {key}")
        case_id = case.get("id")
        if isinstance(case_id, str):
            if case_id in seen:
                FAILURES.append(f"重复用例 ID: {case_id}")
            seen.add(case_id)
        if case.get("level") not in ("MUST", "SHOULD"):
            FAILURES.append(f"cases[{index}] level 非法")
        if not isinstance(case.get("then"), list) or not case.get("then"):
            FAILURES.append(f"cases[{index}] then 必须是非空数组")

    must = sum(1 for case in cases if isinstance(case, dict) and case.get("level") == "MUST")
    print(f"一致性用例: {len(cases)} 条（MUST {must}）")


def check_stubs() -> None:
    """检查桩文件存在、继承统一基类，并由基类统一声明 degraded。"""
    expected = [
        "adapters/stub/README.md",
        "adapters/stub/src/index.ts",
        "adapters/stub/src/common.ts",
        "adapters/stub/src/identity.ts",
        "adapters/stub/src/secrets.ts",
        "adapters/stub/src/artifact-store.ts",
        "adapters/stub/src/model-gateway.ts",
        "adapters/stub/src/compute.ts",
        "adapters/stub/src/events.ts",
        "adapters/stub/src/session.ts",
        "adapters/stub/src/telemetry.ts",
    ]
    for rel in expected:
        if not (ROOT / rel).exists():
            FAILURES.append(f"缺少 {rel}")

    common = ROOT / "adapters/stub/src/common.ts"
    if common.exists():
        text = common.read_text(encoding="utf-8")
        if "degraded: true" not in text:
            FAILURES.append("common.ts 必须在能力声明中强制 degraded: true")
        if "degradedReason" not in text:
            FAILURES.append("common.ts 必须支持 degradedReason")

    port_files = [
        "identity.ts",
        "secrets.ts",
        "artifact-store.ts",
        "model-gateway.ts",
        "compute.ts",
        "events.ts",
        "session.ts",
        "telemetry.ts",
    ]
    for name in port_files:
        path = ROOT / "adapters/stub/src" / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "StubBase" not in text:
            FAILURES.append(f"{name} 必须继承统一的 StubBase")
        if "degradedReason:" not in text:
            FAILURES.append(f"{name} 必须给出 degradedReason")


def check_canvas() -> None:
    path = ROOT / "canvas" / "autonomous-ai-research-workflow.canvas.tsx"
    if not path.exists():
        FAILURES.append("缺少 canvas 文件")
        return
    text = path.read_text(encoding="utf-8")
    if "export default" not in text:
        FAILURES.append("canvas 缺少 default export")
    if '@deepseek-ai/dsh-sdk-client' not in text:
        FAILURES.append("canvas 未包含 DSH 官方组件内容")


def check_contracts() -> None:
    """契约版本、目录与桩声明的一致性检查。"""
    contracts_dir = ROOT / "contracts"
    required = [
        contracts_dir / "VERSION",
        contracts_dir / "README.md",
        contracts_dir / "package.json",
        contracts_dir / "tsconfig.json",
        contracts_dir / "src" / "index.ts",
        contracts_dir / "src" / "types.ts",
        contracts_dir / "src" / "ports" / "identity.ts",
        contracts_dir / "src" / "ports" / "secrets.ts",
        contracts_dir / "src" / "ports" / "artifact-store.ts",
        contracts_dir / "src" / "ports" / "model-gateway.ts",
        contracts_dir / "src" / "ports" / "compute.ts",
        contracts_dir / "src" / "ports" / "events.ts",
        contracts_dir / "src" / "ports" / "session.ts",
        contracts_dir / "src" / "ports" / "telemetry.ts",
        contracts_dir / "conformance" / "cases.md",
        contracts_dir / "conformance" / "cases.yaml",
    ]
    for path in required:
        if not path.exists():
            FAILURES.append(f"缺少契约文件: {path.relative_to(ROOT)}")

    version_path = contracts_dir / "VERSION"
    index_path = contracts_dir / "src" / "index.ts"
    if version_path.exists() and index_path.exists():
        version = version_path.read_text(encoding="utf-8").strip()
        index_text = index_path.read_text(encoding="utf-8")
        marker = f'CONTRACT_VERSION = "{version}"'
        if marker not in index_text:
            FAILURES.append(
                f"contracts/VERSION ({version}) 与 CONTRACT_VERSION 不一致"
            )

    package_path = contracts_dir / "package.json"
    if package_path.exists():
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            if package.get("name") != "@company/dsh-contracts":
                FAILURES.append("contracts/package.json 的包名必须是 @company/dsh-contracts")
        except Exception as exc:  # noqa: BLE001
            FAILURES.append(f"contracts/package.json 解析失败: {exc}")

    # 桩必须通过基类声明 degraded
    stub_dir = ROOT / "adapters" / "stub" / "src"
    if not stub_dir.is_dir():
        FAILURES.append("缺少 adapters/stub/src")
        return

    common = stub_dir / "common.ts"
    if not common.exists():
        FAILURES.append("缺少 adapters/stub/src/common.ts")
    else:
        text = common.read_text(encoding="utf-8")
        if "degraded: true" not in text:
            FAILURES.append("common.ts 必须在能力声明中强制 degraded: true")
        if "degradedReason" not in text:
            FAILURES.append("common.ts 必须支持 degradedReason")

    stub_files = sorted(stub_dir.glob("*.ts"))
    if not stub_files:
        FAILURES.append("adapters/stub/src 下没有 TypeScript 文件")
        return

    for path in stub_files:
        text = path.read_text(encoding="utf-8")
        if path.name == "common.ts" or path.name == "index.ts":
            continue
        if "degradedReason" not in text:
            FAILURES.append(f"{path.name} 必须给出 degradedReason")

    # 一致性用例关键编号
    cases_path = contracts_dir / "conformance" / "cases.md"
    if cases_path.exists():
        cases = cases_path.read_text(encoding="utf-8")
        for case_id in ["ID-01", "OS-01", "CR-01", "MD-01", "HP-01", "SS-01", "TL-01", "XP-03"]:
            if case_id not in cases:
                FAILURES.append(f"一致性用例缺少 {case_id}")

    # 本工程不得直接依赖 DSH 或 harness-core 内部实现
    forbidden_patterns = ["@deepseek-ai/", "from \"harness-core", "from 'harness-core"]
    code_dirs = [ROOT / "packages", ROOT / "adapters", contracts_dir / "src"]
    for base in code_dirs:
        if not base.is_dir():
            continue
        for path in base.rglob("*.ts"):
            text = path.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                if pattern in text:
                    FAILURES.append(
                        f"{path.relative_to(ROOT)} 直接依赖了 harness 内部实现: {pattern}"
                    )


def check_packages() -> None:
    package_json = ROOT / "package.json"
    if not package_json.exists():
        FAILURES.append("缺少根 package.json")
        return
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"根 package.json 解析失败: {exc}")
        return
    if data.get("type") != "module":
        FAILURES.append("根 package.json 必须声明 type=module")
    workspaces = data.get("workspaces")
    if not isinstance(workspaces, list) or "contracts" not in workspaces:
        FAILURES.append("根 package.json 的 workspaces 必须包含 contracts")

    for rel in ["contracts", "packages/domain", "packages/pipeline", "packages/workspace", "adapters/stub"]:
        path = ROOT / rel / "package.json"
        if not path.exists():
            FAILURES.append(f"缺少 {rel}/package.json")


def main() -> int:
    print(f"工程根目录: {ROOT}")
    schemas = check_schemas()
    yaml_files = check_yaml()
    check_examples(schemas, yaml_files)
    check_conformance_cases()
    check_stubs()
    check_contracts()
    check_packages()
    check_canvas()

    print(f"schema 数量: {len(schemas)}")
    print(f"YAML 数量: {len(yaml_files)}")

    for note in NOTES:
        print(f"[跳过] {note}")

    if FAILURES:
        print("\n失败项:")
        for item in FAILURES:
            print(f"  - {item}")
        return 1

    print("\n全部检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
