"""
Portfolio composition and allocation logic.
"""


def compute_target_allocation(
    confirmed_alloc: float, tickers: list[str], target_weight: float, cash_etf: str
) -> dict:
    """
    Compute target allocation for each ticker given the confirmed allocation level.

    Args:
        confirmed_alloc: Fraction allocated to equities (0.0, 0.33, 0.66, 1.0).
        tickers: List of equity tickers.
        target_weight: Target weight per equity ticker (e.g. 0.20).
        cash_etf: Cash ETF ticker (e.g. 'SGOV').

    Returns:
        dict mapping ticker -> target weight.
    """
    alloc = {}
    equity_weight = confirmed_alloc * target_weight
    for ticker in tickers:
        alloc[ticker] = round(equity_weight, 4)
    alloc[cash_etf] = round(1.0 - confirmed_alloc, 4)
    return alloc


def compute_dca_split(
    monthly_deposit: float, confirmed_alloc: float, tickers: list[str], cash_etf: str
) -> dict:
    """
    Split a monthly DCA deposit according to current allocation level.

    Args:
        monthly_deposit: Total deposit amount in USD.
        confirmed_alloc: Fraction allocated to equities.
        tickers: List of equity tickers.
        cash_etf: Cash ETF ticker.

    Returns:
        dict mapping ticker -> dollar amount.
    """
    n = len(tickers)
    equity_total = monthly_deposit * confirmed_alloc
    per_stock = equity_total / n if n > 0 else 0
    cash_amount = monthly_deposit - equity_total

    split = {}
    for ticker in tickers:
        split[ticker] = round(per_stock, 2)
    split[cash_etf] = round(cash_amount, 2)
    return split
