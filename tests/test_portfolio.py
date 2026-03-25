"""
Unit tests for portfolio allocation logic.
"""

import pytest

from src.portfolio import compute_target_allocation, compute_dca_split


TICKERS = ["AAPL", "NVDA", "MSFT", "AMZN", "GOOG"]
CASH_ETF = "SGOV"


class TestTargetAllocation:
    def test_full_equity(self):
        alloc = compute_target_allocation(1.0, TICKERS, 0.20, CASH_ETF)
        for t in TICKERS:
            assert alloc[t] == pytest.approx(0.20)
        assert alloc[CASH_ETF] == pytest.approx(0.0)

    def test_zero_equity(self):
        alloc = compute_target_allocation(0.0, TICKERS, 0.20, CASH_ETF)
        for t in TICKERS:
            assert alloc[t] == pytest.approx(0.0)
        assert alloc[CASH_ETF] == pytest.approx(1.0)

    def test_partial_66(self):
        alloc = compute_target_allocation(0.66, TICKERS, 0.20, CASH_ETF)
        for t in TICKERS:
            assert alloc[t] == pytest.approx(0.132)
        assert alloc[CASH_ETF] == pytest.approx(0.34)

    def test_weights_sum_to_one(self):
        for level in [0.0, 0.33, 0.66, 1.0]:
            alloc = compute_target_allocation(level, TICKERS, 0.20, CASH_ETF)
            total = sum(alloc.values())
            assert total == pytest.approx(1.0, abs=0.01)


class TestDCASplit:
    def test_full_equity_split(self):
        split = compute_dca_split(3000, 1.0, TICKERS, CASH_ETF)
        for t in TICKERS:
            assert split[t] == pytest.approx(600.0)
        assert split[CASH_ETF] == pytest.approx(0.0)

    def test_zero_equity_split(self):
        split = compute_dca_split(3000, 0.0, TICKERS, CASH_ETF)
        for t in TICKERS:
            assert split[t] == pytest.approx(0.0)
        assert split[CASH_ETF] == pytest.approx(3000.0)

    def test_33_split(self):
        split = compute_dca_split(3000, 0.33, TICKERS, CASH_ETF)
        for t in TICKERS:
            assert split[t] == pytest.approx(198.0)
        assert split[CASH_ETF] == pytest.approx(2010.0)

    def test_total_equals_deposit(self):
        for level in [0.0, 0.33, 0.66, 1.0]:
            split = compute_dca_split(3000, level, TICKERS, CASH_ETF)
            total = sum(split.values())
            assert total == pytest.approx(3000.0, abs=0.01)
