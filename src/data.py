"""
Download and cache price data using yfinance.
"""

import os
from pathlib import Path

import pandas as pd
import yfinance as yf


def download_prices(
    ticker: str, lookback_days: int = 300, cache_dir: str | None = None
) -> pd.DataFrame:
    """
    Download OHLC price data for a ticker.

    Args:
        ticker: Stock/ETF ticker symbol (e.g. 'SPY').
        lookback_days: Number of calendar days of history to fetch.
        cache_dir: Optional directory to cache downloaded data.

    Returns:
        DataFrame with columns [open, high, low, close, volume] indexed by date.
    """
    end = pd.Timestamp.now() + pd.Timedelta(days=1)  # yfinance end is exclusive
    start = end - pd.Timedelta(days=lookback_days)

    data = yf.download(ticker, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), progress=False)

    if data.empty:
        raise ValueError(f"No data returned for {ticker}")

    # Flatten multi-level columns if present (yfinance >= 0.2.30)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # Normalize column names to lowercase
    data.columns = [c.lower() for c in data.columns]

    # Ensure we have the required columns
    required = ["open", "high", "low", "close", "volume"]
    for col in required:
        if col not in data.columns:
            raise ValueError(f"Missing column '{col}' in downloaded data for {ticker}")

    data = data[required]
    data.index.name = "date"

    # Cache if requested
    if cache_dir:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"{ticker}.csv")
        data.to_csv(cache_path)

    return data
