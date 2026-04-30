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
- 若有發行商失敗，main.py 內部會 fallback 到前一天 snapshot；目前僅 console log 顯示，UI 上不會直接告知（v1.6 補強）

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
