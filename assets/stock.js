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

/* ── K 線圖：Lightweight Charts (Apache 2.0) + TWSE/TPEx OHLC ── */

function _rocDateToIso(rocDate) {
  const p = rocDate.replace(/\//g, "-").split("-");
  if (p.length !== 3) return null;
  return `${parseInt(p[0]) + 1911}-${p[1]}-${p[2]}`;
}

function _safeNum(s) {
  const n = parseFloat(String(s).replace(/,/g, ""));
  return isNaN(n) ? null : n;
}

async function _fetchTwseOhlc(sid, months) {
  const candles = [];
  for (const ym of months) {
    try {
      const url = `https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=${ym}01&stockNo=${sid}`;
      const res = await fetch(url);
      if (!res.ok) continue;
      const d = await res.json();
      if (d.stat !== "OK") continue;
      for (const row of d.data || []) {
        const time = _rocDateToIso(row[0]);
        const open = _safeNum(row[3]), high = _safeNum(row[4]);
        const low  = _safeNum(row[5]), close = _safeNum(row[6]);
        const volume = _safeNum(row[1]);
        if (!time || open == null || close == null) continue;
        candles.push({ time, open, high, low, close, volume: volume ?? 0 });
      }
    } catch (_) {}
  }
  return candles;
}

async function _fetchTpexOhlc(sid, months) {
  const candles = [];
  for (const ym of months) {
    try {
      const year  = parseInt(ym.slice(0, 4)) - 1911;
      const month = ym.slice(4, 6);
      const url = `https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php?l=zh-tw&d=${year}/${month}&se=EW&s=${sid}`;
      const res = await fetch(url);
      if (!res.ok) continue;
      const d = await res.json();
      for (const row of d.aaData || []) {
        const time = _rocDateToIso(row[0]);
        const open = _safeNum(row[4]), high = _safeNum(row[5]);
        const low  = _safeNum(row[6]), close = _safeNum(row[7]);
        const volume = _safeNum(row[1]);
        if (!time || open == null || close == null) continue;
        candles.push({ time, open, high, low, close, volume: volume ?? 0 });
      }
    } catch (_) {}
  }
  return candles;
}

async function initChart(sid) {
  const container = document.getElementById("tv-container");
  container.innerHTML = `<div style="color:var(--text3);padding:16px;font-size:var(--fs-sm)">K 線載入中…</div>`;

  const exchange = state.prices?.prices?.[sid]?.exchange || "TWSE";

  // Build last 3 months in YYYYMM format
  const months = [];
  const now = new Date();
  for (let i = 2; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    months.push(`${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}`);
  }

  const candles = exchange === "TPEX"
    ? await _fetchTpexOhlc(sid, months)
    : await _fetchTwseOhlc(sid, months);

  if (!candles.length) {
    container.innerHTML = `<div style="color:var(--text3);padding:16px;font-size:var(--fs-sm)">無法取得歷史資料（TWSE/TPEx API 未回應）</div>`;
    return;
  }
  candles.sort((a, b) => a.time < b.time ? -1 : 1);

  container.innerHTML = "";
  const chartDiv = document.createElement("div");
  chartDiv.style.cssText = "width:100%;height:420px;";
  container.appendChild(chartDiv);

  const chart = LightweightCharts.createChart(chartDiv, {
    width: chartDiv.clientWidth,
    height: 420,
    layout: { background: { color: "#161b22" }, textColor: "#e6edf3" },
    grid: { vertLines: { color: "#21262d" }, horzLines: { color: "#21262d" } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: "#30363d", scaleMargins: { top: 0.05, bottom: 0.22 } },
    timeScale: { borderColor: "#30363d", timeVisible: false },
    localization: { locale: "zh-TW" },
  });

  // K 線（台灣慣例：漲=紅 跌=綠）
  const candleSeries = chart.addCandlestickSeries({
    upColor:         "#f85149",
    downColor:       "#3fb950",
    borderUpColor:   "#f85149",
    borderDownColor: "#3fb950",
    wickUpColor:     "#f85149",
    wickDownColor:   "#3fb950",
  });
  candleSeries.setData(candles);

  // 成交量柱
  const volSeries = chart.addHistogramSeries({
    priceFormat: { type: "volume" },
    priceScaleId: "vol",
  });
  chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  volSeries.setData(candles.map(c => ({
    time: c.time,
    value: c.volume,
    color: c.close >= c.open ? "rgba(248,81,73,0.5)" : "rgba(63,185,80,0.5)",
  })));

  // MA 均線
  function calcMA(data, n) {
    return data.map((c, i) => {
      if (i < n - 1) return null;
      const avg = data.slice(i - n + 1, i + 1).reduce((s, x) => s + x.close, 0) / n;
      return { time: c.time, value: +avg.toFixed(2) };
    }).filter(Boolean);
  }
  const maConfig = [
    { n: 5,  color: "#f0883e", label: "MA5"  },
    { n: 20, color: "#d2a8ff", label: "MA20" },
    { n: 60, color: "#7ee787", label: "MA60" },
  ];
  for (const { n, color } of maConfig) {
    const data = calcMA(candles, n);
    if (!data.length) continue;
    chart.addLineSeries({
      color, lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    }).setData(data);
  }

  chart.timeScale().fitContent();

  // MA 圖例 + 授權標註
  const bar = document.createElement("div");
  bar.style.cssText = "display:flex;align-items:center;padding:3px 8px;font-size:11px;gap:12px;background:#161b22;";
  bar.innerHTML = maConfig.map(m =>
    `<span style="color:${m.color}">● ${m.label}</span>`
  ).join("") +
  `<span style="flex:1;text-align:right;color:var(--text3)">Charts by <a href="https://www.tradingview.com/" target="_blank" rel="noopener" style="color:var(--text2)">TradingView</a></span>`;
  container.appendChild(bar);

  new ResizeObserver(() => chart.applyOptions({ width: chartDiv.clientWidth }))
    .observe(chartDiv);
}

/* ── Entry point ── */
document.addEventListener("DOMContentLoaded", init);
