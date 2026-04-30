# StockETF

台灣主動式 ETF 交叉持股分析工具（v1.6）。

## 快速開始（新電腦 / 換電腦從零安裝）

### 前置需求
- **Windows**（專案目前只測過 Windows）
- **Python 3.12**（[官網下載](https://www.python.org/downloads/)，安裝時記得勾選「Add Python to PATH」）
- **Git**（[git-scm.com/download/win](https://git-scm.com/download/win)）

### Step 1：下載專案
```bat
cd %USERPROFILE%\source\repos
git clone https://github.com/segaqoo-eng/StockETF.git
cd StockETF
```

### Step 2：一鍵建環境（雙擊 or cmd 執行）
```bat
init.bat
```
自動建 `.venv` 虛擬環境 + 裝 `requirements.txt` 所有套件。完成後會顯示常用指令。

### Step 3：一鍵抓資料 + 開網站
```bat
update.bat
```
跑完瀏覽器自動開到 `http://localhost:8000`。第一次跑可能 1-2 分鐘（爬 7 家發行商）。

### 跨電腦工作流（家裡 ↔ 公司）
```bat
git pull              :: 開工：拿最新 code + data
update.bat            :: 看當天最新分析
git add data/         :: 收工：commit 今天的資料
git commit -m "data: update %DATE%"
git push
```
`.venv\` 跟 `.claude\` 是每台電腦獨立的（不跟著 git），換電腦要重跑 `init.bat`。

---

## 常用指令

### 一鍵更新（推薦）
雙擊或 cmd 執行 `update.bat`，自動執行 3 步：
1. **`[1/3]`** 抓 ETF 持股 + 抓今日股價（`main.py`，走 4-tier provider chain：FinMind → yfinance → TWSE+TPEx → cache）
2. **`[2/3]`** 產生個人持倉報告（`scripts/my_status.py` → `my_status.md`）
3. **`[3/3]`** 啟動本機 web server + 開瀏覽器

> 💡 **注意**：v1.6 起 `update.bat` **不再跑回測**（太慢 + FinMind 容易爆配額）。回測改在網頁按「🔄 回測」按鈕**手動觸發**。

### 網頁按鈕（v1.6 新功能）
網頁 header 副標有 3 顆按鈕：
- **🔄 股價** — 重抓今日收盤（10-30 秒）
- **🔄 ETF** — 重抓 ETF 持股 + 股價（1-2 分鐘）
- **🔄 回測** — 跑 backtest + 產生 status_today.md + paper_status.md（2-5 分鐘）

旁邊的徽章顯示當前股價來源：🟢 FinMind / 🟡 yfinance / 🔵 TWSE+TPEx / 🔴 Cache（舊資料）。

### 手動跑單一步驟
```bat
.venv\Scripts\python.exe main.py                      :: 更新持股 + 股價
.venv\Scripts\python.exe backtest.py                  :: 回測
.venv\Scripts\python.exe scripts\web_server.py 8000   :: 啟動網站（含 API endpoints）
```

> ⚠️ 不要用 `python -m http.server 8000` — 那只是靜態檔伺服器，沒有 `/api/refresh/*` 等 endpoint，網頁按鈕不會動。

### FinMind Token（選用）
匿名用 600 calls/hour 對單機足夠。若想升級 6000/hour：
1. 註冊 [finmindtrade.com](https://finmindtrade.com/)
2. 拿 token 後 `setx FINMIND_TOKEN "你的token"`
3. 重開 cmd 跑 `update.bat`

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

### Backend
- `scrapers/` — per-issuer HTML parsers (Yuanta, Nomura, Capital, President, Fuhhwa)
- `scrapers/twse_prices.py` — TWSE + TPEx 每日收盤價 bulk fetcher
- `scrapers/daily_close.py` — **(v1.5)** 4-tier 股價 provider chain（FinMind → yfinance → TWSE+TPEx → cache）+ dispatch logic
- `normalizer.py` — merges scraped data + config into `data/latest.json`
- `main.py` — orchestrator；個別 ETF 失敗時 fallback 到前一天 snapshot
- `data_provider.py` — SQLite cache + multi-source (FinMind / yfinance) fallback for backtest
- `backtest.py` — multi-strategy backtester with cost deduction + 0050 benchmark

### Scripts
- `scripts/web_server.py` — **(v1.5)** 本機 web server，提供 `/api/positions` + `/api/refresh/{prices,etfs,backtest,status}` endpoints
- `scripts/tee.py` — **(v1.6)** Python tee wrapper（避免 PowerShell `Tee-Object` 在 PS 5.1 的 NativeCommandError 問題）
- `scripts/generate_status.py` — produces `status_today.md`
- `scripts/paper_trade.py` — paper 模擬交易，產 `paper_status.md`
- `scripts/my_status.py` — 實際持倉追蹤 + 回本進度，產 `my_status.md`
- `scripts/portfolio_sim.py` — 資金管理模擬

### Frontend
- `index.html` + `assets/style.css` — 主頁
- `assets/app.js` — 主邏輯、交叉持股表、徽章 render
- `assets/refresh.js` — **(v1.5)** 強制刷新按鈕邏輯 + polling
- `assets/toast.js` — **(v1.5)** 簡易 toast lib
- `assets/ranking.js` — 「買進評分」tab
- `assets/positions.js` — 「我的部位」tab
- `assets/markdown_view.js` — 「今日訊號」/「Paper 模擬」tab（讀 `.md` 渲染）

### Config & docs
- `config/etfs.yml` — 追蹤哪幾檔 ETF；tags 跟顏色
- `config/stocks.yml` — 產業分類（optional）
- `update.bat` — 一鍵更新（v1.6: 3 步流程，已分離回測）
- `init.bat` — 一鍵建環境
- `docs/VERIFY.md` — 本機驗收清單
- `docs/SCRAPING.md` — 爬蟲開發方法論
- `docs/ARCHITECTURE.md` — 模組職責與資料流
- `docs/STRATEGY.md` — 便當 5 策略決策紀錄

## Tests

```bash
pytest -v
```

Scraper tests use saved HTML/JSON fixtures in `tests/fixtures/` so they don't hit live sites.

## Manual UI checklist

跑完 `update.bat` 後，瀏覽器自動開到 `http://localhost:8000`。驗收：

### Header
- [ ] 看到「更新於 YYYY-MM-DD HH:MM · 🟢 FinMind / 🟡 yfinance / 🔵 TWSE+TPEx」徽章
- [ ] 三顆按鈕：🔄 股價 / 🔄 ETF / 🔄 回測
- [ ] hover 徽章看到 tooltip：「抓取於 ... · N 檔抓不到」

### Tabs（8 個）
- [ ] 交叉持股、ETF 總覽、各 ETF 持股變化、共識加減碼、買進評分、📋 今日訊號、📈 Paper 模擬、💰 我的部位

### 交叉持股 tab（預設）
- [ ] 表格顯示前幾名跨 ETF 持有的個股
- [ ] 篩選「最少被持有 N 檔以上」會縮小範圍
- [ ] 點任一列展開明細（顯示每檔 ETF 持有此股的權重）

### Refresh 按鈕（v1.5/v1.6）
- [ ] 按「🔄 股價」→ 兩按鈕灰掉、徽章變 ⏳ → 10-30 秒後表格自動更新
- [ ] 按「🔄 回測」→ 等 2-5 分鐘 → 「買進評分」tab 點進去看到新資料
- [ ] 同時間只允許一個 job（第二個會 toast「已有任務在跑」）

### 不該出現的東西
- [ ] DevTools console 沒紅字 (F12 → Console)
- [ ] 跑 `update.bat` 時 cmd 視窗沒有 PowerShell `NativeCommandError` 紅字
- [ ] yfinance 不會印「possibly delisted」噪音（v1.6 修了）

## 免責聲明

本網站資訊僅供參考，不構成投資建議。

## License

MIT — see [LICENSE](LICENSE).

## Credits

UI concept inspired by [zhaoyuanliu/etf-analysis](https://zhaoyuanliu.github.io/etf-analysis/).
All scraping, normalization, and frontend code is original to this project.
