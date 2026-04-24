# StockETF — 台灣 ETF 交叉持股分析網站 設計文件

**日期**：2026-04-24
**參考產品**：https://zhaoyuanliu.github.io/etf-analysis/
**本專案位置**：`C:\Users\User\source\repos\StockETF`
**部署目標**：GitHub Pages（public repo）+ GitHub Actions 排程

---

## 1. 目標與動機

做一個跟參考網站類似的台灣 ETF 交叉持股分析工具，混合三種需求：

- **個人自用**：研究投資時參考
- **公開分享**：放在 FB 粉專導流，未來搭配 Google AdSense 變現
- **學習作品**：練習 Python 爬蟲、資料處理、前端 JS、GitHub Actions；同時作為作品集

### 成功標準

MVP v1 完成時：
- 打開 GitHub Pages 網址，能看到至少 4 檔 ETF 的交叉持股表
- 表格可篩選、可展開股票看持有 ETF 明細
- 爬蟲 + 前端 + 部署流程跑得通

v3 完成時：
- 每天自動更新，不用人工干預
- FB 貼連結有漂亮縮圖
- 具備申請 Google AdSense 的基本條件

---

## 2. 功能範圍

### 包含

| ID | 功能 | 階段 |
|---|---|---|
| F1 | ETF 交叉持股分析表（主表格） | v1 |
| F2 | 表格篩選（最少被 N 檔持有、產業別、搜尋） | v1 |
| F3 | 點擊股票展開持有 ETF 明細 | v1 |
| F4 | ETF 總覽頁（卡片式） | v2 |
| F5 | 主動式 ETF 持股變動歷史 | v3 |
| F7 | 匯出 CSV | v3 |
| F8 | 產生 FB 分享圖（html2canvas） | v3 |
| F9 | 手機 RWD | v2 |

### 明確排除（MVP 不做）

- F6 使用者帳號 / 留言系統
- 即時股價、K 線圖、技術指標
- 投資組合模擬、回測
- 多語系
- 券商下單連結（法規風險）
- PWA / 原生 App

---

## 3. 系統架構

三層分離：**爬蟲層（Python）｜ 資料層（JSON）｜ 前端層（靜態 HTML+JS）**

```
┌───────────────────────────────────────────────────────┐
│  GitHub Actions Cron  每日 16:00 / 18:00 台北時間      │
└────────────────┬──────────────────────────────────────┘
                 ▼
┌───────────────────────────────────────────────────────┐
│  Python 爬蟲層  scrapers/                             │
│  野村 ── 統一 ── 群益 ── 元大 ── ...                  │
│                     ▼                                  │
│  Normalizer  統一成分股資料格式                        │
└────────────────┬──────────────────────────────────────┘
                 ▼
┌───────────────────────────────────────────────────────┐
│  data/ (JSON 檔)  commit 到 repo                      │
│    ├─ latest.json          ← 最新聚合                 │
│    └─ snapshots/YYYY-MM-DD.json  ← 每日快照           │
└────────────────┬──────────────────────────────────────┘
                 ▼ git push
┌───────────────────────────────────────────────────────┐
│  GitHub Pages  (免費)                                  │
│  index.html + assets/ + data/*.json                    │
└────────────────┬──────────────────────────────────────┘
                 ▼ HTTPS
┌───────────────────────────────────────────────────────┐
│  瀏覽器  (手機/桌機)                                   │
└───────────────────────────────────────────────────────┘
```

### 技術選型

| 層 | 技術 | 理由 |
|---|---|---|
| 爬蟲 | Python 3.12 + requests + BeautifulSoup4 + pyyaml | 主流、資料處理強 |
| 測試 | pytest | 標準 |
| 前端 | 原生 HTML + CSS + ES6+ JS | 降低學習負擔；跟參考站一致；零建置流程 |
| 分享圖 | html2canvas (CDN) | DOM → PNG，輕量 |
| 排程 | GitHub Actions cron | 免費、跟 repo 綁一起 |
| 託管 | GitHub Pages（public） | 免費；有 HTTPS |

---

## 4. 資料模型

### 4.1 `data/latest.json` — 首頁主資料

F1 / F2 / F3 / F4 共用。前端 fetch 一次即可渲染。

```json
{
  "updated_at": "2026-04-24T16:00:00+08:00",
  "etfs": [
    {
      "ticker": "00980A",
      "name": "野村臺灣智慧優選",
      "type": "active",
      "aum_billion": 197,
      "price": 26.51,
      "holdings_count": 53,
      "tags": ["主動", "台股型"],
      "color": "#34d399"
    }
  ],
  "holdings": [
    {
      "stock_id": "2330",
      "stock_name": "台積電",
      "industry": "半導體",
      "market_cap_billion": 30000,
      "held_by": [
        { "etf": "0050",   "weight_pct": 48.5, "shares": 100000000 },
        { "etf": "00980A", "weight_pct": 32.1, "shares":   5000000 }
      ]
    }
  ]
}
```

### 4.2 `data/snapshots/YYYY-MM-DD.json` — 每日快照

結構與 `latest.json` 相同。每日由爬蟲 commit 一份，append-only。F5 的「持股變動」讀多份 snapshot 做 diff。

### 4.3 `data/etfs/{ticker}.json` — 暫不實作

先用 latest + snapshots 即可。等前端載入 snapshots 出現效能問題再加。

### 4.4 資料設計原則

1. **前端只需知道 `latest.json`** 就能渲染 80% 內容
2. **歷史資料 append-only**：舊 snapshot 永不動
3. **欄位存事實不存計算結果**：存 `weight_pct`、`shares`，排名由前端即時算
4. **Primary key**：ETF 用 `ticker`、股票用 `stock_id`

---

## 5. 爬蟲層設計

### 5.1 原則

**一家發行商一支爬蟲**（不是一檔 ETF 一支）— 同一發行商網站結構通常一致，可重用。

### 5.2 目錄結構

```
scrapers/
  __init__.py
  base.py            ← BaseScraper: HTTP session、重試、User-Agent
  nomura.py          ← 00980A
  capital.py         ← 00981A (統一)
  yuanta.py          ← 0050, 0056
  cathay.py          ← 00878 (v2)
  ...
config/
  etfs.yml           ← ticker → scraper 模組、tags、color
  stocks.yml         ← stock_id → industry（爬蟲抓不到時補）
main.py              ← 排程進入點
normalizer.py        ← 合併、產出 latest.json 與 snapshot
tests/
  fixtures/          ← 各家網站的 HTML 樣本
  test_nomura.py     ← 離線單元測試
```

### 5.3 Scraper 介面

```python
class NomuraScraper(BaseScraper):
    def fetch(self, ticker: str) -> list[Holding]:
        """回傳該 ETF 的持股清單。
        每筆: {stock_id, stock_name, weight_pct, shares}
        """
```

每支爬蟲職責**只有一件事**：從官網抓回一張持股清單。tags、color、合併、寫檔都交給 normalizer。

### 5.4 容錯策略 — 單點失敗不影響全局

```
跑 N 家爬蟲
  ├─ (N-1) 家成功 → 用新資料
  └─ 1 家失敗
      → log 錯誤
      → 沿用前一天該 ETF 的資料
      → 該 ETF 的 updated_at 保留舊日期
      → 前端顯示「⚠️ 資料延遲 X 天」
```

永遠不讓單家爬蟲失敗導致整個網站空白。

### 5.5 測試策略 — 離線優先

- 初次爬到的 HTML 存成 `tests/fixtures/nomura_00980A_2026-04-24.html`
- 單元測試以 HTML fixture 為輸入，驗證 parser 正確
- 整合測試（冒煙）偶爾手動跑一次打真實網站，確認沒被改版

### 5.6 禮貌爬蟲

- User-Agent: `StockETF-Bot/1.0 (+https://github.com/<user>/StockETF)`
- 請求間隔 2-3 秒
- 失敗重試 3 次（exponential backoff: 2s, 4s, 8s）
- 僅在排程時間執行

### 5.7 config/etfs.yml 範例

```yaml
"0050":
  scraper: yuanta
  name: 元大台灣50
  type: passive
  tags: [市值型]
  color: "#4a9eff"

"00980A":
  scraper: nomura
  name: 野村臺灣智慧優選
  type: active
  tags: [主動, 台股型]
  color: "#34d399"
```

爬蟲抓完資料後，normalizer 把這份 config 合併進 JSON 輸出。

---

## 6. 前端設計

### 6.1 頁面結構

```
┌──────────────────────────────────────────────┐
│  📊 StockETF       更新於: 2026-04-24 16:00  │  ← 頂欄
├──────────────────────────────────────────────┤
│  [交叉持股]  [ETF 總覽]  [持股變動]            │  ← Tab
├──────────────────────────────────────────────┤
│            主內容區（隨分頁切換）              │
└──────────────────────────────────────────────┘
```

### 6.2 分頁 1：交叉持股（F1+F2+F3，首頁）

- 篩選列：最少被 X 檔持有（2/3/4/5+）、產業下拉、搜尋
- 主表格：股票 ｜ 產業 ｜ 被幾檔 ｜ 最高權重 ｜ 總市值
- 點一列展開：顯示該股在哪些 ETF 各佔多少
- 預設排序：被持有數由多到少

### 6.3 分頁 2：ETF 總覽（F4，v2）

- 卡片式：ticker、名稱、規模、tags、color 色條
- 點卡片 → 展開該 ETF 完整持股明細（依權重排序）
- 分組：被動式 / 主動式

### 6.4 分頁 3：持股變動（F5，v3）

- 選 ETF + 日期區間（預設：最近 7 日）
- 顯示四組變化：新進、剔除、增持（權重變高）、減持（權重變低）
- 以前後兩日 snapshot 的 diff 為準

### 6.5 額外元件

- 頂欄右側：分享按鈕（F8）、CSV 下載（F7）
- 頁尾：免責聲明、資料來源、最後更新、GitHub 連結
- RWD（F9，v2）：寬度 < 768px 時表格轉卡片直列

### 6.6 視覺風格

比照參考網站：深色底 `#0d1117`、藍色主色 `#58a6ff`、
字體 Noto Sans TC（中文）+ JetBrains Mono（數字）、Tab 列置頂。

---

## 7. 排程與部署

### 7.1 流水線

```
每天 16:00 / 18:00 台北時間
  ↓
GitHub Actions 觸發
  ↓
checkout + setup Python + pip install
  ↓
python main.py  (跑 scrapers → normalizer → 寫 data/)
  ↓
檢查 git diff data/
  ├─ 無變化 → 結束
  └─ 有變化 → git commit + push
       ↓
  GitHub Pages 自動部署 (~1 分鐘)
```

16:00 與 18:00 共用同一個 workflow；用 `git diff` 當狀態：若 16:00 已拿到新資料，18:00 就沒變化自然 no-op。

### 7.2 GitHub Actions Workflow

`.github/workflows/daily-update.yml`：

```yaml
name: Daily ETF Data Update
on:
  schedule:
    - cron: "0 8 * * *"    # 台北 16:00 (UTC+8)
    - cron: "0 10 * * *"   # 台北 18:00
  workflow_dispatch:

jobs:
  scrape:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python main.py
      - name: Commit if changed
        run: |
          git config user.name "etf-bot"
          git config user.email "bot@users.noreply.github.com"
          git add data/
          git diff --staged --quiet || git commit -m "data: update $(date +%Y-%m-%d)"
          git push
```

### 7.3 部署結構

```
StockETF/
├─ index.html
├─ assets/
│   ├─ style.css
│   └─ app.js
├─ data/                   ← Actions 每日更新
│   ├─ latest.json
│   └─ snapshots/*.json
├─ config/
│   ├─ etfs.yml
│   └─ stocks.yml
├─ scrapers/
│   ├─ base.py
│   └─ *.py
├─ tests/
│   ├─ fixtures/
│   └─ test_*.py
├─ main.py
├─ normalizer.py
├─ requirements.txt
├─ .github/workflows/daily-update.yml
└─ README.md
```

GitHub Pages 設定：Settings → Pages → Source: `main` branch / root。

### 7.4 監控

MVP 只用 GitHub Actions 預設失敗 email 通知。v4 再考慮 Discord / Telegram。

### 7.5 成本

| 項目 | 月費 |
|---|---|
| GitHub Pages | $0 |
| GitHub Actions (public) | $0 |
| 網域（選配） | ~$25 NTD/月 |
| **合計（MVP）** | **$0** |

---

## 8. 階段規劃

### 8.1 MVP v1（2-3 週）— 證明整條路通

- 4 檔 ETF：`0050`、`0056`、`00980A`、`00981A`
- 3 支爬蟲：元大、野村、統一
- `data/latest.json` 產出
- 前端分頁 1（F1 + F2 + F3），桌機版
- config/etfs.yml 手動維護 tags/color
- **手動**跑 `python main.py`，commit 推上 GitHub Pages

**驗收**：打開網址能看到交叉持股表，可篩選、可展開。

### 8.2 v2（1-2 週）— 自動化 + 擴展

- GitHub Actions 每日 16:00 / 18:00 排程
- Snapshot 歸檔
- 擴充到 8-10 檔 ETF（加 2-3 家發行商）
- 分頁 2：F4 ETF 總覽
- F9 手機 RWD
- Google Analytics 4

**驗收**：一整週不干預資料自動更新。

### 8.3 v3（1-2 週）— 進階功能 + 變現準備

- 分頁 3：F5 持股變動（讀 snapshots diff）
- F7 匯出 CSV（client-side）
- F8 分享圖（html2canvas）
- Open Graph meta tags
- Google AdSense 送審
- SEO：sitemap、robots.txt

**驗收**：FB 貼連結有縮圖，可下載 CSV，AdSense 送件。

### 8.4 v4+（不列入本 spec）

- 圖表（Chart.js）
- 自訂網域
- 若要 F6 → 架構升級為前後端分離

---

## 9. 風險與備註

### 9.1 技術風險

| 風險 | 緩解 |
|---|---|
| 發行商網站改版導致爬蟲失效 | 離線測試 fixture 會抓到變化；容錯策略沿用舊資料 |
| 爬蟲被擋 IP | 禮貌爬蟲（User-Agent、節流、重試） |
| 主動式 ETF 每日 18:00 才公布 | 18:00 跑第二次，git diff 自動處理 |
| GitHub Pages 部署延遲 | 接受 ~1 分鐘落差 |

### 9.2 法律與合規

- 頁尾明確免責聲明：「資訊僅供參考，不構成投資建議」
- 資料來源標註各發行商官網
- 不做券商下單連結（避免觸及投顧法）
- 遵守各網站 robots.txt（若有）

### 9.3 變現現實

- FB 粉專分潤（Performance Bonus）是對**FB 原生內容**付費，不對外部網站連結付費
- 網站本身變現走 Google AdSense
- 兩邊流量互相導：粉專貼圖文（可能拿 FB 分潤）→ 導流到網站（累積 AdSense 點擊）

---

## 10. 開放問題（等 MVP 做完再處理）

- 主動式 ETF 品項快速增加，是否做自動發現機制？（v3 之後考慮）
- 是否要保留「盤中更新」能力？（現階段 NO）
- 手機 RWD 表格設計的具體互動（v2 時再細設計）
- 分享圖的版型是固定模板還是隨內容調整？（v3 時 mockup）

---

**本文件版本**：v1.0
**下一步**：使用 `superpowers:writing-plans` skill 產出 v1 的實作計畫（tasks 層級）。
