"""
E2 Composite signal logic with 3-day confirmation.

The signal is computed on SPY and applied to the top-5 portfolio.
"""

import pandas as pd
import numpy as np

from src.indicators import ema, adx_system, roc


def compute_sub_signals(
    df: pd.DataFrame, config: dict
) -> pd.DataFrame:
    """
    Compute the three E2 sub-signals for the entire DataFrame.

    Args:
        df: DataFrame with columns [close, high, low] indexed by date.
        config: signal parameters from config.yaml['signal'].

    Returns:
        DataFrame with columns:
            ema200, score_ema, adx, plus_di, minus_di, score_adx,
            roc126, score_roc, raw_score
    """
    ema_period = config["ema_period"]
    adx_period = config["adx_period"]
    adx_threshold = config["adx_threshold"]
    roc_period = config["roc_period"]

    result = pd.DataFrame(index=df.index)

    # 1. Trend: Close > EMA(200)
    result["ema200"] = ema(df["close"], ema_period)
    result["score_ema"] = (df["close"] > result["ema200"]).astype(int)

    # 2. Strength: ADX(14) > 25 AND +DI(14) > -DI(14)
    adx_df = adx_system(df["high"], df["low"], df["close"], adx_period)
    result["adx"] = adx_df["adx"]
    result["plus_di"] = adx_df["plus_di"]
    result["minus_di"] = adx_df["minus_di"]
    result["score_adx"] = (
        (result["adx"] > adx_threshold) & (result["plus_di"] > result["minus_di"])
    ).astype(int)

    # 3. Momentum: ROC(126) > 0
    result["roc126"] = roc(df["close"], roc_period)
    result["score_roc"] = (result["roc126"] > 0).astype(int)

    # Raw composite score
    result["raw_score"] = result["score_ema"] + result["score_adx"] + result["score_roc"]

    return result


def apply_confirmation(
    raw_scores: pd.Series,
    allocation_map: dict[int, float],
    confirmation_days: int = 3,
) -> pd.DataFrame:
    """
    Apply 3-day confirmation rule to raw scores.

    The confirmed allocation only changes when the raw score stays at a
    new level for `confirmation_days` consecutive trading days.

    Args:
        raw_scores: Series of raw scores (0-3) indexed by date.
        allocation_map: Mapping from score to allocation fraction.
        confirmation_days: Number of consecutive days required.

    Returns:
        DataFrame with columns:
            confirmed_score, confirmed_alloc, days_at_pending, pending_score
    """
    confirmed_score = np.full(len(raw_scores), np.nan)
    pending_score_arr = np.full(len(raw_scores), np.nan)
    days_at_pending = np.zeros(len(raw_scores), dtype=int)

    current_confirmed = None
    pending = None
    pending_count = 0

    for i, score in enumerate(raw_scores.values):
        if np.isnan(score):
            confirmed_score[i] = np.nan
            continue

        score_int = int(score)

        # Initialize on first valid score
        if current_confirmed is None:
            current_confirmed = score_int
            pending = None
            pending_count = 0
            confirmed_score[i] = current_confirmed
            continue

        if score_int == current_confirmed:
            # Score matches current confirmed — reset any pending change
            pending = None
            pending_count = 0
        elif score_int == pending:
            # Score matches pending — increment counter
            pending_count += 1
        else:
            # New score — start new pending
            pending = score_int
            pending_count = 1

        # Check if pending has been confirmed
        if pending is not None and pending_count >= confirmation_days:
            current_confirmed = pending
            pending = None
            pending_count = 0

        confirmed_score[i] = current_confirmed
        days_at_pending[i] = pending_count
        if pending is not None:
            pending_score_arr[i] = pending

    confirmed_alloc = pd.Series(confirmed_score, index=raw_scores.index).map(
        {k: v for k, v in allocation_map.items()}
    )

    return pd.DataFrame({
        "confirmed_score": pd.Series(confirmed_score, index=raw_scores.index),
        "confirmed_alloc": confirmed_alloc,
        "days_at_pending": pd.Series(days_at_pending, index=raw_scores.index),
        "pending_score": pd.Series(pending_score_arr, index=raw_scores.index),
    })


def compute_e2_signal(df: pd.DataFrame, config: dict) -> dict:
    """
    Compute E2 composite signal for the latest date.

    Args:
        df: DataFrame with columns [close, high, low] indexed by date.
        config: signal parameters from config.yaml['signal'].

    Returns:
        dict with keys:
            - date: latest date
            - spy_close: latest close price
            - score: int 0-3 (raw score today)
            - confirmed_alloc: float (allocation after 3-day confirmation)
            - sub_signals: dict with each component's value and score
            - days_at_pending: int (days at pending new level)
            - pending_change: None or dict with pending score and days remaining
            - full_signals: DataFrame with all computed signals
            - full_confirmation: DataFrame with confirmation data
    """
    signal_config = config if "ema_period" in config else config.get("signal", config)
    allocation_map = signal_config["allocation_map"]
    confirmation_days = signal_config["confirmation_days"]

    # Compute sub-signals
    signals_df = compute_sub_signals(df, signal_config)

    # Apply confirmation
    confirmation_df = apply_confirmation(
        signals_df["raw_score"], allocation_map, confirmation_days
    )

    # Get latest values
    latest = signals_df.iloc[-1]
    latest_conf = confirmation_df.iloc[-1]
    latest_date = df.index[-1]

    pending_change = None
    if not np.isnan(latest_conf["pending_score"]):
        pending_change = {
            "pending_score": int(latest_conf["pending_score"]),
            "pending_alloc": allocation_map[int(latest_conf["pending_score"])],
            "days_counted": int(latest_conf["days_at_pending"]),
            "days_remaining": confirmation_days - int(latest_conf["days_at_pending"]),
        }

    return {
        "date": latest_date,
        "spy_close": float(latest["ema200"]) if np.isnan(df["close"].iloc[-1]) else float(df["close"].iloc[-1]),
        "score": int(latest["raw_score"]),
        "confirmed_alloc": float(latest_conf["confirmed_alloc"]),
        "confirmed_score": int(latest_conf["confirmed_score"]),
        "sub_signals": {
            "ema200": {
                "value": bool(latest["score_ema"]),
                "detail": f"SPY {df['close'].iloc[-1]:.2f} {'>' if latest['score_ema'] else '<'} EMA200 {latest['ema200']:.2f}",
            },
            "adx_di": {
                "value": bool(latest["score_adx"]),
                "detail": f"ADX {latest['adx']:.1f} {'>' if latest['adx'] > signal_config['adx_threshold'] else '<'} {signal_config['adx_threshold']}, +DI {latest['plus_di']:.1f} {'>' if latest['plus_di'] > latest['minus_di'] else '<'} -DI {latest['minus_di']:.1f}",
            },
            "roc126": {
                "value": bool(latest["score_roc"]),
                "detail": f"ROC126 {latest['roc126'] * 100:.1f}% {'>' if latest['score_roc'] else '<'} 0",
            },
        },
        "days_at_pending": int(latest_conf["days_at_pending"]),
        "pending_change": pending_change,
        "full_signals": signals_df,
        "full_confirmation": confirmation_df,
    }
