# CLAUDE.md — Instructions for Claude Code

## Project Context

This is a live trading signal monitoring system for a concentrated S&P 500 strategy.
See PROJECT_SPEC.md for the complete specification.

## Quick Summary

- **Strategy:** Buy top 5 S&P 500 stocks by market cap, equal weight
- **Signal:** E2 Composite (0-3 score → 4 allocation levels: 0%, 33%, 66%, 100%)
- **When signal says reduce:** Move proportional allocation to SGOV (short-term treasuries)
- **Runs daily** via GitHub Actions after market close

## Key Technical Requirements

1. **Indicator calculations must be EXACT:** EMA uses pandas `ewm(span=N, adjust=False)`. 
   ADX uses Wilder smoothing (`ewm(alpha=1/14, adjust=False)`). Any deviation from 
   the backtest formulas will cause signal drift.

2. **3-day confirmation is critical:** The allocation level only changes after the raw 
   score stays at the new level for 3 consecutive trading days. Without this, the 
   strategy whipsaws and loses money on transaction costs.

3. **Signal is computed on SPY, applied to top-5 stocks.** Don't compute signals on 
   individual stocks.

4. **Config-driven:** All parameters (thresholds, tickers, costs) come from config.yaml.
   No hardcoded magic numbers in the code.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run daily signal check
python monitor/daily_check.py

# Run tests
pytest tests/ -v

# Check current signal status
python monitor/status.py
```

## Important Files

- `config.yaml` — All adjustable parameters
- `src/signals.py` — Core E2 signal logic (most critical file)
- `monitor/daily_check.py` — Main entry point for daily runs
- `data/signal_log.csv` — Append-only log of daily signals
- `PROJECT_SPEC.md` — Complete project specification

## When Adding Features

- Always add tests first
- Keep signal calculation isolated in `src/signals.py` — don't mix with I/O
- Alert logic goes in `src/alerts.py` — keep it pluggable
- Any new parameter goes in `config.yaml`, never hardcoded
