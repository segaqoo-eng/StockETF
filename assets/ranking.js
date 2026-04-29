// ranking.js — 買進評分排行榜
// 依賴：app.js 先載入（state.payload、state.prices、escapeHtml 為全域）

let _rankingInitialized = false;
let _rankingResults = [];

/* ── 快取管理 ── */

function _rankingCacheKey() {
  const now = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Taipei" }));
  const hh = now.getHours();
  const pad = n => String(n).padStart(2, "0");
  if (hh < 14) {
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    return `scores_${yesterday.getFullYear()}-${pad(yesterday.getMonth()+1)}-${pad(yesterday.getDate())}`;
  }
  return `scores_${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}`;
}

function _loadRankingCache() {
  try {
    const raw = localStorage.getItem(_rankingCacheKey());
    return raw ? JSON.parse(raw) : null;
  } catch (_) { return null; }
}

function _saveRankingCache(data) {
  const key = _rankingCacheKey();
  try {
    localStorage.setItem(key, JSON.stringify(data));
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && k.startsWith("scores_") && k !== key) localStorage.removeItem(k);
    }
  } catch (e) {
    console.warn("localStorage quota exceeded, cache skipped");
  }
}

/* ── FinMind helpers ── */

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

/* ── 評分計算 ── */

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
  let avgGain = 0, avgLoss = 0;
  for (let i = 1; i <= period; i++) {
    const d = candles[i].close - candles[i - 1].close;
    if (d > 0) avgGain += d; else avgLoss -= d;
  }
  avgGain /= period; avgLoss /= period;
  const results = [];
  for (let i = period; i < candles.length; i++) {
    const d = candles[i].close - candles[i - 1].close;
    avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period;
    avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period;
    results.push({ time: candles[i].time, value: +(avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)).toFixed(2) });
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
    const s = signalLine[i];
    return { time: candles[slow - 1 + i].time, macd: +m.toFixed(3), signal: +s.toFixed(3), hist: +(m - s).toFixed(3) };
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
  const sign = rows[0][1][key] >= 0 ? 1 : -1;
  let count = 0;
  for (const [, vals] of rows) {
    if ((vals[key] >= 0 ? 1 : -1) === sign) count++;
    else break;
  }
  return sign * count;
}

function _rComputeScore(candles, instRows) {
  let techScore = 0;
  const rsiData = _rCalcRSI(candles);
  if (rsiData.length) {
    const rsi = rsiData[rsiData.length - 1].value;
    if (rsi < 30)      techScore += 6;
    else if (rsi < 50) techScore += 3;
    else if (rsi < 70) techScore += 2;
    else if (rsi < 80) techScore -= 2;
    else               techScore -= 5;
  }
  const macdData = _rCalcMACD(candles);
  if (macdData.length >= 2) {
    const prev = macdData[macdData.length - 2], curr = macdData[macdData.length - 1];
    if (prev.hist <= 0 && curr.hist > 0)      techScore += 6;
    else if (prev.hist >= 0 && curr.hist < 0) techScore -= 6;
    else if (curr.macd > 0)                   techScore += 3;
  }
  const kdData = _rCalcKD(candles);
  if (kdData.length >= 2) {
    const prev = kdData[kdData.length - 2], curr = kdData[kdData.length - 1];
    if (prev.k <= prev.d && curr.k > curr.d)                         techScore += 5;
    else if (curr.k < 20)                                             techScore += 4;
    else if (prev.k >= prev.d && curr.k < curr.d && curr.k >= 20)    techScore -= 3;
    else if (curr.k > 80)                                             techScore -= 3;
  }
  const ma5 = _rCalcMA(candles, 5), ma20 = _rCalcMA(candles, 20), ma60 = _rCalcMA(candles, 60);
  if (ma5.length && ma20.length && ma60.length) {
    const v5 = ma5[ma5.length-1].value, v20 = ma20[ma20.length-1].value, v60 = ma60[ma60.length-1].value;
    if (v5 > v20 && v20 > v60)      techScore += 8;
    else if (v5 < v20 && v20 < v60) techScore -= 8;
  }
  const tech = Math.max(-30, Math.min(30, techScore));

  let chipScore = 0;
  if (instRows && instRows.length) {
    const near5 = instRows.slice(0, 5);
    const fT = near5.reduce((s, [,v]) => s + v.foreign, 0);
    const tT = near5.reduce((s, [,v]) => s + v.trust, 0);
    const dT = near5.reduce((s, [,v]) => s + v.dealer, 0);
    if (fT > 0) chipScore += 5; else if (fT < 0) chipScore -= 5;
    if (tT > 0) chipScore += 4; else if (tT < 0) chipScore -= 4;
    if (dT > 0) chipScore += 2; else if (dT < 0) chipScore -= 2;
    const fDays = _rConsecutiveDays(instRows, "foreign");
    if (fDays >= 5) chipScore += 5; else if (fDays <= -5) chipScore -= 5;
    if (fT > 0 && tT > 0 && dT > 0) chipScore += 6;
    else if (fT < 0 && tT < 0 && dT < 0) chipScore -= 6;
  }
  const chip = Math.max(-30, Math.min(30, chipScore));

  let volScore = 0;
  if (candles.length >= 6) {
    const last = candles[candles.length - 1], prev = candles[candles.length - 2];
    const avg5vol = candles.slice(candles.length - 6, candles.length - 1).reduce((s, c) => s + c.volume, 0) / 5;
    if (last.volume > avg5vol * 1.5 && last.close > prev.close)       volScore += 6;
    else if (last.volume > avg5vol * 1.5 && last.close < prev.close)  volScore -= 6;
    else if (last.volume < avg5vol * 0.7 && last.close > prev.close)  volScore -= 2;
    else if (last.volume < avg5vol * 0.7 && last.close < prev.close)  volScore += 2;
  }
  const vol = Math.max(-20, Math.min(20, volScore));

  let trendScore = 0;
  if (candles.length >= 2) {
    const last = candles[candles.length - 1], prev = candles[candles.length - 2];
    const s60 = candles.slice(-60);
    if (last.close >= Math.max(...s60.map(c => c.high)))      trendScore += 8;
    else if (last.close <= Math.min(...s60.map(c => c.low)))  trendScore -= 8;
    const ma20d = _rCalcMA(candles, 20);
    if (ma20d.length >= 2) {
      const m = ma20d[ma20d.length-1].value, mp = ma20d[ma20d.length-2].value;
      if (last.close > m && prev.close <= mp)      trendScore += 4;
      else if (last.close < m && prev.close >= mp) trendScore -= 4;
    }
    const dailyChg = (last.close - prev.close) / prev.close * 100;
    if (dailyChg > 7) trendScore -= 3;
    else if (dailyChg < -7) trendScore -= 5;
  }
  const trend = Math.max(-20, Math.min(20, trendScore));

  const total = Math.max(0, Math.min(100, tech + chip + vol + trend + 50));
  const recommendation =
    total >= 80 ? "強買進" : total >= 60 ? "買進" :
    total >= 40 ? "觀望"   : total >= 20 ? "減碼" : "強賣出";
  return { total, recommendation };
}

/* ── 主流程 ── */

async function initRankingTab() {
  if (_rankingInitialized) return;

  const root = document.getElementById("ranking-root");
  if (!root) return;

  const cached = _loadRankingCache();
  if (cached) {
    _rankingInitialized = true;
    _rankingResults = cached;
    const now = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Taipei" }));
    _renderRankingFull(root, now.getHours() < 14 ? "yesterday" : "today");
    return;
  }

  const allStocks = _getAllStocks();
  if (!allStocks.length) {
    // 持股資料尚未載入（load() 還在跑），保持 flag=false 讓使用者再點一次
    root.innerHTML = `<p class="loading">持股資料載入中，請稍候再點一次「買進評分」</p>`;
    return;
  }

  _rankingInitialized = true;

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
      : { total: 0, recommendation: "無資料" };

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

    if (done % 10 === 0 || done === allStocks.length) {
      const partial = [..._rankingResults].sort((a, b) => b.score - a.score).slice(0, 20);
      const partialEl = document.getElementById("rk-partial-table");
      if (partialEl) partialEl.innerHTML = _buildTableHTML(partial);
    }
  }

  _saveRankingCache(_rankingResults);
  _renderRankingFull(root, "fresh");
}

function _getAllStocks() {
  if (!window.state || !state.payload || !state.payload.holdings) return [];
  return state.payload.holdings.map(h => ({
    stock_id:   h.stock_id,
    stock_name: h.stock_name,
    tags:       h.tags || [],
    held_by:    (h.held_by || []).map(b => b.etf),
  }));
}

/* ── 渲染 ── */

const _REC_CLS = {
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
        <tbody>${top20.map((s, i) => _buildRow(s, i + 1)).join("")}</tbody>
      </table>
    </div>
    ${sorted.length > 20 ? `
      <div class="rk-expand-wrap">
        <button class="rk-expand-btn" id="rk-expand-btn">展開顯示全部 ${sorted.length} 筆</button>
      </div>
      <div class="rk-table-wrap" id="rk-rest-wrap" style="display:none">
        <table class="rk-table">
          <tbody>${sorted.slice(20).map((s, i) => _buildRow(s, i + 21)).join("")}</tbody>
        </table>
      </div>
    ` : ""}
  `;

  const btn = document.getElementById("rk-expand-btn");
  if (btn) btn.addEventListener("click", () => {
    const wrap = document.getElementById("rk-rest-wrap");
    if (wrap) { wrap.style.display = "block"; btn.style.display = "none"; }
  });
}

function _buildTagStatsHTML(top20) {
  const freq = {};
  for (const s of top20) for (const t of (s.tags || [])) freq[t] = (freq[t] || 0) + 1;
  const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]);
  if (!sorted.length) return "";
  return `<div class="rk-tag-stats">
    <span class="rk-tag-label">熱門話題（前20名中）：</span>
    ${sorted.map(([tag, cnt]) => `<span class="rk-tag-chip">${escapeHtml(tag)} ×${cnt}</span>`).join("")}
  </div>`;
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
  const p = window.state?.prices?.prices?.[s.stock_id];
  const priceHtml  = p ? `<span class="price-close">${p.close.toLocaleString()}</span>` : `<span class="price-na">—</span>`;
  const changeHtml = p ? (() => {
    const up = p.change > 0, dn = p.change < 0;
    return `<span class="${up?"price-up":dn?"price-down":"price-flat"}">${up?"▲":dn?"▼":"·"}${up?"+":""}${p.change_pct.toFixed(2)}%</span>`;
  })() : `<span class="price-na">—</span>`;

  const tags = s.tags || [];
  const tagsHtml = tags.slice(0, 3).map(t => `<span class="tag-chip tag-chip-sm">${escapeHtml(t)}</span>`).join("") +
    (tags.length > 3 ? `<span class="tag-chip tag-chip-sm tag-chip-more">+${tags.length - 3}</span>` : "");

  const etfsHtml = (s.held_by || []).map(t => `<span class="rk-etf-chip">${escapeHtml(t)}</span>`).join("");

  const score  = typeof s.score === "number" ? s.score : 0;
  const scoreCls = score >= 60 ? "score-hi" : score >= 40 ? "score-mid" : "score-lo";
  const recCls   = _REC_CLS[s.recommendation] || "rec-na";
  const href = `stock.html?id=${encodeURIComponent(s.stock_id)}`;

  return `<tr>
    <td class="rk-rank">${rank}</td>
    <td><a class="stock-detail-link" href="${href}" target="_blank" rel="noopener">
      <b>${escapeHtml(s.stock_id)}</b> ${escapeHtml(s.stock_name)}
    </a></td>
    <td class="rk-score-cell"><span class="rk-score ${scoreCls}">${score}</span></td>
    <td><span class="rk-rec ${recCls}">${escapeHtml(s.recommendation)}</span></td>
    <td class="r">${priceHtml}</td>
    <td class="r">${changeHtml}</td>
    <td class="rk-tags">${tagsHtml}</td>
    <td class="rk-etfs">${etfsHtml}</td>
  </tr>`;
}
