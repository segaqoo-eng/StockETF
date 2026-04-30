# 股價資料源切換 + 強制刷新按鈕 — 設計規格

**日期：** 2026-04-30
**狀態：** 已確認，待實作
**前置：** v1.5（feat/v1.5-active-etf 分支基礎；本 spec 不直接相依，可獨立實作）

---

## 一句話

把 `data/prices_today.json` 從「只走 TWSE+TPEx」升級為 4 層 fallback chain（FinMind → yfinance → TWSE+TPEx → cache），網頁 header 顯示資料源徽章 + 兩個強制刷新按鈕（股價 / ETF 持股），並把 ETF chip-bar 與 tab-nav 上下對調。

---

## 使用情境

使用者下班回家後雙擊 `update.bat` → 跑完開網頁看一輪。看到一半想再刷新某段資料時，不必關掉瀏覽器再重跑 `update.bat`，直接在 header 點按鈕：

| 時間 | 動作 | 對應按鈕 |
|---|---|---|
| 19:30 | 雙擊 `update.bat`，看一輪 | — |
| 19:45 | 想看當日某檔股票最新收盤 | 🔄 股價（10–30 秒） |
| 21:00 | 認為發行商現在應該更新了，重抓 ETF 持股 | 🔄 ETF（1–2 分鐘） |

徽章（🟢 FinMind / 🟡 yfinance / 🔵 TWSE+TPEx / 🔴 cache only）讓使用者一眼知道資料源 — 解決「FinMind 配額有沒有爆」這類隱性焦慮。

---

## 功能範圍

### 在 scope

- 新增 `scrapers/daily_close.py`：4 層 PriceProvider chain
- `data/prices_today.json` schema 加 3 欄：`source`, `fetched_at`, `missing`
- `web_server.py` 新增 3 endpoints：`POST /api/refresh/prices`、`POST /api/refresh/etfs`、`GET /api/refresh/status`
- 後端 mutex（同時間只允許一個 refresh job）
- `index.html` header 加徽章 + 兩按鈕；`<nav id="etf-chip-bar">` 與 `<nav class="tab-nav">` 上下對調
- 新增 `assets/refresh.js` 處理按鈕、polling、reload
- 新增簡易 toast lib（~30 行 JS + CSS）
- TDD 測試：fixture 覆蓋 4 個 provider + dispatch 邏輯

### 不在 scope

- 首頁表格新增「成交量」「三大法人」欄（成交量/法人已透過 `data_provider.py` + `/api/ohlcv` 服務個股頁與 ranking，不在本次 redesign 觸碰）
- `data_provider.py` 任何修改（個股 OHLCV / institutional 流程不動）
- GitHub Actions 自動排程（依 memory：cloud automation 已擱置）
- 註冊 FinMind 付費 sponsor token（保持免費等級可用）
- 前端測試框架（沒既有，不為本次新增）

---

## 資料來源 — 兩條獨立路徑（重要）

| 路徑 | 內容 | 用在哪 | 本次 redesign 是否觸碰 |
|---|---|---|---|
| **A** `data/prices_today.json` | 當日 close + change + change_pct | 首頁交叉持股表的「收盤」「漲跌%」欄 | ✅ 本次重點 |
| **B** SQLite cache（`data_provider.py`）via `/api/ohlcv` | 歷史 OHLCV + 成交量 + 三大法人 | 個股頁 (`stock.html`) + 買進評分 (`ranking.js`) | ❌ 不動 |

兩條路徑互相獨立。本 spec 只動 A。

---

## 架構

```
┌──────────────────────────────────────────────────────┐
│ scrapers/daily_close.py  ← 新檔案                      │
│   class PriceProvider (abstract)                     │
│     ├─ FinMindDailyClose   (per-stock loop)          │
│     ├─ YFinanceDailyClose  (yf.download bulk multi)  │
│     ├─ TwseTpexDailyClose  (包現有 PricesFetcher)     │
│     └─ CacheDailyClose     (讀現有 prices_today.json)│
│                                                      │
│   class ProviderUnavailable(Exception)               │
│                                                      │
│   def fetch_daily_close(                             │
│         stock_ids, target_date, providers=None       │
│       ) -> dict                                      │
└──────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────┐
│ main.py 末尾（取代現有 PricesFetcher 呼叫）           │
│ web_server.py POST /api/refresh/prices               │
│ web_server.py POST /api/refresh/etfs (內部 main.main)│
└──────────────────────────────────────────────────────┘
        │
        ▼
   data/prices_today.json
   { date, source, fetched_at, missing, prices: {…} }
        │
        ▼
   index.html header badge + 🔄 buttons
```

### 股票宇集（universe）

來自 `data/latest.json` 的 unique `stock_id`（~150 檔）。**不爬全市場 1700 檔。** 理由：
- FinMind 免費等級 bulk-by-date 被擋（HTTP 400 "level is free"）
- per-stock 1700 = 14 分鐘 + 爆配額
- 首頁只看 ETF 持股，1700 檔絕大多數用不到

### Provider 鏈優先順序

`FinMind → yfinance → TWSE+TPEx → cache`

「停在哪家」的判定 = **回傳 ≥ 80% stock_ids 視為成功**：
- 150 檔請求，145 檔回傳 → ≥ 80%，停在這家
- 150 檔請求，100 檔回傳 → < 80%，視為失敗，跳下一家
- 150 檔請求，0 檔回傳 / raise ProviderUnavailable → 失敗，跳下一家

「missing」回傳：成功 provider 沒回到的 stock_ids（前端 toast 提示）。**不**用下一家補（簡化邏輯，避免 source 變 mixed）。

---

## 元件介面

### `scrapers/daily_close.py`

```python
class PriceProvider:
    name: str  # "finmind" / "yfinance" / "twse_tpex" / "cache"

    def fetch(
        self, stock_ids: list[str], target_date: date
    ) -> dict[str, dict]:
        """
        Return {stock_id: {"close": float, "change": float,
                          "change_pct": float, "exchange": str}}

        部分失敗（149/150 成功）：仍 return 那 149 檔的 dict
        整體失敗（HTTP error / 配額爆 / 等級不足 / 空回傳）：raise ProviderUnavailable
        """


class ProviderUnavailable(Exception):
    """Provider 整體不可用 — dispatch 應跳下一家。"""


SUCCESS_THRESHOLD = 0.80  # ≥80% 視為該 provider 成功


def fetch_daily_close(
    stock_ids: list[str],
    target_date: date,
    providers: list[PriceProvider] | None = None,
) -> dict:
    """
    Walk providers; first one returning ≥ SUCCESS_THRESHOLD 視為成功，停。
    全失敗 → 從 CacheDailyClose 讀，source="cache"。
    cache 也沒有 → return {ok: False, error: "no data"}.

    Return:
      {
        "ok":         True,
        "date":       "2026-04-30",
        "source":     "finmind",
        "fetched_at": "2026-04-30T19:23:11+08:00",
        "prices":     {"2330": {...}, ...},
        "missing":    ["1234", "5678"],   # 該 provider 抓不到的 stock_ids
        "tried":      ["finmind"],         # 嘗試過的 providers (debug 用)
      }
    """
```

### `web_server.py` 新 endpoints

```
POST /api/refresh/prices
  → 取 mutex；spawn thread 跑 fetch_daily_close()
  → 立刻 return 202 {job: "prices", started_at: "..."}
  → mutex busy → return 409 {error: "another job running"}

POST /api/refresh/etfs
  → 同上，但 thread 跑 main.main() 完整流程（內含 fetch_daily_close）

GET /api/refresh/status
  → return {
      running: bool,
      current_job: "prices" | "etfs" | null,
      started_at: str | null,
      last_result: dict | null,    # 上次完成的結果
      last_error: str | null,      # 上次 thread crash 訊息
    }
```

**Mutex 實作：** `web_server.py` module-level `_running_job: str | None = None` + `threading.Lock()`。`_exhausted` 等 provider 狀態 cache 在 `fetch_daily_close` 模組層；同一 process 內 FinMind 配額爆 → 後續呼叫直接跳過 FinMind，直到 server 重啟（即下次 `update.bat`）。

### `index.html` header 改造

```html
<header class="header">
  <h1>📊 Stock<span>ETF</span></h1>
  <div class="header-sub">
    主動式 ETF 交叉持股分析（+ 0050 對照） ·
    更新於 <b id="updated-at">—</b> ·
    <span id="price-source-badge" class="source-badge">—</span>
    <button id="btn-refresh-prices" class="header-btn"
            title="只重抓股價，10-30 秒">🔄 股價</button>
    <button id="btn-refresh-etfs" class="header-btn"
            title="重抓 ETF 持股 + 股價，1-2 分鐘">🔄 ETF</button>
  </div>
</header>

<!-- ↓ tab-nav 與 etf-chip-bar 順序對調 ↓ -->
<nav class="tab-nav"> ... </nav>
<nav id="etf-chip-bar" class="etf-chip-bar"> ... </nav>
```

### `assets/refresh.js`（新檔案）

職責：
- `initRefreshButtons()` — bind click handlers
- `pollRefreshStatus()` — 每 2 秒 poll；跑時兩個 button 灰掉、徽章變 ⏳
- 跑完：re-fetch `data/prices_today.json`（+ `data/latest.json` if etfs job）→ re-render badge + 表格
- 失敗 / 部分失敗 → 呼叫 toast lib

### Toast lib（簡易，~30 行 JS + ~30 行 CSS）

API：
```js
toast(message, { level: "warn" | "error" | "info", manual: true })
```
- `manual: true`（本 spec 用）→ 角落顯示直到使用者按 ✕ 關閉（**手動關**，依 §3 確認）
- 多筆訊息合併成同一條 toast（依 §4 確認）：例如「⚠️ 元大、富邦爬蟲失敗，相關 ETF 用前一天資料」

---

## 資料流（Data Flow）

### 場景 1：開啟網頁（不按按鈕）

```
1. 瀏覽器 GET /index.html
2. app.js → fetch('data/prices_today.json')
3. 讀到 {date, source, fetched_at, prices}
4. render badge 根據 source：🟢/🟡/🔵/🔴
   舊格式（無 source 欄）→ 預設 🔵 TWSE+TPEx
5. render 表格（讀 prices[stock_id].close / change_pct）
```

### 場景 2：按「🔄 股價」

```
[Frontend]                              [Backend]
按下 button
  ├─ disable 兩個 button
  ├─ badge → "⏳ 抓取中..."
  └─ POST /api/refresh/prices
                                        web_server: 取 mutex
                                          ├─ busy → 409 Conflict
                                          └─ 否 → spawn thread, return 202

每 2 秒 poll /api/refresh/status
                                        thread 內：
                                          1. load data/latest.json
                                          2. unique = {h.stock_id for h in holdings}
                                          3. fetch_daily_close(unique, today())
                                             ├─ FinMind 145/150 ≥ 80% → 停
                                             ├─ (else) yfinance → ...
                                             └─ (else) TWSE+TPEx → ...
                                          4. write data/prices_today.json
                                          5. release mutex

poll 看到 running=false:
  ├─ re-fetch data/prices_today.json
  ├─ update badge
  ├─ re-render 表格
  ├─ re-enable buttons
  └─ missing > 0 → toast 「⚠️ N 檔股票今日抓不到」
```

### 場景 3：按「🔄 ETF」

同場景 2，但 thread 跑 `main.main()` 完整流程：
1. 4-7 家發行商 scrapers
2. 寫 `latest.json` + snapshot + diff + leaderboard
3. 末尾呼叫 `fetch_daily_close()`（同場景 2 step 3-4）
4. 個別 ETF 失敗 → 用前一天 snapshot fallback + 加進 `partial_failures`
5. 跑完前端 reload `latest.json` + `prices_today.json`，partial_failures 合併成一條 toast

### 場景 4：兩個按鈕同時按

第一個：取 mutex、spawn thread、return 202
第二個：mutex busy → 409 → 前端 toast「⏳ 已有任務在跑，請等候」
（UI 上 buttons 已 disable，理論上點不到，race 防一下）

---

## 錯誤處理

### 後端：每個 provider 失敗的偵測

| 失敗類型 | 偵測 | 行為 |
|---|---|---|
| HTTP 連線錯誤 | `requests.exceptions.RequestException` | log warning，跳下家 |
| FinMind 配額爆 (status==402) | parse JSON | 設 `_exhausted=True`、log、跳下家 |
| FinMind 等級不夠 (status==400, "level is free") | parse JSON | log 一次、跳 FinMind |
| 回傳 < 80% | `len(result) / len(stock_ids) < 0.8` | log warning，跳下家 |
| yfinance 包未裝 | `ImportError` | log info、跳下家 |
| TWSE/TPEx 5xx | HTTP status | log、跳下家 |
| 全 4 家失敗 | chain 跑完 nothing returned | 從 cache 讀 source="cache" |
| cache 也沒（首次安裝） | 檔案不存在 | return `{ok: False, error: "no data"}` |

### 後端：partial_failures（既有 main.py 邏輯沿用）

`main.main()` 內部對個別發行商的 fallback **不動現有邏輯**，只在 web_server 收集 return value 加 `partial_failures` list：

```python
{
  "ok": True,
  "source": "...",
  "partial_failures": [
    {"etf_id": "0050", "issuer": "yuanta", "reason": "HTTP 503",
     "fallback": "used 2026-04-29 snapshot"},
  ],
  "elapsed_ms": 87000,
}
```

前端看到 `partial_failures` 非空 → 合併訊息成一條 toast。

### 前端：Toast 樣式

| 後端回應 | 樣式 | 內容 |
|---|---|---|
| ok, partial_failures 空 | （不顯示）| — |
| ok, partial_failures N 筆 | ⚠️ 黃 | 「⚠️ 元大、富邦爬蟲失敗，相關 ETF 用前一天資料」（合併） |
| ok, missing > 0 | ⚠️ 黃 | 「N 檔股票今日收盤抓不到」 |
| 409 Conflict | 🔵 藍 | 「⏳ 已有任務在跑，請等候」 |
| 500 / 連線失敗 | ❌ 紅 | 「刷新失敗：{error}」 |

所有 toast 皆 `manual: true`（手動關閉 ✕）。

### 後端 thread crash 防護

`web_server.py` 的 background thread 整個 wrap 在 try/except：
1. log full traceback 到 stderr
2. 寫 `_last_job_error: str` 到 mutex 旁邊
3. 釋放 mutex
4. `/api/refresh/status` 回 `last_error` 給前端 → 紅 toast

---

## 測試策略

照專案慣例：**TDD + fixtures 離線跑、不打網路**。

### 新增測試檔案

```
tests/
  test_daily_close_providers.py   ← 4 個 provider 各自的解析邏輯
  test_daily_close_dispatch.py    ← chain 退級、80% 門檻、metadata 寫入
  test_web_server_refresh.py      ← API 端到端（mutex / 202 / 409 / status）
  fixtures/
    finmind_daily_close_ok.json       ← FinMind 150 檔成功
    finmind_daily_close_partial.json  ← FinMind 100 檔（< 80%）
    finmind_quota_exhausted.json      ← {status: 402}
    finmind_level_too_low.json        ← {status: 400, msg: "level is free"}
    yfinance_batch_ok.csv             ← yf.download 多 ticker 回傳
    twse_index_ok.json                ← (重用既有)
    tpex_quote_ok.json                ← (重用既有)
```

### 主要測試案例

```python
# test_daily_close_providers.py
def test_finmind_provider_returns_normalized_dict()
def test_finmind_provider_raises_on_quota_402()
def test_finmind_provider_raises_on_level_too_low()
def test_yfinance_provider_handles_multiindex_columns()
def test_yfinance_provider_skipped_when_not_installed()
def test_twse_tpex_merges_both_endpoints()
def test_cache_provider_reads_existing_prices_json()

# test_daily_close_dispatch.py
def test_dispatch_stops_at_first_successful_provider()
def test_dispatch_falls_through_on_under_80pct()
def test_dispatch_returns_error_when_all_providers_fail()
def test_dispatch_writes_correct_metadata()
def test_dispatch_excludes_finmind_after_quota_exhausted_in_same_process()

# test_web_server_refresh.py
def test_post_refresh_prices_returns_202_and_starts_thread()
def test_concurrent_refresh_returns_409()
def test_status_endpoint_reflects_running_state()
def test_thread_crash_writes_last_error_releases_mutex()
```

### 不測

- ❌ `BaseScraper.get/post` 重試邏輯（沿用既有政策，CLAUDE.md 已排除）
- ❌ 真實 FinMind / yfinance 網路呼叫（fixture 替代）
- ❌ 前端 JS（無框架測試）
- ❌ Toast UI 細節（純 DOM，眼睛驗證）

### 手動驗收（寫進 `docs/VERIFY.md`）

```markdown
## 強制刷新按鈕驗收

1. 跑 update.bat → 開瀏覽器 → header 徽章 🔵 TWSE+TPEx（main.py 預設）
2. 按「🔄 股價」→
   - 兩按鈕灰掉、徽章 ⏳
   - 10-30 秒後 → 🟢 FinMind / 🟡 yfinance / 🔵 TWSE+TPEx 之一
   - 表格自動更新
3. 連按 🔄 股價 N 次 → FinMind 配額爆 → 徽章退到 🟡 yfinance
4. 拔網路、按按鈕 → 徽章 🔴 cache only + 紅 toast
5. 按「🔄 ETF」→ 1-2 分鐘流程；發行商失敗時合併 toast
6. 同時按兩個 → 第二個顯示「⏳ 已有任務在跑」
```

---

## JSON Schema 變更（向下相容）

### 既有 `data/prices_today.json`

```json
{
  "date": "2026-04-30",
  "prices": { "2330": { "close": 1080, "change": 5, "change_pct": 0.46, "exchange": "TWSE" } }
}
```

### 新格式

```json
{
  "date":       "2026-04-30",
  "source":     "finmind",
  "fetched_at": "2026-04-30T19:23:11+08:00",
  "missing":    ["1234"],
  "prices":     { "2330": { "close": 1080, "change": 5, "change_pct": 0.46, "exchange": "TWSE" } }
}
```

**向下相容：** 前端讀到舊格式（無 `source` 欄）→ badge 顯示 🔵 TWSE+TPEx + tooltip「未知 (舊格式)」。下次 refresh 寫入新格式即正常。

---

## 命名 / 慣例

- Provider 名稱統一小寫底線：`"finmind"` / `"yfinance"` / `"twse_tpex"` / `"cache"`
- 徽章 emoji：🟢 finmind / 🟡 yfinance / 🔵 twse_tpex / 🔴 cache / ⏳ running / ❓ unknown
- toast level：`info` / `warn` / `error`（CSS class `.toast-info` / `.toast-warn` / `.toast-error`）
- 提交訊息風格（CLAUDE.md 已定義）：`feat(refresh): ...` / `feat(provider): ...` / `feat(ui): ...`

---

## 風險 / 已知問題

1. **FinMind 配額爆後同 process 內不再嘗試** — 設計選擇（避免每次 retry 浪費 RTT）。代價：使用者按完一次 🔄 股價 quota 爆掉後，當天剩下時間都不會再用 FinMind，直到下次 `update.bat` 重啟 server。可接受（單機晚上用情境）。
2. **yfinance batch 1700 ticker 會被 Yahoo rate-limit** — 本 spec universe 只 ~150，不會踩到。但日後若擴大 universe 須留意。
3. **`fetched_at` 時區** — 一律 `Asia/Taipei`，遵循 CLAUDE.md。
4. **mutex 跨 process** — 本 spec 假設只有一個 web_server 實例。多開會撞 `prices_today.json` 但這不是現實情境（單機單瀏覽器）。

---

## 待實作後續

- 實作後跑 `pytest -q` 全綠
- 跑完 `update.bat` 走完 6 步手動驗收清單
- commit + push 到 `feat/v1.5-active-etf` 分支（或新開 `feat/refresh-buttons`）
- 更新 `README.md` 加 header 截圖 + 按鈕說明
- 更新 `docs/VERIFY.md` 加驗收章節
