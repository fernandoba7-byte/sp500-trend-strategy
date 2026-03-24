"""
Main daily routine. Designed to run via GitHub Actions or cron.

Flow:
1. Download latest SPY data (last 300 days)
2. Compute indicators
3. Compute E2 signal with confirmation
4. Compare to previous state (from signal_log.csv)
5. If allocation changed: send alert + log trade action needed
6. If no change: log status silently
7. Update signal_log.csv
8. Generate status report
"""

import os
import sys
import json
import logging
from pathlib import Path

import yaml
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


def write_status(result: dict, config: dict) -> None:
    """Write status.json."""
    portfolio_config = config["portfolio"]

    status = {
        "date": result["date"].strftime("%Y-%m-%d") if hasattr(result["date"], "strftime") else str(result["date"]),
        "signal": {
            "confirmed_allocation": result["confirmed_alloc"],
            "allocation_label": f"{int(result['confirmed_alloc'] * 100)}% Equities / {int((1 - result['confirmed_alloc']) * 100)}% SGOV",
            "raw_score": result["score"],
            "confirmed_score": result["confirmed_score"],
            "sub_signals": result["sub_signals"],
            "days_at_pending": result["days_at_pending"],
            "pending_change": result["pending_change"],
        },
        "portfolio": {
            "tickers": portfolio_config["tickers"],
            "target_alloc": {
                "equities": result["confirmed_alloc"],
                "sgov": round(1.0 - result["confirmed_alloc"], 2),
            },
        },
        "action_required": "REBALANCE" if result.get("_action") not in (None, "HOLD", "INIT") else "NONE",
    }

    STATUS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_JSON, "w") as f:
        json.dump(status, f, indent=2, default=str)
    logger.info(f"Status written to {STATUS_JSON}")


def format_alert_message(result: dict, prev_alloc: float) -> str:
    """Format a Telegram/email alert message."""
    alloc_pct = int(result["confirmed_alloc"] * 100)
    prev_pct = int(prev_alloc * 100)
    direction = "UP" if result["confirmed_alloc"] > prev_alloc else "DOWN"

    lines = [
        f"*SP500 Strategy Alert*",
        f"Allocation changed: {prev_pct}% -> {alloc_pct}% equities ({direction})",
        f"",
        f"Raw score: {result['score']}/3",
        f"Confirmed score: {result['confirmed_score']}/3",
        f"",
        f"Sub-signals:",
    ]
    for name, sig in result["sub_signals"].items():
        check = "+" if sig["value"] else "-"
        lines.append(f"  [{check}] {name}: {sig['detail']}")

    lines.append(f"\nAction: Rebalance to {alloc_pct}% equities / {100 - alloc_pct}% SGOV")
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

    prev_alloc = get_previous_alloc()
    alloc_changed = prev_alloc is not None and result["confirmed_alloc"] != prev_alloc

    action = "HOLD"
    if alloc_changed:
        action = "INCREASE_EQUITY" if result["confirmed_alloc"] > prev_alloc else "DECREASE_EQUITY"
    elif prev_alloc is None:
        action = "INIT"
    result["_action"] = action

    # Log signal
    append_signal_log(result, prev_alloc)
    write_status(result, config)

    # Alert on allocation change
    if alloc_changed and config["alerts"]["enabled"]:
        msg = format_alert_message(result, prev_alloc)
        logger.info(f"Allocation changed! Sending alert...")
        send_alert(msg, config["alerts"])
    else:
        logger.info(f"No allocation change. Score={result['score']}, Alloc={result['confirmed_alloc']}")

    # Print summary
    print(f"\n{'='*50}")
    print(f"Date: {result['date']}")
    print(f"SPY Close: {result['spy_close']:.2f}")
    print(f"Raw Score: {result['score']}/3")
    print(f"Confirmed Allocation: {int(result['confirmed_alloc'] * 100)}% equities")
    print(f"Action: {action}")
    if result["pending_change"]:
        pc = result["pending_change"]
        print(f"Pending: score {pc['pending_score']} ({pc['days_counted']}/{config['signal']['confirmation_days']} days)")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
