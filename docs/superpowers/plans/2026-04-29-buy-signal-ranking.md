# 買進評分排行榜 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `index.html` 新增「買進評分」tab，列出所有 ETF 持股的綜合買進分數排行榜，支援漸進式載入與 localStorage 快取。

**Architecture:** 新建 `assets/ranking.js` 負責快取管理、資料抓取、分數計算、渲染。評分函數從 `stock.js` 複製（兩者都是全域 script，無 module 系統），讓 `index.html` 和 `stock.html` 保持獨立載入。Tab 啟動時 lazy init，只初始化一次。

**Tech Stack:** 原生 JS (ES6)、FinMind API（免費，無需 key）、localStorage（快取）、現有 CSS 變數系統

---

## 檔案變動總覽

| 檔案 | 變動類型 | 說明 |
|---|---|---|
| `index.html` | 修改 | 加 tab 按鈕 + `<section id="tab-ranking">` |
| `assets/app.js` | 修改 | `VALID_TABS` 加 "ranking"、`applyHash()` 加觸發 hook |
| `assets/ranking.js` | 新建 | 快取、抓取、計算、渲染全部邏輯 |
| `assets/style.css` | 修改 | 進度條、排行表格、TAG 統計、分數顏色 |

---

## Task 1：index.html — 加 tab 按鈕與排行榜骨架

**Files:**
- Modify: `index.html`

- [ ] **Step 1：加 tab 按鈕**

在 `index.html` 第 26 行的 `<nav class="tab-nav">` 區塊，在最後一個 `<button>` 後面加一個新按鈕：

```html
<button class="tab-btn" data-tab="ranking">買進評分</button>
```

結果（完整 nav）：
```html
<nav class="tab-nav">
  <button class="tab-btn active" data-tab="cross">交叉持股</button>
  <button class="tab-btn" data-tab="etfs">ETF 總覽</button>
  <button class="tab-btn" data-tab="changes">各 ETF 持股變化</button>
  <button class="tab-btn" data-tab="consensus">共識加減碼</button>
  <button class="tab-btn" data-tab="ranking">買進評分</button>
</nav>
```

- [ ] **Step 2：加排行榜 section**

在 `index.html` 第 65 行 `</main>` 之前，加入新 section：

```html
<section id="tab-ranking" class="tab-panel">
  <div id="ranking-root">
    <p class="loading">點選上方「買進評分」載入資料</p>
  </div>
</section>
```

- [ ] **Step 3：加 ranking.js script 標籤**

在 `index.html` 底部，`<script src="assets/app.js"></script>` 之後加：

```html
<script src="assets/ranking.js"></script>
```

- [ ] **Step 4：確認 HTML 結構正確**

開啟 `http://localhost:8080`，確認 tab 列出現「買進評分」按鈕，點後顯示「點選上方…」文字（ranking.js 尚未建立，先確認骨架正確）。

- [ ] **Step 5：commit**

```
git add index.html
git commit -m "feat(ranking): add 買進評分 tab skeleton to index.html"
```

---

## Task 2：app.js — VALID_TABS + 觸發 hook

**Files:**
- Modify: `assets/app.js:712` (VALID_TABS)
- Modify: `assets/app.js:714` (applyHash)

- [ ] **Step 1：VALID_TABS 加入 "ranking"**

找到這一行（app.js 約第 712 行）：
```javascript
const VALID_TABS = new Set(["cross", "etfs", "changes", "consensus"]);
```
改成：
```javascript
const VALID_TABS = new Set(["cross", "etfs", "changes", "consensus", "ranking"]);
```

- [ ] **Step 2：applyHash 加 ranking 觸發**

找到 `applyHash()` 函數，在 `activateTab(...)` 那行之後加入：

```javascript
function applyHash() {
  const hash = location.hash.slice(1);
  const [tab, etfTicker] = hash.split("/");

  activateTab(VALID_TABS.has(tab) ? tab : "cross");

  // 新增：ranking tab 第一次啟動時 lazy init
  if ((VALID_TABS.has(tab) ? tab : "cross") === "ranking") {
    if (typeof initRankingTab === "function") initRankingTab();
  }

  // Sub-routing only matters for the ETF accordion right now.
  if (tab === "etfs" && etfTicker) {
    const card = document.querySelector(`details[data-ticker="${CSS.escape(etfTicker)}"]`);
    if (card) {
      card.open = true;
      requestAnimationFrame(() => {
        card.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }
}
```

- [ ] **Step 3：手動測試**

開啟 `http://localhost:8080`，點「買進評分」tab，確認 URL 變成 `#ranking`，頁面切換正確，無 JS 錯誤（console 可能有 `initRankingTab is not a function`，等 Task 3 後消失）。

- [ ] **Step 4：commit**

```
git add assets/app.js
git commit -m "feat(ranking): wire ranking tab into hash router"
```

---

## Task 3：ranking.js — 建立骨架、快取管理、helper 函數

**Files:**
- Create: `assets/ranking.js`

- [ ] **Step 1：建立 ranking.js，加快取管理**

建立 `assets/ranking.js`，內容如下：

```javascript
// ranking.js — 買進評分排行榜
// 依賴：app.js 已載入（state.payload, state.prices 可用）

let _rankingInitialized = false;

/* ── 快取管理 ── */

function _rankingCacheKey() {
  const now = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Taipei" }));
  const hh = now.getHours();
  const pad = n => String(n).padStart(2, "0");
  // 下午2點前用昨天的資料
  if (hh < 14) {
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    return `scores_${yesterday.getFullYear()}-${pad(yesterday.getMonth()+1)}-${pad(yesterday.getDate())}`;
  }
  return `scores_${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}`;
}

function _loadRankingCache() {
  try {
    const key = _rankingCacheKey();
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch (_) { return null; }
}

function _saveRankingCache(data) {
  const key = _rankingCacheKey();
  try {
    localStorage.setItem(key, JSON.stringify(data));
    // 清除超過2天的舊 key
    const keysToRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith("scores_") && k !== key) {
        keysToRemove.push(k);
      }
    }
    keysToRemove.forEach(k => localStorage.removeItem(k));
  } catch (e) {
    // QuotaExceededError → 降級為只存 session 記憶體（data 已在 _rankingResults）
    console.warn("localStorage quota exceeded, cache skipped");
  }
}

/* ── FinMind API helpers（與 stock.js 相同邏輯，獨立複製） ── */

function _rankingStartDate(monthsBack) {
  const d = new Date();
  d.setMonth(d.getMonth() - monthsBack);
  return d.toISOString().slice(0, 10);
}

async function _rankingFetchOHLCV(sid) {
  const url = `https://api.finmindtrade.com/api/v4/data` +
    `?dataset=TaiwanStockPrice&data_id=${encodeURIComponent(sid)}&start_date=${_rankingStartDate(3)}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return [];
    const d = await res.json();
    if (d.status !== 200 || !Array.isArray(d.data)) return [];
    return d.data.map(r => ({
      time: r.date, open: r.open, high: r.max, low: r.min,
      close: r.close, volume: r.Trading_Volume || 0,
    })).filter(c => c.open != null && c.close != null);
  } catch (_) { return []; }
}

async function _rankingFetchInstitutional(sid) {
  const url = `https://api.finmindtrade.com/api/v4/data` +
    `?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id=${encodeURIComponent(sid)}&start_date=${_rankingStartDate(2)}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return [];
    const d = await res.json();
    if (d.status !== 200 || !Array.isArray(d.data)) return [];
    return d.data;
  } catch (_) { return []; }
}

function _rankingParseInstitutional(raw) {
  const byDate = {};
  for (const r of raw) {
    if (!byDate[r.date]) byDate[r.date] = { foreign: 0, trust: 0, dealer: 0 };
    const net = ((r.buy || 0) - (r.sell || 0)) / 1000;
    const n = r.name || "";
    if (n === "Foreign_Investor" || n === "Foreign_Dealer_Self") byDate[r.date].foreign += net;
    else if (n === "Investment_Trust")                            byDate[r.date].trust   += net;
    else if (n === "Dealer_self" || n === "Dealer_Hedging")      byDate[r.date].dealer  += net;
  }
  return Object.entries(byDate).sort((a, b) => a[0] < b[0] ? 1 : -1);
}

/* ── 評分函數（與 stock.js 相同，獨立複製） ── */

function _rCalcEMA(arr, period) {
  const k = 2 / (period + 1);
  let ema = arr[0];
  return arr.map((v, i) => { if (i > 0) ema = v * k + ema * (1 - k); return ema; });
}

function _rCalcMA(candles, n) {
  return candles.map((c, i) => {
    if (i < n - 1) return null;
    const avg = candles.slice(i - n + 1, i + 1).reduce((s, x) => s + x.close, 0) / n;
    return { time: c.time, value: +avg.toFixed(2) };
  }).filter(Boolean);
}

function _rCalcRSI(candles, period = 14) {
  if (candles.length < period + 1) return [];
  const results = [];
  let avgGain = 0, avgLoss = 0;
  for (let i = 1; i <= period; i++) {
    const d = candles[i].close - candles[i - 1].close;
    if (d > 0) avgGain += d; else avgLoss -= d;
  }
  avgGain /= period; avgLoss /= period;
  for (let i = period; i < candles.length; i++) {
    const d = candles[i].close - candles[i - 1].close;
    avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period;
    avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period;
    const rsi = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
    results.push({ time: candles[i].time, value: +rsi.toFixed(2) });
  }
  return results;
}

function _rCalcMACD(candles, fast = 12, slow = 26, sig = 9) {
  const closes = candles.map(c => c.close);
  const emaFast = _rCalcEMA(closes, fast);
  const emaSlow = _rCalcEMA(closes, slow);
  const macdLine = emaFast.map((v, i) => v - emaSlow[i]);
  const signalLine = _rCalcEMA(macdLine.slice(slow - 1), sig);
  return macdLine.slice(slow - 1).map((m, i) => {
    const s = signalLine[i], h = m - s;
    return { time: candles[slow - 1 + i].time, macd: +m.toFixed(3), signal: +s.toFixed(3), hist: +h.toFixed(3) };
  });
}

function _rCalcKD(candles, period = 9, sm = 3) {
  let k = 50, d = 50;
  return candles.slice(period - 1).map((c, i) => {
    const sl = candles.slice(i, i + period);
    const hi = Math.max(...sl.map(x => x.high));
    const lo = Math.min(...sl.map(x => x.low));
    const rsv = hi === lo ? 50 : (c.close - lo) / (hi - lo) * 100;
    k = (k * (sm - 1) + rsv) / sm;
    d = (d * (sm - 1) + k) / sm;
    return { time: c.time, k: +k.toFixed(2), d: +d.toFixed(2) };
  });
}

function _rConsecutiveDays(rows, key) {
  if (!rows.length) return 0;
  const first = rows[0][1][key] >= 0 ? 1 : -1;
  let count = 0;
  for (const [, vals] of rows) {
    if ((vals[key] >= 0 ? 1 : -1) === first) count++;
    else break;
  }
  return first * count;
}

function _rComputeScore(candles, instRows) {
  // Technical
  let techScore = 0; const techSigs = [];
  const rsiData = _rCalcRSI(candles);
  if (rsiData.length) {
    const rsi = rsiData[rsiData.length - 1].value;
    if (rsi < 30)      { techScore += 6; techSigs.push({ reason: "RSI 超賣（<30）", score: 6 }); }
    else if (rsi < 50) { techScore += 3; techSigs.push({ reason: "RSI 中低區", score: 3 }); }
    else if (rsi < 70) { techScore += 2; techSigs.push({ reason: "RSI 健康", score: 2 }); }
    else if (rsi < 80) { techScore -= 2; techSigs.push({ reason: "RSI 偏熱", score: -2 }); }
    else               { techScore -= 5; techSigs.push({ reason: "RSI 過熱（>80）", score: -5 }); }
  }
  const macdData = _rCalcMACD(candles);
  if (macdData.length >= 2) {
    const prev = macdData[macdData.length - 2], curr = macdData[macdData.length - 1];
    if (prev.hist <= 0 && curr.hist > 0)      { techScore += 6; techSigs.push({ reason: "MACD 黃金交叉", score: 6 }); }
    else if (prev.hist >= 0 && curr.hist < 0) { techScore -= 6; techSigs.push({ reason: "MACD 死亡交叉", score: -6 }); }
    else if (curr.macd > 0)                   { techScore += 3; techSigs.push({ reason: "MACD DIF>0", score: 3 }); }
  }
  const kdData = _rCalcKD(candles);
  if (kdData.length >= 2) {
    const prev = kdData[kdData.length - 2], curr = kdData[kdData.length - 1];
    if (prev.k <= prev.d && curr.k > curr.d)  { techScore += 5; techSigs.push({ reason: "KD 黃金交叉", score: 5 }); }
    else if (curr.k < 20)                      { techScore += 4; techSigs.push({ reason: "KD 超賣", score: 4 }); }
    else if (prev.k >= prev.d && curr.k < curr.d && curr.k >= 20) { techScore -= 3; techSigs.push({ reason: "KD 死亡交叉", score: -3 }); }
    else if (curr.k > 80)                      { techScore -= 3; techSigs.push({ reason: "KD 超買", score: -3 }); }
  }
  const ma5 = _rCalcMA(candles, 5), ma20 = _rCalcMA(candles, 20), ma60 = _rCalcMA(candles, 60);
  if (ma5.length && ma20.length && ma60.length) {
    const v5 = ma5[ma5.length-1].value, v20 = ma20[ma20.length-1].value, v60 = ma60[ma60.length-1].value;
    if (v5 > v20 && v20 > v60)      { techScore += 8; techSigs.push({ reason: "均線多頭排列", score: 8 }); }
    else if (v5 < v20 && v20 < v60) { techScore -= 8; techSigs.push({ reason: "均線空頭排列", score: -8 }); }
  }
  const tech = Math.max(-30, Math.min(30, techScore));

  // Chip
  let chipScore = 0; const chipSigs = [];
  if (instRows && instRows.length) {
    const near5 = instRows.slice(0, 5);
    const fT = near5.reduce((s, [,v]) => s + v.foreign, 0);
    const tT = near5.reduce((s, [,v]) => s + v.trust, 0);
    const dT = near5.reduce((s, [,v]) => s + v.dealer, 0);
    if (fT > 0) { chipScore += 5; chipSigs.push({ reason: "外資近5日買超", score: 5 }); }
    else if (fT < 0) { chipScore -= 5; chipSigs.push({ reason: "外資近5日賣超", score: -5 }); }
    if (tT > 0) { chipScore += 4; chipSigs.push({ reason: "投信近5日買超", score: 4 }); }
    else if (tT < 0) { chipScore -= 4; chipSigs.push({ reason: "投信近5日賣超", score: -4 }); }
    if (dT > 0) { chipScore += 2; } else if (dT < 0) { chipScore -= 2; }
    const fDays = _rConsecutiveDays(instRows, "foreign");
    if (fDays >= 5)       { chipScore += 5; chipSigs.push({ reason: `外資連${fDays}日買`, score: 5 }); }
    else if (fDays <= -5) { chipScore -= 5; chipSigs.push({ reason: `外資連${Math.abs(fDays)}日賣`, score: -5 }); }
    if (fT > 0 && tT > 0 && dT > 0) { chipScore += 6; chipSigs.push({ reason: "三大法人同買", score: 6 }); }
    else if (fT < 0 && tT < 0 && dT < 0) { chipScore -= 6; chipSigs.push({ reason: "三大法人同賣", score: -6 }); }
  }
  const chip = Math.max(-30, Math.min(30, chipScore));

  // Volume-price
  let volScore = 0;
  if (candles.length >= 6) {
    const last = candles[candles.length - 1], prev = candles[candles.length - 2];
    const slice5 = candles.slice(candles.length - 6, candles.length - 1);
    const avg5vol = slice5.reduce((s, c) => s + c.volume, 0) / 5;
    const 放量 = last.volume > avg5vol * 1.5, 縮量 = last.volume < avg5vol * 0.7;
    const 漲 = last.close > prev.close, 跌 = last.close < prev.close;
    if (放量 && 漲) volScore += 6;
    else if (放量 && 跌) volScore -= 6;
    else if (縮量 && 漲) volScore -= 2;
    else if (縮量 && 跌) volScore += 2;
  }
  const vol = Math.max(-20, Math.min(20, volScore));

  // Trend
  let trendScore = 0;
  if (candles.length >= 2) {
    const last = candles[candles.length - 1], prev = candles[candles.length - 2];
    const s60 = candles.slice(-60);
    const h60 = Math.max(...s60.map(c => c.high)), l60 = Math.min(...s60.map(c => c.low));
    if (last.close >= h60)       trendScore += 8;
    else if (last.close <= l60)  trendScore -= 8;
    const ma20d = _rCalcMA(candles, 20);
    if (ma20d.length >= 2) {
      const m = ma20d[ma20d.length-1].value, mp = ma20d[ma20d.length-2].value;
      if (last.close > m && prev.close <= mp)       trendScore += 4;
      else if (last.close < m && prev.close >= mp)  trendScore -= 4;
    }
    const dailyChg = (last.close - prev.close) / prev.close * 100;
    if (dailyChg > 7)  trendScore -= 3;
    else if (dailyChg < -7) trendScore -= 5;
  }
  const trend = Math.max(-20, Math.min(20, trendScore));

  const raw = tech + chip + vol + trend;
  const total = Math.max(0, Math.min(100, raw + 50));
  const recommendation =
    total >= 80 ? "強買進" : total >= 60 ? "買進" :
    total >= 40 ? "觀望"   : total >= 20 ? "減碼" : "強賣出";

  return { total, recommendation, scores: { tech, chip, vol, trend } };
}
```

- [ ] **Step 2：確認檔案建立成功**

在瀏覽器 console 貼上 `typeof _rankingCacheKey`，應回傳 `"function"`。

- [ ] **Step 3：commit**

```
git add assets/ranking.js
git commit -m "feat(ranking): add cache management and scoring helpers"
```

---

## Task 4：ranking.js — 漸進式載入主流程

**Files:**
- Modify: `assets/ranking.js`（在現有內容後面追加）

- [ ] **Step 1：加入主流程函數**

在 `ranking.js` 現有內容**末尾**追加：

```javascript
/* ── 主流程 ── */

let _rankingResults = [];   // 當前 session 記憶體快取

async function initRankingTab() {
  if (_rankingInitialized) return;
  _rankingInitialized = true;

  const root = document.getElementById("ranking-root");
  if (!root) return;

  // 嘗試讀快取
  const cached = _loadRankingCache();
  if (cached) {
    _rankingResults = cached;
    const now = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Taipei" }));
    _renderRankingFull(root, now.getHours() < 14 ? "yesterday" : "today");
    return;
  }

  // 需要新抓
  const allStocks = _getAllStocks();
  if (!allStocks.length) {
    root.innerHTML = `<p class="loading">尚未載入持股資料，請稍後再試</p>`;
    return;
  }

  // 顯示進度條
  root.innerHTML = `
    <div class="rk-progress-wrap">
      <div class="rk-progress-label">抓取股價中… <span id="rk-prog-num">0</span> / ${allStocks.length}</div>
      <div class="rk-progress-bar"><div id="rk-prog-fill" class="rk-progress-fill" style="width:0%"></div></div>
    </div>
    <div id="rk-partial-table"></div>
  `;

  _rankingResults = [];
  let done = 0;

  for (const stock of allStocks) {
    const [ohlcv, instRaw] = await Promise.all([
      _rankingFetchOHLCV(stock.stock_id),
      _rankingFetchInstitutional(stock.stock_id),
    ]);
    const instRows = _rankingParseInstitutional(instRaw);
    const scoreResult = ohlcv.length
      ? _rComputeScore(ohlcv, instRows)
      : { total: 0, recommendation: "無資料", scores: {} };

    _rankingResults.push({
      stock_id:       stock.stock_id,
      stock_name:     stock.stock_name,
      score:          scoreResult.total,
      recommendation: scoreResult.recommendation,
      tags:           stock.tags || [],
      held_by:        stock.held_by || [],
    });

    done++;
    const pct = Math.round(done / allStocks.length * 100);
    const numEl = document.getElementById("rk-prog-num");
    const fillEl = document.getElementById("rk-prog-fill");
    if (numEl) numEl.textContent = done;
    if (fillEl) fillEl.style.width = pct + "%";

    // 每 10 支更新一次局部表格預覽
    if (done % 10 === 0 || done === allStocks.length) {
      const partial = [..._rankingResults].sort((a, b) => b.score - a.score).slice(0, 20);
      const partialEl = document.getElementById("rk-partial-table");
      if (partialEl) partialEl.innerHTML = _buildTableHTML(partial);
    }
  }

  // 全部完成
  _saveRankingCache(_rankingResults);
  _renderRankingFull(root, "fresh");
}

function _getAllStocks() {
  // 從 app.js 的 state.payload 取得所有持股（state 是全域變數）
  if (!state || !state.payload || !state.payload.holdings) return [];
  return state.payload.holdings.map(h => ({
    stock_id:   h.stock_id,
    stock_name: h.stock_name,
    tags:       h.tags || [],
    held_by:    (h.held_by || []).map(b => b.ticker),
  }));
}
```

- [ ] **Step 2：commit**

```
git add assets/ranking.js
git commit -m "feat(ranking): add progressive fetch main flow"
```

---

## Task 5：ranking.js — 渲染函數（TAG 統計 + 表格）

**Files:**
- Modify: `assets/ranking.js`（繼續追加）

- [ ] **Step 1：加入渲染函數**

在 `ranking.js` 末尾追加：

```javascript
/* ── 渲染 ── */

const REC_CLS = {
  "強買進": "rec-strong-buy", "買進": "rec-buy", "觀望": "rec-hold",
  "減碼": "rec-sell", "強賣出": "rec-strong-sell", "無資料": "rec-na",
};

function _renderRankingFull(root, cacheStatus) {
  const sorted = [..._rankingResults].sort((a, b) => b.score - a.score);
  const top20  = sorted.slice(0, 20);

  const noticeHtml = cacheStatus === "yesterday"
    ? `<div class="rk-notice">⏰ 下午 2 點前，顯示昨日收盤資料</div>`
    : "";
  root.innerHTML = `
    ${noticeHtml}
    ${_buildTagStatsHTML(top20)}
    <div class="rk-table-wrap">
      <table class="rk-table">
        <thead><tr>
          <th class="rk-rank">#</th>
          <th>股票</th>
          <th class="rk-score-h">分數</th>
          <th>建議</th>
          <th class="r">收盤</th>
          <th class="r">漲跌</th>
          <th>TAG</th>
          <th>持有ETF</th>
        </tr></thead>
        <tbody id="rk-tbody-top">
          ${top20.map((s, i) => _buildRow(s, i + 1)).join("")}
        </tbody>
      </table>
    </div>
    ${sorted.length > 20 ? `
      <div class="rk-expand-wrap">
        <button class="rk-expand-btn" id="rk-expand-btn">展開顯示全部 ${sorted.length} 筆</button>
      </div>
      <div class="rk-table-wrap" id="rk-rest-wrap" style="display:none">
        <table class="rk-table">
          <tbody id="rk-tbody-rest">
            ${sorted.slice(20).map((s, i) => _buildRow(s, i + 21)).join("")}
          </tbody>
        </table>
      </div>
    ` : ""}
  `;

  const btn = document.getElementById("rk-expand-btn");
  if (btn) {
    btn.addEventListener("click", () => {
      const wrap = document.getElementById("rk-rest-wrap");
      if (wrap) { wrap.style.display = "block"; btn.style.display = "none"; }
    });
  }
}

function _buildTagStatsHTML(top20) {
  const freq = {};
  for (const s of top20) {
    for (const t of (s.tags || [])) {
      freq[t] = (freq[t] || 0) + 1;
    }
  }
  const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]);
  if (!sorted.length) return "";
  const chips = sorted.map(([tag, cnt]) =>
    `<span class="rk-tag-chip">${escapeHtml(tag)} ×${cnt}</span>`
  ).join("");
  return `<div class="rk-tag-stats"><span class="rk-tag-label">熱門話題（前20名中）：</span>${chips}</div>`;
}

function _buildTableHTML(rows) {
  return `<table class="rk-table">
    <thead><tr>
      <th class="rk-rank">#</th><th>股票</th>
      <th class="rk-score-h">分數</th><th>建議</th>
      <th class="r">收盤</th><th class="r">漲跌</th>
      <th>TAG</th><th>持有ETF</th>
    </tr></thead>
    <tbody>${rows.map((s, i) => _buildRow(s, i + 1)).join("")}</tbody>
  </table>`;
}

function _buildRow(s, rank) {
  const p = state.prices?.prices?.[s.stock_id];
  let priceHtml = `<span class="price-na">—</span>`;
  let changeHtml = `<span class="price-na">—</span>`;
  if (p) {
    priceHtml = `<span class="price-close">${p.close.toLocaleString()}</span>`;
    const up = p.change > 0, down = p.change < 0;
    const cls = up ? "price-up" : down ? "price-down" : "price-flat";
    const sign = up ? "+" : "";
    changeHtml = `<span class="${cls}">${up?"▲":down?"▼":"·"}${sign}${p.change_pct.toFixed(2)}%</span>`;
  }

  const visibleTags = (s.tags || []).slice(0, 3);
  const extraTags   = (s.tags || []).length - 3;
  const tagsHtml = visibleTags.map(t => `<span class="tag-chip tag-chip-sm">${escapeHtml(t)}</span>`).join("") +
    (extraTags > 0 ? `<span class="tag-chip tag-chip-sm tag-chip-more">+${extraTags}</span>` : "");

  const etfsHtml = (s.held_by || []).map(ticker =>
    `<span class="rk-etf-chip">${escapeHtml(ticker)}</span>`
  ).join("");

  const scoreNum = typeof s.score === "number" ? s.score : 0;
  const scoreCls = scoreNum >= 60 ? "score-hi" : scoreNum >= 40 ? "score-mid" : "score-lo";
  const recCls   = REC_CLS[s.recommendation] || "rec-na";

  const href = `stock.html?id=${encodeURIComponent(s.stock_id)}`;
  return `<tr>
    <td class="rk-rank">${rank}</td>
    <td><a class="stock-detail-link" href="${href}" target="_blank" rel="noopener">
      <b>${escapeHtml(s.stock_id)}</b> ${escapeHtml(s.stock_name)}
    </a></td>
    <td class="rk-score-cell"><span class="rk-score ${scoreCls}">${scoreNum}</span></td>
    <td><span class="rk-rec ${recCls}">${escapeHtml(s.recommendation)}</span></td>
    <td class="r">${priceHtml}</td>
    <td class="r">${changeHtml}</td>
    <td class="rk-tags">${tagsHtml}</td>
    <td class="rk-etfs">${etfsHtml}</td>
  </tr>`;
}
```

- [ ] **Step 2：commit**

```
git add assets/ranking.js
git commit -m "feat(ranking): add ranking table and tag stats rendering"
```

---

## Task 6：style.css — 排行榜樣式

**Files:**
- Modify: `assets/style.css`（在末尾追加）

- [ ] **Step 1：加入排行榜 CSS**

在 `assets/style.css` **末尾**追加：

```css
/* ═══ 買進評分排行榜 ═══ */

/* 進度條 */
.rk-progress-wrap { padding: 24px 0 16px; }
.rk-progress-label { font-size: var(--fs-sm); color: var(--text2); margin-bottom: 8px; }
.rk-progress-bar { height: 8px; background: var(--bg2); border-radius: 4px; overflow: hidden; border: 1px solid var(--border); }
.rk-progress-fill { height: 100%; background: var(--accent); border-radius: 4px; transition: width 0.3s; }

/* 熱門話題 */
.rk-tag-stats { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 14px 16px; background: var(--bg2); border: 1px solid var(--border); border-left: 4px solid var(--gold); border-radius: 8px; margin-bottom: 16px; }
.rk-tag-label { font-size: var(--fs-sm); color: var(--text2); white-space: nowrap; }
.rk-tag-chip { padding: 2px 10px; background: var(--bg3); border: 1px solid var(--border); border-radius: 12px; font-size: var(--fs-xs); color: var(--text); }

/* 排行表格 */
.rk-table-wrap { overflow-x: auto; }
.rk-table { width: 100%; border-collapse: collapse; font-size: var(--fs-sm); }
.rk-table th { padding: 8px 10px; text-align: left; font-weight: 500; color: var(--text2); border-bottom: 1px solid var(--border); white-space: nowrap; }
.rk-table td { padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: middle; }
.rk-table tr:hover td { background: var(--bg2); }
.rk-table .r { text-align: right; }

/* 排名欄 */
.rk-rank { width: 36px; text-align: center; color: var(--text3); font-family: var(--mono); }

/* 分數 */
.rk-score-h { text-align: center; }
.rk-score-cell { text-align: center; }
.rk-score { display: inline-block; min-width: 36px; padding: 2px 6px; border-radius: 6px; font-family: var(--mono); font-size: var(--fs-sm); font-weight: 600; text-align: center; }
.rk-score.score-hi  { background: rgba(63,185,80,0.2);  color: #3fb950; }
.rk-score.score-mid { background: rgba(210,153,34,0.2); color: #d29922; }
.rk-score.score-lo  { background: rgba(248,81,73,0.2);  color: #f85149; }

/* 建議標籤 */
.rk-rec { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: var(--fs-xs); font-weight: 500; white-space: nowrap; }
.rec-strong-buy { background: #1a7f37; color: #fff; }
.rec-buy        { background: rgba(63,185,80,0.2); color: #3fb950; }
.rec-hold       { background: rgba(210,153,34,0.2); color: #d29922; }
.rec-sell       { background: rgba(240,136,62,0.2); color: #f0883e; }
.rec-strong-sell { background: rgba(248,81,73,0.2); color: #f85149; }
.rec-na         { background: var(--bg2); color: var(--text3); }

/* TAG chips（小版） */
.tag-chip-sm { padding: 1px 7px; font-size: 11px; border-radius: 10px; background: var(--bg3); border: 1px solid var(--border); color: var(--text2); white-space: nowrap; }
.tag-chip-more { color: var(--text3); border-style: dashed; }
.rk-tags { display: flex; flex-wrap: wrap; gap: 4px; }

/* ETF chips */
.rk-etf-chip { display: inline-block; padding: 1px 6px; font-size: 11px; border-radius: 4px; background: var(--bg3); border: 1px solid var(--border); color: var(--text2); font-family: var(--mono); white-space: nowrap; margin-right: 2px; }
.rk-etfs { display: flex; flex-wrap: wrap; gap: 3px; }

/* 昨日資料提示 */
.rk-notice { padding: 8px 14px; margin-bottom: 12px; background: rgba(210,153,34,0.1); border: 1px solid var(--gold); border-radius: 6px; font-size: var(--fs-sm); color: var(--gold); }

/* 展開按鈕 */
.rk-expand-wrap { text-align: center; padding: 16px 0; }
.rk-expand-btn { padding: 8px 24px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg2); color: var(--text2); font-size: var(--fs-sm); cursor: pointer; font-family: var(--sans); }
.rk-expand-btn:hover { color: var(--text); border-color: var(--accent); }
```

- [ ] **Step 2：commit**

```
git add assets/style.css
git commit -m "feat(ranking): add ranking tab styles"
```

---

## Task 7：整合測試

- [ ] **Step 1：啟動 local server**

```
.venv\Scripts\python.exe -m http.server 8080
```

開啟 `http://localhost:8080`

- [ ] **Step 2：測試首次載入**

1. 點「買進評分」tab
2. 確認出現進度條「抓取股價中… 0 / 104」
3. 確認進度條前進，每 10 支出現局部表格預覽
4. 全部完成後，確認 TAG 統計區塊出現
5. 確認表格顯示前 20 筆，有分數、建議、收盤、漲跌、TAG、ETF

- [ ] **Step 3：測試快取**

1. 不重新載入頁面，切到其他 tab 再切回「買進評分」
2. 確認**立刻**顯示（不重抓）
3. 重新整理頁面，再點「買進評分」
4. 確認立刻顯示（從 localStorage 讀取）

- [ ] **Step 4：測試展開**

點「展開顯示全部 N 筆」按鈕，確認顯示剩餘股票，按鈕消失。

- [ ] **Step 5：測試個股連結**

點任一股票名稱，確認跳到 `stock.html?id=XXXX`。

- [ ] **Step 6：commit**

```
git add .
git commit -m "feat(ranking): complete 買進評分排行榜 feature"
```

---

## 潛在問題備忘

| 問題 | 處理方式 |
|---|---|
| FinMind 單支失敗 | `_rankingFetchOHLCV` 回傳 `[]`，score 設為 0，顯示「無資料」|
| 下午2點前無昨日快取 | `_loadRankingCache` 回傳 null → 直接抓取 |
| `state.payload` 尚未載入就點 ranking | `_getAllStocks` 回傳 `[]` → 顯示「尚未載入持股資料」|
| localStorage quota | `_saveRankingCache` catch QuotaExceededError，降級 session 記憶體 |
