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

  const chartDiv = document.createElement("div");
  chartDiv.style.cssText = "width:100%;height:390px;";
  container.appendChild(chartDiv);

  const chart = LightweightCharts.createChart(chartDiv, {
    width: chartDiv.clientWidth, height: 390,
    layout: { background: { color: "#161b22" }, textColor: "#e6edf3" },
    grid:   { vertLines: { color: "#21262d" }, horzLines: { color: "#21262d" } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: "#30363d", scaleMargins: { top: 0.05, bottom: 0.22 } },
    timeScale: { borderColor: "#30363d", timeVisible: false },
  });

  // 台灣慣例：漲=紅 跌=綠
  chart.addCandlestickSeries({
    upColor: "#f85149", downColor: "#3fb950",
    borderUpColor: "#f85149", borderDownColor: "#3fb950",
    wickUpColor:   "#f85149", wickDownColor:   "#3fb950",
  }).setData(candles);

  // 成交量
  const vol = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol" });
  chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  vol.setData(candles.map(c => ({
    time: c.time, value: c.volume,
    color: c.close >= c.open ? "rgba(248,81,73,0.45)" : "rgba(63,185,80,0.45)",
  })));

  // MA 均線
  const maConfig = [{ n:5, color:"#f0883e" }, { n:20, color:"#d2a8ff" }, { n:60, color:"#7ee787" }];
  for (const { n, color } of maConfig) {
    const ma = candles.map((c, i) => {
      if (i < n - 1) return null;
      const avg = candles.slice(i - n + 1, i + 1).reduce((s, x) => s + x.close, 0) / n;
      return { time: c.time, value: +avg.toFixed(2) };
    }).filter(Boolean);
    if (!ma.length) continue;
    chart.addLineSeries({ color, lineWidth: 1,
      priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
    }).setData(ma);
  }

  chart.timeScale().fitContent();

  const legend = document.createElement("div");
  legend.style.cssText = "display:flex;align-items:center;padding:3px 8px;font-size:11px;gap:12px;background:#161b22;";
  legend.innerHTML = maConfig.map(m => `<span style="color:${m.color}">● MA${m.n}</span>`).join("") +
    `<span style="flex:1;text-align:right;color:var(--text3)">資料來源 <a href="https://finmindtrade.com/" target="_blank" rel="noopener" style="color:var(--text2)">FinMind</a></span>`;
  container.appendChild(legend);

  new ResizeObserver(() => chart.applyOptions({ width: chartDiv.clientWidth })).observe(chartDiv);
}

/* ── Entry point ── */
document.addEventListener("DOMContentLoaded", init);
