"""Postgres-cached LLM judge.

Free-tier RPM makes judge calls the scarce resource: every judgment is keyed
by sha256(judge_model :: prompt) in the judge_cache table, so re-runs and
resumed runs re-judge nothing.
"""

import hashlib
import json
import re
from typing import Any, Protocol

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from opsverse_core.llm import LLMResult, Message


def parse_json_reply(text: str) -> dict | None:
    """Extract the JSON object from a reply that may carry code fences."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


class SupportsComplete(Protocol):
    async def complete(self, messages: list[Message]) -> LLMResult: ...


class JudgeError(RuntimeError):
    """The judge answered, but not with parseable JSON."""


class CachedJudge:
    def __init__(self, llm: SupportsComplete, engine: AsyncEngine, judge_model: str):
        self._llm = llm
        self._engine = engine
        self.judge_model = judge_model
        self.cache_hits = 0
        self.cache_misses = 0

    def _key(self, prompt: str) -> str:
        return hashlib.sha256(f"{self.judge_model}::{prompt}".encode()).hexdigest()

    async def judge(self, prompt: str) -> dict[str, Any]:
        key = self._key(prompt)
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    sa.text("SELECT response FROM judge_cache WHERE prompt_hash = :h"),
                    {"h": key},
                )
            ).first()
        if row is not None:
            self.cache_hits += 1
            return row.response if isinstance(row.response, dict) else json.loads(row.response)

        self.cache_misses += 1
        result = await self._llm.complete([{"role": "user", "content": prompt}])
        parsed = parse_json_reply(result.text)
        if parsed is None:
            raise JudgeError(f"unparseable judge reply: {result.text[:200]}")
        async with self._engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO judge_cache (prompt_hash, judge_model, response, created_at)"
                    " VALUES (:h, :m, :r, now()) ON CONFLICT (prompt_hash) DO NOTHING"
                ),
                {"h": key, "m": self.judge_model, "r": json.dumps(parsed)},
            )
        return parsed
