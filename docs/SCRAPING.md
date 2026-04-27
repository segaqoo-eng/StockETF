# 資料來源發現方法論

> 「你怎麼知道要去哪抓？」— 這份文件回答。

---

## 一、原則：從官方源抓，不從第三方抓

**錯誤做法**（不要這樣）：
- 從 `pocket.tw`、`cmoney.tw`、`goodinfo.tw` 這些第三方站抓
- 從 Google 找到的 blog 截圖複製

**為什麼不行**：
1. **法律風險** — 第三方站的資料是他們整理的，有版權問題
2. **不穩定** — 他們自己也是抓別人的，一旦他們掛了或改版你跟著死
3. **資料可能被過濾** — 第三方會重排、加廣告、延遲更新

**正確做法**：
1. **直接從 ETF 發行商官網** — 法規強制每日公布持股，他們一定有
2. **備援：TWSE 證交所** — `www.twse.com.tw`、`openapi.twse.com.tw`
3. **備援：公開資訊觀測站 MOPS** — `mops.twse.com.tw`（基金申報）

---

## 二、找到發行商的流程

### Step 1：從 TWSE 查 ETF 屬於哪家發行商

證交所有主動式 ETF 清單：
- https://www.twse.com.tw/zh/products/securities/etf/products/active-list.html

被動式 ETF 清單：
- https://www.twse.com.tw/zh/ETF/domestic

表格欄位有「基金管理公司」— 那就是發行商。

例如：
| ETF | 發行商 |
|---|---|
| 0050, 0056 | 元大投信 (Yuanta) |
| 00878 | 國泰投信 (Cathay) |
| 006208 | 富邦投信 (Fubon) |
| 00919 | 群益投信 (Capital — 注意，群益的英文也是 Capital，跟統一不同) |
| 00980A | 野村投信 (Nomura) |
| 00981A | 統一投信 (Uni-President / PresSec) |
| 00982A | 群益投信 |
| 00991A | 復華投信 (Fuh Hwa) |

### Step 2：找發行商官網

Google 搜「<發行商中文名> 投信」通常第一個就是。官網網址舉例：
- 元大投信：`yuantaetfs.com` 或 `yuantafunds.com`
- 國泰投信：`cathaysite.com.tw`
- 富邦投信：`fubon.com` → ETF 專區
- 野村投信：`nomurafunds.com.tw`
- 統一投信：`ezmoney.com.tw`（ETF 專屬品牌，不是 uit.com.tw）
- 復華投信：`fhtrust.com.tw`

**陷阱**：有些發行商的主站是「基金」入口，ETF 有獨立的子站（統一的 ezmoney、元大的 yuantaetfs 都是）。找不到的話搜「<ETF 代號> 持股」通常能導到正確的頁。

### Step 3：找到該 ETF 的「持股明細」頁

進官網後，找：
- 「成分股」「持股明細」「持股資訊」「投資組合」「Shareholding」
- 或直接進「產品介紹 → <ETF 代號>」

URL 常見模式：
```
元大：https://www.yuantaetfs.com/product/detail/<ticker>/ratio
野村：https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo=<ticker>&tab=Shareholding
統一：https://www.ezmoney.com.tw/ETF/Fund/Info?FundCode=<內部代號>
```

---

## 三、抓資料的三種模式（很重要）

現代網站的資料載入方式分三種。**先判斷哪一種，再決定怎麼爬**。

### 模式 A：傳統 HTML 表格（最簡單）

**特徵**：用 `curl` 或瀏覽器「檢視原始碼」直接看到 `<table><tbody><tr>...` 裡面有資料。

**做法**：
```python
from bs4 import BeautifulSoup
soup = BeautifulSoup(html, "html.parser")
rows = soup.select("table.holdings-table tbody tr")
for row in rows:
    cols = [td.get_text(strip=True) for td in row.find_all("td")]
    # cols[0] = 股號, cols[1] = 名稱, cols[2] = 權重...
```

**台灣 ETF 官網用這種的**：很少（早期的、政府類的才用）。

### 模式 B：前後端分離（JSON API）

**特徵**：打開原始碼 HTML 裡**沒資料**，只有 `<div id="app"></div>` 之類的空殼。資料是 JS 跑起來後另外向 API 要的。

**怎麼發現**：
1. Chrome / Firefox 按 **F12** 打開 DevTools
2. 切到 **Network** 分頁
3. 勾選 **XHR/Fetch**（過濾掉圖片、CSS）
4. 重新整理頁面 / 點「持股明細」Tab
5. 看新跑出來的 request，點開 → Response 分頁看有沒有持股資料
6. 找到後，看 **Headers** 分頁：URL、Method (GET/POST)、Request Payload

範例 — **野村 00980A 就是這種**：
- 原始 HTML 是 `<app-root></app-root>`（Angular SPA）
- Network Tab 看到 `POST /API/ETFAPI/api/Fund/GetFundAssets`
- Payload: `{"FundID": "00980A", "SearchDate": "2026-04-24"}`
- Response: 乾淨 JSON

**做法**：
```python
url = "https://www.nomurafunds.com.tw/API/ETFAPI/api/Fund/GetFundAssets"
payload = {"FundID": "00980A", "SearchDate": "2026-04-24"}
text = self.post(url, json=payload)   # BaseScraper 的 post() 會自動加 Content-Type
data = json.loads(text)
rows = data["Entries"][0]["Data"]["Table"][0]["Rows"]
```

### 模式 C：SSR（伺服器端渲染）框架

**特徵**：HTML 裡**有資料**，但不是在 `<table>` 裡，而是：
- `<script>window.__NUXT__=function(a,b,...){...}(...)</script>`（Nuxt.js）
- `<script id="__NEXT_DATA__">{...}</script>`（Next.js）
- `<div data-content="{...JSON...}">`（Vue SSR 或自訂）

資料是預先塞進 HTML 的，但為了效能被壓縮、編碼、或放在非預期位置。

**怎麼發現**：
1. `curl` 抓原始 HTML（**不要用瀏覽器看，因為瀏覽器會執行 JS 把 HTML 改掉**）
   ```bash
   curl -A "StockETF-Bot/1.0" -L <URL> > page.html
   ```
2. 打開 page.html，搜「2330」「台積電」「StockWeights」「holdings」看有沒有命中
3. 找到後，觀察資料是怎麼被包裝的

**元大 0050 就是 Nuxt.js（模式 C）**：
- HTML 有 `window.__NUXT__=function(a,b,c,...,qc){...StockWeights:[{code:kF,...}]...}(...)`
- 資料嵌在 IIFE 裡，921 個參數當壓縮字典
- 每筆 stock 是 `{code:kF, name:kG, weights:62.09, qty:472180760}`，需要查字典還原

**統一 00981A 則是模式 B+C 混合**：
- 頁面是 Vue 3 SSR
- 資料放在 `<div id="DataAsset" data-content="[{...}, {...}]">` 屬性裡
- 用 BeautifulSoup 抓屬性 → JSON decode 就拿到

---

## 四、實戰：本專案三支 scraper 的發現過程

### 1. 元大 Yuanta（0050、0056）

**嘗試 1**：直接 curl `https://www.yuantaetfs.com/product/detail/0050/ratio`
→ 拿到 1.1MB HTML，但 `<table>` 是空的（只有 5-6 筆預渲染）

**嘗試 2**：搜尋 HTML 裡的 `"2330"` 字串
→ 命中大量，都在一段 `window.__NUXT__=function(a,b,c,...,qc){...}(...)` 裡

**關鍵發現**：這是 Nuxt.js 壓縮壓製過的 payload
- 函式簽名有 921 個參數（a, b, c, d, ..., qc）
- 函式 body 裡 `StockWeights:[{code:kF, ym:a, name:kG, ename:kH, weights:62.09, qty:472180760}]`
- 呼叫時傳入 921 個對應值當字典

**解法**：
1. 抽出參數名（那 921 個 variable letters）
2. 抽出對應值（從括號裡 tokenize）
3. 建 `param_map = {"kF": "2330", "kG": "台積電", ...}`
4. Regex 抓 `StockWeights:[...]` 的每筆，把變數名丟字典查值

### 2. 野村 Nomura（00980A）

**嘗試 1**：curl `https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo=00980A&tab=Shareholding`
→ 拿到幾 KB HTML，幾乎空的，有 `<app-root></app-root>`

**關鍵**：這是 Angular SPA，資料來自另一個 API

**嘗試 2**：瀏覽器打開 DevTools → Network → Fetch/XHR → 點 Shareholding Tab
→ 看到一個 POST request 到 `/API/ETFAPI/api/Fund/GetFundAssets`

**進一步驗證**：看 JS bundle
- 下載 `main.xxx.js`
- 搜「GetFundAssets」確認這是 API 端點
- 看 payload 格式：`{FundID, SearchDate}`

**解法**：直接 POST 打 API，parse 乾淨 JSON。是三種裡最簡單的。

### 3. 統一 Capital（00981A）

**嘗試 1**：搜「統一 00981A 持股」
→ 一堆第三方網站，排除

**嘗試 2**：找官網，發現統一投信官方 ETF 站是 `ezmoney.com.tw`（不是公司主站 uit.com.tw）

**嘗試 3**：進 ezmoney 找 00981A 的頁面
→ 需要知道內部 `FundCode`（不是股市代號）

**怎麼找 FundCode**：
- 搜首頁 HTML 裡的 00981A 字串
- 發現 `<div id="DataFund" data-content="{... FundCode:'49YTW' ...}">`
- 知道了：URL 是 `?FundCode=49YTW`

**解法**：
- GET `https://www.ezmoney.com.tw/ETF/Fund/Info?FundCode=49YTW`
- BeautifulSoup 取 `<div id="DataAsset">` 的 `data-content` 屬性（裡面是 JSON 字串）
- `json.loads()` 解析，取 `AssetCode == "ST"` 那組的 `Details`

---

## 五、給新 scraper 的 checklist

要加一個新 ETF 發行商時，照這個順序做：

### 探索階段（1-2 小時）

- [ ] 確認發行商官網主網址（不是第三方）
- [ ] 找到該 ETF 的持股頁 URL
- [ ] 用 `curl -A "StockETF-Bot/1.0" -L <URL> -o test.html` 抓原始 HTML
- [ ] 用文字編輯器打開 test.html，搜一個已知股票名（例如「台積電」）
  - 命中 → 模式 A 或 C，繼續分析位置
  - 沒命中 → 模式 B，去看 Network
- [ ] 判斷是哪種模式
- [ ] 如果是模式 B：記下 API URL、Method、Payload、Response 格式
- [ ] 如果是模式 C：找出資料的 script tag 或 data-* attribute

### 實作階段（1-2 小時）

- [ ] 先存 fixture（HTML 或 JSON 檔）到 `tests/fixtures/`
- [ ] 先寫測試（assert 持股數、assert 某檔股票在裡面、assert 權重 sum ~100%）
- [ ] 跑測試看 ModuleNotFoundError（紅燈）
- [ ] 寫 `parse_xxx_holdings(text)` 純解析函式（不打網路）
- [ ] 跑測試到綠燈
- [ ] 寫 `XxxScraper(BaseScraper)` 包 fetch()

### 整合階段（30 分鐘）

- [ ] 在 `main.py` 的 `SCRAPERS` dict 註冊
- [ ] 在 `config/etfs.yml` 加 ticker
- [ ] 跑 `python main.py` 驗證
- [ ] 開瀏覽器看 UI 有沒有正常顯示

### 品質檢查

- [ ] 爬蟲失敗時有清楚的 ValueError（不要吞錯誤變空 list）
- [ ] 測試用 fixture，不打真實網路（離線可執行）
- [ ] User-Agent 正確設定（BaseScraper 自動加）
- [ ] 請求間隔 ≥ 2 秒（main.py 的 `INTER_REQUEST_DELAY_SEC` 已處理）

---

## 六、常見雷點

| 雷點 | 症狀 | 解 |
|---|---|---|
| 拿到 HTML 但表格是空的 | 模式 B 或 C | 看 Network 或搜 HTML 找嵌入資料 |
| 回傳 403 / 429 | 發行商擋爬蟲 | 檢查 User-Agent、加長 sleep、降低頻率 |
| 回傳 302 redirect | 需要 session cookie | 用 `requests.Session` 自動跟 redirect |
| JSON 解析出來欄位對不上 | 發行商改了欄位順序 | 用 key 名稱而不是 index：`row["Weight"]` 而不是 `row[3]` |
| 週末/假日抓不到 | 當日沒交易資料 | Fallback 用前一次資料（main.py 已處理） |
| 部分股票重複計算 | Dedup 錯誤 | normalizer 用 `stock_id` 當 key，重複會自動蓋掉 |

---

## 七、倫理與法律

**可以做的**：
- ✅ 讀公開網頁（法規強制公開的 ETF 持股資料）
- ✅ 合理速率（2-3 秒間隔、一天跑一兩次）
- ✅ 設定 User-Agent 自我介紹
- ✅ 遵守 `robots.txt`（若有）

**不要做的**：
- ❌ 登入後的資料（需要權限的）
- ❌ 繞過付費牆
- ❌ 高頻率轟炸（每秒好幾次）
- ❌ 偽裝成真人瀏覽器試圖規避反爬（headless Chrome 不要亂用）
- ❌ 把抓到的資料當作自己原創發布 — 標註來源：「資料來源：各 ETF 發行商官網」

網站合理使用範圍內的爬蟲在台灣和多數地區都是合法的（判決有「Webcrawler.com 案」、美國 hiQ v. LinkedIn 等先例），但**商業使用時要更小心**。這專案的定位是個人學習 + 非營利分享，風險低。
