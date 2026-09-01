import random

import pytest

from opsverse_evals.stats import bootstrap_ci, paired_permutation_test


def test_bootstrap_ci_brackets_the_mean():
    values = [0.0, 1.0] * 50
    ci = bootstrap_ci(values)
    assert ci.n == 100
    assert ci.mean == pytest.approx(0.5)
    assert ci.lo < ci.mean < ci.hi
    # a 50/50 Bernoulli at n=100 has a CI roughly +/-0.10; anything much tighter
    # would mean the resampling is not actually resampling
    assert 0.05 < (ci.hi - ci.lo) < 0.30


def test_bootstrap_ci_degenerate_inputs():
    assert bootstrap_ci([]).as_dict() == {"mean": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "n": 0}
    one = bootstrap_ci([0.7])
    assert (one.mean, one.lo, one.hi, one.n) == (0.7, 0.7, 0.7, 1)
    # zero variance -> zero-width interval, not a crash
    flat = bootstrap_ci([0.4] * 20)
    assert flat.lo == flat.hi == pytest.approx(0.4)


def test_bootstrap_ci_is_deterministic():
    values = [random.Random(7).random() for _ in range(50)]
    assert bootstrap_ci(values, seed=99).as_dict() == bootstrap_ci(values, seed=99).as_dict()


def test_paired_permutation_identical_systems_not_significant():
    rng = random.Random(1)
    a = [rng.random() for _ in range(80)]
    result = paired_permutation_test(a, list(a))
    assert result.delta == pytest.approx(0.0)
    assert not result.significant


def test_paired_permutation_detects_a_real_difference():
    rng = random.Random(2)
    base = [rng.random() for _ in range(80)]
    better = [min(1.0, x + 0.25) for x in base]
    result = paired_permutation_test(better, base)
    assert result.delta > 0
    assert result.significant
    # the CI for a strictly positive shift must exclude zero
    assert result.ci_lo > 0


def test_paired_permutation_p_value_is_never_zero():
    """+1/+1 smoothing: a finite permutation count cannot prove p == 0."""
    base = [0.0] * 40
    better = [1.0] * 40
    result = paired_permutation_test(better, base, n_perm=100)
    assert result.p_value > 0
    assert result.p_value == pytest.approx(1 / 101)


def test_paired_permutation_requires_equal_lengths():
    # an unpaired comparison here would be a silent methodology error
    with pytest.raises(ValueError, match="equal-length"):
        paired_permutation_test([1.0, 2.0, 3.0], [1.0, 2.0])


def test_paired_permutation_empty():
    result = paired_permutation_test([], [])
    assert result.n == 0
    assert result.p_value == 1.0
    assert not result.significant
