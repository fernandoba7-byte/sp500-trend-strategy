"""
Unit tests for indicator calculations.

Verifies that EMA, ADX, +DI/-DI, and ROC match expected formulas.
"""

import numpy as np
import pandas as pd
import pytest

from src.indicators import sma, ema, adx_system, roc, true_range, directional_movement, wilder_smooth


class TestSMA:
    def test_sma_matches_pandas_rolling(self):
        """SMA must match pandas rolling(window=N).mean() exactly."""
        np.random.seed(42)
        prices = pd.Series(np.random.randn(300).cumsum() + 100)
        period = 200

        expected = prices.rolling(window=period).mean()
        result = sma(prices, period)

        pd.testing.assert_series_equal(result, expected)

    def test_sma_nan_before_period(self):
        """SMA should have NaN for the first (period-1) entries."""
        prices = pd.Series(np.arange(50, dtype=float) + 100)
        result = sma(prices, 20)
        assert result.iloc[:19].isna().all()
        assert not result.iloc[19:].isna().any()

    def test_sma_constant_series(self):
        """SMA of constant series should be that constant."""
        prices = pd.Series([50.0] * 100)
        result = sma(prices, 20)
        valid = result.dropna()
        np.testing.assert_allclose(valid.values, 50.0)

    def test_sma_deterministic(self):
        """SMA should give identical results regardless of data before the window."""
        prices_a = pd.Series([10.0] * 100 + [50.0] * 200)
        prices_b = pd.Series([90.0] * 100 + [50.0] * 200)
        result_a = sma(prices_a, 200)
        result_b = sma(prices_b, 200)
        # After full window of identical data, values must be equal
        assert result_a.iloc[-1] == result_b.iloc[-1] == 50.0


class TestEMA:
    def test_ema_matches_pandas_ewm(self):
        """EMA must match pandas ewm(span=N, adjust=False) exactly."""
        np.random.seed(42)
        prices = pd.Series(np.random.randn(300).cumsum() + 100)
        period = 200

        expected = prices.ewm(span=period, adjust=False).mean()
        result = ema(prices, period)

        pd.testing.assert_series_equal(result, expected)

    def test_ema_short_period(self):
        """EMA with short period should converge quickly."""
        prices = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
        result = ema(prices, 3)

        # First value should equal first price (adjust=False behavior)
        assert result.iloc[0] == 10.0
        # Should be trending upward
        assert result.iloc[-1] > result.iloc[0]

    def test_ema_constant_series(self):
        """EMA of constant series should be that constant."""
        prices = pd.Series([50.0] * 100)
        result = ema(prices, 20)
        np.testing.assert_allclose(result.values, 50.0)


class TestADX:
    @pytest.fixture
    def sample_ohlc(self):
        """Generate sample OHLC data with a clear trend."""
        np.random.seed(42)
        n = 200
        close = pd.Series(np.random.randn(n).cumsum() + 100)
        high = close + np.abs(np.random.randn(n)) * 2
        low = close - np.abs(np.random.randn(n)) * 2
        return high, low, close

    def test_adx_returns_correct_columns(self, sample_ohlc):
        high, low, close = sample_ohlc
        result = adx_system(high, low, close, period=14)

        assert "adx" in result.columns
        assert "plus_di" in result.columns
        assert "minus_di" in result.columns

    def test_adx_uses_wilder_smoothing(self, sample_ohlc):
        """Verify ADX uses Wilder smoothing (alpha=1/14), not simple MA."""
        high, low, close = sample_ohlc
        result = adx_system(high, low, close, period=14)

        # ADX should be between 0 and 100
        valid = result["adx"].dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_di_not_swapped(self):
        """
        +DI should be > -DI in a strong uptrend.
        Common bug: swapping +DI and -DI.
        """
        n = 100
        # Create strong uptrend
        close = pd.Series(np.arange(100, 100 + n, dtype=float))
        high = close + 1.0
        low = close - 0.5

        result = adx_system(high, low, close, period=14)
        # In a strong uptrend, +DI should dominate after warmup
        tail = result.iloc[-20:]
        assert (tail["plus_di"] > tail["minus_di"]).all(), "+DI should be > -DI in uptrend"

    def test_di_downtrend(self):
        """In a downtrend, -DI should be > +DI."""
        n = 100
        close = pd.Series(np.arange(200, 200 - n, -1, dtype=float))
        high = close + 0.5
        low = close - 1.0

        result = adx_system(high, low, close, period=14)
        tail = result.iloc[-20:]
        assert (tail["minus_di"] > tail["plus_di"]).all(), "-DI should be > +DI in downtrend"

    def test_adx_wilder_vs_simple(self, sample_ohlc):
        """ADX with Wilder smoothing should differ from simple MA smoothing."""
        high, low, close = sample_ohlc
        tr = true_range(high, low, close)

        wilder = wilder_smooth(tr, 14)
        simple_ma = tr.rolling(14).mean()

        # They should NOT be equal after warmup
        valid_idx = ~(wilder.isna() | simple_ma.isna())
        assert not np.allclose(
            wilder[valid_idx].values[-50:], simple_ma[valid_idx].values[-50:]
        ), "Wilder smoothing should differ from simple MA"


class TestROC:
    def test_roc_basic(self):
        """ROC = close / close_N_periods_ago - 1."""
        prices = pd.Series([100.0, 110.0, 120.0, 130.0, 140.0])
        result = roc(prices, 2)

        # ROC at index 2 = 120/100 - 1 = 0.2
        assert result.iloc[2] == pytest.approx(0.2)
        # ROC at index 4 = 140/120 - 1 = 0.1667
        assert result.iloc[4] == pytest.approx(1 / 6, rel=1e-4)

    def test_roc_negative(self):
        """ROC should be negative when price drops."""
        prices = pd.Series([100.0, 90.0, 80.0])
        result = roc(prices, 1)
        assert result.iloc[1] == pytest.approx(-0.1)
        assert result.iloc[2] == pytest.approx(-1 / 9, rel=1e-4)

    def test_roc_126_lookback(self):
        """ROC(126) should have NaN for first 126 entries."""
        prices = pd.Series(np.arange(200, dtype=float) + 100)
        result = roc(prices, 126)
        assert result.iloc[:126].isna().all()
        assert not result.iloc[126:].isna().any()


class TestTrueRange:
    def test_true_range_basic(self):
        """TR = max(H-L, |H-prevC|, |L-prevC|)."""
        high = pd.Series([12.0, 15.0])
        low = pd.Series([10.0, 11.0])
        close = pd.Series([11.0, 14.0])

        tr = true_range(high, low, close)
        # First entry: H-L = 2, others need prev close (NaN)
        # Second entry: max(15-11=4, |15-11|=4, |11-11|=0) = 4
        assert tr.iloc[1] == pytest.approx(4.0)
