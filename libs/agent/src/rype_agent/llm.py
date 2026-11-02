"""Minimal OpenAI-compatible chat client with tool calling (OpenRouter by default).

The key comes from the environment (`OPENROUTER_API_KEY`) and is never logged:
errors carry the exception type only. Tests use `ScriptedChat` instead.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    raw_arguments: str = ""


class ChatTurn(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ChatClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | dict[str, Any] | None = None,
    ) -> ChatTurn: ...


def parse_message(message: dict[str, Any], usage: dict[str, Any] | None = None) -> ChatTurn:
    calls = []
    for call in message.get("tool_calls") or []:
        fn = call.get("function", {})
        raw = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        calls.append(
            ToolCall(
                id=call.get("id", ""),
                name=fn.get("name", ""),
                arguments=args,
                raw_arguments=str(raw),
            )
        )
    usage = usage or {}
    return ChatTurn(
        content=message.get("content"),
        tool_calls=calls,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
    )


class OpenAICompatibleChat:
    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 4,
        sleep: Callable[[float], None] = time.sleep,
    ):
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("set OPENROUTER_API_KEY (or pass api_key)")
        self.model = model
        self._retries, self._sleep = max_retries, sleep
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {key}", "X-Title": "RYPE agent eval"},
            timeout=120,
            transport=transport,
        )

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | dict[str, Any] | None = None,
    ) -> ChatTurn:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "temperature": 0,
            "max_tokens": 800,
        }
        if tool_choice is not None:
            body["tool_choice"] = tool_choice
        delay = 2.0
        for attempt in range(self._retries + 1):
            response = self._client.post("/chat/completions", json=body)
            if response.status_code in (429, 500, 502, 503, 504) and attempt < self._retries:
                self._sleep(delay)
                delay *= 2
                continue
            response.raise_for_status()
            data = response.json()
            return parse_message(data["choices"][0]["message"], data.get("usage"))
        raise RuntimeError("unreachable")


class ScriptedChat:
    """Replays a fixed list of turns; records what it was sent. For tests."""

    def __init__(self, turns: list[ChatTurn]):
        self.turns = list(turns)
        self.seen: list[list[dict[str, Any]]] = []
        self.tool_choices: list[Any] = []

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | dict[str, Any] | None = None,
    ) -> ChatTurn:
        self.seen.append([dict(m) for m in messages])
        self.tool_choices.append(tool_choice)
        return self.turns.pop(0) if self.turns else ChatTurn(content="(no more scripted turns)")
