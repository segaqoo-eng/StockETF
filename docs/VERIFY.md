# 驗證步驟（後端 pipeline v1）

## 啟動環境

```powershell
cd C:\Users\User\source\repos\StockETF
.venv\Scripts\activate
```

成功後提示字首會多 `(.venv)`。

## 1. 跑測試（驗證 code 邏輯）

```powershell
pytest -v
```

預期：8 passed
- test_base.py × 2（Holding dataclass）
- test_yuanta.py × 2（0050、0056 parser）
- test_nomura.py × 1（00980A parser）
- test_capital.py × 1（00981A parser）
- test_normalizer.py × 2（聚合 + 排序）

## 2. 跑爬蟲（驗證真的能上網）

```powershell
python main.py
```

預期（約 10-20 秒）：
```
[FETCH] 0050 via yuanta...
  ok: 50 holdings
[FETCH] 0056 via yuanta...
  ok: 49 holdings
[FETCH] 00980A via nomura...
  ok: 51 holdings
[FETCH] 00981A via capital...
  ok: 52 holdings

Wrote data/latest.json (4 ETFs, 124 unique stocks)
```

## 3. 看產出資料

用編輯器打開 `data/latest.json`。
快照存在 `data/snapshots/YYYY-MM-DD.json`，每天 append 一份。

原始爬蟲快照在 `tests/fixtures/`：
- `yuanta_0050.html` / `yuanta_0056.html` — Nuxt.js SSR
- `nomura_00980A.json` — 野村 API 回傳（最乾淨）
- `capital_00981A.html` — 統一投信，JSON 塞在 `<div data-content>`

## 常見錯誤

| 症狀 | 解 |
|---|---|
| `pytest: command not found` | 忘記 `.venv\Scripts\activate` |
| `ImportError: No module named requests` | 同上 |
| 某檔 FAIL | 官網當下不穩，等 1 分鐘再跑 |
| `ZoneInfoNotFoundError: Asia/Taipei` | `pip install tzdata` |

## 資料來源速查

| ETF | 發行商 | 資料來源 |
|---|---|---|
| 0050, 0056 | 元大投信 | `yuantaetfs.com/product/detail/<ticker>/ratio`（Nuxt SSR） |
| 00980A | 野村投信 | `nomurafunds.com.tw/API/ETFAPI/api/Fund/GetFundAssets`（POST） |
| 00981A | 統一投信 | `ezmoney.com.tw/ETF/Fund/Info?FundCode=49YTW` |
