from __future__ import annotations

import re

CUSTOMER_VOICE_HINT = (
    "（对人只给短结论。不要报工具名、配方名、scenario 名。"
    "不要主动写映射名和 Pauli 展开，除非人要公式。"
    "公式用 \\(...\\) 行内、$$...$$ 独立成行，脸会渲染，不必改成 Unicode。"
    "不要为图去导出线路。图由脸用 circuit_id 画。）"
)

_CIRCUIT = re.compile(r"\bcirc_[0-9a-f]{8,}\b", re.IGNORECASE)
_ASSET = re.compile(r"\basset_[0-9a-z]{6,}\b", re.IGNORECASE)
_TWIN = re.compile(r"\btwin_[0-9a-f]{8,}\b", re.IGNORECASE)
_SESSION = re.compile(r"\bsession-[0-9a-f-]{8,}\b", re.IGNORECASE)
_ASSIGN = re.compile(r"\basg_[0-9a-z_]{4,}\b", re.IGNORECASE)
_RECIPE = re.compile(r"\b(?:a2_chem\w*|a2_spin\w*|a1_closed\w*|qem_[a-z0-9_]{4,})\b")
_TOOLS = (
    (re.compile(r"\bqiskit_export_circuit\b"), "线路"),
    (re.compile(r"\bqiskit_transpile\b"), "线路处理"),
    (re.compile(r"\bqiskit_aer_run\b"), "对照模拟"),
    (re.compile(r"\bqchem_run\b"), "化学计算"),
    (re.compile(r"\bqdata_run_recipe\b"), "数据计算"),
    (re.compile(r"\bqdata_list_assets\b"), "数据目录"),
    (re.compile(r"\bqagent_pin_circuit\b"), "钉住线路"),
    (re.compile(r"\bqagent_list_engines\b"), "已接软件"),
    (re.compile(r"\bqagent_hub_list\b"), "算法目录"),
    (re.compile(r"\bqagent_hub_describe\b"), "算法说明"),
    (re.compile(r"\bqagent_hub_choose\b"), "算法选型"),
    (re.compile(r"\bqagent_hub_validate\b"), "配置校验"),
    (re.compile(r"\bqagent_hub_translate\b"), "配置转写"),
    (re.compile(r"\bqagent_circuit_job\b"), "线路作业"),
    (re.compile(r"\bionstack_compile_estimate\b"), "时间估计"),
    (re.compile(r"\buccsd_pauli\b"), "UCCSD"),
    (re.compile(r"\bminimal_vqe\b"), "VQE"),
    (re.compile(r"\b\w*twin\w*run\b", re.IGNORECASE), "上机"),
)


def redact_customer_text(text: str) -> str:
    """Strip handles and internal names from customer-visible copy. No I/O."""
    out = str(text or "")
    out = _CIRCUIT.sub("这份线路", out)
    out = _ASSET.sub("这份数据", out)
    out = _TWIN.sub("签收回执", out)
    out = _SESSION.sub("这次会话", out)
    out = _ASSIGN.sub("这份交办", out)
    out = _RECIPE.sub("这份计算", out)
    for pattern, label in _TOOLS:
        out = pattern.sub(label, out)
    return out
