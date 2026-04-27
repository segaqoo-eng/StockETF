# 群益 scraper — 完整持股操作手冊

## 背景：為什麼需要手動 xlsx

`capitalfund.com.tw` 完整持股 JSON 存於內網 API（`125.227.3.107`），外網無法存取。SSR HTML 僅 render 前 10 大持股；`/JsonData/Hourly/ETFBuyback/{fundId}_{ts}.json` 的 mapping 已過期 3 個月（檔案被 rotate 但 mapping 沒更新）。

JS bundle 內 `exportEtfPortfolio()` 是 client-side SheetJS 動態組 xlsx，沒對應 server URL 可抓。

→ **解法**：使用者手動下載官網 xlsx，scraper 優先讀本地檔。

## 操作流程

每隔幾天（建議週末或重大持股調整公告後），手動更新 xlsx：

### 1. 從官網下載

| ETF | URL |
|---|---|
| 00982A | https://www.capitalfund.com.tw/etf/product/detail/399/portfolio |
| 00992A | https://www.capitalfund.com.tw/etf/product/detail/500/portfolio |

進入頁面，點「**下載資料 ⬇**」按鈕（在表格右上方），會下載一個 `xxxxxx.xlsx`。

### 2. 改名 + 放到 `data/manual/`

檔名格式：`capital_{ticker}_{YYYYMMDD}.xlsx`

範例：
```
data/manual/capital_00982A_20260427.xlsx
data/manual/capital_00992A_20260427.xlsx
```

日期用「資料日期」（xlsx 內第三行 `日期: 2026/04/24` 那個），不是下載日期。

### 3. commit + push

```bash
git add data/manual/
git commit -m "data: refresh capital manual xlsx (YYYY-MM-DD)"
git push
```

下次（手動 trigger 或排程）執行 `python main.py` 時，scraper 自動讀最新 xlsx，full ~50 檔持股就會出現在 `data/latest.json` 與前端 modal。

## 行為細節

- **找檔邏輯**：`scrapers/capital.py: find_latest_manual_xlsx(ticker)` 撈 `data/manual/capital_{ticker}_*.xlsx`，取**檔名 YYYYMMDD 最大**的那個
- **xlsx 不存在** → 自動 fallback 到 SSR top-10 + log warning
- **xlsx 損毀** → raise ValueError → main.py per-ETF fallback 會用前一天的 `latest.json`（不會破整支 build）
- **多支 ETF 各自獨立** — 00982A 有 xlsx 但 00992A 沒有 → 00982A 完整、00992A top-10
- **沒上限頻率**：xlsx 一旦放著就會一直被讀，直到你放更新的；30 天前的 xlsx 也照吃，由你自己負責新鮮度

## 未來進一步自動化選項

- **選項 B（廢案）**：用 Playwright 跑真實瀏覽器、等 hydration → 太重，破壞 fixture 離線測試慣例
- **選項 D**：寫腳本固定週末用 selenium-headless 自動跑 xlsx 下載 + 自動 commit。比 Playwright 輕但仍需 browser binary。如果手動流程嫌煩再考慮

## 相關檔案

- `scrapers/capital.py` — 完整實作
- `tests/test_capital.py` — xlsx parser + 檔案 picker 單元測試
- `data/manual/.gitkeep` — 確保目錄被 git 追蹤
