# 個股分析頁面 — Design Spec

**Date:** 2026-04-28  
**Scope:** Phase 1 — 靜態資料展示，不含法人籌碼與技術指標

---

## 目標

交叉持股表中每支股票的名稱可點擊，開新分頁顯示個股分析頁面，整合 TradingView K 線圖與現有 ETF 持倉資料。

---

## 架構

### 新增檔案
- `stock.html` — 獨立頁面，透過 `?id=2330` query string 取得股票代號
- `assets/stock.js` — 個股頁面專用 JS（不汙染現有 app.js）

### 修改檔案
- `assets/app.js` — 交叉持股表股票名稱加上 `<a href="stock.html?id=2330" target="_blank">`
- `assets/style.css` — 沿用現有 CSS 變數（`--fs-*`、`--mono`、顏色）

### 資料來源（現有，不需新 scraper）
| 資料 | 來源檔案 |
|------|----------|
| 收盤價 / 漲跌% | `data/prices_today.json` |
| ETF 持倉 / 權重 | `data/latest.json` |
| 各 ETF 持倉走勢 | `data/history_per_stock.json` |
| weight diff | `data/latest_diff.json` |

---

## 頁面佈局

```
┌─ topbar ─────────────────────────────────────────┐
│ ← 返回交叉持股  |  StockETF 個股分析              │
├─ stock-header ───────────────────────────────────┤
│  2330  台灣積體電路製造                           │
│  550.00  ▲ +3.66%  (04-27 盤後)                  │
├─ main-layout (grid 60% / 40%) ───────────────────┤
│  LEFT: K 線圖               RIGHT: ETF 持倉表     │
│  TradingView Widget                  +走勢 sparkline│
│  (TWSE:2330 / TPEX:XXXX)            +法人籌碼預留  │
└──────────────────────────────────────────────────┘
```

---

## 元件細節

### 股票標頭
- 股票代號（大字 monospace）+ 名稱（次標）
- 收盤價 + 漲跌% + 漲跌方向（台灣慣例：紅漲綠跌）
- 資料日期 badge（價格 stale 時顯示黃色）

### K 線圖（左欄）
- TradingView Lightweight Widget（免費嵌入）
- symbol：上市用 `TWSE:{id}`，上櫃用 `TPEX:{id}`
- Exchange 判斷：從 `prices_today.json` 的 `exchange` 欄位取得
- theme: dark，locale: zh_TW，interval: D（日 K）
- 若 TradingView 載入失敗（無網路）顯示提示訊息

### ETF 持倉表（右欄上）
- 列出所有持有此股的 ETF：代號 / 名稱 / 權重% / 變化 badge
- 變化 badge 從 `latest_diff.json` 取 `changed` 陣列
- 按權重 desc 排序

### 持倉走勢 sparkline（右欄中）
- 複用現有 `drawStockTrend(stockId)` 函數邏輯
- 資料來源：`history_per_stock.json`

### 法人籌碼預留（右欄下）
- 黃色 coming-soon 區塊
- 文字：「外資 / 投信淨買賣超 — 即將推出」

---

## Exchange 欄位

`prices_today.json` 需在每筆加上 `exchange` 欄位：

```json
"2330": { "close": 550.0, "change": 19.5, "change_pct": 3.66, "exchange": "TWSE" }
"3037": { "close": 85.0, "change": -1.2, "change_pct": -1.39, "exchange": "TPEX" }
```

修改 `scrapers/twse_prices.py` 的 `PricesFetcher.fetch_all()` 分別標記 TWSE / TPEX 來源。

---

## 不在本次範圍
- 法人籌碼（Phase 2）
- 技術指標計算（Phase 3）
- 手機 RWD（另立計畫）
- K 線歷史資料自行儲存（TradingView widget 自行處理）
