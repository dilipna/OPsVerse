"""Uncertainty and significance for eval deltas.

An eval that reports `hybrid 0.705 vs sparse 0.759` and stops has not said
whether the gap is real. With n=100 queries, differences of a few points are
routinely noise -- this project already measured a +/-22% run-to-run spread on
the inference side (ADR-0017) and the same discipline belongs on retrieval.

Two tools, both non-parametric (no normality assumption, which per-query metric
scores badly violate -- `hit@k` is Bernoulli, `mrr@k` is a spike-and-slab):

* `bootstrap_ci` -- resample queries with replacement to get a confidence
  interval for a single system's mean.
* `paired_permutation_test` -- the honest way to compare two systems scored on
  *the same* queries. Pairing removes per-query difficulty, which is the
  dominant variance component; an unpaired test on the same data is both wrong
  and much less sensitive.

Deterministic: every function takes a seed, so a reported interval is
reproducible rather than "whatever the run happened to draw".
"""

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


@dataclass(frozen=True)
class Interval:
    mean: float
    lo: float
    hi: float
    n: int

    def as_dict(self) -> dict[str, float | int]:
        return {"mean": self.mean, "ci_lo": self.lo, "ci_hi": self.hi, "n": self.n}

    def __str__(self) -> str:
        return f"{self.mean:.4f} [{self.lo:.4f}, {self.hi:.4f}] (n={self.n})"


@dataclass(frozen=True)
class Comparison:
    delta: float
    ci_lo: float
    ci_hi: float
    p_value: float
    n: int

    @property
    def significant(self) -> bool:
        """Two-sided at alpha=0.05."""
        return self.p_value < 0.05

    def as_dict(self) -> dict[str, float | int | bool]:
        return {
            "delta": self.delta,
            "ci_lo": self.ci_lo,
            "ci_hi": self.ci_hi,
            "p_value": self.p_value,
            "n": self.n,
            "significant": self.significant,
        }


def bootstrap_ci(
    values: Sequence[float],
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 20260831,
) -> Interval:
    """Percentile bootstrap CI for the mean of per-query scores."""
    n = len(values)
    if n == 0:
        return Interval(0.0, 0.0, 0.0, 0)
    if n == 1:
        v = float(values[0])
        return Interval(v, v, v, 1)
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(_mean(sample))
    means.sort()
    lo_idx = int((alpha / 2) * n_boot)
    hi_idx = min(n_boot - 1, int((1 - alpha / 2) * n_boot))
    return Interval(_mean(values), means[lo_idx], means[hi_idx], n)


def bootstrap_statistic_ci[T](
    items: Sequence[T],
    statistic: Callable[[Sequence[T]], float],
    strata: Sequence[str] | None = None,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 20260831,
) -> Interval:
    """Percentile bootstrap CI for an arbitrary statistic of a sample.

    `bootstrap_ci` covers the common case where the statistic is the mean of
    per-query scores. Agreement statistics are not means of anything: Cohen's
    kappa, TPR and TNR are all ratios computed from a contingency table over the
    *whole* sample, so the interval has to come from recomputing the statistic on
    each resample rather than from resampling scalars.

    `strata` (one label per item) makes this a **stratified** bootstrap:
    resampling happens within each stratum, preserving that stratum's sample
    size. That is the bootstrap that matches a stratified sampling design -- an
    unstratified resample would let the realised stratum sizes drift, which
    changes the estimand when items carry design weights.

    `mean` on the returned Interval is the statistic on the observed sample (the
    point estimate), not the mean of the bootstrap replicates.
    """
    n = len(items)
    if n == 0:
        return Interval(0.0, 0.0, 0.0, 0)
    point = float(statistic(items))
    if n == 1:
        return Interval(point, point, point, 1)
    if strata is not None and len(strata) != n:
        raise ValueError(f"strata must be one label per item, got {len(strata)} for {n}")

    # index pools to resample from: one pool overall, or one per stratum
    if strata is None:
        pools = [list(range(n))]
    else:
        by_label: dict[str, list[int]] = {}
        for idx, label in enumerate(strata):
            by_label.setdefault(label, []).append(idx)
        pools = list(by_label.values())

    rng = random.Random(seed)
    replicates: list[float] = []
    for _ in range(n_boot):
        drawn: list[T] = []
        for pool in pools:
            size = len(pool)
            drawn.extend(items[pool[rng.randrange(size)]] for _ in range(size))
        replicates.append(float(statistic(drawn)))
    replicates.sort()
    lo_idx = int((alpha / 2) * n_boot)
    hi_idx = min(n_boot - 1, int((1 - alpha / 2) * n_boot))
    return Interval(point, replicates[lo_idx], replicates[hi_idx], n)


def paired_permutation_test(
    a: Sequence[float],
    b: Sequence[float],
    n_perm: int = 10000,
    seed: int = 20260831,
) -> Comparison:
    """Test whether mean(a) - mean(b) differs from zero, pairing by query.

    Under the null the two systems are exchangeable *within a query*, so each
    permutation flips the sign of a random subset of per-query differences. The
    p-value is the share of permutations whose |mean difference| is at least the
    observed one. The CI comes from a paired bootstrap over the same differences.

    Raises ValueError if the two score vectors are not the same length -- an
    unpaired comparison here would be a silent methodology error.
    """
    if len(a) != len(b):
        raise ValueError(f"paired test needs equal-length vectors, got {len(a)} and {len(b)}")
    n = len(a)
    if n == 0:
        return Comparison(0.0, 0.0, 0.0, 1.0, 0)

    diffs = [float(x) - float(y) for x, y in zip(a, b, strict=True)]
    observed = _mean(diffs)

    rng = random.Random(seed)
    at_least = 0
    for _ in range(n_perm):
        flipped = _mean([d if rng.random() < 0.5 else -d for d in diffs])
        if abs(flipped) >= abs(observed) - 1e-15:
            at_least += 1
    # +1/+1 smoothing: never report p == 0 from a finite permutation count
    p_value = (at_least + 1) / (n_perm + 1)

    boot = bootstrap_ci(diffs, seed=seed)
    return Comparison(observed, boot.lo, boot.hi, p_value, n)
