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


# ---------------------------------------------------------------------------
# Task 5: FinMindDailyClose
# ---------------------------------------------------------------------------
from scrapers.daily_close import FinMindDailyClose


def _build_finmind_response(stock_ids, date_str="2026-04-30"):
    """Build a FinMind-shape response for the given stocks."""
    data = []
    for sid in stock_ids:
        data.append({
            "date": date_str,
            "stock_id": sid,
            "Trading_Volume": 100000,
            "open": 100.0,
            "max": 102.0,
            "min": 99.0,
            "close": 101.5,
            "spread": 1.5,
        })
    return {"status": 200, "data": data}


def test_finmind_provider_happy_path(monkeypatch):
    """每 stock_id 各打一次 FinMind，組成 dict 回傳。"""
    calls = []

    def fake_get(url, params, timeout):
        calls.append(params["data_id"])
        resp = _build_finmind_response([params["data_id"]])
        class R:
            def json(self): return resp
            status_code = 200
        return R()

    monkeypatch.setattr("scrapers.daily_close.requests.get", fake_get)

    p = FinMindDailyClose()
    result = p.fetch(["2330", "0050"], date(2026, 4, 30))

    assert calls == ["2330", "0050"]
    assert result["2330"]["close"] == 101.5
    assert result["2330"]["change"] == 1.5
    assert "change_pct" in result["2330"]
    assert "exchange" in result["2330"]


def test_finmind_provider_skips_stocks_with_no_data(monkeypatch):
    """某 stock_id 回空 data → 那檔 missing；不算整體失敗。"""
    def fake_get(url, params, timeout):
        if params["data_id"] == "2330":
            resp = _build_finmind_response(["2330"])
        else:
            resp = {"status": 200, "data": []}
        class R:
            def json(self): return resp
            status_code = 200
        return R()

    monkeypatch.setattr("scrapers.daily_close.requests.get", fake_get)

    p = FinMindDailyClose()
    result = p.fetch(["2330", "0050"], date(2026, 4, 30))

    assert "2330" in result
    assert "0050" not in result


# ---------------------------------------------------------------------------
# Task 6: FinMindDailyClose — error paths（quota + level）
# ---------------------------------------------------------------------------

def test_finmind_raises_on_quota_402(monkeypatch):
    """status==402 → raise ProviderUnavailable + 設 _exhausted=True"""
    def fake_get(url, params, timeout):
        class R:
            def json(self): return {"status": 402, "msg": "Requests reach the upper limit."}
            status_code = 200
        return R()

    monkeypatch.setattr("scrapers.daily_close.requests.get", fake_get)
    p = FinMindDailyClose()
    with pytest.raises(ProviderUnavailable, match="quota"):
        p.fetch(["2330"], date(2026, 4, 30))
    assert p._exhausted is True


def test_finmind_raises_on_level_too_low(monkeypatch):
    """status==400 + 'level is free' → raise ProviderUnavailable"""
    def fake_get(url, params, timeout):
        class R:
            def json(self):
                return {"status": 400,
                        "msg": "Your level is free. Please update your user level."}
            status_code = 200
        return R()

    monkeypatch.setattr("scrapers.daily_close.requests.get", fake_get)
    p = FinMindDailyClose()
    with pytest.raises(ProviderUnavailable, match="level"):
        p.fetch(["2330"], date(2026, 4, 30))


def test_finmind_skips_subsequent_calls_after_exhausted(monkeypatch):
    """_exhausted=True 後再呼叫 fetch → 直接 raise，不打網路"""
    p = FinMindDailyClose()
    p._exhausted = True
    called = []
    monkeypatch.setattr("scrapers.daily_close.requests.get",
                        lambda *a, **k: called.append(1))
    with pytest.raises(ProviderUnavailable):
        p.fetch(["2330"], date(2026, 4, 30))
    assert called == []   # 沒打過網路


# ---------------------------------------------------------------------------
# Task 7: YFinanceDailyClose
# ---------------------------------------------------------------------------
from scrapers.daily_close import YFinanceDailyClose


def test_yfinance_provider_handles_multi_ticker_download(monkeypatch):
    """yf.download 多 ticker 回傳 MultiIndex DataFrame，要 flatten 成 dict。"""
    import pandas as pd

    def fake_download(tickers, start, end, progress, threads, group_by, auto_adjust):
        idx = pd.DatetimeIndex([pd.Timestamp("2026-04-29"), pd.Timestamp("2026-04-30")])
        cols = pd.MultiIndex.from_product(
            [["2330.TW", "0050.TW"], ["Open", "High", "Low", "Close", "Volume"]]
        )
        data = [
            [100, 102, 99, 101, 1000, 200, 202, 199, 201, 2000],
            [101, 103, 100, 102, 1100, 201, 203, 200, 202, 2100],
        ]
        return pd.DataFrame(data, index=idx, columns=cols)

    import yfinance as yf
    monkeypatch.setattr(yf, "download", fake_download)

    p = YFinanceDailyClose()
    result = p.fetch(["2330", "0050"], date(2026, 4, 30))
    assert result["2330"]["close"] == 102
    assert result["2330"]["change"] == 102 - 101
    assert result["0050"]["close"] == 202


def test_yfinance_raises_on_empty_dataframe(monkeypatch):
    """yf.download 回 None / empty → ProviderUnavailable"""
    import yfinance as yf
    monkeypatch.setattr(yf, "download", lambda *a, **k: None)
    p = YFinanceDailyClose()
    with pytest.raises(ProviderUnavailable):
        p.fetch(["2330"], date(2026, 4, 30))


def test_yfinance_raises_on_import_error(monkeypatch):
    """yfinance 未安裝 → ProviderUnavailable（不 crash）"""
    import sys, builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yfinance":
            raise ImportError("No module named 'yfinance'")
        return real_import(name, *args, **kwargs)

    # 先把 yfinance 從 sys.modules 移除，確保 import 觸發 __import__
    monkeypatch.delitem(sys.modules, "yfinance", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    p = YFinanceDailyClose()
    with pytest.raises(ProviderUnavailable, match="not installed"):
        p.fetch(["2330"], date(2026, 4, 30))
