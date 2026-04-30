import pytest
from datetime import date
from scrapers.daily_close import (
    PriceProvider, ProviderUnavailable, fetch_daily_close
)


class _FakeProvider(PriceProvider):
    """測試用 — 可控 return / raise。"""
    def __init__(self, name, result=None, raises=None):
        self.name = name
        self._result = result or {}
        self._raises = raises
        self.call_count = 0

    def fetch(self, stock_ids, target_date):
        self.call_count += 1
        if self._raises:
            raise self._raises
        return {sid: self._result[sid] for sid in stock_ids if sid in self._result}


def _make_prices(stock_ids):
    return {sid: {"close": 100.0, "change": 0.5, "change_pct": 0.5, "exchange": "TWSE"}
            for sid in stock_ids}


def test_dispatch_stops_at_first_successful_provider():
    """FinMind 回 ≥80% → 後面 yfinance/TWSE/cache 不該被呼叫。"""
    stocks = [f"S{i}" for i in range(10)]
    finmind = _FakeProvider("finmind", result=_make_prices(stocks))   # 10/10 成功
    yfin    = _FakeProvider("yfinance")
    twse    = _FakeProvider("twse_tpex")

    result = fetch_daily_close(stocks, date(2026, 4, 30),
                               providers=[finmind, yfin, twse])

    assert result["ok"] is True
    assert result["source"] == "finmind"
    assert finmind.call_count == 1
    assert yfin.call_count == 0
    assert twse.call_count == 0
    assert len(result["prices"]) == 10
