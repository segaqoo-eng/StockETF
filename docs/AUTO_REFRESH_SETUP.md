# 自動每日刷新設定（Windows Task Scheduler）

`update.bat` 已支援 **headless 模式**（環境變數 `SKIP_PAUSE=1`）—
不會啟動本機網站、不會開瀏覽器、跑完直接結束。
這正是 Task Scheduler 想要的行為。

## 設定步驟

### 1. 開「工作排程器」

按 `Win` 鍵 → 輸入「工作排程器」（Task Scheduler）→ 開啟。

### 2. 建立基本工作

右側「動作」面板 → **建立基本工作**（不是「建立工作」，那個是進階版）。

### 3. 一般

- **名稱**：`StockETF 每日更新`
- **描述**：`收盤後抓 ETF 持股 + 跑回測 + 產生貼文摘要`

### 4. 觸發程序

選 **每天**，按下一步：
- **開始時間**：`14:00:00`（台股 13:30 收盤後）
- **每隔 1 天發生一次**

> 為何 14:00？台股 13:30 收盤，發行商更新持股資料約需 30 分鐘。
> 14:00 通常已可抓到當日收盤後資訊。

### 5. 動作

選 **啟動程式**：
- **程式或指令碼**：`C:\Users\User\source\repos\StockETF\update.bat`
- **新增引數**：（留空）
- **開始位置**：`C:\Users\User\source\repos\StockETF`

> 「開始位置」很重要！update.bat 的 `cd /d "%~dp0"` 雖然會自動切到 .bat
> 所在目錄，但 Task Scheduler 預設工作目錄是 `C:\Windows\System32`，
> 寫死「開始位置」比較保險。

### 6. 完成 → 勾「按下完成時開啟對話方塊以檢視屬性」

進「屬性」對話框，調整這幾個欄位：

#### 一般 tab
- ✅ **使用最高權限執行**（避免某些情況下檔案讀寫權限問題）
- 「設定」選 **Windows 10**

#### 條件 tab
- ☐ **只有在電腦使用 AC 電源時才啟動**（如果是桌機可不勾，筆電建議勾）
- ☐ **如果電腦切換到電池電源，停止工作**（同上）
- ✅ **喚醒電腦執行此工作**（可選 — 排程時間到會把電腦喚醒；不勾則需電腦本來就開著）

#### 設定 tab
- ✅ **如果工作排定的時間已到，立即啟動工作**（電腦關機時錯過會在開機後補跑）
- ✅ **若工作執行失敗，重新啟動工作**：每 30 分鐘 / 嘗試 3 次
- ✅ **如果工作執行時間超過下列時間則停止**：`1 小時`（防止網路卡住卡到下次觸發）
- 「如果此工作的執行個體已經在執行：**不啟動新的執行個體**」

### 7. 設定環境變數 SKIP_PAUSE

Task Scheduler 沒有直接設定環境變數的 UI，要用包裝方式。建立 `update_scheduled.bat`（與 update.bat 同層）：

```bat
@echo off
set SKIP_PAUSE=1
call "%~dp0update.bat"
```

然後把 Task Scheduler 動作改指向 `update_scheduled.bat`。

> 不放在 update.bat 內是因為手動執行時想看 server + 瀏覽器，
> 排程才需要 headless。

### 8. 設定環境變數 FINMIND_TOKEN（可選但強烈建議）

如果你已註冊 FinMind 帳號取得 token，在 update_scheduled.bat 多一行：

```bat
@echo off
set SKIP_PAUSE=1
set FINMIND_TOKEN=eyJ0eXAiOiJKV1Q...你的 token
call "%~dp0update.bat"
```

> 請勿把 token 放進 git。`update_scheduled.bat` 已被 .gitignore 排除（如果還沒，加上）。

## 驗證

- 右鍵點工作 → **執行** — 立刻跑一次，不等排程
- 看 `logs/update_YYYY-MM-DD.log` 是否有完整輸出
- 看 `data/snapshots/YYYY-MM-DD.json` 是否有今天的快照
- 看 `status_today.md` 是否更新

如果失敗，「上次執行結果」欄會顯示錯誤碼（0x0 = 成功，其他都要進去查 log）。

## 故障排除

| 症狀 | 原因 | 解法 |
|---|---|---|
| 跑完日誌全是亂碼 | cmd cp950 解析 .bat 中文 | update.bat 已純 ASCII，若你改過要還原 |
| 跑完有 `卡住沒退出` | 漏設 `SKIP_PAUSE=1` | 確認 update_scheduled.bat 第一行有 `set SKIP_PAUSE=1` |
| `[FAIL] see logs\update...` | scraper 失敗 | 看 log 找哪家發行商網站變了，回 `docs/SCRAPING.md` 排查 |
| 0050 等股票「無資料」| FinMind 配額用完 | 加 FINMIND_TOKEN 提升到 6000/hr，或讓 yfinance fallback 接手 |
| 排程時間到沒跑 | 「使用最高權限」沒勾 / 條件勾太多 | 對照第 6 步的設定 |

## 停用排程

工作排程器 → 找到 `StockETF 每日更新` → 右鍵 → **停用**（保留設定，可隨時啟用）
或 **刪除**（永久移除）。
