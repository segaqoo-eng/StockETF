# StockETF

台灣 ETF 交叉持股分析工具（v1 MVP）。

## 快速開始（新電腦 / 換電腦）

**Step 1：下載專案**
```
git clone https://github.com/segaqoo-eng/StockETF.git
cd StockETF
```

**Step 2：一鍵安裝（雙擊 or 執行）**
```
init.bat
```
自動建立虛擬環境 + 安裝所有套件，完成後會顯示常用指令。

---

## 常用指令

**一鍵更新（推薦）**：雙擊 `update.bat`，自動執行：
1. 抓 ETF 持股 (`main.py`)
2. 跑 5 種策略回測 (`backtest.py`)
3. 產生貼文摘要 (`scripts/generate_status.py` → `status_today.md`)
4. 啟動本機網站 + 開瀏覽器

**設定每日自動刷新（不用記得每天跑）**：見 [docs/AUTO_REFRESH_SETUP.md](docs/AUTO_REFRESH_SETUP.md)

**手動跑單一步驟**：

```bash
.venv\Scripts\python.exe main.py        # 更新持股
.venv\Scripts\python.exe backtest.py    # 回測
.venv\Scripts\python.exe -m http.server 8000   # 看網站
```

---

## 手動安裝（舊方式）

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

Fetch data once (takes ~15 seconds, hits 3 issuer sites):

```bash
python main.py
```

Run tests to confirm everything works:

```bash
pytest -v
```

Serve the site locally:

```bash
python -m http.server 8000
```

Open http://localhost:8000/ in a browser. (Leave the server running; Ctrl+C to stop.)

## Deploying to GitHub Pages

1. Push this repo to GitHub (public repo recommended — GitHub Pages is free for public).
2. On GitHub: Settings → Pages → Source: `main` branch, `/` (root) → Save.
3. Wait ~1 minute; site appears at `https://<your-user>.github.io/StockETF/`.

To refresh data:

```bash
update.bat              # 一鍵全跑 (持股 + 回測 + 摘要 + 開網站)
git add data/
git commit -m "data: update $(date +%Y-%m-%d)"
git push
```

每日自動排程見 [docs/AUTO_REFRESH_SETUP.md](docs/AUTO_REFRESH_SETUP.md)。

## Project layout

- `scrapers/` — per-issuer HTML parsers (Yuanta, Nomura, Capital, ...)
- `normalizer.py` — merges scraped data + config into `data/latest.json`
- `main.py` — orchestrator; handles per-ETF failures by reusing previous data
- `data_provider.py` — SQLite cache + multi-source (FinMind / yfinance) fallback for backtest
- `backtest.py` — multi-strategy backtester with cost deduction + 0050 benchmark
- `scripts/generate_status.py` — produces `status_today.md` from latest data
- `update.bat` — one-click update orchestrator (supports headless mode for Task Scheduler)
- `config/etfs.yml` — which ETFs to track; tags and color per ETF
- `config/stocks.yml` — industry mapping (optional enrichment)
- `index.html` + `assets/` — static frontend
- `docs/VERIFY.md` — local verification steps
- `docs/AUTO_REFRESH_SETUP.md` — Windows Task Scheduler setup
- `docs/STRATEGY.md` — 便當 5 策略決策紀錄與實戰指南
- `scripts/portfolio_sim.py` — 資金管理模擬（驗證 + 比較不同策略）
- `scripts/my_status.py` — 實際持倉追蹤 + 回本進度

## Tests

```bash
pytest -v
```

Scraper tests use saved HTML/JSON fixtures in `tests/fixtures/` so they don't hit live sites.

## Manual UI checklist

After running `python main.py` and `python -m http.server 8000`, open http://localhost:8000/ in a browser and verify:

- [ ] Dark theme loads, header shows "更新於 YYYY-MM-DD HH:MM"
- [ ] Tab bar shows "交叉持股" (active), "ETF 總覽" (disabled), "持股變動" (disabled)
- [ ] Main table first row is 聯發科 (2454) with count badge "4"
- [ ] Filter "最少被持有 4 檔以上" narrows table to ~4 rows
- [ ] Industry dropdown lists values like "半導體", selecting narrows the table
- [ ] Search "2330" narrows to 台積電
- [ ] Click any row → a detail row appears below listing each ETF and weight; click again → it collapses
- [ ] No errors in the browser console (F12 → Console)

## 免責聲明

本網站資訊僅供參考，不構成投資建議。

## License

MIT — see [LICENSE](LICENSE).

## Credits

UI concept inspired by [zhaoyuanliu/etf-analysis](https://zhaoyuanliu.github.io/etf-analysis/).
All scraping, normalization, and frontend code is original to this project.
