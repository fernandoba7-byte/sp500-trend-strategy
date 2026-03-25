"""
View and analyze signal history from signal_log.csv.
"""

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SIGNAL_LOG = PROJECT_ROOT / "data" / "signal_log.csv"


def show_history(n: int = 20):
    """Show the last N entries from signal_log.csv."""
    if not SIGNAL_LOG.exists():
        print("No signal log found. Run daily_check.py first.")
        sys.exit(1)

    df = pd.read_csv(SIGNAL_LOG)
    print(f"Signal history ({len(df)} total entries, showing last {min(n, len(df))}):\n")
    print(df.tail(n).to_string(index=False))

    # Summary stats
    changes = df[df["action"].isin(["INCREASE_EQUITY", "DECREASE_EQUITY"])]
    print(f"\nTotal allocation changes: {len(changes)}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    show_history(n)
