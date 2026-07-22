"""Quality-vs-latency Pareto frontier for quantization (and any speed/quality knob).

Picking a quantization level is a trade, not a win: FP16 is most faithful and
slowest; Q4 is fastest and least faithful. The engineering artifact that answers
"which quant should we serve?" is the **Pareto frontier** — the set of configs
where you cannot get lower latency without giving up quality (or vice-versa).
Everything off the frontier is strictly dominated and should never be shipped.

This assembles the frontier from two measurements the project already produces
per config: **latency** from the inference harness (`benchmarks/harness.py`) and
**quality** from the Phase-4 eval harness (the same faithfulness/field-accuracy
gate used everywhere else). Keeping quality on the same axis as speed is what
stops "faster" from quietly meaning "worse" — the honesty bar ADR-0011 sets.

Pure functions, unit-tested offline; the numbers that flow in come from the GPU
serving session.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigPoint:
    label: str  # e.g. "fp16", "q8_0", "q4_k_m"
    latency_ms: float  # lower is better (e.g. harness p50 latency or TPOT)
    quality: float  # higher is better (e.g. eval faithfulness in [0, 1])


def pareto_frontier(points: list[ConfigPoint]) -> list[ConfigPoint]:
    """Return the non-dominated configs (minimize latency, maximize quality).

    A point p is dominated if some other q is at least as good on both axes and
    strictly better on one. Ties (identical latency and quality) keep all copies.
    Output preserves input order.
    """
    frontier: list[ConfigPoint] = []
    for p in points:
        dominated = any(
            q is not p
            and q.latency_ms <= p.latency_ms
            and q.quality >= p.quality
            and (q.latency_ms < p.latency_ms or q.quality > p.quality)
            for q in points
        )
        if not dominated:
            frontier.append(p)
    return frontier


def knee_point(frontier: list[ConfigPoint]) -> ConfigPoint | None:
    """A pragmatic default pick: the frontier config closest to the ideal corner
    (min latency, max quality) after min-max normalizing both axes. This is the
    "best bang for the buck" quant — the one to serve unless a hard quality floor
    dictates otherwise. Returns None for an empty frontier.
    """
    if not frontier:
        return None
    if len(frontier) == 1:
        return frontier[0]
    lat = [p.latency_ms for p in frontier]
    qual = [p.quality for p in frontier]
    lat_lo, lat_hi = min(lat), max(lat)
    qual_lo, qual_hi = min(qual), max(qual)
    lat_span = lat_hi - lat_lo or 1.0
    qual_span = qual_hi - qual_lo or 1.0

    def distance(p: ConfigPoint) -> float:
        # normalized latency (0 = fastest) and quality gap (0 = best)
        nlat = (p.latency_ms - lat_lo) / lat_span
        nqual_gap = (qual_hi - p.quality) / qual_span
        return (nlat**2 + nqual_gap**2) ** 0.5

    return min(frontier, key=distance)


def frontier_table(points: list[ConfigPoint], *, quality_floor: float | None = None) -> list[dict]:
    """Render configs for a report: latency, quality, whether each is on the
    frontier, and whether it clears an optional hard quality floor. Sorted by
    latency ascending (fastest first)."""
    front = set(pareto_frontier(points))
    knee = knee_point(sorted(front, key=lambda p: p.latency_ms)) if front else None
    rows = []
    for p in sorted(points, key=lambda p: p.latency_ms):
        rows.append(
            {
                "label": p.label,
                "latency_ms": p.latency_ms,
                "quality": p.quality,
                "on_frontier": p in front,
                "recommended": p == knee,
                "meets_floor": (quality_floor is None or p.quality >= quality_floor),
            }
        )
    return rows
