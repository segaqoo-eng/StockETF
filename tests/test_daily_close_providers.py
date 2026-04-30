import json
import pytest
from datetime import date
from unittest.mock import patch
from scrapers.daily_close import PriceProvider, ProviderUnavailable, SUCCESS_THRESHOLD


def test_provider_abstract_raises_on_fetch():
    """抽象類別 fetch() 沒實作時應 raise NotImplementedError。"""
    p = PriceProvider()
    with pytest.raises(NotImplementedError):
        p.fetch(["2330"], None)


def test_provider_unavailable_is_an_exception():
    """ProviderUnavailable 是 Exception 子類。"""
    assert issubclass(ProviderUnavailable, Exception)


def test_success_threshold_is_80_percent():
    """門檻常數固定 0.80。"""
    assert SUCCESS_THRESHOLD == 0.80


# ---------------------------------------------------------------------------
# Task 3: CacheDailyClose
# ---------------------------------------------------------------------------
from scrapers.daily_close import CacheDailyClose


def test_cache_provider_reads_existing_prices_json(tmp_path):
    """從現有 prices_today.json 讀。"""
    cache_file = tmp_path / "prices_today.json"
    cache_file.write_text(json.dumps({
        "date": "2026-04-29",
        "prices": {
            "2330": {"close": 1080, "change": 5, "change_pct": 0.46, "exchange": "TWSE"},
            "0050": {"close": 195, "change": -1, "change_pct": -0.51, "exchange": "TWSE"},
        }
    }, ensure_ascii=False), encoding="utf-8")

    p = CacheDailyClose(cache_path=cache_file)
    result = p.fetch(["2330", "0050", "1234"], date(2026, 4, 30))
    assert result["2330"]["close"] == 1080
    assert result["0050"]["change_pct"] == -0.51
    assert "1234" not in result        # cache 沒就略過


def test_cache_provider_raises_when_file_missing(tmp_path):
    """檔案不存在 → ProviderUnavailable。"""
    p = CacheDailyClose(cache_path=tmp_path / "no_such_file.json")
    with pytest.raises(ProviderUnavailable):
        p.fetch(["2330"], date(2026, 4, 30))


def test_cache_provider_raises_on_empty_prices(tmp_path):
    """檔案存在但 prices 空 → ProviderUnavailable。"""
    cache_file = tmp_path / "prices_today.json"
    cache_file.write_text(json.dumps({"date": "2026-04-29", "prices": {}}, ensure_ascii=False), encoding="utf-8")
    p = CacheDailyClose(cache_path=cache_file)
    with pytest.raises(ProviderUnavailable):
        p.fetch(["2330"], date(2026, 4, 30))


# ---------------------------------------------------------------------------
# Task 4: TwseTpexDailyClose
# ---------------------------------------------------------------------------
from scrapers.daily_close import TwseTpexDailyClose

TWSE_STUB = '''{
  "stat": "OK",
  "tables": [{
    "title": "每日收盤行情",
    "fields": ["證券代號","收盤價","漲跌(+/-)","漲跌價差"],
    "data": [["2330","550.00","<p style=\\"color:red\\">+</p>","19.50"]]
  }]
}'''
TPEX_STUB = '''{
  "stat": "ok",
  "tables": [{
    "title": "上櫃股票行情",
    "fields": ["代號","收盤","漲跌"],
    "data": [["3037","85.00","-1.20"]]
  }]
}'''


def test_twse_tpex_returns_only_requested_stock_ids():
    """只 return 在 stock_ids 集合內的股票，其餘略過。"""
    p = TwseTpexDailyClose()
    with patch.object(p._fetcher, "get", side_effect=[TWSE_STUB, TPEX_STUB]):
        result = p.fetch(["2330", "3037"], date(2026, 4, 27))
    assert "2330" in result
    assert "3037" in result


def test_twse_tpex_raises_when_both_endpoints_empty():
    """兩個 endpoint 都空 → ProviderUnavailable。"""
    empty = '{"stat":"OK","tables":[]}'
    p = TwseTpexDailyClose()
    with patch.object(p._fetcher, "get", side_effect=[empty, empty]):
        with pytest.raises(ProviderUnavailable):
            p.fetch(["2330"], date(2026, 4, 27))
