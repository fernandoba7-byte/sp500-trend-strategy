# Project Spec: sp500-trend-strategy

## Overview

Automated trend-following signal monitor for a concentrated S&P 500 strategy.
Tracks the E2 Composite signal (4-level allocation) applied to a top-5 S&P 500 
stocks portfolio, with automatic daily checks and alerts on signal changes.

## Background & Context

The owner backtested 16 trend-following signals on SPY (2000–2025) using walk-forward 
analysis, then applied the top signals to a "Top 5 S&P 500 by market cap" portfolio.
Monte Carlo simulations (10,000 runs, block bootstrap, data from 1970–2025) confirmed 
that E2 Composite dominates both unfiltered buy-and-hold and simpler signals like SMA200.

Key Monte Carlo results (20-year, top-5 scaled):
- E2: CAGR median 23.3%, Max DD median -16.0%, P(DD > -40%) = 0.0%
- No filter: CAGR median 22.1%, Max DD median -47.6%, P(DD > -40%) = 80.5%
- P(E2 better risk-adjusted return than no filter) = 95.8%

## Strategy Rules

### Portfolio Composition
- Hold the top 5 S&P 500 stocks by market cap, equal weight (20% each)
- Rebalance composition annually (first trading day of January)
- When composition changes: sell exits, buy entries (pay tx costs only on rotated fraction)
- Between rebalances: let positions drift (no intra-year rebalancing to 20%)
- Current top 5 (2025): AAPL, NVDA, MSFT, AMZN, GOOG (verify annually)

### Signal: E2 Composite (4-Level Allocation)
Computed daily on SPY (not on individual stocks). Three sub-signals scored 0 or 1:

1. **Trend (EMA200):** Close > EMA(200) → 1 point
2. **Strength (ADX+DI):** ADX(14) > 25 AND +DI(14) > -DI(14) → 1 point  
3. **Momentum (ROC126):** ROC(126 days) > 0 → 1 point

Total score (0–3) maps to allocation:
- 3 points → 100% equities
- 2 points → 66% equities, 34% SGOV
- 1 point  → 33% equities, 67% SGOV
- 0 points → 0% equities, 100% SGOV

**3-Day Confirmation Rule:** A new allocation level only activates after the score 
stays at the new level for 3 consecutive trading days. This prevents whipsaw.

### Cash Management
- Risk-off allocation goes to SGOV (iShares 0-3 Month Treasury Bond ETF)
- Monthly DCA deposits of $3,000 USD split according to current allocation level
- Transaction cost budget: 0.40% per one-way trade (Actinver Mexico: 0.35% + IVA)

## Repository Structure

```
sp500-trend-strategy/
├── README.md                      # Project overview, current signal status badge
├── CLAUDE.md                      # Instructions for Claude Code
├── config.yaml                    # All adjustable parameters
├── requirements.txt               # Python dependencies
│
├── src/
│   ├── __init__.py
│   ├── data.py                    # Download price data (yfinance), caching
│   ├── indicators.py              # EMA, SMA, ADX, +DI/-DI, ROC calculations
│   ├── signals.py                 # E2 composite signal logic + confirmation
│   ├── portfolio.py               # Top-5 composition, allocation, rebalancing
│   └── alerts.py                  # Notification system (email and/or Telegram)
│
├── monitor/
│   ├── daily_check.py             # Main entry point: compute signal, check for changes
│   ├── status.py                  # Generate current status report (markdown/JSON)
│   └── history.py                 # Log signal changes over time (append to CSV)
│
├── data/
│   ├── signal_log.csv             # Historical log: date, score, alloc, sub-signals
│   ├── trades.csv                 # Executed trades log
│   └── top5_history.csv           # Annual top-5 composition changes
│
├── backtest/
│   ├── phase1_spy_signals.py      # Phase 1: 16 signals on SPY
│   ├── phase2_top5.py             # Phase 2: Top-5 portfolio strategies
│   ├── monte_carlo.py             # Phase 2.5: MC simulations
│   └── mc_extended_1970.py        # Extended MC with ^GSPC from 1970
│
├── docs/
│   ├── methodology.md             # Full research methodology
│   ├── signal_rules.md            # E2 rules explained simply
│   └── playbook.md                # Step-by-step trading playbook
│
├── .github/
│   └── workflows/
│       └── daily_signal.yml       # GitHub Actions: daily cron job
│
└── tests/
    ├── test_indicators.py         # Unit tests for indicator calculations
    ├── test_signals.py            # Unit tests for E2 logic + confirmation
    └── test_portfolio.py          # Unit tests for allocation logic
```

## config.yaml Specification

```yaml
# ── Signal Parameters ────────────────────────────────────────────
signal:
  ema_period: 200
  adx_period: 14
  adx_threshold: 25
  roc_period: 126
  confirmation_days: 3
  
  allocation_map:
    3: 1.00
    2: 0.66
    1: 0.33
    0: 0.00

# ── Portfolio ────────────────────────────────────────────────────
portfolio:
  # Updated annually. Top 5 S&P 500 by market cap.
  tickers:
    - AAPL
    - NVDA
    - MSFT
    - AMZN
    - GOOG
  cash_etf: SGOV
  signal_ticker: SPY  # Signal computed on SPY, not individual stocks
  rebalance_month: 1  # January
  target_weight: 0.20 # Equal weight
  
# ── Trading ──────────────────────────────────────────────────────
trading:
  transaction_cost: 0.004   # 0.40% one-way
  monthly_deposit: 3000     # USD
  broker: Actinver          # Primary
  broker_secondary: GBM     # Secondary (if applicable)

# ── Alerts ───────────────────────────────────────────────────────
alerts:
  enabled: true
  channels:
    - telegram    # Recommended: instant, free
    - email       # Backup
  telegram:
    bot_token: ${TELEGRAM_BOT_TOKEN}     # Set as GitHub secret
    chat_id: ${TELEGRAM_CHAT_ID}         # Set as GitHub secret
  email:
    smtp_server: smtp.gmail.com
    sender: ${EMAIL_SENDER}
    recipient: ${EMAIL_RECIPIENT}
    password: ${EMAIL_PASSWORD}
  
  # Only alert on allocation changes, not daily
  alert_on_change_only: true
  # Also send weekly summary every Sunday
  weekly_summary: true

# ── Data ─────────────────────────────────────────────────────────
data:
  source: yfinance
  lookback_days: 300  # Need 200+ for EMA200 warmup
  cache_dir: data/cache
```

## Key Implementation Details

### src/indicators.py
```python
# All indicators must match the backtest exactly:
# - EMA: pandas ewm(span=N, adjust=False)
# - ADX: Wilder smoothing (alpha=1/period)
# - ROC: simple (close / close_shift_N - 1)
# 
# IMPORTANT: Use the EXACT same formulas as the backtest.
# Any deviation will cause signal drift from tested performance.
```

### src/signals.py
```python
def compute_e2_signal(df: pd.DataFrame, config: dict) -> dict:
    """
    Compute E2 composite signal.
    
    Args:
        df: DataFrame with columns [close, high, low] indexed by date
        config: signal parameters from config.yaml
    
    Returns:
        dict with keys:
            - score: int 0-3 (raw score today)
            - confirmed_alloc: float (allocation after 3-day confirmation)
            - sub_signals: dict with each component's value and score
            - days_at_current_level: int
            - pending_change: None or dict with new level + days remaining
    """
    # Implementation should track state for confirmation logic
    pass
```

### monitor/daily_check.py
```python
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
8. Generate status report (update README badge or status.md)
"""
```

### .github/workflows/daily_signal.yml
```yaml
name: Daily Signal Check
on:
  schedule:
    - cron: '30 21 * * 1-5'  # 4:30 PM ET / 3:30 PM CT (after market close)
  workflow_dispatch:           # Allow manual trigger

jobs:
  check-signal:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python monitor/daily_check.py
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
      - name: Commit signal log
        run: |
          git config user.name "Signal Bot"
          git config user.email "bot@signal"
          git add data/signal_log.csv data/status.json README.md
          git diff --staged --quiet || git commit -m "📊 Signal update $(date +%Y-%m-%d)"
          git push
```

## Status Output Format

### data/signal_log.csv (append daily)
```
date,spy_close,ema200,adx,plus_di,minus_di,roc126,score_ema,score_adx,score_roc,raw_score,confirmed_alloc,prev_alloc,action
2025-03-21,557.59,563.30,22.4,18.1,23.8,-0.02,0,0,0,0,0.33,0.33,HOLD
```

### Status report (README badge or status.json)
```json
{
  "date": "2025-03-21",
  "signal": {
    "confirmed_allocation": 0.33,
    "allocation_label": "33% Equities / 67% SGOV",
    "raw_score": 0,
    "sub_signals": {
      "ema200": {"value": false, "detail": "SPY 557.59 < EMA200 563.30"},
      "adx_di": {"value": false, "detail": "ADX 22.4 < 25 threshold"},
      "roc126": {"value": false, "detail": "ROC126 -2.1% < 0"}
    },
    "days_at_current_level": 15,
    "pending_change": null
  },
  "portfolio": {
    "tickers": ["AAPL", "NVDA", "MSFT", "AMZN", "GOOG"],
    "target_alloc": {"equities": 0.33, "sgov": 0.67}
  },
  "action_required": "NONE"
}
```

## Testing Requirements

### test_signals.py must verify:
1. E2 score calculation matches backtest exactly for known dates
2. 3-day confirmation logic: signal doesn't change on day 1 or 2
3. Edge cases: NaN handling during warmup, weekends/holidays
4. Allocation map: score 0→0%, 1→33%, 2→66%, 3→100%

### test_indicators.py must verify:
1. EMA200 matches pandas ewm output
2. ADX matches Wilder smoothing (not simple MA)
3. +DI/-DI signs are correct (common bug: swapping +DI and -DI)
4. ROC126 handles the 126-day lookback correctly

## Playbook (docs/playbook.md outline)

### When Signal Changes Allocation Level:
1. Bot sends Telegram alert with: new level, old level, action needed
2. Within 1-2 trading days, execute the rebalance in Actinver:
   - If increasing equity allocation: buy more of each top-5 stock proportionally
   - If decreasing: sell proportionally, buy SGOV with proceeds
3. Log the trade in data/trades.csv
4. Confirm execution by replying to the Telegram bot (future feature)

### Monthly DCA Deposit ($3,000 USD):
1. Convert MXN to USD at Actinver
2. Split according to CURRENT allocation level:
   - If 100%: buy equal amounts of each top-5 stock ($600 each)
   - If 66%: $396 each stock + $1,020 SGOV
   - If 33%: $198 each stock + $2,010 SGOV
   - If 0%: $3,000 to SGOV
3. If any position drifted significantly (>5pp from 20%), use deposit to rebalance

### Annual Top-5 Review (January):
1. Check current S&P 500 top 5 by market cap
2. If composition changed: sell exits, buy entries
3. Update config.yaml with new tickers
4. Commit change to repo

## Non-Functional Requirements
- Python 3.11+
- No paid APIs (yfinance is free)
- GitHub Actions free tier (2,000 minutes/month — we use <5 min/day)
- Secrets managed via GitHub Secrets (Telegram token, email creds)
- All data in CSV (no database needed)
- Repo can be private (recommended) or public
