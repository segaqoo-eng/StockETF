# 群益 scraper 已知限制

## 問題

`capitalfund.com.tw` 的完整持股 JSON 存於內網 API（`125.227.3.107`），外網無法存取。SSR HTML 僅提供前 10 大持股；客戶端「展開全部」按鈕觸發的 fetch 走的是無法從外部到達的 endpoint。

## 現況

`scrapers/capital.py` 目前只抓 SSR top-10（約佔總權重 60-70%）。

影響範圍：
- 00982A 主動群益台灣強棒（總共約 58 檔，抓到 10 檔）
- 00992A 主動群益科技創新（總共約 41 檔，抓到 10 檔）

跨持股分析仍可運作（top-10 通常是經理人最重押的部位，訊號最強），但完整資料還是要靠後續升級。

## 未來改進選項

- **選項 A**：找到 `FileMapping.json` 正確路徑後直接 fetch JSON  
  pattern: `/JsonData/Hourly/ETFBuyback/{fundId}_{timestamp}.json`  
  目前 mapping 內的時間戳已過期 3 個月（檔案被 rotate 但 mapping 沒更新）
- **選項 B**：用 Playwright 跑真實瀏覽器，等 Angular hydration 完成後抓 DOM  
  缺點：跑爬蟲變重，破壞 fixture 離線測試的單純性
- **選項 C**：使用者手動下載 xlsx 放到 `data/manual/capital_{ticker}.xlsx`，scraper 優先讀本地檔，沒有才 fallback 到 SSR top-10  
  優點：完全可控；缺點：失去自動化

## Discovery 中間產物（未 commit；在 `tmp/`）

下次有人想接續找完整資料來源，可以從這些抽出來的 bundle 開始看：

- `tmp/main.js`（2.4 MB Angular 主 bundle）
- `tmp/chunk_44.js`、`tmp/chunk_494.js`（portfolio + buyback 元件）
- `tmp/file_mapping.json`（過期 mapping，可觀察 URL pattern）

這些檔案在 `.gitignore` 的 `tmp/` 規則內，不會被 commit；要重抓就重跑 discovery script。
