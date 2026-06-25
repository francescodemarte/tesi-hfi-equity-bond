"""Test windows: 3 finestre disgiunte (regime, aspettativa, evento)."""
import numpy as np
import pandas as pd
import pytest

import config
import windows as W


def test_three_windows_disjoint():
    cal = pd.bdate_range("2018-01-01", "2022-12-31")
    e = list(cal).index(pd.Timestamp("2022-06-10"))
    r, p, ev = W.three_windows(cal, e)
    assert set(r).isdisjoint(set(p))
    assert set(r).isdisjoint({ev})
    assert set(p).isdisjoint({ev})


def test_window_endpoints_match_spec():
    cal = pd.bdate_range("2018-01-01", "2022-12-31")
    e = 300
    r, p, ev = W.three_windows(cal, e)
    # spec: regime finisce a t-4
    assert max(r) == e - config.REGIME_END_OFFSET_DAYS
    # spec: aspettativa t-3..t-1
    assert p == [e - 3, e - 2, e - 1]
    # evento è e
    assert ev == e
    # regime ha lunghezza 63 sedute
    assert len(r) == config.REGIME_WINDOW_DAYS


def test_three_windows_refuses_when_event_too_early():
    cal = pd.bdate_range("2018-01-01", "2022-12-31")
    with pytest.raises(ValueError):
        W.three_windows(cal, event_idx=10)


def test_regime_sign_from_window():
    rng = np.random.default_rng(0)
    base = rng.standard_normal(63)
    r_eq = base + 0.05 * rng.standard_normal(63)
    r_bo = base + 0.05 * rng.standard_normal(63)        # corr +
    assert W.regime_sign(r_eq, r_bo) == "pos"
    r_bo_neg = -base + 0.05 * rng.standard_normal(63)   # corr -
    assert W.regime_sign(r_eq, r_bo_neg) == "neg"


def test_assert_no_lookahead_helper():
    W.assert_no_lookahead(used_indices=[10, 20, 50], event_idx=51)
    with pytest.raises(AssertionError):
        W.assert_no_lookahead(used_indices=[10, 51], event_idx=51)
    with pytest.raises(AssertionError):
        W.assert_no_lookahead(used_indices=[10, 52], event_idx=51)
