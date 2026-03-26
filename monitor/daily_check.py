"""
Main daily routine. Designed to run via GitHub Actions or cron.

Flow:
1. Download latest SPY data (last 500 days)
2. Compute indicators
3. Compute E2 signal with confirmation
4. Compare to previous state (from signal_log.csv)
5. If allocation changed: send alert + log trade action needed
6. If no change: log status silently
7. Update signal_log.csv
8. Generate status report + dashboard data
"""

import os
import sys
import json
import logging
from pathlib import Path

import yaml
import numpy as np
import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data import download_prices
from src.signals import compute_e2_signal
from src.alerts import send_alert

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SIGNAL_LOG = PROJECT_ROOT / "data" / "signal_log.csv"
STATUS_JSON = PROJECT_ROOT / "data" / "status.json"
DASHBOARD_JSON = PROJECT_ROOT / "docs" / "data.json"


def load_config() -> dict:
    config_path = PROJECT_ROOT / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_previous_alloc() -> float | None:
    """Read the last confirmed allocation from signal_log.csv."""
    if not SIGNAL_LOG.exists():
        return None
    try:
        log = pd.read_csv(SIGNAL_LOG)
        if log.empty:
            return None
        return float(log["confirmed_alloc"].iloc[-1])
    except Exception:
        return None


def append_signal_log(result: dict, prev_alloc: float | None) -> None:
    """Append today's signal to signal_log.csv."""
    SIGNAL_LOG.parent.mkdir(parents=True, exist_ok=True)

    action = "HOLD"
    if prev_alloc is not None and result["confirmed_alloc"] != prev_alloc:
        if result["confirmed_alloc"] > prev_alloc:
            action = "INCREASE_EQUITY"
        else:
            action = "DECREASE_EQUITY"
    elif prev_alloc is None:
        action = "INIT"

    signals = result["full_signals"].iloc[-1]
    row = {
        "date": result["date"].strftime("%Y-%m-%d") if hasattr(result["date"], "strftime") else str(result["date"]),
        "spy_close": round(result["spy_close"], 2),
        "ema200": round(float(signals["ema200"]), 2),
        "adx": round(float(signals["adx"]), 1),
        "plus_di": round(float(signals["plus_di"]), 1),
        "minus_di": round(float(signals["minus_di"]), 1),
        "roc126": round(float(signals["roc126"]) * 100, 2),
        "score_ema": int(signals["score_ema"]),
        "score_adx": int(signals["score_adx"]),
        "score_roc": int(signals["score_roc"]),
        "raw_score": result["score"],
        "confirmed_alloc": result["confirmed_alloc"],
        "prev_alloc": prev_alloc if prev_alloc is not None else "",
        "action": action,
    }

    write_header = not SIGNAL_LOG.exists() or SIGNAL_LOG.stat().st_size == 0
    df = pd.DataFrame([row])
    df.to_csv(SIGNAL_LOG, mode="a", header=write_header, index=False)
    logger.info(f"Signal log updated: {action}")
    return action


def build_recent_history(result: dict, df: pd.DataFrame, n: int = 90) -> list[dict]:
    """Build recent history for dashboard."""
    signals = result["full_signals"]
    confirmation = result["full_confirmation"]

    history = []
    start = max(0, len(signals) - n)
    for i in range(start, len(signals)):
        row = signals.iloc[i]
        conf = confirmation.iloc[i]
        date = signals.index[i]
        history.append({
            "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date),
            "spy_close": round(float(df["close"].iloc[i]), 2),
            "ema200": round(float(row["ema200"]), 2),
            "adx": round(float(row["adx"]), 1),
            "plus_di": round(float(row["plus_di"]), 1),
            "minus_di": round(float(row["minus_di"]), 1),
            "roc126": round(float(row["roc126"]) * 100, 2) if not np.isnan(row["roc126"]) else None,
            "raw_score": int(row["raw_score"]) if not np.isnan(row["raw_score"]) else None,
            "confirmed_alloc": float(conf["confirmed_alloc"]) if not np.isnan(conf["confirmed_alloc"]) else None,
        })
    return history


def compute_watch_items(result: dict, config: dict) -> list[dict]:
    """Compute what-to-watch items based on current signal state."""
    items = []
    sigs = result["sub_signals"]
    signal_config = config["signal"]

    # EMA200
    spy_close = result["spy_close"]
    ema_val = float(result["full_signals"].iloc[-1]["ema200"])
    ema_pct = (spy_close / ema_val - 1) * 100
    if sigs["ema200"]["value"]:
        items.append({
            "icon": "above",
            "text": f"SPY is {ema_pct:.1f}% above EMA200 — buffer of ${spy_close - ema_val:.2f}",
        })
    else:
        items.append({
            "icon": "below",
            "text": f"SPY is {abs(ema_pct):.1f}% below EMA200 — needs to cross above for +1 point",
        })

    # ADX
    latest = result["full_signals"].iloc[-1]
    adx_val = float(latest["adx"])
    threshold = signal_config["adx_threshold"]
    plus_di = float(latest["plus_di"])
    minus_di = float(latest["minus_di"])
    if adx_val < threshold:
        items.append({
            "icon": "below",
            "text": f"ADX at {adx_val:.1f} — needs {threshold - adx_val:.1f} more to cross {threshold} threshold",
        })
    else:
        di_dir = "+DI > -DI" if plus_di > minus_di else "+DI < -DI"
        items.append({
            "icon": "above" if plus_di > minus_di else "warning",
            "text": f"ADX at {adx_val:.1f} (above {threshold}), but {di_dir}",
        })

    # ROC
    roc_val = float(latest["roc126"]) * 100
    if roc_val > 0:
        items.append({"icon": "above", "text": f"6-month momentum is positive ({roc_val:+.1f}%)"})
    else:
        items.append({"icon": "below", "text": f"6-month momentum is negative ({roc_val:.1f}%) — watch for turn positive"})

    return items


def compute_days_at_confirmed(confirmation_df: pd.DataFrame) -> int:
    """Count how many consecutive days the signal has been at the current confirmed level."""
    confirmed = confirmation_df["confirmed_alloc"].dropna()
    if confirmed.empty:
        return 0
    current = confirmed.iloc[-1]
    count = 0
    for i in range(len(confirmed) - 1, -1, -1):
        if confirmed.iloc[i] == current:
            count += 1
        else:
            break
    return count


def write_status(result: dict, config: dict, action: str, days_at_confirmed: int) -> None:
    """Write status.json and docs/data.json for dashboard."""
    portfolio_config = config["portfolio"]
    alloc = result["confirmed_alloc"]

    # DCA split
    deposit = config["trading"]["monthly_deposit"]
    tickers = portfolio_config["tickers"]
    n_stocks = len(tickers)
    eq_total = deposit * alloc
    per_stock = eq_total / n_stocks if n_stocks else 0
    sgov_total = deposit - eq_total

    status = {
        "date": result["date"].strftime("%Y-%m-%d") if hasattr(result["date"], "strftime") else str(result["date"]),
        "signal": {
            "confirmed_allocation": alloc,
            "allocation_label": f"{int(alloc * 100)}% Equities / {int((1 - alloc) * 100)}% SGOV",
            "raw_score": result["score"],
            "confirmed_score": result["confirmed_score"],
            "sub_signals": result["sub_signals"],
            "days_at_confirmed": days_at_confirmed,
            "days_at_pending": result["days_at_pending"],
            "pending_change": result["pending_change"],
        },
        "portfolio": {
            "tickers": tickers,
            "cash_etf": portfolio_config["cash_etf"],
            "target_alloc": {
                "equities": alloc,
                "sgov": round(1.0 - alloc, 2),
            },
        },
        "dca": {
            "monthly_deposit": deposit,
            "per_stock": round(per_stock, 2),
            "sgov": round(sgov_total, 2),
        },
        "watch": compute_watch_items(result, config),
        "action_required": action if action not in ("HOLD", "INIT") else "NONE",
    }

    # Write data/status.json
    STATUS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_JSON, "w") as f:
        json.dump(status, f, indent=2, default=str)

    # Write docs/data.json (includes recent history for dashboard)
    dashboard_data = {**status}
    dashboard_data["history"] = result.get("_history", [])

    DASHBOARD_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(DASHBOARD_JSON, "w") as f:
        json.dump(dashboard_data, f, indent=2, default=str)

    logger.info(f"Status + dashboard data written")


def format_alert_message(result: dict, prev_alloc: float, config: dict) -> str:
    """Format a Telegram/email alert message."""
    alloc_pct = int(result["confirmed_alloc"] * 100)
    prev_pct = int(prev_alloc * 100)
    direction = "UP" if result["confirmed_alloc"] > prev_alloc else "DOWN"

    tickers = config["portfolio"]["tickers"]
    deposit = config["trading"]["monthly_deposit"]
    eq_total = deposit * result["confirmed_alloc"]
    per_stock = eq_total / len(tickers) if tickers else 0
    sgov_total = deposit - eq_total

    lines = [
        f"SP500 Strategy Alert",
        f"",
        f"Allocation changed: {prev_pct}% -> {alloc_pct}% equities ({direction})",
        f"",
        f"Raw score: {result['score']}/3",
        f"Confirmed score: {result['confirmed_score']}/3",
        f"",
        f"Sub-signals:",
    ]
    for name, sig in result["sub_signals"].items():
        check = "[+]" if sig["value"] else "[-]"
        lines.append(f"  {check} {name}: {sig['detail']}")

    lines.append(f"")
    lines.append(f"Action: Rebalance to {alloc_pct}% equities / {100 - alloc_pct}% SGOV")
    lines.append(f"")
    lines.append(f"Monthly DCA ${deposit:,.0f}:")
    if alloc_pct == 0:
        lines.append(f"  ${deposit:,.0f} -> SGOV")
    else:
        for t in tickers:
            lines.append(f"  {t}: ${per_stock:,.0f}")
        lines.append(f"  SGOV: ${sgov_total:,.0f}")

    return "\n".join(lines)


def main():
    config = load_config()
    signal_ticker = config["portfolio"]["signal_ticker"]
    lookback = config["data"]["lookback_days"]
    cache_dir = config["data"].get("cache_dir")

    logger.info(f"Downloading {signal_ticker} data (last {lookback} days)...")
    df = download_prices(signal_ticker, lookback_days=lookback, cache_dir=cache_dir)
    logger.info(f"Got {len(df)} trading days from {df.index[0]} to {df.index[-1]}")

    logger.info("Computing E2 signal...")
    result = compute_e2_signal(df, config["signal"])

    # Build recent history and days at confirmed level
    result["_history"] = build_recent_history(result, df, n=30)
    days_at_confirmed = compute_days_at_confirmed(result["full_confirmation"])

    prev_alloc = get_previous_alloc()
    alloc_changed = prev_alloc is not None and result["confirmed_alloc"] != prev_alloc

    action = "HOLD"
    if alloc_changed:
        action = "INCREASE_EQUITY" if result["confirmed_alloc"] > prev_alloc else "DECREASE_EQUITY"
    elif prev_alloc is None:
        action = "INIT"

    # Log signal
    append_signal_log(result, prev_alloc)
    write_status(result, config, action, days_at_confirmed)

    # Alert on allocation change
    if alloc_changed and config["alerts"]["enabled"]:
        msg = format_alert_message(result, prev_alloc, config)
        logger.info(f"Allocation changed! Sending alert...")
        send_alert(msg, config["alerts"])
    else:
        logger.info(f"No allocation change. Score={result['score']}, Alloc={result['confirmed_alloc']}")

    # Print summary
    alloc_pct = int(result["confirmed_alloc"] * 100)
    print(f"\n{'='*60}")
    print(f"  E2 COMPOSITE SIGNAL — {result['date']}")
    print(f"{'='*60}")
    print(f"  SPY Close:  ${result['spy_close']:.2f}")
    print(f"  Raw Score:  {result['score']}/3")
    print(f"  Confirmed:  {alloc_pct}% equities / {100 - alloc_pct}% SGOV")
    print(f"  Status:     {action} (confirmed for {days_at_confirmed} days)")
    print(f"{'─'*60}")
    for name, sig in result["sub_signals"].items():
        mark = "+" if sig["value"] else "-"
        print(f"  [{mark}] {sig['detail']}")
    if result["pending_change"]:
        pc = result["pending_change"]
        pending_alloc = int(pc["pending_alloc"] * 100)
        print(f"{'─'*60}")
        print(f"  PENDING: {pending_alloc}% equities ({pc['days_counted']}/{config['signal']['confirmation_days']} days)")
        print(f"  {pc['days_remaining']} day(s) remaining for confirmation")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
