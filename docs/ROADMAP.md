# StockETF — 待優化項目清單

> 紀錄日期 2026-04-27。做完的項目就從這裡刪掉，留下沒做的。
> 規模標記：**S** ≈ 半天內、**M** ≈ 1-2 天、**L** ≈ 3 天以上。

---

## v2 收尾（手邊還沒做完）

### 手機 RWD — **M**
**現況**：桌面 OK，手機（< 640px）三個問題 — chip 條 7 顆會排成 4 列佔太高、modal 表格 4 欄擠不下、filter 搜尋框 `min-width: 220px` 會撐爆 viewport。

**做法**：加 `@media (max-width: 640px)` 段，chip 收掉名稱只顯 ticker、modal 隱藏「股數」欄、搜尋框 `width: 100%`。CSS 大概 +30 行。

### snapshots/ 30 天保留 + 自動清理 — **S**
**現況**：snapshots 永遠累積在 git，30 天後 ~30 檔 × 150 KB ≈ 4.5 MB（可接受但會持續長）。

**做法**：`main.py` 跑完後加幾行 `for p in snapshots: if p.stem < cutoff_iso: p.unlink()`，30 天 cutoff。

### README 全面更新 — **S**
**現況**：README 還停留在 v1 MVP 描述（提 3 家 issuer / 4 檔 ETF / 沒提 chip bar / modal / diff / Actions / fuhhwa / 群益 manual xlsx）。新人來看 repo 會被誤導。

**做法**：重寫 Quickstart + Project layout + Manual UI checklist 三段。

---

## v3 ideas（功能擴充，已討論但沒動）

### 30 天歷史檢視 — **M**（C ✅ 已實作；A / B 待做）

| 方案 | 呈現 | 狀態 |
|---|---|---|
| A. **股票時光機** | 點股票 → 折線圖：每檔 ETF 對它的持股數 / 權重 30 天曲線 | ⬜ 需要 chart lib（建議 Chart.js） |
| B. **ETF 變動表** | 點 ETF → 表格：每檔成分股 30 天 weight 每日一欄 | ⬜ 純 HTML table |
| C. **重大變動排行榜** | 首頁過去 7 天加碼/減碼 TOP 5 | ✅ `compute_leaderboard()` + 前端 section |

### 個股技術分析 — **L**
點股票 → 顯示 K 線、量柱、MA / RSI / MACD 等。需要每檔 ~1 年 OHLCV，~3 MB 資料。

| 方案 | 成本 | 限制 |
|---|---|---|
| A. **自抓 + 自畫** — `yfinance` 每晚 cron 抓 OHLCV，前端用 Chart.js / Lightweight Charts | ~3 天 | 完全自主，任何 indicator 都能加 |
| B. **嵌 TradingView widget** — 點股票開 modal，塞 widget snippet | ~2 小時 | 版面 TradingView 風格、有 logo、客製空間小 |

建議 **B 先做**，嫌不夠看再考慮 A。

### 各 scraper 補抓 ETF metadata — ✅ 已實作（5/5）
**標準 schema**：`payload.etfs[i].fund_meta = {as_of_date, nav_total, units_outstanding, p_unit, asset_breakdown}`，每家 scraper 抓得到什麼填什麼，缺的就 omit key。框架在 `ScrapeResult.fund_meta`。

| Scraper | 抓到什麼 |
|---|---|
| president (統一) | 5 欄位全套 + asset_breakdown 4 類（股票 / 現金 / 期貨保證金 / 應收付）|
| fuhhwa (復華) | as_of_date + nav_total + units_outstanding + p_unit |
| nomura (野村) | as_of_date + nav_total + units_outstanding + p_unit（API 上 FundAsset 區塊）|
| yuanta (元大；0050/0056/00990A) | as_of_date + nav_total + units_outstanding + p_unit（NUXT PCF 區塊）|
| capital (群益；SSR top-10 路徑) | as_of_date + nav_total + units_outstanding + p_unit（manual xlsx 路徑尚未抓 — 需要實際 xlsx fixture）|

剩下小工：capital 的 manual xlsx PCF metadata 還沒抓（需要使用者實際下載一份 xlsx 才能寫 parser）。

### Cross-table per-stock aggregate diff badge — **S**
**現況**：diff 只在 ETF modal 內顯示。交叉表上的股票列沒有差異提示。

**做法**：聚合所有 ETF 的 diff，每檔股票算「今日新被 N 檔 ETF 持有」/「平均權重變化」，render 在表格列。

---

## 維護 / 衛生

### 群益 scraper 升級到 selenium-headless（option D）— **M**
**現況**：依賴使用者手動下載 xlsx。

**做法**：寫週末跑的 selenium 腳本，自動模擬瀏覽器點「下載資料」按鈕、把檔案 commit 上去。比 Playwright 輕但仍需 browser binary。手動流程嫌煩才考慮。

### 啟用 GitHub Pages — **S**
**現況**：repo public 但 Pages 沒開，朋友還看不到。

**做法**：`gh api -X POST repos/segaqoo-eng/StockETF/pages -f source[branch]=main -f source[path]=/`，~1 分鐘上線到 `https://segaqoo-eng.github.io/StockETF/`。

### 加 LICENSE 改本名 — **S**
**現況**：MIT LICENSE 的 copyright holder 是 GitHub 帳號 `segaqoo-eng`。如果想用本名（更正式），改一下文字就好。

---

## 不會做的（範圍外，記錄避免再討論）

- ❌ 真資料庫（sqlite / postgres）— 對靜態 GitHub Pages 部署 overkill；snapshots/ + git history 就夠
- ❌ 使用者帳號 / 留言 / 收藏 — F6，v1 spec 已刻意排除
- ❌ 即時股價（盤中即時）— 跟「ETF 持股分析」核心 use case 無關
- ❌ 重 SPA 框架（React / Vue）— 現在純 JS 夠用、無 build step
