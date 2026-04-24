# StockETF — Claude 專案指引

> 給未來開啟這個專案的 Claude（不管是新對話、新電腦）看的。讀這份文件 2 分鐘就能上手。

## 專案一句話

台灣 ETF 交叉持股分析網站。爬 3 家發行商的持股資料 → 合併成 JSON → 靜態 HTML 前端呈現交叉分析表。部署目標是 GitHub Pages。

## 現在的狀態

- **分支**：`feat/mvp-v1`（MVP v1 完成，tag `v1.0.0-mvp`）
- **主線 main**：只有 spec + plan，沒有實作
- **v1 範圍**：4 檔 ETF（0050、0056、00980A、00981A），手動執行 `python main.py`，靜態前端
- **v2 範圍（尚未動工）**：GitHub Actions 排程、F4 ETF 總覽、F9 手機 RWD、擴充到 8-10 檔
- **v3 範圍（尚未動工）**：F5 持股變動歷史、F7 CSV 匯出、F8 FB 分享圖、AdSense

## 使用者背景（重要）

- 曾寫過 C#、C++（10 年前），Python 和現代 JS 較陌生
- 這專案動機是 **A 個人自用 + B 朋友社群分享（FB 導流）+ D 學習作品**
- 不做 **F6 使用者帳號 / 留言**（刻意排除，保持靜態站簡單）
- 用繁體中文回覆

## 關鍵文件（依重要性）

| 文件 | 用途 |
|---|---|
| `docs/superpowers/specs/2026-04-24-...-design.md` | 設計規格（what + why）|
| `docs/superpowers/plans/2026-04-24-stocketf-mvp-v1.md` | MVP v1 的 12 個實作 task |
| `docs/ARCHITECTURE.md` | 架構 tutorial（每個模組的職責 + 資料流） |
| `docs/SCRAPING.md` | 資料源發現方法論（加新 scraper 照這份走）|
| `docs/VERIFY.md` | 本機驗證步驟（跑測試、跑爬蟲、開網頁）|
| `README.md` | Quickstart、部署、UI 手動驗收清單 |

如果 user 的問題涉及「為什麼這樣設計」，優先查 spec。涉及「某個步驟怎麼做」，查 plan。涉及「我要加新功能」，先看 ARCHITECTURE 和 SCRAPING。

## 工程慣例（已經決定、請遵守）

### Python (scrapers + pipeline)
- **TDD**：寫測試 → 紅 → 實作 → 綠 → commit
- **測試用 fixtures 離線跑**，不打真實網路（`tests/fixtures/*.html|.json`）
- **爬蟲失敗要 fail loudly** — 所有解析器在結構異常時 raise `ValueError("... page structure may have changed ...")`
- **單點失敗不影響全局** — `main.py` 某一家爬蟲失敗會 fallback 到前一天的資料，不 crash 整個 build
- **BaseScraper 統一 HTTP** — 不直接用 `requests.session.get/post`，一律走 `self.get()` / `self.post()`（帶重試）
- **禮貌爬蟲** — User-Agent `StockETF-Bot/1.0`、請求間隔 2 秒、失敗 exponential backoff
- **Taiwan 時區** — `ZoneInfo("Asia/Taipei")`，不用 `date.today()`（會拿系統時區）

### 前端
- **無框架** — 原生 HTML + CSS + ES6 JS，不上 React/Vue
- **無建置步驟** — 直接瀏覽器載入，不走 webpack
- **escapeHtml 每個 user-visible 字串** — 即使資料源是 trusted JSON 也要（一致性）
- **state + render 模式** — 改狀態 → 呼叫 `render()` 重繪整個表格，不做細粒度 DOM diff

### 資料
- **JSON 存在 git 裡** — `data/latest.json` 和 `data/snapshots/YYYY-MM-DD.json` 都 commit
- **append-only 歷史** — snapshots 舊檔不動，每天新增一份
- **tags / color 走 config** — `config/etfs.yml` 手動維護，爬蟲不自動「猜」
- **`updated_at` 不騙人** — 如果用了 fallback 資料，要保留前次的 timestamp

### Git
- **commit 訊息風格**：`feat(xxx): ...` / `fix(xxx): ...` / `docs: ...` / `data: ...` / `scaffold: ...`
- **單一 commit 一個目的**
- **v1 的 branch：`feat/mvp-v1`** — 還沒 merge 到 main，等 v1 完全穩定後再 merge

## 不要做的事（YAGNI / 範圍外）

- ❌ 使用者帳號、留言系統（F6，被刻意排除）
- ❌ 即時股價、K 線圖、技術指標
- ❌ 投資組合模擬、回測
- ❌ 多語系（中文就夠）
- ❌ 券商下單連結（法規風險）
- ❌ PWA / App
- ❌ 引入重框架（React、Vue、jQuery）— 純 JS 就夠
- ❌ 測試 `BaseScraper.get/post` 的重試邏輯（plan 刻意排除，不值得 mock）
- ❌ 從第三方聚合站（pocket.tw、cmoney.tw、goodinfo）抓資料 — **只從發行商官網**

## 跨電腦工作流（給使用者）

這專案會在家裡和公司兩台電腦輪流開發。慣例：
- **開工**：`git checkout feat/mvp-v1 && git pull && .venv\Scripts\activate`
- **收工**：`git add . && git commit -m "..." && git push`
- **忘記 push**：到另一台電腦 pull 不到 → 回去先 push

`.venv/` 和 `.claude/settings.local.json` 是每台電腦獨立的（不跟著 git），要重建：
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 使用者啟動新對話時的標準流程

1. 先 `git log --oneline | head -10` 看最近 commit 狀態
2. 看 `docs/superpowers/plans/*.md` 看上次 plan 到哪
3. 如果是新功能請求 → 先 brainstorming skill 再動手
4. 如果是 bug / 小改動 → 直接動手但遵守 TDD + fail-loudly
