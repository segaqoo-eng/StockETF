# 架構與運作原理

寫給「想搞懂這東西怎麼跑」的你，當作 tutorial 和之後加功能的參考。

---

## 一、三層分離

```
┌─────────────────────────────────────────────────┐
│  1. 爬蟲層 (Python)  scrapers/                  │
│     ─ 每家發行商一支 py                         │
│     ─ 吃 ticker、吐 list[Holding]               │
│     ─ 不知道 config、不寫檔                     │
└──────────────┬──────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────┐
│  2. 資料層 (JSON)  data/                        │
│     ─ latest.json (主檔)                        │
│     ─ snapshots/YYYY-MM-DD.json (每日歸檔)      │
│     ─ 由 normalizer.py 產出                     │
│     ─ 前端只需要這個，不需要懂爬蟲              │
└──────────────┬──────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────┐
│  3. 前端層 (靜態 HTML+JS)                       │
│     ─ index.html + assets/style.css + app.js    │
│     ─ fetch('data/latest.json') 讀資料          │
│     ─ 渲染表格、處理篩選、點擊展開              │
└─────────────────────────────────────────────────┘
```

**為什麼要分三層？** 每層只做一件事，之間用 JSON 當契約。
- 想換前端框架（React、Vue）？改第 3 層就好，資料不動
- 想加新 ETF？改第 1 層加一支 scraper + 改 `config/etfs.yml`
- 想加資料庫？在第 2 層和第 3 層之間插進去（v2+ 再說）

---

## 二、Python 端每個檔案的職責

### `scrapers/base.py` — 共用基礎建設

```python
@dataclass(frozen=True)
class Holding:
    stock_id: str      # "2330"
    stock_name: str    # "台積電"
    weight_pct: float  # 48.5
    shares: int        # 100000000
```

`Holding` 是**所有 scraper 的共通輸出格式**。不管你從 Yuanta、Nomura、Capital 抓，最後都要變成這個樣子。

`BaseScraper` 提供：
- `get(url)` — 帶重試（3 次、2s/4s/8s backoff）的 GET
- `post(url, json=...)` — 帶重試的 POST
- 共用 User-Agent: `StockETF-Bot/1.0`

為什麼要有 `BaseScraper`？共用 HTTP 邏輯一次寫好，每個 scraper 就不用重寫重試。

### `scrapers/yuanta.py`、`nomura.py`、`capital.py` — 每家一支

每支都長得一樣：
```python
class SomeScraper(BaseScraper):
    def fetch(self, ticker: str) -> list[Holding]:
        text = self.get(HOLDINGS_URL)  # 或 self.post(...)
        return parse_some_holdings(text)

def parse_some_holdings(text: str) -> list[Holding]:
    # 拆 HTML 或 JSON，每筆變成 Holding
    ...
```

**職責分離**：
- `fetch()` 只負責「發 request」，錯誤丟給 BaseScraper 處理
- `parse_...()` 只負責「解析 text」，不打網路（可以離線測試）

### `normalizer.py` — 把多家資料聚合成一份 JSON

輸入：
- `scraped: dict[ticker, list[Holding]]` — 各 scraper 的輸出
- `etfs_config: dict` — `config/etfs.yml` 的內容（tags、color）
- `stocks_config: dict` — `config/stocks.yml` 的內容（產業別）

輸出：符合 spec §4.1 的 dict，寫成 `data/latest.json`。

**關鍵操作 — cross-holding 反轉**：
```
輸入長這樣 (以 ETF 為主角):
  0050 → [台積電, 聯發科, 鴻海...]
  0056 → [聯發科, 鴻海...]

反轉後 (以股票為主角):
  台積電 → held by [0050]
  聯發科 → held by [0050, 0056]
  鴻海   → held by [0050, 0056]
```

這個反轉就是「交叉持股分析」的核心邏輯，程式碼只有 10 行（`build_payload` 函式裡）。

### `main.py` — 總指揮

1. 讀 config
2. 讀前一次的 `data/latest.json`（為了容錯用）
3. 迴圈叫每家 scraper `fetch()`
4. 如果成功 → 用新資料
5. 如果失敗 → 用前一次的資料 (fallback)
6. 呼叫 `build_payload` + `write_payload`

**容錯策略**：任何一家 scraper 爆掉不會讓整個 pipeline 爛掉。但如果用了 fallback，`updated_at` 會保留前次時間（不騙人說是新資料）。

---

## 三、前端怎麼運作

### `index.html` — 骨架

- Header、Tab 列、主內容區、Footer
- 三個 Tab 中只有「交叉持股」啟用（v1）
- 載入 `assets/style.css` 和 `assets/app.js`

### `assets/style.css` — 視覺

- CSS variables 定義配色（`--accent`、`--bg` 等）
- 深色主題 `#0d1117`（仿 GitHub 的樣子）
- 無框架、純 CSS

### `assets/app.js` — 互動邏輯

流程：
```
頁面載入
  ↓
load() 呼叫 fetch('data/latest.json')
  ↓
JSON 存在 state.payload
  ↓
populateIndustryFilter() — 動態填產業下拉
  ↓
render() — 產生表格 HTML
  ↓
wireRowClicks() — 每一列掛上 click listener
  ↓
使用者操作：
  改篩選 → state 更新 → render() 重畫
  點一列 → toggleDetail() 插入/移除 detail 列
```

**狀態管理**：用一個全域 `state` 物件，沒有框架也沒有 setState。改 state 後自己呼叫 `render()` 重畫整個表格。124 筆股票重畫不會卡（現代瀏覽器 < 50ms）。

---

## 四、資料流（從你按右鍵執行到網頁顯示）

```
你在終端打 python main.py
  ↓
main.py 讀 config/etfs.yml (4 個 ticker)
  ↓
迴圈 for ticker, meta in etfs_config.items():
  ├─ time.sleep(2)  (第二個開始才 sleep，禮貌)
  ├─ scraper = SCRAPERS[meta["scraper"]]  (找對的 scraper 物件)
  ├─ holdings = scraper.fetch(ticker)
  │     ↓
  │   YuantaScraper.fetch("0050")
  │     ├─ self.get("https://www.yuantaetfs.com/product/detail/0050/ratio")
  │     │     ↓ (BaseScraper 包了重試)
  │     │   HTTP 200, 回傳 1.1MB HTML
  │     └─ parse_yuanta_holdings(html)
  │           ↓
  │         [Holding("2330", "台積電", 62.09, 472180760), ...]
  ├─ scraped["0050"] = holdings
  └─ (重複 0056, 00980A, 00981A)
  ↓
normalizer.build_payload(scraped, etfs_config, stocks_config)
  ├─ 產生 etfs_block (每檔 ETF 的 metadata)
  ├─ 反轉成 held_by_map (以股票為主角)
  └─ 輸出 dict
  ↓
normalizer.write_payload(payload)
  ├─ 寫 data/latest.json
  └─ 寫 data/snapshots/2026-04-24.json
  ↓
終端顯示 "Wrote data/latest.json (4 ETFs, 124 unique stocks)"

之後使用者開瀏覽器 http://localhost:8000/
  ↓
index.html 載入
  ↓
app.js 跑 load() → fetch('data/latest.json')
  ↓
json 載入到 state.payload
  ↓
render() 產生 <table>...</table>
  ↓
使用者看到表格
```

---

## 五、為什麼這樣設計？設計決策筆記

| 決策 | 選擇 | 為什麼 |
|---|---|---|
| 爬蟲語言 | Python | 生態成熟（requests + BeautifulSoup），解析 HTML/JSON 方便 |
| 資料存哪 | Git 裡的 JSON | 免費、有版本歷史、GitHub Pages 直接讀 |
| 前端框架 | 無 | 資料只有 124 筆，純 JS 夠用。學習曲線低 |
| 排程 | 目前手動，v2 GitHub Actions | 先驗證流程通，再自動化 |
| 後端 | 沒有 | 沒帳號、沒留言，靜態站就夠 |
| 樣板引擎 | 沒有 | Template literals 就夠，不用 Handlebars |
| 狀態管理 | 全域 `state` 物件 | 一個頁面沒必要上 Redux/Zustand |

---

## 六、加新 ETF 的流程（給未來的你）

假設你要加 `00878` 國泰永續高股息：

1. **在 `config/etfs.yml` 加一段**：
   ```yaml
   "00878":
     scraper: cathay        # 新的 scraper 名稱
     name: 國泰永續高股息
     type: passive
     tags: [高股息/ESG]
     color: "#a78bfa"
   ```

2. **寫 `scrapers/cathay.py`**：
   - 從國泰投信官網找持股頁
   - 依「資料源發現方法論」找到真實資料端點（看 `docs/SCRAPING.md`）
   - 複製 `scrapers/nomura.py` 或 `yuanta.py` 改

3. **在 `main.py` 註冊**：
   ```python
   from scrapers.cathay import CathayScraper
   SCRAPERS = {
       "yuanta":  YuantaScraper(),
       "nomura":  NomuraScraper(),
       "capital": CapitalScraper(),
       "cathay":  CathayScraper(),   # ← 加這行
   }
   ```

4. **寫測試 `tests/test_cathay.py`** + 存 fixture

5. 跑 `python main.py` 看能不能抓到新資料

6. 開瀏覽器看網頁，00878 應該出現在表格裡

就這樣。整個架構是為了讓「加一檔 ETF」只需要動這 4 個地方。
