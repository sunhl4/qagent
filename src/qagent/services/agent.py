"""Deprecated harness. agent.turn is not the product loop (H-02f)."""

from __future__ import annotations

import json
from typing import Any

from qagent.adapters.agent_store import clear_thread, save_thread
from qagent.adapters.contracts import load_tool_catalog
from qagent.adapters.llm import LlmError, OpenAICompatClient
from qagent.adapters.preset import active_preset
from qagent.adapters.workplace_store import WorkplaceStore
from qagent.models.invoke import STATUS_NEEDS_ASK
from qagent.services.invoke import invoke
from qagent.services.workplace import load_workplace, workplace_status

_MAX_ROUNDS = 8


def openai_tools() -> list[dict[str, Any]]:
    tools = []
    for spec in load_tool_catalog():
        schema = spec.schema if isinstance(spec.schema, dict) else {}
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": str(schema.get("description") or spec.name),
                    "parameters": schema.get("parameters") or {"type": "object", "properties": {}},
                },
            }
        )
    return tools


def turn(*, message: str, client: Any | None = None) -> dict[str, Any]:
    del message, client
    raise RuntimeError(
        "agent.turn 不是产品循环。产品入口是 services.chat.turn。"
    )


def reset_agent() -> None:
    clear_thread()


def _default_client() -> OpenAICompatClient | None:
    row, hidden = WorkplaceStore().load()
    if not row.ready():
        return None
    return OpenAICompatClient(
        base_url=row.llm_base_url,
        model=row.llm_model,
        api_key=hidden.get("llm_api_key", ""),
    )


def _system_prompt() -> str:
    status = workplace_status()
    packs = "、".join(f"{item['label']}（{item['status']}）" for item in status["engines"])
    return (
        "你是幺正量子的 Qagent，公司内部和客户共用的科研 Agent。"
        "除了普通助手能做的计划与解释，你必须通过工具使用公司已经接上的软件包："
        f"{packs}。"
        "以后加开源包只登记引擎包，不要发明新的 agent。"
        "上机（ionstack_twin_run）必须等人批准。没有活 twin_id 就不要说已经签收。"
        "Aer / 外机不能冒充 twin_id。知识库用 qccd_docs_search。"
        "超算和量子计算机账户在设置里，不要向用户回显密码。"
        "工具由你按任务选择，不要走写死的黄金路径。"
    )


def _loop(history: list[dict[str, Any]], thread: dict[str, Any], client: Any) -> dict[str, Any]:
    used: list[str] = []
    tools = openai_tools()
    try:
        for _ in range(_MAX_ROUNDS):
            answer = client.complete(history, tools)
            calls = list(answer.get("tool_calls") or [])
            text = str(answer.get("content") or "").strip()
            if not calls:
                history.append({"role": "assistant", "content": text})
                thread["messages"] = history
                thread["pending"] = None
                save_thread(thread)
                return _out(text or "这一轮没有新的输出。", None, used)
            assistant: dict[str, Any] = {"role": "assistant", "content": text or None, "tool_calls": []}
            results: list[dict[str, Any]] = []
            for call in calls:
                name = str(call.get("name") or "")
                args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
                used.append(name)
                result = invoke(name, active_preset(), args, approved=False)
                if result.status == STATUS_NEEDS_ASK:
                    thread["messages"] = history
                    thread["pending"] = {"tool": name, "args": args, "preset": active_preset()}
                    save_thread(thread)
                    return _out(
                        (text + "\n" if text else "") + f"{name} 需要你批准。回「批准」才会上机。",
                        "approve",
                        used,
                    )
                assistant["tool_calls"].append(
                    {
                        "id": call.get("id"),
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
                    }
                )
                results.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": json.dumps(result.__dict__, ensure_ascii=False, default=str),
                    }
                )
            history.append(assistant)
            history.extend(results)
        thread["messages"] = history
        save_thread(thread)
        return _out("这一轮工具用得太多，先停在这里。再说一句我继续。", None, used)
    except LlmError as exc:
        return _out(str(exc), None, used)


def _resume_ask(thread: dict[str, Any], client: Any | None) -> dict[str, Any]:
    pending = thread.get("pending")
    if not isinstance(pending, dict) or not pending.get("tool"):
        return _out("现在没有等批准的上机。直接说你要做什么。", None)
    result = invoke(
        str(pending["tool"]),
        str(pending.get("preset") or active_preset()),
        pending.get("args") if isinstance(pending.get("args"), dict) else {},
        approved=True,
    )
    thread["pending"] = None
    history = list(thread.get("messages") or [])
    history.append(
        {
            "role": "tool",
            "content": json.dumps(result.__dict__, ensure_ascii=False, default=str),
        }
    )
    worker = client or _default_client()
    if worker is None:
        thread["messages"] = history
        save_thread(thread)
        return _out(result.error or result.status or "已按批准调用。", None, [str(pending["tool"])])
    return _loop(history, thread, worker)


def _out(reply: str, awaiting: str | None, used: list[str] | None = None) -> dict[str, Any]:
    return {
        "reply": reply,
        "awaiting": awaiting,
        "used_tools": list(used or []),
        "ready": load_workplace().ready(),
    }
