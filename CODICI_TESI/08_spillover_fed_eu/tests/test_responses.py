"""Test responses (Stadio 1): Δy^B (bp), r^ES (log-return), Δsp (bp)."""
import math
import numpy as np
import pytest

import responses as rs


def test_yield_change_bp_uses_percentage_points_times_100():
    # convenzione FRED-style: yield in %, variazione in p.b. = (post-pre)*100
    assert rs.yield_change_bp(pre=2.50, post=2.55) == pytest.approx(5.0)
    assert rs.yield_change_bp(pre=2.50, post=2.40) == pytest.approx(-10.0)


def test_log_return_matches_natural_log():
    assert rs.log_return(pre=100.0, post=101.0) == pytest.approx(math.log(101 / 100))


def test_log_return_nan_on_nonpositive_price():
    assert math.isnan(rs.log_return(pre=0.0, post=100.0))
    assert math.isnan(rs.log_return(pre=-1.0, post=100.0))
    assert math.isnan(rs.log_return(pre=100.0, post=0.0))


def test_spread_change_bp_is_difference_of_yield_changes():
    # Δsp = Δy_BTP − Δy_Bund, in p.b.
    assert rs.spread_change_bp(y_btp_pre=3.0, y_btp_post=3.2,
                                y_bund_pre=2.5, y_bund_post=2.6) == pytest.approx(10.0)


def test_compute_eu_responses_returns_named_dict_per_event():
    # input minimo per evento j: close pre e close post per ciascun asset
    pre_post = {
        "bund_yield_pct": (2.50, 2.55),       # +5 bp
        "estoxx_price": (4000.0, 3960.0),     # log(3960/4000)
        "btp_yield_pct": (3.00, 3.20),
        # spread = BTP - Bund
    }
    out = rs.compute_eu_responses_single(pre_post)
    assert out["dy_bund_bp"] == pytest.approx(5.0)
    assert out["r_estoxx"] == pytest.approx(math.log(3960 / 4000))
    # Δsp = (post_btp - pre_btp)*100 - (post_bund - pre_bund)*100 = 20 - 5 = 15
    assert out["dsp_bp"] == pytest.approx(15.0)
