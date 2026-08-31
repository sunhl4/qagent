from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class LlmError(RuntimeError):
    """OpenAI-compatible HTTP failed. Not a science error."""


class OpenAICompatClient:
    """Company-local chat/completions. No third harness — only the model HTTP."""

    def __init__(self, *, base_url: str, model: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        url = self.base_url if self.base_url.endswith("/chat/completions") else f"{self.base_url}/chat/completions"
        body: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = tools
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise LlmError(f"模型接口 {exc.code}：{detail}") from exc
        except urllib.error.URLError as exc:
            raise LlmError(f"连不上本地模型：{exc.reason}") from exc
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        calls = []
        for item in message.get("tool_calls") or []:
            function = item.get("function") or {}
            raw_args = function.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except json.JSONDecodeError:
                args = {}
            calls.append(
                {
                    "id": str(item.get("id") or f"call_{len(calls)}"),
                    "name": str(function.get("name") or ""),
                    "arguments": args if isinstance(args, dict) else {},
                }
            )
        return {"content": message.get("content"), "tool_calls": calls}
