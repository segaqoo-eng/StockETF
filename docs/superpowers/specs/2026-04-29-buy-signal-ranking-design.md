# 買進評分排行榜 — 設計規格

**日期：** 2026-04-29
**狀態：** 已確認，待實作

---

## 一句話

在 `index.html` 新增「買進評分」tab，列出所有 ETF 持股的技術 + 籌碼綜合分數排行，並顯示熱門話題 TAG 統計。

---

## 使用情境

使用者早上或下午開網站，想知道「這些 ETF 持股裡，現在哪幾支最值得關注？」不需要逐一點入個股頁面，直接在排行榜看全貌。

---

## 功能範圍

### 在 scope
- `index.html` 新增第二個 tab「買進評分」
- 熱門話題 TAG 統計區塊（排名前 20 內的 TAG 頻率）
- 排行榜表格：前 20 筆預設顯示，「展開顯示全部 104 筆」按鈕
- 漸進式載入：逐支抓取，即時插入，有進度條
- localStorage 快取（key = `scores_YYYY-MM-DD`）
- 下午 2 點前開啟 → 使用昨天的快取；下午 2 點後 → 重新抓取

### 不在 scope
- GitHub Actions 自動排程（之後做）
- Facebook / LINE 自動發文（之後做）
- SQLite 本機儲存（純前端 localStorage 即可）
- 個股頁面 (stock.html) 的改動

---

## 資料來源

與現有 `stock.js` 相同：
- **K線 OHLCV**：FinMind `TaiwanStockPrice`（3 個月，日K）
- **三大法人**：FinMind `TaiwanStockInstitutionalInvestorsBuySell`（2 個月）
- **TAG / 持有 ETF / 收盤價**：`data/latest.json` + `data/prices_today.json`（已有）

每支股票 2 次 API call × 104 支 = 208 次。FinMind 免費額度 500次/天，安全。

---

## 快取策略

```
localStorage key: "scores_2026-04-29"
value: JSON array，每個元素 = { stock_id, score, recommendation, signals, ... }

開啟 tab 時：
  1. 取得台灣時間（Asia/Taipei）
  2. 判斷現在是否 >= 14:00
     - 是 → cacheKey = 今天日期
     - 否 → cacheKey = 昨天日期
  3. localStorage.getItem(cacheKey) 有資料 → 直接渲染
  4. 沒資料（含第一次使用、昨天也沒快取）→ 不管時間，直接抓取
```

快取 key 只保留最近 2 天，舊的清除（避免 localStorage 滿）。

---

## UI 設計

### Tab 列
```
[交叉持股]  [買進評分]
```
點選「買進評分」才觸發資料載入（lazy load）。

### 熱門話題區塊
```
熱門話題（前20名持股中）：
[AI ×8]  [半導體 ×6]  [網通 ×4]  [伺服器 ×3]  ...
```
chip 樣式，依出現次數排序，顏色沿用現有 concept tag 配色。

### 進度條（載入中）
```
抓取股價中… 23 / 104
[████████░░░░░░░░░░░░] 22%
```
每抓完一支立刻插入排行（分數低的排後面），全部完成後重新排序。

### 排行榜表格

| 欄位 | 說明 |
|---|---|
| # | 排名 |
| 股票 | `2379 瑞昱`，可點擊進 stock.html |
| 分數 | 0–100，顏色：≥60綠、40-60黃、<40紅 |
| 建議 | 強買進 / 買進 / 觀望 / 減碼 / 強賣出 |
| 收盤 | 來自 `prices_today.json` |
| 漲跌 | +2.1% 紅色 / -1.3% 綠色（台股慣例） |
| TAG | 該股的 concept tags，最多顯示 3 個，超過顯示 `+N` |
| 持有ETF | 持有此股的 ETF 代號，用小 chip |

預設顯示前 20 筆，底部「展開顯示全部 104 筆」按鈕，點後顯示剩餘。

---

## 評分邏輯

沿用現有 `stock.js` 的 `computeScore(candles, instRows)`，不重複實作：
- `scoreTechnical()`：RSI、MACD、KD、均線排列（滿分 ±30）
- `scoreChip()`：三大法人近5日買賣超（滿分 ±30）
- `scoreVolumePrice()`：量價關係（滿分 ±20）
- `scoreTrend()`：60日新高/新低、MA20/MA60（滿分 ±20）
- 加底數 50，總分 0–100

---

## 檔案變動

| 檔案 | 變動 |
|---|---|
| `index.html` | 新增 tab UI、排行榜 HTML 骨架 |
| `assets/app.js` | 新增 `initRankingTab()`、快取邏輯、漸進載入 |
| `assets/stock.js` | **不動**，共用評分函數需 export 或 app.js 直接複製 |
| `assets/app.css` | 排行榜樣式（進度條、熱門 TAG、表格）|

> `stock.js` 的評分函數（`computeScore`、`_calcRSI` 等）目前是全域函數，`app.js` 載入後可直接呼叫，不需重構。

---

## 錯誤處理

- 單支股票 FinMind 失敗 → 跳過，不影響其他股票，該股顯示「無資料」
- 全部失敗（網路斷線）→ 顯示錯誤訊息，保留昨日快取繼續使用
- localStorage 超過 5MB → catch QuotaExceededError，降級為 session 記憶體快取

---

## 成功標準

1. 點「買進評分」tab，有進度條出現
2. 逐步顯示排行，不需等全部完成
3. 同一天第二次開 tab，立刻顯示（不重抓）
4. 下午 2 點前開啟，使用昨日資料（有提示）
5. TAG 統計正確反映前 20 名的 tag 分佈
6. 可展開看全部 104 筆
