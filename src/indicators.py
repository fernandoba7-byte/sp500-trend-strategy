"""
Technical indicator calculations for the E2 Composite signal.

All indicators must match the backtest exactly:
- EMA: pandas ewm(span=N, adjust=False)
- ADX: Wilder smoothing (alpha=1/period)
- ROC: simple (close / close_shift_N - 1)
"""

import pandas as pd
import numpy as np


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average using rolling window."""
    return series.rolling(window=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average using pandas ewm(span=N, adjust=False)."""
    return series.ewm(span=period, adjust=False).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True Range: max(H-L, |H-prevC|, |L-prevC|)."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def directional_movement(high: pd.Series, low: pd.Series) -> tuple[pd.Series, pd.Series]:
    """
    Compute raw +DM and -DM.

    +DM = H - prevH if positive and > (prevL - L), else 0
    -DM = prevL - L if positive and > (H - prevH), else 0
    """
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = pd.Series(0.0, index=high.index)
    minus_dm = pd.Series(0.0, index=high.index)

    plus_mask = (up_move > down_move) & (up_move > 0)
    minus_mask = (down_move > up_move) & (down_move > 0)

    plus_dm[plus_mask] = up_move[plus_mask]
    minus_dm[minus_mask] = down_move[minus_mask]

    return plus_dm, minus_dm


def wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """Wilder smoothing: EMA with alpha=1/period (equivalent to span=2*period-1)."""
    return series.ewm(alpha=1.0 / period, adjust=False).mean()


def adx_system(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.DataFrame:
    """
    Compute ADX, +DI, -DI using Wilder smoothing.

    Returns DataFrame with columns: ['adx', 'plus_di', 'minus_di']
    """
    tr = true_range(high, low, close)
    plus_dm, minus_dm = directional_movement(high, low)

    # Wilder-smoothed TR, +DM, -DM
    atr = wilder_smooth(tr, period)
    smooth_plus_dm = wilder_smooth(plus_dm, period)
    smooth_minus_dm = wilder_smooth(minus_dm, period)

    # Directional indicators
    plus_di = 100.0 * smooth_plus_dm / atr
    minus_di = 100.0 * smooth_minus_dm / atr

    # DX and ADX
    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    dx = 100.0 * di_diff / di_sum.replace(0, np.nan)

    adx = wilder_smooth(dx, period)

    return pd.DataFrame({
        "adx": adx,
        "plus_di": plus_di,
        "minus_di": minus_di,
    }, index=high.index)


def roc(series: pd.Series, period: int) -> pd.Series:
    """Rate of Change: (close / close_N_periods_ago) - 1."""
    return series / series.shift(period) - 1.0
