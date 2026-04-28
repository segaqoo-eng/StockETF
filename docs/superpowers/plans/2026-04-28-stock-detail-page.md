# 個股分析頁面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交叉持股表個股名稱可點擊，開新分頁顯示 TradingView K 線 + ETF 持倉 + 走勢 sparkline 的個股分析頁面。

**Architecture:** 獨立的 `stock.html` + `assets/stock.js`，透過 `?id=2330` 讀取現有 JSON 資料。修改 `scrapers/twse_prices.py` 在每筆價格加 `exchange` 欄位（TWSE/TPEX），供 TradingView symbol 使用。

**Tech Stack:** 原生 HTML/CSS/JS（無 framework）、TradingView Lightweight Widget（CDN）

---

## File Map

| 動作 | 檔案 | 說明 |
|------|------|------|
| Modify | `scrapers/twse_prices.py` | `fetch_all()` 在每筆加 `exchange` 欄位 |
| Create | `tests/test_twse_prices.py` | exchange 欄位單元測試 |
| Modify | `assets/app.js` | `renderRow()` 股票名稱加 `<a>` 連結 |
| Create | `stock.html` | 個股分析頁面 HTML |
| Create | `assets/stock.js` | 頁面邏輯：載入資料 / 渲染 / TradingView init |
| Modify | `assets/style.css` | 個股頁面 CSS（`stock-*` 類別） |
| Delete | `mockup_stock.html` | 刪除 mockup 暫存檔 |

---

## Task 1: `exchange` 欄位 — twse_prices.py

**Files:**
- Modify: `scrapers/twse_prices.py`
- Create: `tests/test_twse_prices.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_twse_prices.py`：

```python
from scrapers.twse_prices import PricesFetcher
from unittest.mock import patch
from datetime import date

TWSE_STUB = '''{
  "stat": "OK",
  "tables": [{
    "title": "每日收盤行情",
    "fields": ["證券代號","收盤價","漲跌(+/-)","漲跌價差"],
    "data": [["2330","550.00","<p style=\\"color:red\\">+</p>","19.50"]]
  }]
}'''

TPEX_STUB = '''{
  "stat": "ok",
  "tables": [{
    "title": "上櫃股票行情",
    "fields": ["代號","收盤","漲跌"],
    "data": [["3037","85.00","-1.20"]]
  }]
}'''

def test_fetch_all_tags_twse_exchange():
    fetcher = PricesFetcher()
    with patch.object(fetcher, "get", side_effect=[TWSE_STUB, TPEX_STUB]):
        result = fetcher.fetch_all(date(2026, 4, 27))
    assert result["2330"]["exchange"] == "TWSE"

def test_fetch_all_tags_tpex_exchange():
    fetcher = PricesFetcher()
    with patch.object(fetcher, "get", side_effect=[TWSE_STUB, TPEX_STUB]):
        result = fetcher.fetch_all(date(2026, 4, 27))
    assert result["3037"]["exchange"] == "TPEX"

def test_twse_takes_priority_over_tpex():
    """If same stock_id appears in both, TWSE wins."""
    fetcher = PricesFetcher()
    tpex_with_2330 = TPEX_STUB.replace('"3037"', '"2330"')
    with patch.object(fetcher, "get", side_effect=[TWSE_STUB, tpex_with_2330]):
        result = fetcher.fetch_all(date(2026, 4, 27))
    assert result["2330"]["exchange"] == "TWSE"
```

- [ ] **Step 2: 跑測試確認失敗**

```
.venv/Scripts/python -m pytest tests/test_twse_prices.py -v
```

期望：`AttributeError` 或 `KeyError: 'exchange'`

- [ ] **Step 3: 修改 `fetch_all()` 加 exchange 標記**

在 `scrapers/twse_prices.py` 的 `PricesFetcher.fetch_all()` 中：

```python
def fetch_all(self, target_date: date) -> dict[str, dict]:
    twse_date = target_date.strftime("%Y%m%d")
    tpex_date = f"{target_date.year - 1911}/{target_date.month:02d}/{target_date.day:02d}"

    prices: dict[str, dict] = {}
    try:
        twse_text = self.get(TWSE_URL.format(date=twse_date))
        twse = parse_twse_prices(twse_text)
        for sid, data in twse.items():
            prices[sid] = {**data, "exchange": "TWSE"}
        logger.info("prices: TWSE %d stocks", len(twse))
    except Exception as exc:
        logger.warning("prices: TWSE fetch failed: %s", exc)

    try:
        tpex_text = self.get(TPEX_URL.format(date=tpex_date))
        tpex = parse_tpex_prices(tpex_text)
        for sid, data in tpex.items():
            if sid not in prices:   # TWSE takes priority
                prices[sid] = {**data, "exchange": "TPEX"}
        logger.info("prices: TPEx %d stocks", len(tpex))
    except Exception as exc:
        logger.warning("prices: TPEx fetch failed: %s", exc)

    return prices
```

- [ ] **Step 4: 跑測試確認全過**

```
.venv/Scripts/python -m pytest tests/test_twse_prices.py -v
```

期望：3 passed

- [ ] **Step 5: 跑全套測試確認沒有 regression**

```
.venv/Scripts/python -m pytest -q
```

期望：all passed

- [ ] **Step 6: 重跑 main.py 更新 prices_today.json**

```
.venv/Scripts/python main.py
```

確認 `data/prices_today.json` 內容有 `"exchange": "TWSE"` 或 `"exchange": "TPEX"` 欄位。

- [ ] **Step 7: Commit**

```bash
git add scrapers/twse_prices.py tests/test_twse_prices.py data/
git commit -m "feat: tag prices with exchange field (TWSE/TPEX) for TradingView symbol"
```

---

## Task 2: 交叉持股表加個股連結

**Files:**
- Modify: `assets/app.js` line ~151

- [ ] **Step 1: 修改 `renderRow()` 讓股票名稱可點**

找到 `assets/app.js` 的 `renderRow` 函數，將第一欄改為：

```javascript
function renderRow(h) {
  const maxWeight = Math.max(...h.held_by.map(b => b.weight_pct));
  const badge = renderMarketBadge(h.market);
  const stockLink = `<a class="stock-detail-link" href="stock.html?id=${encodeURIComponent(h.stock_id)}" target="_blank" rel="noopener noreferrer">${escapeHtml(h.stock_name)}</a>`;
  return `
    <tr data-stock-id="${escapeHtml(h.stock_id)}">
      <td><b>${escapeHtml(h.stock_id)}</b> ${stockLink}${badge}</td>
      <td>${escapeHtml(h.industry || "—")}</td>
      <td class="center"><span class="count-badge">${h.held_by.length}</span></td>
      <td class="num weight">${maxWeight.toFixed(2)}%</td>
      <td class="num">${renderPriceCell(h.stock_id)}</td>
    </tr>
  `;
}
```

- [ ] **Step 2: 加 `.stock-detail-link` CSS**

在 `assets/style.css` 末尾加（在現有 stock page 區塊之前也可以）：

```css
.stock-detail-link { color: var(--text); text-decoration: none; }
.stock-detail-link:hover { color: #79c0ff; text-decoration: underline; }
```

- [ ] **Step 3: 瀏覽器驗證**

開 `http://localhost:8080`，在交叉持股表的個股名稱 hover 時應出現底線，點擊後開新分頁（此時 stock.html 還不存在，會 404，但連結行為正確）。

- [ ] **Step 4: Commit**

```bash
git add assets/app.js assets/style.css
git commit -m "ux: cross-table stock names link to stock.html?id=XXXX (new tab)"
```

---

## Task 3: `stock.html` 頁面骨架

**Files:**
- Create: `stock.html`

- [ ] **Step 1: 建立 `stock.html`**

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>個股分析 — StockETF</title>
  <link rel="stylesheet" href="assets/style.css">
  <style>
    /* ── 個股頁面專用覆蓋 ── */
    body { overflow-x: hidden; }

    .sp-topbar { display: flex; align-items: center; gap: 16px; padding: 10px 24px;
      background: var(--bg2); border-bottom: 1px solid var(--border); }
    .sp-back { color: #79c0ff; text-decoration: none; font-size: var(--fs-md); }
    .sp-back:hover { text-decoration: underline; }
    .sp-site { color: var(--text3); font-size: var(--fs-md); }

    .sp-header { padding: 20px 24px 16px; border-bottom: 1px solid var(--border); }
    .sp-title-row { display: flex; align-items: baseline; gap: 12px; margin-bottom: 8px; }
    .sp-id   { font-size: 30px; font-weight: 700; font-family: var(--mono); }
    .sp-name { font-size: 20px; color: var(--text2); }
    .sp-price-row { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
    .sp-close  { font-size: 34px; font-weight: 700; font-family: var(--mono); }
    .sp-change { font-size: 18px; font-weight: 600; }
    .sp-date   { font-size: var(--fs-sm); color: var(--text3);
      background: var(--bg2); border: 1px solid var(--border);
      padding: 2px 8px; border-radius: 10px; }
    .sp-date.stale { color: #d29922; border-color: rgba(210,153,34,0.4); }

    .sp-main { display: grid; grid-template-columns: 60fr 40fr;
      min-height: calc(100vh - 130px); }

    .sp-left  { border-right: 1px solid var(--border); padding: 16px; }
    .sp-right { padding: 16px; display: flex; flex-direction: column; gap: 18px;
      overflow-y: auto; }

    .sp-section-label { font-size: var(--fs-xs); font-weight: 600; letter-spacing: 0.08em;
      color: var(--text3); text-transform: uppercase; margin-bottom: 10px; }

    #tv-container { background: var(--bg2); border: 1px solid var(--border);
      border-radius: 8px; height: 460px; overflow: hidden; }

    .sp-card { background: var(--bg2); border: 1px solid var(--border);
      border-radius: 8px; padding: 14px; }
    .sp-card h3 { font-size: var(--fs-sm); font-weight: 600; color: var(--text2);
      text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 12px; }

    .sp-etf-table { width: 100%; border-collapse: collapse; }
    .sp-etf-table th { font-size: var(--fs-sm); color: var(--text3); text-align: left;
      padding: 4px 0; border-bottom: 1px solid var(--border); font-weight: 500; }
    .sp-etf-table th.r { text-align: right; }
    .sp-etf-table td { padding: 8px 0; border-bottom: 1px solid rgba(48,54,61,0.4);
      font-size: var(--fs-md); vertical-align: middle; }
    .sp-etf-table td.r { text-align: right; font-family: var(--mono); }
    .sp-etf-ticker { font-family: var(--mono); font-weight: 700; color: #79c0ff;
      font-size: var(--fs-md); }
    .sp-etf-name   { color: var(--text2); font-size: var(--fs-base); }

    .sp-coming { background: rgba(187,128,9,0.08); border: 1px solid rgba(187,128,9,0.3);
      border-radius: 8px; padding: 14px; display: flex; align-items: center;
      gap: 10px; color: #d29922; font-size: var(--fs-md); }

    .sp-loading { color: var(--text3); font-size: var(--fs-md); padding: 32px 0;
      text-align: center; }
    .sp-error   { color: #f85149; font-size: var(--fs-md); padding: 32px 0;
      text-align: center; }

    .tv-unavailable { height: 100%; display: flex; align-items: center;
      justify-content: center; color: var(--text3); font-size: var(--fs-md); }
  </style>
</head>
<body>

<div class="sp-topbar">
  <a class="sp-back" href="index.html">← 返回交叉持股</a>
  <span style="color:var(--border)">|</span>
  <span class="sp-site">StockETF 個股分析</span>
</div>

<div id="sp-header" class="sp-header">
  <div class="sp-loading">載入中…</div>
</div>

<div id="sp-main" class="sp-main" style="display:none">
  <div class="sp-left">
    <div class="sp-section-label">日 K 走勢</div>
    <div id="tv-container"></div>
  </div>
  <div class="sp-right">
    <div class="sp-card">
      <h3>ETF 持倉</h3>
      <div id="sp-etf-holdings"><div class="sp-loading">載入中…</div></div>
    </div>
    <div class="sp-card">
      <h3>各 ETF 持倉走勢</h3>
      <div id="sp-trend"></div>
    </div>
    <div class="sp-coming">
      <span style="font-size:20px">🏦</span>
      <div>
        <strong>法人籌碼</strong><br>
        <span style="font-size:var(--fs-sm)">外資 / 投信淨買賣超 — 即將推出</span>
      </div>
    </div>
  </div>
</div>

<!-- TradingView Widget -->
<script src="https://s3.tradingview.com/tv.js"></script>
<script src="assets/stock.js"></script>
</body>
</html>
```

- [ ] **Step 2: 確認骨架可在瀏覽器打開**

開 `http://localhost:8080/stock.html?id=2330`，應看到「載入中…」文字，無 JS 錯誤（stock.js 尚不存在所以會有 404 錯誤，下一 task 解決）。

- [ ] **Step 3: Commit**

```bash
git add stock.html
git commit -m "feat: add stock.html skeleton for individual stock analysis page"
```

---

## Task 4: `assets/stock.js` — 資料載入與渲染

**Files:**
- Create: `assets/stock.js`

- [ ] **Step 1: 建立 `assets/stock.js`**

```javascript
"use strict";

const state = {
  stockId: null,
  payload: null,    // latest.json
  prices: null,     // prices_today.json
  diff: null,       // latest_diff.json
  history: null,    // history_per_stock.json
};

/* ── 工具函數 ── */
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function formatDateShort(iso) {
  return iso ? iso.slice(5).replace("-", "/") : "";
}

/* ── 初始化：從 query string 取得 stock id ── */
function init() {
  const params = new URLSearchParams(location.search);
  state.stockId = params.get("id");
  if (!state.stockId) {
    document.getElementById("sp-header").innerHTML =
      `<div class="sp-error">網址缺少 ?id= 參數</div>`;
    return;
  }
  document.title = `${state.stockId} — StockETF 個股分析`;
  loadData();
}

/* ── 資料載入 ── */
async function loadData() {
  try {
    const [payloadRes, pricesRes, diffRes, histRes] = await Promise.all([
      fetch("data/latest.json",            { cache: "no-store" }),
      fetch("data/prices_today.json",      { cache: "no-store" }),
      fetch("data/latest_diff.json",       { cache: "no-store" }),
      fetch("data/history_per_stock.json", { cache: "no-store" }),
    ]);
    state.payload = payloadRes.ok  ? await payloadRes.json()  : null;
    state.prices  = pricesRes.ok   ? await pricesRes.json()   : null;
    state.diff    = diffRes.ok     ? await diffRes.json()     : null;
    state.history = histRes.ok     ? await histRes.json()     : null;
    render();
  } catch (err) {
    document.getElementById("sp-header").innerHTML =
      `<div class="sp-error">資料載入失敗：${escapeHtml(err.message)}</div>`;
  }
}

/* ── 主渲染 ── */
function render() {
  const sid = state.stockId;

  // 找股票名稱（從任意 ETF 持倉取）
  let stockName = sid;
  let market = "TW";
  if (state.payload) {
    for (const etf of state.payload.etfs) {
      const h = (etf.holdings || []).find(h => h.stock_id === sid);
      if (h) { stockName = h.stock_name; market = h.market || "TW"; break; }
    }
  }

  renderHeader(sid, stockName);
  renderEtfHoldings(sid);
  renderTrend(sid);
  initTradingView(sid);

  document.getElementById("sp-main").style.display = "grid";
}

/* ── 股票標頭 ── */
function renderHeader(sid, stockName) {
  const p = state.prices?.prices?.[sid];
  const priceDate = state.prices?.date || "";
  const todayIso = new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Taipei" });
  const stale = priceDate && priceDate < todayIso;

  let priceHtml = `<span style="color:var(--text3)">—</span>`;
  if (p) {
    const up = p.change > 0, down = p.change < 0;
    const cls = up ? "price-up" : down ? "price-down" : "";
    const arrow = up ? "▲" : down ? "▼" : "·";
    const sign = up ? "+" : "";
    priceHtml = `
      <span class="sp-close">${p.close.toLocaleString()}</span>
      <span class="sp-change ${cls}">${arrow} ${sign}${p.change_pct.toFixed(2)}%</span>`;
  }

  const dateBadge = priceDate
    ? `<span class="sp-date${stale ? " stale" : ""}" title="${stale ? "上次盤後資料" : "今日盤後"}">${priceDate.slice(5)} 盤後</span>`
    : "";

  document.getElementById("sp-header").innerHTML = `
    <div class="sp-title-row">
      <span class="sp-id">${escapeHtml(sid)}</span>
      <span class="sp-name">${escapeHtml(stockName)}</span>
    </div>
    <div class="sp-price-row">
      ${priceHtml}
      ${dateBadge}
    </div>
  `;
}

/* ── ETF 持倉表 ── */
function renderEtfHoldings(sid) {
  if (!state.payload) {
    document.getElementById("sp-etf-holdings").innerHTML =
      `<div class="sp-loading">無資料</div>`;
    return;
  }

  const byEtf = state.diff?.by_etf || {};
  const rows = state.payload.etfs
    .map(etf => {
      const h = (etf.holdings || []).find(h => h.stock_id === sid);
      if (!h) return null;
      const changed = (byEtf[etf.ticker]?.changed || []).find(c => c.stock_id === sid);
      const added   = (byEtf[etf.ticker]?.added   || []).find(c => c.stock_id === sid);
      let badge = "";
      if (added) {
        badge = `<span class="diff-badge diff-added">🆕</span>`;
      } else if (changed) {
        const up = changed.delta > 0;
        const sign = up ? "+" : "";
        badge = `<span class="diff-badge diff-${up ? "up" : "down"}">${sign}${changed.delta.toFixed(2)}%</span>`;
      }
      return { ticker: etf.ticker, name: etf.name, weight: h.weight_pct, badge };
    })
    .filter(Boolean)
    .sort((a, b) => b.weight - a.weight);

  if (rows.length === 0) {
    document.getElementById("sp-etf-holdings").innerHTML =
      `<div class="sp-loading">無 ETF 持有此股</div>`;
    return;
  }

  const trs = rows.map(r => `
    <tr>
      <td><span class="sp-etf-ticker">${escapeHtml(r.ticker)}</span></td>
      <td><span class="sp-etf-name">${escapeHtml(r.name)}</span></td>
      <td class="r">${r.weight.toFixed(2)}%</td>
      <td class="r">${r.badge}</td>
    </tr>`).join("");

  document.getElementById("sp-etf-holdings").innerHTML = `
    <table class="sp-etf-table">
      <thead><tr>
        <th>代號</th><th>名稱</th><th class="r">權重</th><th class="r">變化</th>
      </tr></thead>
      <tbody>${trs}</tbody>
    </table>`;
}

/* ── 持倉走勢 sparkline ── */
function renderTrend(sid) {
  const root = document.getElementById("sp-trend");
  const series = state.history && state.history[sid];
  if (!series) {
    root.innerHTML = `<div style="color:var(--text3);font-size:var(--fs-sm);padding:8px 0">無歷史資料</div>`;
    return;
  }
  const lines = Object.entries(series).filter(([, pts]) => pts.length >= 2);
  if (lines.length === 0) {
    root.innerHTML = `<div style="color:var(--text3);font-size:var(--fs-sm);padding:8px 0">資料點不足（需 ≥ 2 個交易日）</div>`;
    return;
  }

  const W = 560, H = 160, PAD_L = 40, PAD_R = 12, PAD_T = 10, PAD_B = 24;
  const allDates = [...new Set(lines.flatMap(([, pts]) => pts.map(p => p.date)))].sort();
  const dateIndex = Object.fromEntries(allDates.map((d, i) => [d, i]));
  const allWeights = lines.flatMap(([, pts]) => pts.map(p => p.weight));
  const minW = Math.min(...allWeights), maxW = Math.max(...allWeights);
  const range = maxW - minW || 0.01;
  const xScale = n => PAD_L + (n / Math.max(allDates.length - 1, 1)) * (W - PAD_L - PAD_R);
  const yScale = v => PAD_T + (1 - (v - minW) / range) * (H - PAD_T - PAD_B);

  const COLORS = ["#79c0ff","#f0883e","#56d364","#d2a8ff","#ffa198","#7ee787","#e3b341"];
  const paths = lines.map(([ticker, pts], i) => {
    const d = pts.map((p, j) => `${j === 0 ? "M" : "L"}${xScale(dateIndex[p.date]).toFixed(1)},${yScale(p.weight).toFixed(1)}`).join(" ");
    return `<path d="${d}" stroke="${COLORS[i % COLORS.length]}" stroke-width="2" fill="none"/>`;
  });

  const yLabels = [minW, (minW + maxW) / 2, maxW].map(v =>
    `<text x="${PAD_L - 4}" y="${yScale(v).toFixed(1)}" text-anchor="end" dominant-baseline="middle" fill="#6e7681" font-size="10">${v.toFixed(1)}%</text>`
  );
  const xLabels = [0, allDates.length - 1].map(i =>
    `<text x="${xScale(i).toFixed(1)}" y="${H - 4}" text-anchor="middle" fill="#6e7681" font-size="10">${allDates[i] ? allDates[i].slice(5) : ""}</text>`
  );

  const legend = lines.map(([ticker], i) =>
    `<span style="display:inline-flex;align-items:center;gap:5px;font-size:var(--fs-xs);color:var(--text2)">
      <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${COLORS[i % COLORS.length]}"></span>
      ${escapeHtml(ticker)}
    </span>`
  ).join("");

  root.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block">
      ${yLabels.join("")}${xLabels.join("")}${paths.join("")}
    </svg>
    <div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:6px">${legend}</div>`;
}

/* ── TradingView Widget ── */
function initTradingView(sid) {
  const exchange = state.prices?.prices?.[sid]?.exchange || "TWSE";
  const symbol = `${exchange}:${sid}`;
  const container = document.getElementById("tv-container");

  if (typeof TradingView === "undefined") {
    container.innerHTML = `<div class="tv-unavailable">📈 K 線圖需要網路連線（TradingView）</div>`;
    return;
  }

  try {
    new TradingView.widget({
      autosize: true,
      symbol,
      interval: "D",
      container_id: "tv-container",
      theme: "dark",
      locale: "zh_TW",
      toolbar_bg: "#161b22",
      hide_top_toolbar: false,
      hide_legend: false,
      save_image: false,
      studies: [],
    });
  } catch (e) {
    container.innerHTML = `<div class="tv-unavailable">K 線圖載入失敗：${escapeHtml(String(e))}</div>`;
  }
}

/* ── Entry point ── */
document.addEventListener("DOMContentLoaded", init);
```

- [ ] **Step 2: 瀏覽器驗證**

開 `http://localhost:8080/stock.html?id=2330`，確認：
- 頁面顯示「台灣積體電路製造」標頭與收盤價
- 右側 ETF 持倉表有資料
- 右側走勢 sparkline 有圖
- 左側 TradingView K 線圖嵌入（需要網路，顯示 TWSE:2330）
- 法人籌碼顯示「即將推出」黃色區塊

再測 `http://localhost:8080/stock.html?id=3037`（上櫃股），確認 symbol 為 `TPEX:3037`。

- [ ] **Step 3: Commit**

```bash
git add assets/stock.js
git commit -m "feat: stock.js — load data and render stock detail page"
```

---

## Task 5: 收尾

**Files:**
- Delete: `mockup_stock.html`
- Modify: `docs/superpowers/specs/2026-04-28-stock-detail-page-design.md`（確認完成）

- [ ] **Step 1: 刪除 mockup 檔案**

```bash
git rm mockup_stock.html
```

- [ ] **Step 2: 最終驗收清單**

手動確認：
1. `http://localhost:8080` → 交叉持股表 → 點台積電名稱 → 開新分頁 → 顯示正確
2. 收盤價顏色：漲=紅、跌=綠（台灣慣例）
3. 價格 stale 時日期 badge 為黃色
4. ETF 持倉表依權重排序，有加減碼 badge
5. sparkline 有折線圖
6. TradingView widget 嵌入（有網路）
7. `http://localhost:8080/stock.html?id=FAKE` → ETF 持倉欄顯示「無 ETF 持有此股」

- [ ] **Step 3: 最終 commit**

```bash
git add -A
git commit -m "feat: individual stock analysis page (stock.html + stock.js)"
git push
```

---

## 自我審查結果

- **Spec coverage:** 所有 spec 需求都有對應 task ✓
- **Exchange 欄位:** Task 1 實作並有測試 ✓
- **TradingView fallback:** stock.js `initTradingView` 有 `typeof TradingView === "undefined"` 防護 ✓
- **無 TDD for frontend:** HTML/JS 無單元測試，以手動驗收清單替代 ✓
- **Type consistency:** `state.prices.prices[sid].exchange` 在 Task 1/4 一致 ✓
