# 股價資料源切換 + 強制刷新按鈕 — 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `data/prices_today.json` 從只走 TWSE+TPEx 升級為 4 層 fallback chain（FinMind → yfinance → TWSE+TPEx → cache），網頁 header 顯示資料源徽章 + 兩個強制刷新按鈕，並把 etf-chip-bar 與 tab-nav 上下對調。

**Architecture:** 新增 `scrapers/daily_close.py` 抽象 `PriceProvider`，包 4 個具體 provider；`web_server.py` 加 mutex + 3 個 endpoint；前端 header 加徽章 + 按鈕、新增 `assets/refresh.js` + `assets/toast.js`。所有後端走 TDD 離線 fixture 測試。

**Tech Stack:** Python 3.12 / pytest / requests / yfinance / Vanilla ES6 JS / threading / SimpleHTTPRequestHandler

**Spec:** `docs/superpowers/specs/2026-04-30-prices-source-and-refresh-design.md`

---

## File Structure

### Create
- `scrapers/daily_close.py` — PriceProvider abstract + 4 concrete impls + dispatch function
- `tests/test_daily_close_providers.py` — provider 解析邏輯測試
- `tests/test_daily_close_dispatch.py` — chain 退級、80% 門檻、metadata 測試
- `tests/test_web_server_refresh.py` — API 端到端整合測試
- `tests/fixtures/finmind_daily_close_ok.json` — 150 檔 FinMind 成功
- `tests/fixtures/finmind_daily_close_partial.json` — 100 檔（< 80%）
- `tests/fixtures/finmind_quota_exhausted.json` — `{status:402}`
- `tests/fixtures/finmind_level_too_low.json` — `{status:400, msg:"level is free"}`
- `assets/refresh.js` — 前端按鈕 + polling
- `assets/toast.js` — 簡易 toast lib

### Modify
- `main.py` — `write_prices()` 改用 `fetch_daily_close()`
- `scripts/web_server.py` — 新增 mutex + 3 個 endpoint
- `index.html` — header 加徽章/按鈕、tab-nav ↔ etf-chip-bar 對調、加 script tag
- `assets/style.css` — 加徽章、按鈕、toast 樣式
- `assets/app.js` — 載入時 render badge from `state.prices.source`
- `docs/VERIFY.md` — 加手動驗收章節

---

## Task 1: 建立 fixtures（純資料檔，無測試）

**Files:**
- Create: `tests/fixtures/finmind_daily_close_ok.json`
- Create: `tests/fixtures/finmind_daily_close_partial.json`
- Create: `tests/fixtures/finmind_quota_exhausted.json`
- Create: `tests/fixtures/finmind_level_too_low.json`

- [ ] **Step 1: 建立 finmind_daily_close_ok.json (150 stocks)**

寫一個小腳本產生 150 檔的 mock data。用 Python 直接產，不打網路：

```python
# 暫時用 Python REPL 產生，產完直接刪掉腳本
import json, random
random.seed(42)
stocks = [f"{1000 + i:04d}" for i in range(150)]
data = []
for sid in stocks:
    close = round(random.uniform(10, 500), 2)
    chg = round(random.uniform(-5, 5), 2)
    data.append({
        "date": "2026-04-30",
        "stock_id": sid,
        "Trading_Volume": random.randint(1000, 1000000),
        "Trading_money": 0,
        "open": close - chg,
        "max": close + 1,
        "min": close - 1,
        "close": close,
        "spread": chg,
        "Trading_turnover": 0,
    })
out = {"status": 200, "data": data}
with open("tests/fixtures/finmind_daily_close_ok.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
```

存到 `tests/fixtures/finmind_daily_close_ok.json`。

- [ ] **Step 2: 建立 finmind_daily_close_partial.json (100 stocks)**

同 Step 1 但只取前 100 檔（<80% of 150 = <120 → 觸發退級）：

```python
data = data[:100]   # 取前 100 筆
out = {"status": 200, "data": data}
# write to tests/fixtures/finmind_daily_close_partial.json
```

- [ ] **Step 3: 建立 finmind_quota_exhausted.json**

```json
{
  "status": 402,
  "msg": "Requests reach the upper limit. https://finmindtrade.com/analysis/#/api/sponsor",
  "data": []
}
```

- [ ] **Step 4: 建立 finmind_level_too_low.json**

```json
{
  "status": 400,
  "msg": "Your level is free. Please update your user level. Detail information:https://finmindtrade.com/analysis/#/Sponsor/sponsor",
  "data": []
}
```

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/finmind_daily_close_ok.json \
        tests/fixtures/finmind_daily_close_partial.json \
        tests/fixtures/finmind_quota_exhausted.json \
        tests/fixtures/finmind_level_too_low.json
git commit -m "test(fixtures): add FinMind daily-close mock responses"
```

---

## Task 2: PriceProvider abstract + ProviderUnavailable

**Files:**
- Create: `scrapers/daily_close.py`
- Create: `tests/test_daily_close_providers.py`

- [ ] **Step 1: 寫失敗的測試**

```python
# tests/test_daily_close_providers.py
import pytest
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
```

- [ ] **Step 2: Run test to verify fail**

Run: `pytest tests/test_daily_close_providers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scrapers.daily_close'`

- [ ] **Step 3: 寫最小 implementation**

```python
# scrapers/daily_close.py
"""4 層 PriceProvider chain for fetching today's close prices.

Spec: docs/superpowers/specs/2026-04-30-prices-source-and-refresh-design.md
"""
from __future__ import annotations

from datetime import date


SUCCESS_THRESHOLD = 0.80   # 回傳 ≥ 80% stock_ids 視為該 provider 成功


class ProviderUnavailable(Exception):
    """Provider 整體不可用 — dispatch 應跳下一家。"""


class PriceProvider:
    """Abstract daily-close fetcher.

    fetch() 部分失敗（149/150 成功）：仍 return 那 149 檔 dict
    fetch() 整體失敗（HTTP error / 配額爆 / 等級不足 / 空回傳）：raise ProviderUnavailable
    """
    name: str = "abstract"

    def fetch(self, stock_ids: list[str], target_date: date) -> dict[str, dict]:
        raise NotImplementedError
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_daily_close_providers.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scrapers/daily_close.py tests/test_daily_close_providers.py
git commit -m "feat(daily_close): PriceProvider abstract + ProviderUnavailable"
```

---

## Task 3: CacheDailyClose provider

**Files:**
- Modify: `scrapers/daily_close.py`
- Modify: `tests/test_daily_close_providers.py`

- [ ] **Step 1: 寫失敗的測試**

加到 `tests/test_daily_close_providers.py` 末尾：

```python
import json
from datetime import date
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
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_daily_close_providers.py -v`
Expected: 3 new tests FAIL with `ImportError: cannot import name 'CacheDailyClose'`

- [ ] **Step 3: Implement**

加到 `scrapers/daily_close.py` 末尾：

```python
import json
from pathlib import Path


class CacheDailyClose(PriceProvider):
    """Read existing data/prices_today.json — last-resort fallback."""
    name = "cache"

    def __init__(self, cache_path: Path | str = Path("data/prices_today.json")):
        self.cache_path = Path(cache_path)

    def fetch(self, stock_ids: list[str], target_date: date) -> dict[str, dict]:
        if not self.cache_path.exists():
            raise ProviderUnavailable(f"cache file missing: {self.cache_path}")
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            raise ProviderUnavailable(f"cache read failed: {e}")
        prices = payload.get("prices") or {}
        if not prices:
            raise ProviderUnavailable("cache prices empty")
        # filter to only requested stock_ids
        return {sid: prices[sid] for sid in stock_ids if sid in prices}
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_daily_close_providers.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add scrapers/daily_close.py tests/test_daily_close_providers.py
git commit -m "feat(daily_close): CacheDailyClose provider reads prices_today.json"
```

---

## Task 4: TwseTpexDailyClose provider（包現有 PricesFetcher）

**Files:**
- Modify: `scrapers/daily_close.py`
- Modify: `tests/test_daily_close_providers.py`

- [ ] **Step 1: 寫失敗的測試**

加到 `tests/test_daily_close_providers.py` 末尾：

```python
from datetime import date
from unittest.mock import patch
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
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_daily_close_providers.py::test_twse_tpex_returns_only_requested_stock_ids -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement**

加到 `scrapers/daily_close.py` 末尾：

```python
from scrapers.twse_prices import PricesFetcher


class TwseTpexDailyClose(PriceProvider):
    """TWSE + TPEx bulk daily-close — wraps existing PricesFetcher."""
    name = "twse_tpex"

    def __init__(self):
        self._fetcher = PricesFetcher()

    def fetch(self, stock_ids: list[str], target_date: date) -> dict[str, dict]:
        raw = self._fetcher.fetch_all(target_date)
        if not raw:
            raise ProviderUnavailable("TWSE+TPEx returned empty")
        wanted = set(stock_ids)
        return {sid: raw[sid] for sid in wanted if sid in raw}
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_daily_close_providers.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add scrapers/daily_close.py tests/test_daily_close_providers.py
git commit -m "feat(daily_close): TwseTpexDailyClose wraps PricesFetcher"
```

---

## Task 5: FinMindDailyClose — happy path（per-stock loop）

**Files:**
- Modify: `scrapers/daily_close.py`
- Modify: `tests/test_daily_close_providers.py`

- [ ] **Step 1: 寫失敗的測試**

加到 `tests/test_daily_close_providers.py` 末尾：

```python
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
        # 2330 有資料，0050 空
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
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_daily_close_providers.py -v`
Expected: 2 new tests FAIL with `ImportError: cannot import name 'FinMindDailyClose'`

- [ ] **Step 3: Implement**

加到 `scrapers/daily_close.py` 末尾：

```python
import os
import logging
import requests

logger = logging.getLogger(__name__)

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


class FinMindDailyClose(PriceProvider):
    """FinMind per-stock loop. Free tier blocks bulk-by-date so we loop.

    Uses FINMIND_TOKEN env var if set (raises 600/hr → 6000/hr quota).
    """
    name = "finmind"

    def __init__(self):
        self.token = os.environ.get("FINMIND_TOKEN", "").strip()
        self._exhausted = False    # 同 process 內配額爆就停試

    def fetch(self, stock_ids: list[str], target_date: date) -> dict[str, dict]:
        if self._exhausted:
            raise ProviderUnavailable("FinMind quota exhausted earlier in this process")

        date_str = target_date.isoformat()
        result: dict[str, dict] = {}
        for sid in stock_ids:
            params = {
                "dataset": "TaiwanStockPrice",
                "data_id": sid,
                "start_date": date_str,
                "end_date": date_str,
            }
            if self.token:
                params["token"] = self.token
            try:
                r = requests.get(FINMIND_URL, params=params, timeout=20)
                d = r.json()
            except Exception as e:
                logger.warning("[finmind] %s: %s", sid, e)
                continue

            status = d.get("status")
            if status == 402:
                self._exhausted = True
                raise ProviderUnavailable(f"FinMind quota: {d.get('msg')}")
            if status == 400 and "level" in (d.get("msg") or "").lower():
                raise ProviderUnavailable(f"FinMind level too low: {d.get('msg')}")
            if status != 200:
                logger.warning("[finmind] %s status=%s msg=%s", sid, status, d.get("msg"))
                continue

            rows = d.get("data") or []
            if not rows:
                continue
            row = rows[-1]   # 取最新一筆（理論上只有一筆，保險起見）
            close = float(row["close"])
            change = float(row.get("spread") or 0.0)
            prev = close - change
            change_pct = round(change / prev * 100, 2) if prev > 0 else 0.0
            result[sid] = {
                "close": round(close, 2),
                "change": round(change, 2),
                "change_pct": change_pct,
                "exchange": "TWSE",   # FinMind 不提供，預設 TWSE；後續 dispatcher 可覆蓋
            }
        return result
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_daily_close_providers.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add scrapers/daily_close.py tests/test_daily_close_providers.py
git commit -m "feat(daily_close): FinMindDailyClose per-stock happy path"
```

---

## Task 6: FinMindDailyClose — error paths（quota + level）

**Files:**
- Modify: `tests/test_daily_close_providers.py`

(implementation 在 Task 5 已寫好錯誤分支，這 task 只補測試)

- [ ] **Step 1: 寫失敗的測試**

加到 `tests/test_daily_close_providers.py` 末尾：

```python
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
```

- [ ] **Step 2: Run to verify pass**

Run: `pytest tests/test_daily_close_providers.py -v`
Expected: 13 passed (Task 5 implementation 已 cover 這些路徑)

- [ ] **Step 3: Commit**

```bash
git add tests/test_daily_close_providers.py
git commit -m "test(daily_close): FinMind quota/level/exhausted error paths"
```

---

## Task 7: YFinanceDailyClose

**Files:**
- Modify: `scrapers/daily_close.py`
- Modify: `tests/test_daily_close_providers.py`

- [ ] **Step 1: 寫失敗的測試**

加到 `tests/test_daily_close_providers.py` 末尾：

```python
from scrapers.daily_close import YFinanceDailyClose


def test_yfinance_provider_handles_multi_ticker_download(monkeypatch):
    """yf.download 多 ticker 回傳 MultiIndex DataFrame，要 flatten 成 dict。"""
    import pandas as pd

    # mock yf.download 回傳一個 MultiIndex DataFrame
    def fake_download(tickers, start, end, progress, threads, group_by, auto_adjust):
        idx = pd.DatetimeIndex([pd.Timestamp("2026-04-29"), pd.Timestamp("2026-04-30")])
        cols = pd.MultiIndex.from_product(
            [["2330.TW", "0050.TW"], ["Open", "High", "Low", "Close", "Volume"]]
        )
        # 每 ticker 各 5 欄 × 2 row
        data = [
            [100, 102, 99, 101, 1000, 200, 202, 199, 201, 2000],   # 4/29
            [101, 103, 100, 102, 1100, 201, 203, 200, 202, 2100],  # 4/30
        ]
        return pd.DataFrame(data, index=idx, columns=cols)

    import yfinance as yf
    monkeypatch.setattr(yf, "download", fake_download)

    p = YFinanceDailyClose()
    result = p.fetch(["2330", "0050"], date(2026, 4, 30))
    assert result["2330"]["close"] == 102
    assert result["2330"]["change"] == 102 - 101    # close - prev_close
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
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_daily_close_providers.py -v`
Expected: 3 new tests FAIL with `ImportError: cannot import name 'YFinanceDailyClose'`

- [ ] **Step 3: Implement**

加到 `scrapers/daily_close.py` 末尾：

```python
from datetime import timedelta


class YFinanceDailyClose(PriceProvider):
    """yfinance batch download for multiple tickers.

    Tries .TW (TWSE) suffix only; per spec we don't iterate .TWO since the
    universe comes from latest.json which already classifies. If a stock
    is on TPEx, this provider will miss it — TWSE+TPEx fallback covers.
    """
    name = "yfinance"

    def fetch(self, stock_ids: list[str], target_date: date) -> dict[str, dict]:
        try:
            import yfinance as yf
        except ImportError:
            raise ProviderUnavailable("yfinance not installed")

        if not stock_ids:
            return {}

        tickers = [f"{sid}.TW" for sid in stock_ids]
        # 抓 2 個交易日（要算 change vs prev_close）
        start = target_date - timedelta(days=5)
        end = target_date + timedelta(days=1)

        try:
            df = yf.download(
                tickers,
                start=start.isoformat(),
                end=end.isoformat(),
                progress=False,
                threads=True,
                group_by="ticker",
                auto_adjust=False,
            )
        except Exception as e:
            raise ProviderUnavailable(f"yfinance download failed: {e}")

        if df is None or df.empty:
            raise ProviderUnavailable("yfinance returned empty DataFrame")

        result: dict[str, dict] = {}
        for sid in stock_ids:
            ticker = f"{sid}.TW"
            try:
                if ticker not in df.columns.get_level_values(0):
                    continue
                sub = df[ticker].dropna(subset=["Close"])
                if len(sub) < 1:
                    continue
                close = float(sub["Close"].iloc[-1])
                prev = float(sub["Close"].iloc[-2]) if len(sub) >= 2 else close
                change = close - prev
                change_pct = round(change / prev * 100, 2) if prev > 0 else 0.0
                result[sid] = {
                    "close": round(close, 2),
                    "change": round(change, 2),
                    "change_pct": change_pct,
                    "exchange": "TWSE",
                }
            except Exception as e:
                logger.warning("[yfinance] %s: %s", sid, e)
                continue
        return result
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_daily_close_providers.py -v`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add scrapers/daily_close.py tests/test_daily_close_providers.py
git commit -m "feat(daily_close): YFinanceDailyClose batch multi-ticker"
```

---

## Task 8: fetch_daily_close dispatch — happy path（FinMind 第一家成功）

**Files:**
- Modify: `scrapers/daily_close.py`
- Create: `tests/test_daily_close_dispatch.py`

- [ ] **Step 1: 寫失敗的測試**

```python
# tests/test_daily_close_dispatch.py
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
    assert yfin.call_count == 0      # 不該被呼叫
    assert twse.call_count == 0
    assert len(result["prices"]) == 10
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_daily_close_dispatch.py -v`
Expected: FAIL with `ImportError: cannot import name 'fetch_daily_close'`

- [ ] **Step 3: Implement**

加到 `scrapers/daily_close.py` 末尾：

```python
from datetime import datetime
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")


def fetch_daily_close(
    stock_ids: list[str],
    target_date: date,
    providers: list[PriceProvider] | None = None,
) -> dict:
    """Walk providers in order; first one returning ≥ SUCCESS_THRESHOLD wins.

    See spec §3 + §4 for full behavior.

    Returns:
      {
        "ok":         bool,
        "date":       "YYYY-MM-DD",
        "source":     "finmind" | "yfinance" | "twse_tpex" | "cache" | None,
        "fetched_at": ISO8601 with Asia/Taipei tz,
        "prices":     {stock_id: {close, change, change_pct, exchange}},
        "missing":    [stock_id, ...],   # 該 provider 沒回到的
        "tried":      [provider_name, ...],
        "error":      str | None,
      }
    """
    if providers is None:
        providers = [
            FinMindDailyClose(),
            YFinanceDailyClose(),
            TwseTpexDailyClose(),
            CacheDailyClose(),
        ]

    tried: list[str] = []
    for p in providers:
        tried.append(p.name)
        try:
            partial = p.fetch(stock_ids, target_date)
        except ProviderUnavailable as e:
            logger.warning("[%s] unavailable: %s", p.name, e)
            continue
        except Exception as e:
            logger.warning("[%s] unexpected error: %s", p.name, e)
            continue

        if not partial:
            continue
        ratio = len(partial) / max(1, len(stock_ids))
        if ratio < SUCCESS_THRESHOLD:
            logger.info("[%s] returned %d/%d (<%.0f%%), trying next",
                        p.name, len(partial), len(stock_ids), SUCCESS_THRESHOLD * 100)
            continue

        missing = [sid for sid in stock_ids if sid not in partial]
        return {
            "ok":         True,
            "date":       target_date.isoformat(),
            "source":     p.name,
            "fetched_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
            "prices":     partial,
            "missing":    missing,
            "tried":      tried,
            "error":      None,
        }

    return {
        "ok":         False,
        "date":       target_date.isoformat(),
        "source":     None,
        "fetched_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "prices":     {},
        "missing":    list(stock_ids),
        "tried":      tried,
        "error":      "all providers failed",
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_daily_close_dispatch.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add scrapers/daily_close.py tests/test_daily_close_dispatch.py
git commit -m "feat(daily_close): fetch_daily_close dispatch happy path"
```

---

## Task 9: Dispatch — 80% 門檻退級

**Files:**
- Modify: `tests/test_daily_close_dispatch.py`

- [ ] **Step 1: 寫失敗的測試**

加到 `tests/test_daily_close_dispatch.py` 末尾：

```python
def test_dispatch_falls_through_on_under_80pct():
    """FinMind 只回 50% → 跳到 yfinance"""
    stocks = [f"S{i}" for i in range(10)]
    finmind = _FakeProvider("finmind",
                            result=_make_prices(stocks[:5]))    # 5/10 = 50%
    yfin = _FakeProvider("yfinance",
                         result=_make_prices(stocks))           # 10/10 ≥ 80%

    result = fetch_daily_close(stocks, date(2026, 4, 30),
                               providers=[finmind, yfin])

    assert result["source"] == "yfinance"
    assert finmind.call_count == 1
    assert yfin.call_count == 1


def test_dispatch_skips_provider_that_raises_unavailable():
    """ProviderUnavailable → 跳下一家，不影響後續流程"""
    stocks = ["S1", "S2"]
    finmind = _FakeProvider("finmind", raises=ProviderUnavailable("quota"))
    twse = _FakeProvider("twse_tpex", result=_make_prices(stocks))

    result = fetch_daily_close(stocks, date(2026, 4, 30),
                               providers=[finmind, twse])
    assert result["source"] == "twse_tpex"


def test_dispatch_returns_missing_list():
    """成功 provider 沒回到的 stock_ids 寫進 missing"""
    stocks = [f"S{i}" for i in range(10)]
    only_8 = _FakeProvider("twse_tpex", result=_make_prices(stocks[:8]))   # 8/10 = 80% ≥ threshold
    result = fetch_daily_close(stocks, date(2026, 4, 30), providers=[only_8])
    assert result["source"] == "twse_tpex"
    assert sorted(result["missing"]) == ["S8", "S9"]
```

- [ ] **Step 2: Run to verify pass**

Run: `pytest tests/test_daily_close_dispatch.py -v`
Expected: 4 passed (Task 8 已 cover 邏輯)

- [ ] **Step 3: Commit**

```bash
git add tests/test_daily_close_dispatch.py
git commit -m "test(dispatch): 80%% threshold + ProviderUnavailable fallthrough"
```

---

## Task 10: Dispatch — 全失敗 + metadata 寫入

**Files:**
- Modify: `tests/test_daily_close_dispatch.py`

- [ ] **Step 1: 寫失敗的測試**

加到 `tests/test_daily_close_dispatch.py` 末尾：

```python
def test_dispatch_returns_error_when_all_providers_fail():
    """4 家全失敗 → ok=False, error 訊息明確"""
    stocks = ["S1"]
    providers = [_FakeProvider(n, raises=ProviderUnavailable("bork"))
                 for n in ("finmind", "yfinance", "twse_tpex", "cache")]
    result = fetch_daily_close(stocks, date(2026, 4, 30), providers=providers)

    assert result["ok"] is False
    assert result["source"] is None
    assert result["error"] == "all providers failed"
    assert result["tried"] == ["finmind", "yfinance", "twse_tpex", "cache"]
    assert result["missing"] == ["S1"]


def test_dispatch_metadata_includes_date_fetched_at_tried():
    """成功時 result 帶 date / fetched_at / tried 三欄"""
    stocks = ["S1"]
    p = _FakeProvider("twse_tpex", result=_make_prices(stocks))
    result = fetch_daily_close(stocks, date(2026, 4, 30), providers=[p])

    assert result["date"] == "2026-04-30"
    assert result["fetched_at"]   # 非空
    assert "T" in result["fetched_at"]   # ISO8601
    assert result["tried"] == ["twse_tpex"]
```

- [ ] **Step 2: Run to verify pass**

Run: `pytest tests/test_daily_close_dispatch.py -v`
Expected: 6 passed

- [ ] **Step 3: Commit**

```bash
git add tests/test_daily_close_dispatch.py
git commit -m "test(dispatch): all-fail error + metadata schema"
```

---

## Task 11: 把 main.py write_prices 切到 fetch_daily_close

**Files:**
- Modify: `main.py:236-272`

- [ ] **Step 1: 改寫 write_prices**

找到 `main.py` 的 `def write_prices(today_payload: dict, data_dir: Path) -> None:` 函式（line ~236）。整個替換成：

```python
def write_prices(today_payload: dict, data_dir: Path) -> None:
    """Fetch today's close prices via 4-tier provider chain.

    Spec: docs/superpowers/specs/2026-04-30-prices-source-and-refresh-design.md

    Universe = unique stock_ids in today_payload's TW holdings (~150).
    Walks FinMind → yfinance → TWSE+TPEx → cache; first ≥80% wins.
    On total failure, keeps existing prices_today.json unchanged.
    """
    from scrapers.daily_close import fetch_daily_close

    target = datetime.now(TAIPEI).date()
    held_ids = sorted({
        h["stock_id"]
        for etf in today_payload.get("etfs", [])
        for h in etf.get("holdings", [])
        if h.get("market") == "TW"
    })
    prices_path = data_dir / "prices_today.json"

    result = fetch_daily_close(list(held_ids), target)

    if not result["ok"]:
        if prices_path.exists():
            prev_date = json.loads(prices_path.read_text(encoding="utf-8")).get("date", "?")
            print(f"Prices: all providers failed for {target} — keeping previous ({prev_date})")
        else:
            prices_path.write_text(
                json.dumps({"date": target.isoformat(), "source": None,
                            "fetched_at": result["fetched_at"], "prices": {},
                            "missing": list(held_ids)}, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"Prices: no data for {target}, wrote empty placeholder")
        return

    payload = {
        "date":       result["date"],
        "source":     result["source"],
        "fetched_at": result["fetched_at"],
        "prices":     result["prices"],
        "missing":    result["missing"],
    }
    prices_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"Prices: wrote {len(result['prices'])} stocks from {result['source']} "
          f"(missing {len(result['missing'])})")
```

把 line 17 的 `from scrapers.twse_prices import PricesFetcher` **刪掉**（main.py 不再直接用，PricesFetcher 仍由新的 `TwseTpexDailyClose` 包裝重用，所以類別本身還活著）。

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `pytest tests/ -v --ignore=tests/test_web_server_refresh.py`
Expected: all passing (twse_prices tests 還在跑因為 PricesFetcher 仍存在)

- [ ] **Step 3: Run main.py with --skip-network 環境變數模擬**（手動驗證）

實際跑一次 main.py 看 prices_today.json 寫得對不對。如果你電腦上現在沒網路或 FinMind 配額爆，會走到 yfinance 或 TWSE+TPEx，都正常。

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe main.py
```

打開 `data/prices_today.json` 確認多了 `source` / `fetched_at` / `missing` 三欄。

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat(prices): main.py write_prices uses fetch_daily_close 4-tier chain"
```

---

## Task 12: web_server mutex skeleton + GET /api/refresh/status

**Files:**
- Modify: `scripts/web_server.py`
- Create: `tests/test_web_server_refresh.py`

- [ ] **Step 1: 寫失敗的測試**

```python
# tests/test_web_server_refresh.py
"""End-to-end API tests for /api/refresh/* endpoints.

啟動真實 HTTPServer 在隨機 port，用 http.client 打 request。
"""
import json
import threading
import time
import http.client
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import pytest


@pytest.fixture
def server():
    """Start web_server.StockETFHandler on a random free port; yield (host, port)."""
    from http.server import HTTPServer
    import scripts.web_server as ws

    # 重置 mutex state（每個測試獨立）
    ws._reset_for_tests()

    httpd = HTTPServer(("127.0.0.1", 0), ws.StockETFHandler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield ("127.0.0.1", port)
    finally:
        httpd.shutdown()


def _get(server, path):
    conn = http.client.HTTPConnection(*server)
    conn.request("GET", path)
    r = conn.getresponse()
    body = r.read().decode("utf-8")
    conn.close()
    return r.status, json.loads(body) if body else None


def test_refresh_status_initial_state(server):
    """初始狀態：running=False, current_job=None"""
    status, body = _get(server, "/api/refresh/status")
    assert status == 200
    assert body["running"] is False
    assert body["current_job"] is None
    assert body["last_error"] is None
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_web_server_refresh.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute '_reset_for_tests'`

- [ ] **Step 3: Implement — 改 scripts/web_server.py**

在 `scripts/web_server.py` 開頭（imports 之後）加：

```python
import threading

# ── Refresh job state（module-level mutex）──────────────────
_job_lock = threading.Lock()
_running_job: str | None = None         # "prices" | "etfs" | None
_job_started_at: str | None = None
_last_result: dict | None = None
_last_error: str | None = None


def _reset_for_tests() -> None:
    """Test-only: reset module state between tests."""
    global _running_job, _job_started_at, _last_result, _last_error
    _running_job = None
    _job_started_at = None
    _last_result = None
    _last_error = None
```

然後在 `do_GET` 內加 status endpoint route（在現有 `/api/positions` 那段附近）：

```python
def do_GET(self):
    if self.path == "/api/refresh/status":
        return self._send_json({
            "running":     _running_job is not None,
            "current_job": _running_job,
            "started_at":  _job_started_at,
            "last_result": _last_result,
            "last_error":  _last_error,
        })
    if self.path == "/api/positions":
        return self._send_json(my_status.get_full_status())
    # ...（其餘維持）
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_web_server_refresh.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/web_server.py tests/test_web_server_refresh.py
git commit -m "feat(web_server): mutex state + GET /api/refresh/status"
```

---

## Task 13: POST /api/refresh/prices

**Files:**
- Modify: `scripts/web_server.py`
- Modify: `tests/test_web_server_refresh.py`

- [ ] **Step 1: 寫失敗的測試**

加到 `tests/test_web_server_refresh.py` 末尾：

```python
def _post(server, path, body=None):
    conn = http.client.HTTPConnection(*server)
    body_bytes = json.dumps(body).encode("utf-8") if body else b""
    headers = {"Content-Type": "application/json", "Content-Length": str(len(body_bytes))}
    conn.request("POST", path, body=body_bytes, headers=headers)
    r = conn.getresponse()
    text = r.read().decode("utf-8")
    conn.close()
    return r.status, json.loads(text) if text else None


def test_post_refresh_prices_returns_202_and_starts_thread(server, monkeypatch):
    """正常情況：return 202 並啟動背景 thread"""
    import scripts.web_server as ws

    # 替換真實的 fetch_daily_close 成 fake（避免打網路）
    fake_done = threading.Event()
    def fake_run_prices_job():
        time.sleep(0.05)
        fake_done.set()

    monkeypatch.setattr(ws, "_run_prices_job", fake_run_prices_job)

    status, body = _post(server, "/api/refresh/prices")
    assert status == 202
    assert body["job"] == "prices"
    assert "started_at" in body

    # 等 thread 完成
    assert fake_done.wait(timeout=2)
    # 等 mutex 釋放（最多 1 秒）
    deadline = time.time() + 1
    while time.time() < deadline and ws._running_job is not None:
        time.sleep(0.01)
    assert ws._running_job is None


def test_concurrent_refresh_returns_409(server, monkeypatch):
    """第二個 request 撞 mutex → 409 Conflict"""
    import scripts.web_server as ws
    blocking = threading.Event()

    def slow_run():
        blocking.wait(timeout=2)

    monkeypatch.setattr(ws, "_run_prices_job", slow_run)

    s1, b1 = _post(server, "/api/refresh/prices")
    assert s1 == 202

    s2, b2 = _post(server, "/api/refresh/prices")
    assert s2 == 409
    assert "running" in b2["error"].lower()

    blocking.set()   # 解鎖第一個 thread
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_web_server_refresh.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute '_run_prices_job'`

- [ ] **Step 3: Implement**

在 `scripts/web_server.py` 加 `_run_prices_job` 函式（mutex skeleton 後面）：

```python
import json as _json   # 避免遮蔽 do_POST 內的 json 匯入

def _run_prices_job() -> None:
    """Background runner: fetch_daily_close + write prices_today.json."""
    global _running_job, _last_result, _last_error
    try:
        from scrapers.daily_close import fetch_daily_close
        from datetime import datetime
        from zoneinfo import ZoneInfo

        latest_path = ROOT / "data" / "latest.json"
        prices_path = ROOT / "data" / "prices_today.json"
        target = datetime.now(ZoneInfo("Asia/Taipei")).date()

        latest = _json.loads(latest_path.read_text(encoding="utf-8"))
        held_ids = sorted({
            h["stock_id"]
            for etf in latest.get("etfs", [])
            for h in etf.get("holdings", [])
            if h.get("market") == "TW"
        })
        result = fetch_daily_close(list(held_ids), target)

        if result["ok"]:
            payload = {
                "date":       result["date"],
                "source":     result["source"],
                "fetched_at": result["fetched_at"],
                "prices":     result["prices"],
                "missing":    result["missing"],
            }
            prices_path.write_text(_json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        _last_result = {
            "job":            "prices",
            "ok":             result["ok"],
            "source":         result["source"],
            "missing_count":  len(result["missing"]),
            "tried":          result["tried"],
            "error":          result["error"],
        }
        _last_error = None
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        _last_error = f"{type(e).__name__}: {e}"
        _last_result = None


def _try_start_job(job_name: str, target_fn) -> tuple[bool, str | None]:
    """嘗試取 mutex 並啟動 background thread。回 (started, error_msg)。"""
    global _running_job, _job_started_at, _last_error
    from datetime import datetime
    from zoneinfo import ZoneInfo

    with _job_lock:
        if _running_job is not None:
            return False, f"another job '{_running_job}' is running"
        _running_job = job_name
        _job_started_at = datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")
        _last_error = None

    def _runner():
        global _running_job, _job_started_at
        try:
            target_fn()
        finally:
            with _job_lock:
                _running_job = None
                _job_started_at = None

    threading.Thread(target=_runner, daemon=True).start()
    return True, None
```

在 `do_POST` 內最前面加 route：

```python
def do_POST(self):
    try:
        if self.path == "/api/refresh/prices":
            ok, err = _try_start_job("prices", _run_prices_job)
            if not ok:
                return self._send_json({"ok": False, "error": err}, status=409)
            return self._send_json({"job": "prices", "started_at": _job_started_at},
                                   status=202)
        # ...（其餘 /api/positions/* 維持）
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_web_server_refresh.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/web_server.py tests/test_web_server_refresh.py
git commit -m "feat(web_server): POST /api/refresh/prices + mutex 409"
```

---

## Task 14: POST /api/refresh/etfs + thread crash safety

**Files:**
- Modify: `scripts/web_server.py`
- Modify: `tests/test_web_server_refresh.py`

- [ ] **Step 1: 寫失敗的測試**

加到 `tests/test_web_server_refresh.py` 末尾：

```python
def test_post_refresh_etfs_returns_202(server, monkeypatch):
    """ETF refresh 走獨立 endpoint。"""
    import scripts.web_server as ws
    done = threading.Event()
    monkeypatch.setattr(ws, "_run_etfs_job", lambda: done.set())

    status, body = _post(server, "/api/refresh/etfs")
    assert status == 202
    assert body["job"] == "etfs"
    assert done.wait(timeout=2)


def test_thread_crash_writes_last_error_releases_mutex(server, monkeypatch):
    """Thread 內爆 exception → last_error 有值 + mutex 釋放（不卡死）"""
    import scripts.web_server as ws

    def boom():
        raise RuntimeError("simulated crash")
    monkeypatch.setattr(ws, "_run_prices_job", boom)

    s1, _ = _post(server, "/api/refresh/prices")
    assert s1 == 202

    # 等 thread 跑完
    deadline = time.time() + 2
    while time.time() < deadline and ws._running_job is not None:
        time.sleep(0.02)
    assert ws._running_job is None

    # 下次 request 應該能成功（mutex 釋放了）+ status 帶 last_error
    status, body = _get(server, "/api/refresh/status")
    assert "simulated crash" in (body["last_error"] or "")
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_web_server_refresh.py -v`
Expected: 2 new tests FAIL

- [ ] **Step 3: Implement**

在 `scripts/web_server.py` 加 `_run_etfs_job`：

```python
def _run_etfs_job() -> None:
    """Background runner: re-run main.main() (full ETF pipeline + prices at end)."""
    global _last_result, _last_error
    try:
        # main 的 sys.path 已在 web_server.py 開頭加好
        import importlib
        import main as etf_main
        importlib.reload(etf_main)   # 確保最新 module state
        rc = etf_main.main()
        _last_result = {"ok": rc == 0, "exit_code": rc, "job": "etfs"}
        _last_error = None
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        _last_error = f"{type(e).__name__}: {e}"
        _last_result = None
```

修改 `_try_start_job` 的 `_runner`：把 thread 內 `target_fn()` 包進 try/except（雖然 `_run_*_job` 內已 wrap，但雙重保險，避免漏抓）：

```python
def _runner():
    global _running_job, _job_started_at, _last_error
    try:
        target_fn()
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        _last_error = f"{type(e).__name__}: {e}"
    finally:
        with _job_lock:
            _running_job = None
            _job_started_at = None
```

在 `do_POST` 加 etfs route：

```python
if self.path == "/api/refresh/etfs":
    ok, err = _try_start_job("etfs", _run_etfs_job)
    if not ok:
        return self._send_json({"ok": False, "error": err}, status=409)
    return self._send_json({"job": "etfs", "started_at": _job_started_at}, status=202)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_web_server_refresh.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/web_server.py tests/test_web_server_refresh.py
git commit -m "feat(web_server): POST /api/refresh/etfs + thread crash safety"
```

---

## Task 15: index.html — 對調 tab-nav 與 etf-chip-bar

**Files:**
- Modify: `index.html:17-30`

- [ ] **Step 1: Read 現有結構**

Read `index.html` 行 17-30，目前是 `<nav id="etf-chip-bar">`（17-19）→ `<nav class="tab-nav">`（21-30）。

- [ ] **Step 2: Edit 對調順序**

把整個 `<nav class="tab-nav">...</nav>` block（含結尾 `</nav>`）整段移到 `<nav id="etf-chip-bar">...</nav>` block 上面。

預期改後（行 17-30 區段）：

```html
  <nav class="tab-nav">
    <button class="tab-btn active" data-tab="cross">交叉持股</button>
    <button class="tab-btn" data-tab="etfs">ETF 總覽</button>
    <button class="tab-btn" data-tab="changes">各 ETF 持股變化</button>
    <button class="tab-btn" data-tab="consensus">共識加減碼</button>
    <button class="tab-btn" data-tab="ranking">買進評分</button>
    <button class="tab-btn" data-tab="signals">📋 今日訊號</button>
    <button class="tab-btn" data-tab="paper">📈 Paper 模擬</button>
    <button class="tab-btn" data-tab="positions">💰 我的部位</button>
  </nav>

  <nav id="etf-chip-bar" class="etf-chip-bar" aria-label="ETF 列表，點選查看持股明細">
    <span class="loading">載入中…</span>
  </nav>
```

- [ ] **Step 3: 手動驗證 — 開瀏覽器**

```bash
.venv/Scripts/python.exe scripts/web_server.py 8000
```

打開 `http://localhost:8000`，確認：
- tabs（交叉持股 / ETF 總覽 / ...）在上
- ETF chip-bar（0050 / 00980A / ...）在下
- tab 切換、chip 點擊功能都正常

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat(ui): swap tab-nav and etf-chip-bar order on homepage"
```

---

## Task 16: index.html — header 加徽章 + 兩按鈕；CSS skeleton

**Files:**
- Modify: `index.html:12-15`
- Modify: `assets/style.css`

- [ ] **Step 1: 改 index.html 的 header**

替換原 header 區段（行 12-15）：

```html
  <header class="header">
    <h1>📊 Stock<span>ETF</span></h1>
    <div class="header-sub">
      主動式 ETF 交叉持股分析（+ 0050 對照） ·
      更新於 <b id="updated-at">—</b> ·
      <span id="price-source-badge" class="source-badge source-badge-unknown" title="">—</span>
      <button id="btn-refresh-prices" class="header-btn" title="只重抓股價，10-30 秒">🔄 股價</button>
      <button id="btn-refresh-etfs" class="header-btn" title="重抓 ETF 持股 + 股價，1-2 分鐘">🔄 ETF</button>
    </div>
  </header>
```

- [ ] **Step 2: 加 CSS（assets/style.css 末尾）**

```css
/* ═══ Source badge + refresh buttons ═══ */
.source-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.85em;
  font-weight: 500;
  margin: 0 4px;
  cursor: help;
}
.source-badge-finmind   { background: #d4edda; color: #155724; }   /* 🟢 */
.source-badge-yfinance  { background: #fff3cd; color: #856404; }   /* 🟡 */
.source-badge-twse_tpex { background: #d1ecf1; color: #0c5460; }   /* 🔵 */
.source-badge-cache     { background: #f8d7da; color: #721c24; }   /* 🔴 */
.source-badge-running   { background: #e2e3e5; color: #383d41; }   /* ⏳ */
.source-badge-unknown   { background: #e2e3e5; color: #6c757d; }   /* ❓ */

.header-btn {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  padding: 3px 10px;
  font-size: 0.85em;
  cursor: pointer;
  margin-left: 4px;
  transition: background 0.15s;
}
.header-btn:hover:not(:disabled)  { background: #e9ecef; }
.header-btn:disabled              { opacity: 0.4; cursor: not-allowed; }
```

- [ ] **Step 3: 手動驗證**

重新整理瀏覽器，確認：
- header 副標多了 `❓ —` 徽章 + 兩個 🔄 按鈕
- 按鈕 hover 有效果
- 按下按鈕沒事（先沒 wire — Task 19 會做）

- [ ] **Step 4: Commit**

```bash
git add index.html assets/style.css
git commit -m "feat(ui): header source badge + refresh buttons (skeleton)"
```

---

## Task 17: assets/toast.js — 簡易 toast lib

**Files:**
- Create: `assets/toast.js`
- Modify: `assets/style.css`
- Modify: `index.html` (script tag)

- [ ] **Step 1: Create assets/toast.js**

```javascript
// toast.js — 簡易 toast lib（manual close 模式）
// API: toast(message, { level: "info" | "warn" | "error" })
// 多次呼叫會堆疊在右上角，使用者按 ✕ 關閉

(function () {
  function ensureContainer() {
    let c = document.getElementById("toast-container");
    if (!c) {
      c = document.createElement("div");
      c.id = "toast-container";
      document.body.appendChild(c);
    }
    return c;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, ch => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[ch]);
  }

  window.toast = function (message, opts) {
    opts = opts || {};
    const level = opts.level || "info";
    const c = ensureContainer();

    const el = document.createElement("div");
    el.className = `toast toast-${level}`;
    el.innerHTML =
      `<span class="toast-msg">${escapeHtml(message)}</span>` +
      `<button class="toast-close" aria-label="關閉">✕</button>`;
    el.querySelector(".toast-close").addEventListener("click", () => el.remove());
    c.appendChild(el);
  };

  window.dismissAllToasts = function () {
    const c = document.getElementById("toast-container");
    if (c) c.innerHTML = "";
  };
})();
```

- [ ] **Step 2: 加 CSS（assets/style.css 末尾）**

```css
/* ═══ Toast ═══ */
#toast-container {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 420px;
}
.toast {
  background: #fff;
  border: 1px solid #dee2e6;
  border-left-width: 4px;
  border-radius: 4px;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 10px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  animation: toast-in 0.2s ease-out;
}
@keyframes toast-in {
  from { opacity: 0; transform: translateX(20px); }
  to   { opacity: 1; transform: translateX(0); }
}
.toast-info  { border-left-color: #17a2b8; }
.toast-warn  { border-left-color: #ffc107; background: #fffaeb; }
.toast-error { border-left-color: #dc3545; background: #fdecee; }
.toast-msg   { flex: 1; font-size: 0.9em; }
.toast-close {
  background: none;
  border: none;
  font-size: 1.1em;
  cursor: pointer;
  color: #6c757d;
  padding: 0 4px;
}
.toast-close:hover { color: #000; }
```

- [ ] **Step 3: 加 `<script>` tag 到 index.html**

在 `index.html` 找到 `<script src="assets/app.js"></script>` 那一段，**前面**加：

```html
<script src="assets/toast.js"></script>
```

最終的 script 區塊應該長這樣：

```html
<script src="assets/toast.js"></script>
<script src="assets/app.js"></script>
<script src="assets/ranking.js"></script>
<script src="assets/positions.js"></script>
<script src="assets/markdown_view.js"></script>
```

- [ ] **Step 4: 手動驗證**

重新整理瀏覽器，打開 DevTools console，跑：

```javascript
toast("測試訊息", { level: "warn" });
toast("錯誤訊息", { level: "error" });
toast("一般訊息");
```

預期：3 個 toast 從右上角彈出、堆疊；按 ✕ 各自關閉。

- [ ] **Step 5: Commit**

```bash
git add assets/toast.js assets/style.css index.html
git commit -m "feat(ui): simple toast lib with manual close"
```

---

## Task 18: assets/app.js — 載入時 render badge

**Files:**
- Modify: `assets/app.js:60-80` (loadData 區段)

- [ ] **Step 1: 加 renderBadge function**

在 `assets/app.js` 適當位置（例如 `formatDate` 函式附近）加：

```javascript
const SOURCE_LABELS = {
  finmind:    { emoji: "🟢", label: "FinMind" },
  yfinance:   { emoji: "🟡", label: "yfinance" },
  twse_tpex:  { emoji: "🔵", label: "TWSE+TPEx" },
  cache:      { emoji: "🔴", label: "Cache (舊資料)" },
  running:    { emoji: "⏳", label: "抓取中..." },
  unknown:    { emoji: "❓", label: "未知 (舊格式)" },
};

function renderSourceBadge() {
  const el = document.getElementById("price-source-badge");
  if (!el) return;
  const src = state.prices && state.prices.source;
  const fetchedAt = state.prices && state.prices.fetched_at;
  const missing = (state.prices && state.prices.missing) || [];

  const key = SOURCE_LABELS[src] ? src : "unknown";
  const info = SOURCE_LABELS[key];

  el.className = `source-badge source-badge-${key}`;
  el.textContent = `${info.emoji} ${info.label}`;
  const tooltipParts = [];
  if (fetchedAt) tooltipParts.push(`抓取於 ${fetchedAt}`);
  if (missing.length) tooltipParts.push(`${missing.length} 檔抓不到`);
  el.title = tooltipParts.join(" · ") || info.label;
}

function setBadgeRunning() {
  const el = document.getElementById("price-source-badge");
  if (!el) return;
  const info = SOURCE_LABELS.running;
  el.className = "source-badge source-badge-running";
  el.textContent = `${info.emoji} ${info.label}`;
  el.title = "正在執行 refresh job...";
}
```

- [ ] **Step 2: 在 loadData 內呼叫 renderSourceBadge**

找到 `assets/app.js:65` 附近：

```javascript
document.getElementById("updated-at").textContent = formatDate(state.payload.updated_at);
```

下方加一行：

```javascript
renderSourceBadge();
```

- [ ] **Step 3: Export 給 refresh.js 用**

在 `app.js` 末尾（或檔尾的 init/await 之外）加：

```javascript
// Expose for refresh.js
window.StockETF = window.StockETF || {};
window.StockETF.renderSourceBadge = renderSourceBadge;
window.StockETF.setBadgeRunning = setBadgeRunning;
```

- [ ] **Step 4: 手動驗證**

```bash
.venv/Scripts/python.exe scripts/web_server.py 8000
```

打開 http://localhost:8000，預期 header 徽章顯示：
- 若 `prices_today.json` 已是新格式 → 🟢 / 🟡 / 🔵 / 🔴 之一
- 若是舊格式（沒 `source` 欄）→ ❓ 未知 (舊格式)

(現階段如果還沒跑過 Task 11 後的 main.py，就會是舊格式。可手動跑 main.py 一次重寫 prices_today.json 來看新格式)

- [ ] **Step 5: Commit**

```bash
git add assets/app.js
git commit -m "feat(ui): render source badge from prices_today.source on load"
```

---

## Task 19: assets/refresh.js — 按鈕 + polling + 表格 reload

**Files:**
- Create: `assets/refresh.js`
- Modify: `index.html` (script tag)

- [ ] **Step 1: Create assets/refresh.js**

```javascript
// refresh.js — 強制刷新按鈕邏輯
// 依賴 toast.js + app.js (window.StockETF.renderSourceBadge / setBadgeRunning)

(function () {
  const POLL_INTERVAL_MS = 2000;
  let pollTimer = null;

  function setButtonsDisabled(disabled) {
    document.getElementById("btn-refresh-prices").disabled = disabled;
    document.getElementById("btn-refresh-etfs").disabled = disabled;
  }

  async function startJob(endpoint) {
    setButtonsDisabled(true);
    if (window.StockETF && window.StockETF.setBadgeRunning) {
      window.StockETF.setBadgeRunning();
    }
    try {
      const res = await fetch(endpoint, { method: "POST" });
      if (res.status === 409) {
        const body = await res.json();
        toast(`⏳ ${body.error || "已有任務在跑"}`, { level: "info" });
        setButtonsDisabled(false);
        // 還原徽章
        if (window.StockETF) window.StockETF.renderSourceBadge();
        return;
      }
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      // 202 Accepted → start polling
      pollStatus();
    } catch (e) {
      toast(`刷新失敗：${e.message || e}`, { level: "error" });
      setButtonsDisabled(false);
      if (window.StockETF) window.StockETF.renderSourceBadge();
    }
  }

  function pollStatus() {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(async () => {
      try {
        const res = await fetch("/api/refresh/status", { cache: "no-store" });
        const status = await res.json();
        if (status.running) {
          pollStatus();   // 繼續 poll
        } else {
          // 跑完了 — reload 資料 + render
          await onJobComplete(status);
        }
      } catch (e) {
        toast(`狀態查詢失敗：${e.message || e}`, { level: "error" });
        setButtonsDisabled(false);
      }
    }, POLL_INTERVAL_MS);
  }

  async function onJobComplete(status) {
    // 1. last_error → toast 紅字
    if (status.last_error) {
      toast(`刷新失敗：${status.last_error}`, { level: "error" });
      setButtonsDisabled(false);
      if (window.StockETF) window.StockETF.renderSourceBadge();
      return;
    }

    // 2. re-fetch data files
    try {
      const pricesRes = await fetch("data/prices_today.json", { cache: "no-store" });
      if (pricesRes.ok && window.state) {
        window.state.prices = await pricesRes.json();
      }
      // 若是 etfs job，也 reload latest.json
      if (status.last_result && status.last_result.job === "etfs") {
        const latestRes = await fetch("data/latest.json", { cache: "no-store" });
        if (latestRes.ok && window.state) {
          window.state.payload = await latestRes.json();
        }
      }
    } catch (e) {
      toast(`資料重載失敗：${e.message || e}`, { level: "error" });
    }

    // 3. re-render badge + main table
    if (window.StockETF) window.StockETF.renderSourceBadge();
    if (typeof window.render === "function") window.render();

    // 4. partial failures / missing → 合併 toast
    const r = status.last_result || {};
    const msgs = [];
    if (r.missing_count) {
      msgs.push(`${r.missing_count} 檔股票今日抓不到`);
    }
    if (r.partial_failures && r.partial_failures.length) {
      const issuers = r.partial_failures.map(p => p.issuer).filter(Boolean);
      msgs.push(`${issuers.join("、")} 爬蟲失敗，相關 ETF 用前一天資料`);
    }
    if (msgs.length) {
      toast("⚠️ " + msgs.join("；"), { level: "warn" });
    }

    setButtonsDisabled(false);
  }

  function init() {
    document.getElementById("btn-refresh-prices")
      ?.addEventListener("click", () => startJob("/api/refresh/prices"));
    document.getElementById("btn-refresh-etfs")
      ?.addEventListener("click", () => startJob("/api/refresh/etfs"));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
```

- [ ] **Step 2: 加 script tag 到 index.html**

把 `<script src="assets/refresh.js"></script>` 加到 script 區塊的 toast.js 後面：

```html
<script src="assets/toast.js"></script>
<script src="assets/refresh.js"></script>
<script src="assets/app.js"></script>
<script src="assets/ranking.js"></script>
<script src="assets/positions.js"></script>
<script src="assets/markdown_view.js"></script>
```

- [ ] **Step 3: app.js 補 export `state` 和 `render` 給 refresh.js 用**

`assets/app.js` 開頭找到 `const state = ...` 那行（應該在最上面）。加 alias：

```javascript
const state = { /* 既有內容 */ };
window.state = state;   // 給 refresh.js 用
```

末尾找到 `function render()` 定義之後加：

```javascript
window.render = render;   // 給 refresh.js 用
```

- [ ] **Step 4: 手動驗證 — 完整流程**

```bash
.venv/Scripts/python.exe scripts/web_server.py 8000
```

打開 http://localhost:8000：
1. 按「🔄 股價」→ 兩按鈕灰掉、徽章變 ⏳；10-30 秒後變回正常徽章 + 表格自動更新
2. 按「🔄 ETF」→ 同流程，1-2 分鐘
3. 連按兩下「🔄 股價」（在第一個還沒跑完時）→ 第二個顯示 toast「⏳ 已有任務在跑」（或被 disabled 擋掉）

- [ ] **Step 5: Commit**

```bash
git add assets/refresh.js index.html assets/app.js
git commit -m "feat(ui): refresh buttons with polling + auto reload + toasts"
```

---

## Task 20: docs/VERIFY.md — 加手動驗收章節

**Files:**
- Modify: `docs/VERIFY.md`

- [ ] **Step 1: 加章節**

在 `docs/VERIFY.md` 末尾加：

```markdown

## 強制刷新按鈕驗收（v1.5.x）

### 前置
1. 跑一次 `update.bat`（會啟動 web_server）
2. 開瀏覽器到 http://localhost:8000

### 預期行為

**1. 開頁初始狀態：**
- header 副標看到「更新於 2026-XX-XX HH:MM · 🟢 FinMind 🔄 股價 🔄 ETF」
- 徽章顏色取決於 main.py 跑時哪家 provider 成功（🟢/🟡/🔵/🔴 之一）
- hover 徽章看到 tooltip：「抓取於 ... · N 檔抓不到」

**2. 按「🔄 股價」：**
- 兩按鈕立即灰掉
- 徽章變 `⏳ 抓取中...`
- 10-30 秒後 → 徽章變新顏色（最快通常 🟢 FinMind / 🟡 yfinance）
- 表格「收盤」「漲跌%」欄自動更新（不用 F5）
- 按鈕重新可按

**3. 連按 N 次「🔄 股價」直到 FinMind 配額爆：**
- 約第 600 次（匿名）/ 第 6000 次（token）後
- 徽章退到 🟡 yfinance
- 同 server process 內後續刷新都不再試 FinMind（直到 server 重啟）

**4. 拔網路 + 按按鈕：**
- 徽章 🔴 cache only
- toast 紅字「刷新失敗：...」

**5. 按「🔄 ETF」：**
- 兩按鈕灰掉、徽章 ⏳
- 1-2 分鐘流程
- 跑完表格 + ETF chip-bar 都更新
- 若有發行商失敗 → toast 黃字「⚠️ 元大、富邦爬蟲失敗，相關 ETF 用前一天資料」

**6. 同時按兩個按鈕：**
- 第一個正常啟動
- 第二個 → toast 藍字「⏳ 已有任務在跑」
- (UI 上 buttons 已 disabled，理論上點不到，這是 race condition 防護)

**7. Layout 對調驗收：**
- tabs（交叉持股 / ETF 總覽 / ...）在上
- ETF chip-bar（0050 / 00980A / ...）在下
- tab 切換 + chip 點擊功能正常

### 故障排除
- 徽章一直 ❓ 未知 → `prices_today.json` 沒 `source` 欄（舊格式），跑一次 main.py 就會更新
- 按鈕沒反應 → DevTools console 看有沒有 JS error，常見是 `window.state` undefined（app.js 沒 export）
- toast 沒出現 → 確認 `<script src="assets/toast.js">` 在 `app.js` 之前
```

- [ ] **Step 2: Commit**

```bash
git add docs/VERIFY.md
git commit -m "docs: VERIFY.md adds refresh-button manual acceptance section"
```

---

## 完成條件

跑這條：

```bash
pytest tests/ -v
```

預期：所有測試通過（含本 plan 新增的 ~20 個測試）。

接著手動跑 `docs/VERIFY.md` 新章節的 7 個驗收步驟，全綠 = 完成。

---

## 已知遺留 / 後續

- 註冊 FinMind sponsor token 解鎖 bulk-by-date（不在本 plan 範圍）
- 把 `data/prices_today.json` 加到 `.gitignore` 還是繼續 commit？目前繼續 commit（與專案慣例一致：`data/` 都進 git）
- README.md 加 header 截圖：本 plan 不做，下次有 UI 大改動一起更新
