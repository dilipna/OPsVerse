"""One measurement session against one served configuration.

`harness.py` measures a single concurrency level. This drives a whole
**session**: the concurrency sweep plus the probes that isolate individual
inference-engine features, and stamps the result with the hardware and engine
identity so two JSON files are actually comparable months apart.

One invocation == one (engine, quantization) pair, e.g. "vLLM serving OpsLM-v1
at FP16" or "Ollama serving OpsLM-v1 Q4_K_M". Run it once per configuration;
`report.py` joins the resulting files into the comparison tables.

The probes, and what each one proves:

* **concurrency sweep** — system throughput rising while per-request latency
  degrades sub-linearly is continuous batching working. A server without it
  shows throughput flat and latency rising linearly.
* **prefix cache** — TTFT drop on requests that share a long prefix. Isolates
  prefill reuse (vLLM APC / SGLang RadixAttention) from decode speed.
* **structured output** — JSON parse rate with the engine's guided-decoding
  backend on vs. off. The interesting number is the *floor*: guided decoding
  should be 1.0 by construction, so the measurement's value is the baseline it
  is compared against.

Networked code is deliberately thin; the aggregation and labelling below are
pure functions so they can be unit-tested without a GPU (`tests/test_run_suite.py`).

Usage (on the GPU box, after starting a server):
    python benchmarks/run_suite.py --base-url http://localhost:8000/v1 \\
        --model OpsLM-v1 --engine vllm --quant fp16 \\
        --out benchmarks/results/vllm-opslm-fp16.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# `benchmarks/` is a script directory, not an installed package (see the repo's
# pytest config, which loads these modules by file path). Putting this file's
# own directory on the path makes `harness` importable both when this runs as a
# script and when a test loads it via importlib.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import (
    RequestResult,
    _one_request,
    percentile,
    prefix_cache_speedup,
    run_level,
    shared_prefix_prompts,
)

# A prefix long enough that prefilling it is measurable against the noise floor.
# Real systems hit this shape constantly: a fixed system prompt or a retrieved
# document reused across many user turns — which is exactly OpsVerse's RAG path.
PREFIX_CACHE_SYSTEM = """You are OpsLM, an operations assistant. Answer using only the
runbook excerpts below. Cite the excerpt id inline. If the excerpts do not contain the
answer, say so rather than guessing.

[excerpt ops-001] Readiness probes gate traffic; liveness probes gate restarts. A
readiness probe that fails removes the pod from Service endpoints without killing it.
[excerpt ops-002] CrashLoopBackOff means the container exited repeatedly. Inspect the
previous container's logs with --previous before changing configuration.
[excerpt ops-003] Terraform plan computes a diff against refreshed state; apply executes
it. A plan file passed to apply guarantees the executed diff is the reviewed one.
[excerpt ops-004] A Dockerfile HEALTHCHECK marks a container unhealthy but does not
restart it; the orchestrator's restart policy does that.
[excerpt ops-005] MLflow's model registry versions models and tracks stage transitions;
it does not serve them.
"""

PREFIX_CACHE_SUFFIXES = [
    "Question: when should I use a readiness probe instead of a liveness probe?",
    "Question: my pod is in CrashLoopBackOff. What do I check first?",
    "Question: how does terraform plan differ from apply?",
    "Question: does a Dockerfile HEALTHCHECK restart my container?",
    "Question: what is the MLflow model registry for?",
]

# Schema kept small on purpose: the probe measures whether the engine can be
# forced to emit parseable JSON, not whether the model knows the answer.
STRUCTURED_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "severity": {"type": "string"},
        "component": {"type": "string"},
        "action": {"type": "string"},
    },
    "required": ["severity", "component", "action"],
}

STRUCTURED_PROMPTS = [
    "A pod is in CrashLoopBackOff after a config change. Classify it.",
    "Disk usage on the primary database node hit 94%. Classify it.",
    "A nightly ETL job finished 20 minutes late. Classify it.",
    "TLS certificate for the public API expires in 3 days. Classify it.",
]


@dataclass
class SuiteConfig:
    """Identity of one measured configuration. Everything here lands in the
    report tables, so a file with a missing field is a file nobody can interpret."""

    base_url: str
    model: str
    engine: str  # "vllm" | "ollama" | "sglang" | ...
    quant: str  # "fp16" | "awq" | "q8_0" | "q4_k_m" | ...
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def gpu_info() -> dict[str, Any]:
    """Best-effort GPU identity via nvidia-smi. Returns ``{"gpu": None}`` on CPU
    boxes rather than raising — a CPU run is a legitimate (labelled) datapoint."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
    except Exception:
        return {"gpu": None, "gpu_memory": None}
    first = out.splitlines()[0] if out else ""
    name, _, mem = first.partition(",")
    return {"gpu": name.strip() or None, "gpu_memory": mem.strip() or None}


def suite_metadata(config: SuiteConfig) -> dict[str, Any]:
    """Provenance stamped on every result file: what was served, on what, when.

    Reports generated from these files quote hardware and date, because a
    latency number without them is not a measurement, it is a rumour.
    """
    return {
        "engine": config.engine,
        "quant": config.quant,
        "model": config.model,
        "endpoint": config.base_url,
        "notes": config.notes,
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": platform.python_version(),
        "platform": platform.platform(),
        **gpu_info(),
        **config.extra,
    }


def json_parse_rate(texts: list[str]) -> float:
    """Fraction of completions that parse as JSON objects.

    Fenced ```json blocks are unwrapped first: a model that emits correct JSON
    inside a fence has a *formatting* problem, not a structure problem, and
    conflating the two overstates what guided decoding fixed.
    """
    if not texts:
        return 0.0
    ok = 0
    for text in texts:
        candidate = text.strip()
        if candidate.startswith("```"):
            body = candidate.split("```")
            candidate = body[1] if len(body) > 1 else candidate
            if candidate.startswith("json"):
                candidate = candidate[4:]
            candidate = candidate.strip()
        try:
            ok += isinstance(json.loads(candidate), dict)
        except Exception:
            continue
    return ok / len(texts)


def summarize_prefix_probe(cold: RequestResult, warm: list[RequestResult]) -> dict[str, Any]:
    """Cold-vs-warm TTFT for the shared-prefix probe.

    The first request pays full prefill for the shared prefix; subsequent ones
    should hit the cache. Warm TTFT is taken as the p50 across the warm requests
    so one unlucky request cannot manufacture a speedup.
    """
    warm_ttfts = [r.ttft_s for r in warm if r.ok and r.ttft_s is not None]
    if not cold.ok or cold.ttft_s is None or not warm_ttfts:
        return {"measured": False, "reason": "insufficient successful requests"}
    warm_p50 = percentile(warm_ttfts, 50)
    return {
        "measured": True,
        "cold_ttft_s": round(cold.ttft_s, 4),
        "warm_ttft_s_p50": round(warm_p50, 4),
        "ttft_reduction": round(prefix_cache_speedup(cold.ttft_s, warm_p50), 4),
        "warm_requests": len(warm_ttfts),
    }


def batching_efficiency(levels: list[dict[str, Any]]) -> dict[str, Any]:
    """Throughput scaling across the concurrency sweep — the continuous-batching
    signal.

    ``scaling`` is throughput at max concurrency ÷ throughput at min concurrency.
    Interpretation: near 1.0 means the server serialized the work (no batching);
    growth well above 1.0 means concurrent requests shared decode passes. It is
    reported next to the p95 latency inflation because batching *does* cost
    per-request latency — the trade is the point, and hiding either half of it
    would be dishonest.
    """
    usable = [lv for lv in levels if lv.get("ok", 0) > 0]
    if len(usable) < 2:
        return {"measured": False, "reason": "need >=2 concurrency levels with successful requests"}
    lo = min(usable, key=lambda lv: lv["concurrency"])
    hi = max(usable, key=lambda lv: lv["concurrency"])
    lo_tp = lo["throughput_tokens_s"]
    lo_p95 = lo["latency_s"]["p95"]
    return {
        "measured": True,
        "from_concurrency": lo["concurrency"],
        "to_concurrency": hi["concurrency"],
        "throughput_scaling": round(hi["throughput_tokens_s"] / lo_tp, 3) if lo_tp > 0 else None,
        "p95_latency_inflation": round(hi["latency_s"]["p95"] / lo_p95, 3) if lo_p95 > 0 else None,
    }


async def _collect_text(
    client: Any, base_url: str, model: str, prompt: str, *, guided: bool
) -> str:
    """One non-streamed completion, optionally with the engine's structured-output
    constraint applied. Returns "" on failure so the caller scores it as unparseable
    rather than crashing the session."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Reply with a single JSON object and nothing else."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 200,
        "temperature": 0.0,
    }
    if guided:
        # OpenAI-compatible json_schema; vLLM maps this onto its guided-decoding
        # backend (xgrammar/outlines). Engines lacking it return an error, which
        # is itself a reportable result rather than a crash.
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "incident", "schema": STRUCTURED_SCHEMA, "strict": True},
        }
    try:
        resp = await client.post(f"{base_url}/chat/completions", json=payload, timeout=120.0)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"] or ""
    except Exception:
        return ""


async def run_structured_probe(config: SuiteConfig) -> dict[str, Any]:
    """JSON parse rate with guided decoding off, then on."""
    import httpx

    async with httpx.AsyncClient() as client:
        results: dict[str, Any] = {}
        for label, guided in (("guided_off", False), ("guided_on", True)):
            texts = await asyncio.gather(
                *(
                    _collect_text(client, config.base_url, config.model, p, guided=guided)
                    for p in STRUCTURED_PROMPTS
                )
            )
            results[label] = {
                "json_parse_rate": round(json_parse_rate(list(texts)), 4),
                "n": len(STRUCTURED_PROMPTS),
                # A rate of 0.0 with guided_on usually means the engine rejected
                # response_format rather than that it decoded badly. Keep the
                # empty-response count so the report can tell those apart.
                "empty_responses": sum(1 for t in texts if not t),
            }
    return results


async def run_prefix_probe(config: SuiteConfig) -> dict[str, Any]:
    """Sequential cold-then-warm requests over a shared prefix.

    Strictly sequential: concurrent requests would race on populating the cache
    and the "warm" requests might not actually be warm.
    """
    import httpx

    prompts = shared_prefix_prompts(PREFIX_CACHE_SYSTEM, PREFIX_CACHE_SUFFIXES)
    async with httpx.AsyncClient() as client:
        cold = await _one_request(client, config.base_url, config.model, prompts[0])
        warm = [await _one_request(client, config.base_url, config.model, p) for p in prompts[1:]]
    return summarize_prefix_probe(cold, warm)


async def run_suite(
    config: SuiteConfig,
    *,
    concurrency: list[int],
    requests: int,
    skip_probes: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = {"meta": suite_metadata(config), "levels": []}

    for level in concurrency:
        result = await run_level(config.base_url, config.model, level, requests)
        report["levels"].append(result)
        print(json.dumps(result))

    report["batching"] = batching_efficiency(report["levels"])
    print(json.dumps({"batching": report["batching"]}))

    if not skip_probes:
        report["prefix_cache"] = await run_prefix_probe(config)
        print(json.dumps({"prefix_cache": report["prefix_cache"]}))
        report["structured_output"] = await run_structured_probe(config)
        print(json.dumps({"structured_output": report["structured_output"]}))

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="OpenAI-compatible base URL")
    parser.add_argument("--model", required=True, help="model name as the server knows it")
    parser.add_argument("--engine", required=True, help="vllm | ollama | sglang | ...")
    parser.add_argument("--quant", required=True, help="fp16 | awq | q8_0 | q4_k_m | ...")
    parser.add_argument("--notes", default="", help="free text stamped into the result file")
    parser.add_argument("--concurrency", default="1,4,16")
    parser.add_argument("--requests", type=int, default=32)
    parser.add_argument("--skip-probes", action="store_true", help="concurrency sweep only")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    config = SuiteConfig(
        base_url=args.base_url.rstrip("/"),
        model=args.model,
        engine=args.engine,
        quant=args.quant,
        notes=args.notes,
    )
    report = asyncio.run(
        run_suite(
            config,
            concurrency=[int(c) for c in args.concurrency.split(",")],
            requests=args.requests,
            skip_probes=args.skip_probes,
        )
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
