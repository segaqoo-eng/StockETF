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
  if (state.payload) {
    for (const etf of state.payload.etfs) {
      const h = (etf.holdings || []).find(h => h.stock_id === sid);
      if (h) { stockName = h.stock_name; break; }
    }
  }

  renderHeader(sid, stockName);
  renderEtfHoldings(sid);
  renderTrend(sid);
  renderInstitutional(sid);   // async, fills in after OHLC loads
  renderScore(sid);
  initChart(sid);

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
    const close = p.close ?? 0;
    const changePct = p.change_pct ?? 0;
    priceHtml = `
      <span class="sp-close">${close.toLocaleString()}</span>
      <span class="sp-change ${cls}">${arrow} ${sign}${changePct.toFixed(2)}%</span>`;
  }

  const dateBadge = priceDate
    ? `<span class="sp-date${stale ? " stale" : ""}" title="${stale ? "上次盤後資料" : "今日盤後"}">${escapeHtml(priceDate.slice(5))} 盤後</span>`
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
        const up = changed.shares_delta > 0;
        const sign = up ? "+" : "";
        badge = `<span class="diff-badge diff-${up ? "up" : "down"}">${up ? "▲" : "▼"} ${sign}${Number(changed.shares_delta).toLocaleString()}</span>`;
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

/* ── 法人買賣超 + 信號 ── */

async function _fetchInstitutional(sid, startDate) {
  const url = `https://api.finmindtrade.com/api/v4/data` +
    `?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id=${encodeURIComponent(sid)}&start_date=${startDate}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return [];
    const d = await res.json();
    if (d.status !== 200 || !Array.isArray(d.data)) return [];
    return d.data;
  } catch (_) { return []; }
}

function _parseInstitutional(raw) {
  // Group by date → { 外資: net, 投信: net, 自營商: net }
  const byDate = {};
  for (const r of raw) {
    if (!byDate[r.date]) byDate[r.date] = { foreign: 0, trust: 0, dealer: 0 };
    const net = (r.buy_minus_sell || 0) / 1000; // 股 → 張
    const n = r.name || "";
    if (n.includes("外資") && !n.includes("自營")) byDate[r.date].foreign += net;
    else if (n === "投信")                          byDate[r.date].trust   += net;
    else if (n.includes("自營"))                    byDate[r.date].dealer  += net;
  }
  return Object.entries(byDate).sort((a, b) => a[0] < b[0] ? 1 : -1); // newest first
}

function _consecutiveDays(rows, key) {
  if (!rows.length) return 0;
  const first = rows[0][1][key] >= 0 ? 1 : -1;
  let count = 0;
  for (const [, vals] of rows) {
    if ((vals[key] >= 0 ? 1 : -1) === first) count++;
    else break;
  }
  return first * count; // positive = consecutive buy days, negative = sell days
}

async function renderInstitutional(sid) {
  const root = document.getElementById("sp-institutional");
  if (!root) return;
  root.innerHTML = `<div style="color:var(--text3);font-size:var(--fs-sm);padding:8px 0">法人資料載入中…</div>`;

  const startDate = _startDate(2);   // 2 months back for ~40 trading days
  const raw = await _fetchInstitutional(sid, startDate);
  const rows = _parseInstitutional(raw).slice(0, 10); // last 10 trading days

  if (!rows.length) {
    root.innerHTML = `<div style="color:var(--text3);font-size:var(--fs-sm);padding:8px 0">無法人資料</div>`;
    return;
  }

  const fDays  = _consecutiveDays(rows, "foreign");
  const tDays  = _consecutiveDays(rows, "trust");
  const fTotal = rows.reduce((s, [, v]) => s + v.foreign, 0);
  const tTotal = rows.reduce((s, [, v]) => s + v.trust,   0);

  const fmt = n => {
    const abs = Math.abs(Math.round(n));
    const sign = n >= 0 ? "+" : "-";
    const cls = n >= 0 ? "inst-buy" : "inst-sell";
    return `<span class="${cls}">${sign}${abs.toLocaleString()}</span>`;
  };
  const dayLabel = d => {
    if (d === 0) return `<span style="color:var(--text3)">—</span>`;
    const cls = d > 0 ? "inst-buy" : "inst-sell";
    const arrow = d > 0 ? "▲" : "▼";
    return `<span class="${cls}">${arrow} 連${Math.abs(d)}日${d > 0 ? "買" : "賣"}</span>`;
  };

  const tableRows = rows.map(([date, v]) => `
    <tr>
      <td class="inst-date">${date.slice(5)}</td>
      <td class="inst-num">${fmt(v.foreign)}</td>
      <td class="inst-num">${fmt(v.trust)}</td>
      <td class="inst-num">${fmt(v.dealer)}</td>
    </tr>`).join("");

  root.innerHTML = `
    <div class="inst-summary">
      <span>外資 ${dayLabel(fDays)}，近10日合計 ${fmt(fTotal)} 張</span><br>
      <span>投信 ${dayLabel(tDays)}，近10日合計 ${fmt(tTotal)} 張</span>
    </div>
    <table class="inst-table">
      <thead><tr>
        <th>日期</th><th class="inst-num">外資</th><th class="inst-num">投信</th><th class="inst-num">自營商</th>
      </tr></thead>
      <tbody>${tableRows}</tbody>
    </table>
    <div style="font-size:10px;color:var(--text3);margin-top:4px">單位：張（1張=1,000股）</div>`;

  // After institutional data loads, update the signal panel
  renderSignal(sid, rows, fDays, tDays);
}

function renderSignal(sid, instRows, fDays, tDays) {
  const root = document.getElementById("sp-signal");
  if (!root) return;

  // Read latest TA values from chart data if available (we'll use simple heuristics)
  // Signal based on: RSI + MACD + 外資 + 投信
  const signals = [];

  // Institutional signals
  if (fDays >= 3)       signals.push({ label: "外資", val: "連買", cls: "sig-bull" });
  else if (fDays > 0)   signals.push({ label: "外資", val: "買超", cls: "sig-bull" });
  else if (fDays <= -3) signals.push({ label: "外資", val: "連賣", cls: "sig-bear" });
  else if (fDays < 0)   signals.push({ label: "外資", val: "賣超", cls: "sig-bear" });
  else                  signals.push({ label: "外資", val: "持平", cls: "sig-neutral" });

  if (tDays >= 2)       signals.push({ label: "投信", val: "連買", cls: "sig-bull" });
  else if (tDays > 0)   signals.push({ label: "投信", val: "買超", cls: "sig-bull" });
  else if (tDays <= -2) signals.push({ label: "投信", val: "連賣", cls: "sig-bear" });
  else if (tDays < 0)   signals.push({ label: "投信", val: "賣超", cls: "sig-bear" });
  else                  signals.push({ label: "投信", val: "持平", cls: "sig-neutral" });

  const bulls = signals.filter(s => s.cls === "sig-bull").length;
  const bears = signals.filter(s => s.cls === "sig-bear").length;
  const overall = bulls > bears ? { text: "偏多", cls: "sig-bull" }
                : bears > bulls ? { text: "偏空", cls: "sig-bear" }
                : { text: "中性", cls: "sig-neutral" };

  root.innerHTML = `
    <div class="sig-overall ${overall.cls}">${overall.text}</div>
    <div class="sig-items">
      ${signals.map(s => `<span class="sig-item ${s.cls}">${s.label}<b>${s.val}</b></span>`).join("")}
    </div>`;
}

/* ── K 線圖：Lightweight Charts + FinMind API ── */

async function _fetchFinMind(sid, startDate) {
  const url = `https://api.finmindtrade.com/api/v4/data` +
    `?dataset=TaiwanStockPrice&data_id=${encodeURIComponent(sid)}&start_date=${startDate}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return [];
    const d = await res.json();
    if (d.status !== 200 || !Array.isArray(d.data)) return [];
    return d.data
      .map(r => ({
        time:   r.date,
        open:   r.open,
        high:   r.max,
        low:    r.min,
        close:  r.close,
        volume: r.Trading_Volume || 0,
      }))
      .filter(c => c.open != null && c.close != null);
  } catch (_) { return []; }
}

function _groupByWeek(daily) {
  const map = {};
  for (const c of daily) {
    const d = new Date(c.time), day = d.getDay() || 7;
    const mon = new Date(d); mon.setDate(d.getDate() - day + 1);
    const key = mon.toISOString().slice(0, 10);
    if (!map[key]) map[key] = { ...c, time: key, volume: 0 };
    map[key].high   = Math.max(map[key].high, c.high);
    map[key].low    = Math.min(map[key].low,  c.low);
    map[key].close  = c.close;
    map[key].volume += c.volume;
  }
  return Object.values(map).sort((a, b) => a.time < b.time ? -1 : 1);
}

function _groupByMonth(daily) {
  const map = {};
  for (const c of daily) {
    const key = c.time.slice(0, 7) + "-01";
    if (!map[key]) map[key] = { ...c, time: key, volume: 0 };
    map[key].high   = Math.max(map[key].high, c.high);
    map[key].low    = Math.min(map[key].low,  c.low);
    map[key].close  = c.close;
    map[key].volume += c.volume;
  }
  return Object.values(map).sort((a, b) => a.time < b.time ? -1 : 1);
}

function _startDate(monthsBack) {
  const d = new Date();
  d.setMonth(d.getMonth() - monthsBack);
  return d.toISOString().slice(0, 10);
}

/* ── 技術指標計算 ── */

function _calcMA(candles, n) {
  return candles.map((c, i) => {
    if (i < n - 1) return null;
    const avg = candles.slice(i - n + 1, i + 1).reduce((s, x) => s + x.close, 0) / n;
    return { time: c.time, value: +avg.toFixed(2) };
  }).filter(Boolean);
}

function _calcRSI(candles, period = 14) {
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

function _calcEMA(arr, period) {
  const k = 2 / (period + 1);
  let ema = arr[0];
  return arr.map((v, i) => { if (i > 0) ema = v * k + ema * (1 - k); return ema; });
}

function _calcMACD(candles, fast = 12, slow = 26, sig = 9) {
  const closes = candles.map(c => c.close);
  const emaFast = _calcEMA(closes, fast);
  const emaSlow = _calcEMA(closes, slow);
  const macdLine = emaFast.map((v, i) => v - emaSlow[i]);
  const signalLine = _calcEMA(macdLine.slice(slow - 1), sig);
  return macdLine.slice(slow - 1).map((m, i) => {
    const s = signalLine[i], h = m - s;
    return { time: candles[slow - 1 + i].time,
      macd: +m.toFixed(3), signal: +s.toFixed(3), hist: +h.toFixed(3) };
  });
}

function _calcKD(candles, period = 9, sm = 3) {
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

/* 同步多圖 time scale */
function _syncCharts(charts) {
  let busy = false;
  charts.forEach(src => {
    src.timeScale().subscribeVisibleLogicalRangeChange(range => {
      if (busy || !range) return;
      busy = true;
      charts.forEach(t => { if (t !== src) t.timeScale().setVisibleLogicalRange(range); });
      busy = false;
    });
  });
}

function _makeSubChart(parent, height) {
  const div = document.createElement("div");
  div.style.cssText = `width:100%;height:${height}px;`;
  parent.appendChild(div);
  return LightweightCharts.createChart(div, {
    autoSize: true, height,
    layout: { background: { color: "#161b22" }, textColor: "#8b949e" },
    grid:   { vertLines: { color: "#21262d" }, horzLines: { color: "#21262d" } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: "#30363d", scaleMargins: { top: 0.1, bottom: 0.1 } },
    timeScale: { borderColor: "#30363d", timeVisible: false, visible: false },
    handleScroll: true, handleScale: true,
  });
}

function _subLabel(parent, text) {
  const el = document.createElement("div");
  el.style.cssText = "padding:2px 8px;font-size:10px;color:var(--text3);background:#161b22;";
  el.textContent = text;
  parent.appendChild(el);
}

const CHART_PERIODS = [
  { key: "D", label: "日K", months: 3,  group: null    },
  { key: "W", label: "週K", months: 6,  group: "week"  },
  { key: "M", label: "月K", months: 24, group: "month" },
];
let _activePeriod = "D";

async function initChart(sid) {
  const container = document.getElementById("tv-container");

  // Period switcher bar（只建一次）
  container.innerHTML = "";
  const periodBar = document.createElement("div");
  periodBar.style.cssText = "display:flex;gap:6px;padding:8px 10px 4px;background:#161b22;";
  CHART_PERIODS.forEach(p => {
    const btn = document.createElement("button");
    btn.textContent = p.label;
    btn.dataset.key = p.key;
    btn.style.cssText = `padding:3px 12px;border-radius:6px;border:1px solid var(--border);` +
      `background:${p.key===_activePeriod?"var(--accent)":"var(--bg2)"};` +
      `color:${p.key===_activePeriod?"#000":"var(--text2)"};font-size:var(--fs-sm);cursor:pointer;`;
    btn.onclick = async () => {
      _activePeriod = p.key;
      periodBar.querySelectorAll("button").forEach(b => {
        const on = b.dataset.key === _activePeriod;
        b.style.background = on ? "var(--accent)" : "var(--bg2)";
        b.style.color = on ? "#000" : "var(--text2)";
      });
      await _drawChart(sid, container, periodBar);
    };
    periodBar.appendChild(btn);
  });
  container.appendChild(periodBar);

  await _drawChart(sid, container, periodBar);
}

async function _drawChart(sid, container, periodBar) {
  // 清舊圖，保留 period bar
  container.querySelectorAll(":scope > *:not(div:first-child)").forEach(el => el.remove());

  // 通用參考線 helper（供 RSI、KD 共用）
  const refLine = (chart, val, color) => {
    const s = chart.addLineSeries({ color, lineWidth: 1, lineStyle: 2,
      priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    s.setData(rsiData.map(d => ({ time: d.time, value: val })));
  };

  const cfg = CHART_PERIODS.find(p => p.key === _activePeriod);
  const loading = Object.assign(document.createElement("div"), {
    textContent: "K 線載入中…",
    style: "color:var(--text3);padding:20px;font-size:var(--fs-sm)",
  });
  container.appendChild(loading);

  const daily = await _fetchFinMind(sid, _startDate(cfg.months));
  loading.remove();

  let candles = cfg.group === "week"  ? _groupByWeek(daily)
              : cfg.group === "month" ? _groupByMonth(daily)
              : daily;

  if (!candles.length) {
    container.appendChild(Object.assign(document.createElement("div"), {
      textContent: "FinMind API 無資料（可能是未上市 / 連線失敗）",
      style: "color:var(--text3);padding:20px;font-size:var(--fs-sm)",
    }));
    return;
  }

  // ── 主圖：K 線 + 成交量 + MA ──
  const mainDiv = document.createElement("div");
  mainDiv.style.cssText = "width:100%;height:320px;";
  container.appendChild(mainDiv);

  const main = LightweightCharts.createChart(mainDiv, {
    autoSize: true,
    height: 320,
    layout: { background: { color: "#161b22" }, textColor: "#e6edf3" },
    grid:   { vertLines: { color: "#21262d" }, horzLines: { color: "#21262d" } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: "#30363d", scaleMargins: { top: 0.05, bottom: 0.22 } },
    timeScale: { borderColor: "#30363d", timeVisible: false },
  });
  main.addCandlestickSeries({
    upColor: "#f85149", downColor: "#3fb950",
    borderUpColor: "#f85149", borderDownColor: "#3fb950",
    wickUpColor: "#f85149", wickDownColor: "#3fb950",
  }).setData(candles);

  const vol = main.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol" });
  main.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  vol.setData(candles.map(c => ({
    time: c.time, value: c.volume,
    color: c.close >= c.open ? "rgba(248,81,73,0.45)" : "rgba(63,185,80,0.45)",
  })));

  const maConfig = [{ n: 5, color: "#f0883e" }, { n: 20, color: "#d2a8ff" }, { n: 60, color: "#7ee787" }];
  for (const { n, color } of maConfig) {
    const ma = _calcMA(candles, n);
    if (!ma.length) continue;
    main.addLineSeries({ color, lineWidth: 1,
      priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
    }).setData(ma);
  }
  main.timeScale().fitContent();

  // MA 圖例
  const maLegend = document.createElement("div");
  maLegend.style.cssText = "display:flex;gap:12px;padding:2px 8px;font-size:10px;background:#161b22;";
  maLegend.innerHTML = maConfig.map(m => `<span style="color:${m.color}">● MA${m.n}</span>`).join("");
  container.appendChild(maLegend);

  // ── RSI(14) ──
  const rsiData = _calcRSI(candles);
  if (rsiData.length) {
    _subLabel(container, "RSI(14)");
    const rsiChart = _makeSubChart(container, 100);
    rsiChart.priceScale("right").applyOptions({ scaleMargins: { top: 0.1, bottom: 0.1 } });
    rsiChart.addLineSeries({ color: "#79c0ff", lineWidth: 1,
      priceLineVisible: false, lastValueVisible: true, crosshairMarkerVisible: false,
    }).setData(rsiData);
    // 超買/超賣參考線
    refLine(rsiChart, 70, "rgba(248,81,73,0.4)");
    refLine(rsiChart, 30, "rgba(63,185,80,0.4)");
    rsiChart.timeScale().fitContent();

    // ── KD(9,3,3) ──
    const kdData = _calcKD(candles);
    if (kdData.length) {
      _subLabel(container, "KD(9,3,3)");
      const kdChart = _makeSubChart(container, 100);
      kdChart.addLineSeries({ color: "#f0883e", lineWidth: 1,
        priceLineVisible: false, lastValueVisible: true, crosshairMarkerVisible: false,
      }).setData(kdData.map(d => ({ time: d.time, value: d.k })));
      kdChart.addLineSeries({ color: "#d2a8ff", lineWidth: 1,
        priceLineVisible: false, lastValueVisible: true, crosshairMarkerVisible: false,
      }).setData(kdData.map(d => ({ time: d.time, value: d.d })));
      refLine(kdChart, 80, "rgba(248,81,73,0.3)");
      refLine(kdChart, 20, "rgba(63,185,80,0.3)");
      kdChart.timeScale().fitContent();

      // ── MACD(12,26,9) ──
      const macdData = _calcMACD(candles);
      if (macdData.length) {
        _subLabel(container, "MACD(12,26,9)");
        const macdChart = _makeSubChart(container, 100);
        macdChart.timeScale().applyOptions({ visible: true, borderColor: "#30363d", timeVisible: false });
        // 柱狀圖
        macdChart.addHistogramSeries({ priceScaleId: "right",
          priceLineVisible: false, lastValueVisible: false,
        }).setData(macdData.map(d => ({
          time: d.time, value: d.hist,
          color: d.hist >= 0 ? "rgba(248,81,73,0.6)" : "rgba(63,185,80,0.6)",
        })));
        macdChart.addLineSeries({ color: "#79c0ff", lineWidth: 1,
          priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
        }).setData(macdData.map(d => ({ time: d.time, value: d.macd })));
        macdChart.addLineSeries({ color: "#f0883e", lineWidth: 1,
          priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
        }).setData(macdData.map(d => ({ time: d.time, value: d.signal })));
        macdChart.timeScale().fitContent();

        _syncCharts([main, rsiChart, kdChart, macdChart]);
      } else {
        _syncCharts([main, rsiChart, kdChart]);
      }
    } else {
      _syncCharts([main, rsiChart]);
    }
  }

  // 資料來源
  const credit = document.createElement("div");
  credit.style.cssText = "text-align:right;padding:3px 8px;font-size:10px;color:var(--text3);background:#161b22;";
  credit.innerHTML = `資料來源 <a href="https://finmindtrade.com/" target="_blank" rel="noopener" style="color:var(--text2)">FinMind</a>`;
  container.appendChild(credit);
}

/* ── 綜合評分函數 ── */

function scoreTechnical(candles) {
  const signals = [];
  let rawScore = 0;

  // RSI
  const rsiData = _calcRSI(candles);
  if (rsiData.length) {
    const rsi = rsiData[rsiData.length - 1].value;
    if (rsi < 30) {
      rawScore += 6;
      signals.push({ category: "technical", type: "BUY", reason: "RSI 超賣（<30）", score: 6 });
    } else if (rsi < 50) {
      rawScore += 3;
      signals.push({ category: "technical", type: "BUY", reason: "RSI 中低區（30-50）", score: 3 });
    } else if (rsi < 70) {
      rawScore += 2;
      signals.push({ category: "technical", type: "BUY", reason: "RSI 健康（50-70）", score: 2 });
    } else if (rsi < 80) {
      rawScore -= 2;
      signals.push({ category: "technical", type: "SELL", reason: "RSI 偏熱（70-80）", score: -2 });
    } else {
      rawScore -= 5;
      signals.push({ category: "technical", type: "SELL", reason: "RSI 過熱（>80）", score: -5 });
    }
  }

  // MACD crossover
  const macdData = _calcMACD(candles);
  if (macdData.length >= 2) {
    const prev = macdData[macdData.length - 2];
    const curr = macdData[macdData.length - 1];
    if (prev.hist <= 0 && curr.hist > 0) {
      rawScore += 6;
      signals.push({ category: "technical", type: "BUY", reason: "MACD 黃金交叉", score: 6 });
    } else if (prev.hist >= 0 && curr.hist < 0) {
      rawScore -= 6;
      signals.push({ category: "technical", type: "SELL", reason: "MACD 死亡交叉", score: -6 });
    } else if (curr.macd > 0) {
      rawScore += 3;
      signals.push({ category: "technical", type: "BUY", reason: "MACD DIF 站上零軸", score: 3 });
    }
  }

  // KD crossover
  const kdData = _calcKD(candles);
  if (kdData.length >= 2) {
    const prev = kdData[kdData.length - 2];
    const curr = kdData[kdData.length - 1];
    const goldenCross = prev.k <= prev.d && curr.k > curr.d;
    const deathCross  = prev.k >= prev.d && curr.k < curr.d;
    if (goldenCross) {
      rawScore += 5;
      signals.push({ category: "technical", type: "BUY", reason: "KD 黃金交叉", score: 5 });
    } else if (curr.k < 20) {
      rawScore += 4;
      signals.push({ category: "technical", type: "BUY", reason: "KD 超賣（K<20）", score: 4 });
    }
    if (!goldenCross) {
      if (deathCross && curr.k >= 20) {
        rawScore -= 3;
        signals.push({ category: "technical", type: "SELL", reason: "KD 死亡交叉", score: -3 });
      } else if (curr.k > 80 && !deathCross) {
        rawScore -= 3;
        signals.push({ category: "technical", type: "SELL", reason: "KD 超買（K>80）", score: -3 });
      }
    }
  }

  // MA arrangement
  const ma5  = _calcMA(candles, 5);
  const ma20 = _calcMA(candles, 20);
  const ma60 = _calcMA(candles, 60);
  if (ma5.length && ma20.length && ma60.length) {
    const v5  = ma5[ma5.length - 1].value;
    const v20 = ma20[ma20.length - 1].value;
    const v60 = ma60[ma60.length - 1].value;
    if (v5 > v20 && v20 > v60) {
      rawScore += 8;
      signals.push({ category: "technical", type: "BUY", reason: "均線多頭排列", score: 8 });
    } else if (v5 < v20 && v20 < v60) {
      rawScore -= 8;
      signals.push({ category: "technical", type: "SELL", reason: "均線空頭排列", score: -8 });
    }
  }

  return { score: Math.max(-30, Math.min(30, rawScore)), signals };
}

function scoreChip(instRows) {
  const signals = [];
  let rawScore = 0;

  if (!instRows || instRows.length === 0) return { score: 0, signals };

  // 近5日合計
  const near5 = instRows.slice(0, 5);
  const fTotal5 = near5.reduce((s, [, v]) => s + v.foreign, 0);
  const tTotal5 = near5.reduce((s, [, v]) => s + v.trust,   0);
  const dTotal5 = near5.reduce((s, [, v]) => s + v.dealer,  0);

  if (fTotal5 > 0) {
    rawScore += 5;
    signals.push({ category: "chip", type: "BUY", reason: "外資近5日買超", score: 5 });
  } else if (fTotal5 < 0) {
    rawScore -= 5;
    signals.push({ category: "chip", type: "SELL", reason: "外資近5日賣超", score: -5 });
  }

  if (tTotal5 > 0) {
    rawScore += 4;
    signals.push({ category: "chip", type: "BUY", reason: "投信近5日買超", score: 4 });
  } else if (tTotal5 < 0) {
    rawScore -= 4;
    signals.push({ category: "chip", type: "SELL", reason: "投信近5日賣超", score: -4 });
  }

  if (dTotal5 > 0) {
    rawScore += 2;
    signals.push({ category: "chip", type: "BUY", reason: "自營商近5日買超", score: 2 });
  } else if (dTotal5 < 0) {
    rawScore -= 2;
    signals.push({ category: "chip", type: "SELL", reason: "自營商近5日賣超", score: -2 });
  }

  // 連續性（外資）
  const fDays = _consecutiveDays(instRows, "foreign");
  if (fDays >= 5) {
    rawScore += 5;
    signals.push({ category: "chip", type: "BUY", reason: `外資連${fDays}日買超（額外）`, score: 5 });
  } else if (fDays <= -5) {
    rawScore -= 5;
    signals.push({ category: "chip", type: "SELL", reason: `外資連${Math.abs(fDays)}日賣超（額外）`, score: -5 });
  }

  // 三大同向
  if (fTotal5 > 0 && tTotal5 > 0 && dTotal5 > 0) {
    rawScore += 6;
    signals.push({ category: "chip", type: "BUY", reason: "三大法人同步買超", score: 6 });
  } else if (fTotal5 < 0 && tTotal5 < 0 && dTotal5 < 0) {
    rawScore -= 6;
    signals.push({ category: "chip", type: "SELL", reason: "三大法人同步賣超", score: -6 });
  }

  // 籌碼分歧
  if ((fTotal5 > 0 && tTotal5 < 0) || (fTotal5 < 0 && tTotal5 > 0)) {
    rawScore -= 3;
    signals.push({ category: "chip", type: "SELL", reason: "外資投信方向分歧", score: -3 });
  }

  return { score: Math.max(-30, Math.min(30, rawScore)), signals };
}

function scoreVolumePrice(candles) {
  const signals = [];
  let rawScore = 0;

  if (candles.length < 6) return { score: 0, signals };

  const last = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const slice5 = candles.slice(candles.length - 6, candles.length - 1);
  const avg5vol = slice5.reduce((s, c) => s + c.volume, 0) / 5;

  const 放量 = last.volume > avg5vol * 1.5;
  const 縮量 = last.volume < avg5vol * 0.7;
  const 漲  = last.close > prev.close;
  const 跌  = last.close < prev.close;

  if (放量 && 漲) {
    rawScore += 6;
    signals.push({ category: "volume_price", type: "BUY", reason: "放量上漲", score: 6 });
  } else if (放量 && 跌) {
    rawScore -= 6;
    signals.push({ category: "volume_price", type: "SELL", reason: "放量下跌", score: -6 });
  } else if (縮量 && 漲) {
    rawScore -= 2;
    signals.push({ category: "volume_price", type: "SELL", reason: "量縮上漲（追價意願不足）", score: -2 });
  } else if (縮量 && 跌) {
    rawScore += 2;
    signals.push({ category: "volume_price", type: "BUY", reason: "量縮下跌（賣壓減輕）", score: 2 });
  }

  // 連續3日 價漲量縮
  if (candles.length >= 4) {
    const c = candles;
    const n = c.length;
    const priceLongVolumeShort3 =
      c[n-1].close > c[n-2].close && c[n-1].volume < c[n-2].volume &&
      c[n-2].close > c[n-3].close && c[n-2].volume < c[n-3].volume &&
      c[n-3].close > c[n-4].close && c[n-3].volume < c[n-4].volume;
    if (priceLongVolumeShort3) {
      rawScore -= 4;
      signals.push({ category: "volume_price", type: "SELL", reason: "連3日價漲量縮（背離）", score: -4 });
    }

    // 連續3日 價跌量縮
    const priceDownVolumeDown3 =
      c[n-1].close < c[n-2].close && c[n-1].volume < c[n-2].volume &&
      c[n-2].close < c[n-3].close && c[n-2].volume < c[n-3].volume &&
      c[n-3].close < c[n-4].close && c[n-3].volume < c[n-4].volume;
    if (priceDownVolumeDown3) {
      rawScore += 3;
      signals.push({ category: "volume_price", type: "BUY", reason: "連3日價跌量縮（底部特徵）", score: 3 });
    }
  }

  return { score: Math.max(-20, Math.min(20, rawScore)), signals };
}

function scoreTrend(candles) {
  const signals = [];
  let rawScore = 0;

  if (candles.length < 2) return { score: 0, signals };

  const last = candles[candles.length - 1];
  const prev = candles[candles.length - 2];

  const slice60 = candles.slice(-60);
  const high60 = Math.max(...slice60.map(c => c.high));
  const low60  = Math.min(...slice60.map(c => c.low));

  if (last.close >= high60) {
    rawScore += 8;
    signals.push({ category: "trend", type: "BUY", reason: "收盤突破60日新高", score: 8 });
  } else if (last.close <= low60) {
    rawScore -= 8;
    signals.push({ category: "trend", type: "SELL", reason: "收盤跌破60日新低", score: -8 });
  }

  const ma20Data = _calcMA(candles, 20);
  if (ma20Data.length) {
    const ma20Last = ma20Data[ma20Data.length - 1].value;
    // Need prev bar's MA20 — index one back
    const ma20Prev = ma20Data.length >= 2 ? ma20Data[ma20Data.length - 2].value : null;
    if (ma20Prev !== null) {
      if (last.close > ma20Last && prev.close <= ma20Prev) {
        rawScore += 4;
        signals.push({ category: "trend", type: "BUY", reason: "站上MA20", score: 4 });
      } else if (last.close < ma20Last && prev.close >= ma20Prev) {
        rawScore -= 4;
        signals.push({ category: "trend", type: "SELL", reason: "跌破MA20", score: -4 });
      }
    }
  }

  const ma60Data = _calcMA(candles, 60);
  if (ma60Data.length) {
    const ma60Last = ma60Data[ma60Data.length - 1].value;
    const ma60Prev = ma60Data.length >= 2 ? ma60Data[ma60Data.length - 2].value : null;
    if (ma60Prev !== null) {
      if (last.close > ma60Last && prev.close <= ma60Prev) {
        rawScore += 5;
        signals.push({ category: "trend", type: "BUY", reason: "站上MA60季線", score: 5 });
      } else if (last.close < ma60Last && prev.close >= ma60Prev) {
        rawScore -= 5;
        signals.push({ category: "trend", type: "SELL", reason: "跌破MA60季線", score: -5 });
      }
    }
  }

  const dailyChg = (last.close - prev.close) / prev.close * 100;
  if (dailyChg > 7) {
    rawScore -= 3;
    signals.push({ category: "trend", type: "SELL", reason: "單日暴漲 >7%（追高風險）", score: -3 });
  } else if (dailyChg < -7) {
    rawScore -= 5;
    signals.push({ category: "trend", type: "SELL", reason: "單日暴跌 <-7%（恐慌賣壓）", score: -5 });
  }

  return { score: Math.max(-20, Math.min(20, rawScore)), signals };
}

function computeScore(candles, instRows) {
  const tech  = scoreTechnical(candles);
  const chip  = scoreChip(instRows);
  const vol   = scoreVolumePrice(candles);
  const trend = scoreTrend(candles);

  // Base 50 so neutral stock lands ~50
  const raw = tech.score + chip.score + vol.score + trend.score;
  const total = Math.max(0, Math.min(100, raw + 50));

  const recommendation =
    total >= 80 ? "STRONG_BUY"  :
    total >= 60 ? "BUY"         :
    total >= 40 ? "HOLD"        :
    total >= 20 ? "SELL"        : "STRONG_SELL";

  const allSignals = [
    ...tech.signals, ...chip.signals, ...vol.signals, ...trend.signals
  ].sort((a, b) => Math.abs(b.score) - Math.abs(a.score));

  return { total, recommendation,
    scores: { technical: tech.score, chip: chip.score,
              volume_price: vol.score, trend: trend.score },
    signals: allSignals };
}

/* ── 綜合評分卡 ── */

async function renderScore(sid) {
  const root = document.getElementById("sp-score");
  if (!root) return;

  try {
    const [ohlcvRaw, instRaw] = await Promise.all([
      _fetchFinMind(sid, _startDate(3)),
      _fetchInstitutional(sid, _startDate(2)),
    ]);

    if (!ohlcvRaw.length) {
      root.innerHTML = `<div style="color:var(--text3);font-size:var(--fs-sm)">無 OHLCV 資料</div>`;
      return;
    }

    const instRows = _parseInstitutional(instRaw);
    const result   = computeScore(ohlcvRaw, instRows);

    const recLabel = {
      STRONG_BUY: "強買進", BUY: "買進", HOLD: "觀望",
      SELL: "減碼",  STRONG_SELL: "強賣出"
    }[result.recommendation] || result.recommendation;

    const recCls = {
      STRONG_BUY: "score-strong-buy", BUY: "score-buy", HOLD: "score-hold",
      SELL: "score-sell", STRONG_SELL: "score-strong-sell"
    }[result.recommendation] || "score-hold";

    const barColor = {
      STRONG_BUY: "#1a7f37", BUY: "#3fb950", HOLD: "#d29922",
      SELL: "#f0883e", STRONG_SELL: "#f85149"
    }[result.recommendation] || "#d29922";

    const { technical: t, chip: c, volume_price: v, trend: tr } = result.scores;
    const barRow = (label, val, max) => {
      const pct = Math.round((Math.max(0, val + max) / (max * 2)) * 100);
      return `<div class="score-bar-row">
        <span class="score-bar-label">${label}</span>
        <div class="score-bar-track"><div class="score-bar-fill" style="width:${pct}%;background:${barColor}"></div></div>
        <span class="score-bar-val">${val > 0 ? "+" : ""}${val}</span>
      </div>`;
    };

    const sigList = result.signals.slice(0, 8).map(s => {
      const cls = s.score > 0 ? "score-sig-pos" : "score-sig-neg";
      const sign = s.score > 0 ? "+" : "";
      return `<li><span class="score-sig-reason">${escapeHtml(s.reason)}</span>
               <span class="${cls}">${sign}${s.score}</span></li>`;
    }).join("");

    const riskWarnings = result.signals
      .filter(s => s.score < -2)
      .slice(0, 2)
      .map(s => `⚠️ ${escapeHtml(s.reason)}`)
      .join("　");

    root.innerHTML = `
      <div class="score-wrap">
        <div class="score-circle ${recCls}">
          <span class="sc-num">${result.total}</span>
          <span class="sc-rec">${recLabel}</span>
        </div>
        <div class="score-bars">
          ${barRow("技術", t, 30)}
          ${barRow("籌碼", c, 30)}
          ${barRow("量價", v, 20)}
          ${barRow("趨勢", tr, 20)}
        </div>
      </div>
      <ul class="score-signals">${sigList}</ul>
      ${riskWarnings ? `<div class="score-risk">${riskWarnings}</div>` : ""}
    `;
  } catch (err) {
    root.innerHTML = `<div style="color:var(--text3);font-size:var(--fs-sm)">評分計算失敗</div>`;
  }
}

/* ── Entry point ── */
document.addEventListener("DOMContentLoaded", init);
