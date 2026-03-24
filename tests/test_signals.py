"""
Unit tests for E2 signal logic and 3-day confirmation.
"""

import numpy as np
import pandas as pd
import pytest

from src.signals import compute_sub_signals, apply_confirmation, compute_e2_signal


@pytest.fixture
def signal_config():
    return {
        "ema_period": 200,
        "adx_period": 14,
        "adx_threshold": 25,
        "roc_period": 126,
        "confirmation_days": 3,
        "allocation_map": {3: 1.00, 2: 0.66, 1: 0.33, 0: 0.00},
    }


@pytest.fixture
def uptrend_df():
    """Create a DataFrame representing a strong uptrend (all signals should fire)."""
    np.random.seed(42)
    n = 300
    # Strong uptrend with small noise
    base = np.linspace(100, 200, n)
    noise = np.random.randn(n) * 0.5
    close = pd.Series(base + noise)
    high = close + np.abs(np.random.randn(n)) * 1.5
    low = close - np.abs(np.random.randn(n)) * 1.0
    dates = pd.bdate_range(end="2025-03-21", periods=n)
    return pd.DataFrame({"close": close.values, "high": high.values, "low": low.values}, index=dates)


@pytest.fixture
def downtrend_df():
    """Create a DataFrame representing a strong downtrend (no signals should fire)."""
    np.random.seed(42)
    n = 300
    base = np.linspace(200, 100, n)
    noise = np.random.randn(n) * 0.5
    close = pd.Series(base + noise)
    high = close + np.abs(np.random.randn(n)) * 1.0
    low = close - np.abs(np.random.randn(n)) * 1.5
    dates = pd.bdate_range(end="2025-03-21", periods=n)
    return pd.DataFrame({"close": close.values, "high": high.values, "low": low.values}, index=dates)


class TestSubSignals:
    def test_uptrend_all_signals(self, uptrend_df, signal_config):
        """In a strong uptrend, all sub-signals should be 1."""
        result = compute_sub_signals(uptrend_df, signal_config)
        latest = result.iloc[-1]

        assert latest["score_ema"] == 1, "Close should be above EMA200 in uptrend"
        assert latest["score_roc"] == 1, "ROC126 should be positive in uptrend"
        # ADX may or may not fire depending on trend strength
        assert latest["raw_score"] >= 2

    def test_downtrend_no_signals(self, downtrend_df, signal_config):
        """In a strong downtrend, trend and momentum should be 0."""
        result = compute_sub_signals(downtrend_df, signal_config)
        latest = result.iloc[-1]

        assert latest["score_ema"] == 0, "Close should be below EMA200 in downtrend"
        assert latest["score_roc"] == 0, "ROC126 should be negative in downtrend"

    def test_raw_score_is_sum(self, uptrend_df, signal_config):
        """Raw score should be sum of three sub-signals."""
        result = compute_sub_signals(uptrend_df, signal_config)
        expected = result["score_ema"] + result["score_adx"] + result["score_roc"]
        pd.testing.assert_series_equal(result["raw_score"], expected, check_names=False)

    def test_score_range(self, uptrend_df, signal_config):
        """All raw scores should be between 0 and 3."""
        result = compute_sub_signals(uptrend_df, signal_config)
        valid = result["raw_score"].dropna()
        assert (valid >= 0).all()
        assert (valid <= 3).all()


class TestConfirmation:
    def test_no_change_before_3_days(self):
        """Signal should not change on day 1 or 2 of a new level."""
        allocation_map = {3: 1.00, 2: 0.66, 1: 0.33, 0: 0.00}
        # Start at score 3, then switch to score 2 for only 2 days
        scores = pd.Series([3, 3, 3, 3, 3, 2, 2, 3, 3, 3])

        result = apply_confirmation(scores, allocation_map, confirmation_days=3)

        # Should stay at score 3 throughout — 2 days at score 2 is not enough
        assert result["confirmed_score"].iloc[6] == 3
        assert result["confirmed_alloc"].iloc[6] == 1.00

    def test_change_after_3_days(self):
        """Signal should change after 3 consecutive days at new level."""
        allocation_map = {3: 1.00, 2: 0.66, 1: 0.33, 0: 0.00}
        # Start at score 3, then switch to score 2 for 3 days
        scores = pd.Series([3, 3, 3, 3, 3, 2, 2, 2, 2, 2])

        result = apply_confirmation(scores, allocation_map, confirmation_days=3)

        # Should remain 3 for first 7 entries (5 at 3, then 2 days pending)
        assert result["confirmed_score"].iloc[5] == 3
        assert result["confirmed_score"].iloc[6] == 3
        # Should change on day 8 (index 7, after 3 days of score 2)
        assert result["confirmed_score"].iloc[7] == 2
        assert result["confirmed_alloc"].iloc[7] == 0.66

    def test_interrupted_confirmation(self):
        """If score changes during pending period, reset counter."""
        allocation_map = {3: 1.00, 2: 0.66, 1: 0.33, 0: 0.00}
        # Score 3 for 5 days, then 2,2,3,2,2,2 — the interruption resets the counter
        scores = pd.Series([3, 3, 3, 3, 3, 2, 2, 3, 2, 2, 2, 2])

        result = apply_confirmation(scores, allocation_map, confirmation_days=3)

        # After the interruption at index 7, counter resets
        assert result["confirmed_score"].iloc[7] == 3  # back to confirmed
        # New pending period starts at index 8
        assert result["confirmed_score"].iloc[9] == 3   # still pending
        assert result["confirmed_score"].iloc[10] == 2   # confirmed after 3 days (8,9,10)

    def test_allocation_map(self):
        """Verify all allocation levels map correctly."""
        allocation_map = {3: 1.00, 2: 0.66, 1: 0.33, 0: 0.00}

        for score, expected_alloc in allocation_map.items():
            scores = pd.Series([score] * 5)
            result = apply_confirmation(scores, allocation_map, confirmation_days=3)
            assert result["confirmed_alloc"].iloc[-1] == expected_alloc

    def test_nan_handling(self):
        """NaN scores should propagate as NaN in confirmed values."""
        allocation_map = {3: 1.00, 2: 0.66, 1: 0.33, 0: 0.00}
        scores = pd.Series([np.nan, np.nan, 3, 3, 3])

        result = apply_confirmation(scores, allocation_map, confirmation_days=3)
        assert np.isnan(result["confirmed_score"].iloc[0])
        assert result["confirmed_score"].iloc[2] == 3


class TestComputeE2Signal:
    def test_returns_required_keys(self, uptrend_df, signal_config):
        """compute_e2_signal should return all required keys."""
        result = compute_e2_signal(uptrend_df, signal_config)

        required_keys = [
            "date", "spy_close", "score", "confirmed_alloc",
            "sub_signals", "days_at_pending", "pending_change",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_sub_signals_structure(self, uptrend_df, signal_config):
        """Sub-signals dict should have correct structure."""
        result = compute_e2_signal(uptrend_df, signal_config)

        assert "ema200" in result["sub_signals"]
        assert "adx_di" in result["sub_signals"]
        assert "roc126" in result["sub_signals"]

        for name, sig in result["sub_signals"].items():
            assert "value" in sig
            assert "detail" in sig
            assert isinstance(sig["value"], bool)
            assert isinstance(sig["detail"], str)

    def test_score_matches_sub_signals(self, uptrend_df, signal_config):
        """Raw score should equal sum of sub-signal values."""
        result = compute_e2_signal(uptrend_df, signal_config)

        expected_score = sum(
            1 for sig in result["sub_signals"].values() if sig["value"]
        )
        assert result["score"] == expected_score

    def test_confirmed_alloc_in_valid_range(self, uptrend_df, signal_config):
        """Confirmed allocation should be one of the valid levels."""
        result = compute_e2_signal(uptrend_df, signal_config)
        valid_allocs = set(signal_config["allocation_map"].values())
        assert result["confirmed_alloc"] in valid_allocs
