# 把專案複製到另一台電腦

完整步驟，手動複製即可。從「來源電腦的準備」到「目標電腦可以繼續開發」。

> 用 VS Code 打開這個檔案 Ctrl+A 全選複製即可。
> 或用檔案總管找 `docs\TRANSFER.md`，用記事本打開也能讀。

---

## 一、來源電腦（目前這台）

### 步驟 1：確認所有改動都 commit 了

```powershell
cd C:\Users\User\source\repos\StockETF
git status
```

要看到「nothing to commit, working tree clean」才可以複製。
如果有沒 commit 的東西，先：
```powershell
git add .
git commit -m "wip: 準備轉移到另一台電腦"
```

### 步驟 2：清理不該帶走的大檔

```powershell
cd C:\Users\User\source\repos\StockETF

# 刪除 venv（幾百 MB，到另一台要重建）
Remove-Item -Recurse -Force .venv

# 刪除所有 Python 快取
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
Get-ChildItem -Recurse -Directory -Filter .pytest_cache | Remove-Item -Recurse -Force

# 如果 tmp 存在也刪
if (Test-Path tmp) { Remove-Item -Recurse -Force tmp }
```

**保留的：**
- `.git\` 資料夾（整個 git 歷史，**不能刪！**）
- 所有程式碼、文件、config

### 步驟 3：壓縮整個專案

```powershell
cd C:\Users\User\source\repos
Compress-Archive -Path StockETF -DestinationPath StockETF-portable.zip -CompressionLevel Optimal
```

產生 `StockETF-portable.zip`，可能 20-50 MB（看爬蟲 fixture 大小）。

### 步驟 4：傳到目標電腦

方法任選：
- USB 隨身碟
- OneDrive / Dropbox / Google Drive
- 區網共用資料夾
- 寄 email 給自己

---

## 二、目標電腦（新的那台）

### 步驟 1：安裝必要軟體（只有第一次要做）

**Python 3.12**：
- 下載：https://www.python.org/downloads/
- 安裝時 **務必勾選「Add Python to PATH」**

**Git for Windows**：
- 下載：https://git-scm.com/download/win
- 預設選項即可

**VS Code**（選用）：
- 下載：https://code.visualstudio.com/

**驗證安裝**：打開 PowerShell
```powershell
python --version    # 應看到 Python 3.12.x
git --version       # 應看到 git version 2.x
```

### 步驟 2：解壓專案到工作位置

例如 `C:\projects\` 或 `D:\dev\` 之下。解壓後應該看到：
```
C:\projects\StockETF\
├── .git\
├── .gitignore
├── README.md
├── CLAUDE.md
├── main.py
├── scrapers\
├── tests\
├── docs\
├── config\
├── index.html
├── assets\
├── data\
├── requirements.txt
└── normalizer.py
```

### 步驟 3：重建 Python 環境

```powershell
cd C:\projects\StockETF
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

pip install 會跑 1-2 分鐘（下載 requests、beautifulsoup4、pyyaml、pytest、tzdata）。

### 步驟 4：驗證一切正常

```powershell
# 測試（應看到 9 passed）
pytest -v

# 抓資料（應看到 4 個 ETF 都 ok）
python main.py

# 起 HTTP server 看網頁
python -m http.server 8000
```

另開瀏覽器 → http://localhost:8000/ → 應該看到 StockETF 深色主題網頁、表格正常顯示。

**Ctrl+C** 停掉 server。

### 步驟 5：確認 git 歷史完整

```powershell
git log --oneline | head -10
git status
git branch
```

應該：
- commit 歷史跟原本電腦完全一樣
- `* feat/mvp-v1` 被標記為目前分支
- working tree clean

---

## 三、在新電腦第一次開 Claude Code

1. 用 Claude Code 打開 `C:\projects\StockETF` 資料夾
2. Claude 會自動讀 `CLAUDE.md` → 2 分鐘理解狀況
3. 可能會跳權限請求（WebFetch、Bash 等）→ 你點 Allow
4. 跟它說：「**繼續 v1.5**」
5. 它會讀 `docs/superpowers/specs/2026-04-24-v1.5-active-etf-focus.md`，從階段 1 開始

**Memory 不會跟著走** — 個人記憶存在 `C:\Users\<你>\.claude\projects\...`（使用者目錄），不在專案裡。新電腦的 Claude 是空白記憶。但沒差，`CLAUDE.md` 已把關鍵都寫進去。

---

## 四、日常工作流（有設 GitHub 後才用）

等你哪天把這專案 push 到 GitHub 之後，兩台電腦可以自動同步：

**開工**：
```powershell
cd C:\projects\StockETF
git pull                      # 拉另一台推上來的最新
.venv\Scripts\activate
```

**收工**：
```powershell
git add .
git commit -m "今天做了什麼"
git push
```

**黃金律**：離開電腦前一定 push。不然到另一台 pull 不到會很困擾。

---

## 五、常見問題排除

| 症狀 | 原因 | 解法 |
|---|---|---|
| `python` 找不到 | 沒勾 Add to PATH | 重裝 Python，勾 Add to PATH |
| `pip install` 超慢 | 網路問題 | 換手機熱點試試 |
| `pytest` 找不到 | 沒啟動 venv | `.venv\Scripts\activate` |
| `ImportError: No module named X` | 同上 | 同上 |
| `ZoneInfoNotFoundError: Asia/Taipei` | `tzdata` 沒裝 | `pip install tzdata` |
| 某支爬蟲 FAIL | 網站當下不穩 | 等 1 分鐘再跑 `python main.py` |
| 網頁打開一片白 | 直接開 .html 檔不行 | 要跑 `python -m http.server 8000` |
| `git log` 是空的 | `.git\` 沒複製到 | 重新複製，確認 `.git\` 存在 |

---

## 六、快速 checklist（列印/存手機相簿都行）

### 來源電腦
- [ ] `git status` → clean
- [ ] 刪 `.venv\`、`__pycache__\`、`.pytest_cache\`、`tmp\`
- [ ] `Compress-Archive -Path StockETF -DestinationPath StockETF-portable.zip`
- [ ] 傳到 USB / 雲端

### 目標電腦
- [ ] 裝 Python 3.12（勾 Add to PATH）
- [ ] 裝 Git for Windows
- [ ] 解壓專案到工作目錄
- [ ] `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`
- [ ] `pytest -v` → 9 passed
- [ ] `python main.py` → 4 ETFs ok
- [ ] `python -m http.server 8000` → 瀏覽器看網頁 OK
- [ ] `git log --oneline` → 歷史完整
- [ ] 打開 Claude Code → 說「繼續 v1.5」

搞定。
