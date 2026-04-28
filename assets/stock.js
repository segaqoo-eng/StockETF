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

/* ── TradingView Widget (iframe embed — free, works on any domain) ── */
function initTradingView(sid) {
  const exchange = state.prices?.prices?.[sid]?.exchange || "TWSE";
  const symbol = encodeURIComponent(`${exchange}:${sid}`);
  const container = document.getElementById("tv-container");

  const params = [
    `symbol=${symbol}`,
    "interval=D",
    "theme=dark",
    "style=1",
    "locale=zh_TW",
    "timezone=Asia%2FTaipei",
    "hide_side_toolbar=0",
    "allow_symbol_change=1",
    "save_image=0",
    "hide_volume=0",
  ].join("&");

  container.innerHTML =
    `<iframe src="https://www.tradingview.com/widgetembed/?${params}"` +
    ` style="width:100%;height:100%;border:none;" allowfullscreen></iframe>`;
}

/* ── Entry point ── */
document.addEventListener("DOMContentLoaded", init);
