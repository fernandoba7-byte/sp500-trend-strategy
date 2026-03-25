"""
Generate current status report.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATUS_JSON = PROJECT_ROOT / "data" / "status.json"
SIGNAL_LOG = PROJECT_ROOT / "data" / "signal_log.csv"


def print_status():
    """Print current signal status."""
    if not STATUS_JSON.exists():
        print("No status file found. Run daily_check.py first.")
        sys.exit(1)

    with open(STATUS_JSON) as f:
        status = json.load(f)

    sig = status["signal"]
    port = status["portfolio"]

    print(f"Date: {status['date']}")
    print(f"Allocation: {sig['allocation_label']}")
    print(f"Raw Score: {sig['raw_score']}/3 | Confirmed Score: {sig['confirmed_score']}/3")
    print()
    print("Sub-signals:")
    for name, s in sig["sub_signals"].items():
        mark = "+" if s["value"] else "-"
        print(f"  [{mark}] {s['detail']}")
    print()
    print(f"Portfolio: {', '.join(port['tickers'])}")
    print(f"Target: {int(port['target_alloc']['equities'] * 100)}% equities / {int(port['target_alloc']['sgov'] * 100)}% SGOV")

    if sig["pending_change"]:
        pc = sig["pending_change"]
        print(f"\nPending change: score {pc['pending_score']} ({pc['days_counted']} days, {pc['days_remaining']} remaining)")

    print(f"\nAction required: {status['action_required']}")


if __name__ == "__main__":
    print_status()
