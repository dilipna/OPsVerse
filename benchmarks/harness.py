"""Inference benchmark harness: TTFT, tokens/sec, throughput vs concurrency.

Targets any **OpenAI-compatible** `/v1/chat/completions` endpoint, so the same
harness benchmarks Ollama, vLLM, and SGLang serving OpsLM without per-engine
code. Runs on Colab/Kaggle GPU (where the servers run); this repo commits the
harness + methodology, and the measurement math is unit-tested here.

Metrics per request: TTFT (time to first streamed token), total latency,
output tokens, tokens/sec. Aggregated per concurrency level: p50/p95 of each,
plus system throughput (total output tokens / wall-clock).

Usage (on the GPU box, after starting a server):
    python benchmarks/harness.py --base-url http://localhost:11434/v1 \
        --model opslm --concurrency 1,4,16 --requests 32 \
        --out benchmarks/results/ollama-opslm.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROMPTS = [
    "Explain what a Kubernetes readiness probe does and when to use one.",
    "Write a Dockerfile HEALTHCHECK for a Flask app on port 8000.",
    "How does Terraform plan differ from apply? Answer concisely.",
    "What is MLflow's model registry for?",
    "Diagnose: my pod is stuck in CrashLoopBackOff. First three things to check?",
]


@dataclass
class RequestResult:
    ttft_s: float | None
    latency_s: float
    output_tokens: int
    ok: bool

    @property
    def tokens_per_s(self) -> float:
        return self.output_tokens / self.latency_s if self.latency_s > 0 else 0.0


def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile; pct in [0,100]. Empty -> 0."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100) * (len(ordered) - 1)
    lo = int(rank)
    frac = rank - lo
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def summarize(results: list[RequestResult], wall_clock_s: float) -> dict[str, Any]:
    """Aggregate a concurrency level's requests into the reported metrics."""
    ok = [r for r in results if r.ok]
    ttfts = [r.ttft_s for r in ok if r.ttft_s is not None]
    latencies = [r.latency_s for r in ok]
    tps = [r.tokens_per_s for r in ok]
    total_out = sum(r.output_tokens for r in ok)
    return {
        "requests": len(results),
        "ok": len(ok),
        "errors": len(results) - len(ok),
        "ttft_s": {"p50": round(percentile(ttfts, 50), 4), "p95": round(percentile(ttfts, 95), 4)},
        "latency_s": {
            "p50": round(percentile(latencies, 50), 4),
            "p95": round(percentile(latencies, 95), 4),
        },
        "tokens_per_s_per_req": {
            "p50": round(percentile(tps, 50), 2),
            "p95": round(percentile(tps, 95), 2),
        },
        # system throughput: how many output tokens/sec the server sustained
        # across all concurrent requests — the number that actually scales.
        "throughput_tokens_s": round(total_out / wall_clock_s, 2) if wall_clock_s > 0 else 0.0,
    }


async def _one_request(client: Any, base_url: str, model: str, prompt: str) -> RequestResult:
    start = time.perf_counter()
    ttft: float | None = None
    tokens = 0
    try:
        async with client.stream(
            "POST",
            f"{base_url}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
                "max_tokens": 256,
            },
            timeout=120.0,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: ") or line.strip() == "data: [DONE]":
                    continue
                if ttft is None:
                    ttft = time.perf_counter() - start
                delta = json.loads(line[6:])["choices"][0].get("delta", {}).get("content")
                if delta:
                    tokens += 1  # streamed-chunk count ~ output tokens (documented approximation)
    except Exception:
        return RequestResult(ttft, time.perf_counter() - start, tokens, ok=False)
    return RequestResult(ttft, time.perf_counter() - start, tokens, ok=True)


async def run_level(base_url: str, model: str, concurrency: int, n_requests: int) -> dict[str, Any]:
    import httpx

    prompts = [PROMPTS[i % len(PROMPTS)] for i in range(n_requests)]
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient() as client:

        async def guarded(prompt: str) -> RequestResult:
            async with sem:
                return await _one_request(client, base_url, model, prompt)

        wall_start = time.perf_counter()
        results = await asyncio.gather(*(guarded(p) for p in prompts))
        wall = time.perf_counter() - wall_start
    return {"concurrency": concurrency, **summarize(list(results), wall)}


async def main_async(args: argparse.Namespace) -> None:
    levels = [int(c) for c in args.concurrency.split(",")]
    report = {
        "endpoint": args.base_url,
        "model": args.model,
        "requests_per_level": args.requests,
        "levels": [],
    }
    for c in levels:
        level = await run_level(args.base_url, args.model, c, args.requests)
        report["levels"].append(level)
        print(json.dumps(level))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(f"wrote {args.out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", required=True, help="OpenAI-compatible base, e.g. http://localhost:11434/v1"
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--concurrency", default="1,4,16")
    parser.add_argument("--requests", type=int, default=32)
    parser.add_argument("--out", type=Path, default=None)
    asyncio.run(main_async(parser.parse_args()))


# expose the dataclass constructor name expected by tests
__all__ = ["RequestResult", "percentile", "summarize"]


if __name__ == "__main__":
    main()
