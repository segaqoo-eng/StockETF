// StockETF frontend — cross-holdings table + per-ETF accordion overview.

const DATA_URL = "data/latest.json";

// 0050 is the passive benchmark; everything else in v1.5 is an active ETF.
// Keep the rule by code (not type) so a future config tweak doesn't silently
// flip the visual treatment.
const PASSIVE_ETF_CODES = new Set(["0050"]);
function etfBorderClass(code) {
  return PASSIVE_ETF_CODES.has(code) ? "etf-card etf-card--passive" : "etf-card etf-card--active";
}

// Foreign-market badge for per-ETF holdings views. Cross-table is TW-only
// (see normalizer), so this is a no-op there but used inside the ETF overview.
const MARKET_BADGES = { US: "🇺🇸", JP: "🇯🇵", OTHER: "🌐" };
function renderMarketBadge(market) {
  const label = MARKET_BADGES[market];
  return label ? ` <span class="market-badge">${label}</span>` : "";
}

// Capital scrapes only top-10 of 00982A / 00992A. Their diffs may contain
// false 🆕/❌ when stocks shuffle in/out of the top-10 cutoff while the ETF
// still holds them. Footnote shown in the ETF detail card.
const TOP10_LIMITED_TICKERS = new Set(["00982A", "00992A"]);

const state = {
  payload: null,
  diff: null,           // {as_of_today, as_of_baseline, by_etf} or null on first-ever / fetch failure
  leaderboard: null,
  history: null,        // {stock_id: {ticker: [{date, weight}]}}; per-stock sparkline source
  prices: null,         // {date, prices: {stock_id: {close, change, change_pct}}}; today's close
  minEtfs: 3,
  industry: "",
  search: "",
  expandedStockId: null,
};

async function load() {
  try {
    const res = await fetch(DATA_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.payload = await res.json();

    // Diff and leaderboard are optional — silent failure so a missing/empty
    // file never breaks the main view. Both need ≥ 2 new-format snapshots
    // before they have meaningful data.
    try {
      const diffRes = await fetch("data/latest_diff.json", { cache: "no-store" });
      if (diffRes.ok) state.diff = await diffRes.json();
    } catch (_) { /* swallow */ }
    try {
      const lbRes = await fetch("data/leaderboard_7d.json", { cache: "no-store" });
      if (lbRes.ok) state.leaderboard = await lbRes.json();
    } catch (_) { /* swallow */ }
    try {
      const histRes = await fetch("data/history_per_stock.json", { cache: "no-store" });
      if (histRes.ok) state.history = await histRes.json();
    } catch (_) { /* swallow */ }
    try {
      const pricesRes = await fetch("data/prices_today.json", { cache: "no-store" });
      if (pricesRes.ok) state.prices = await pricesRes.json();
    } catch (_) { /* swallow */ }

    document.getElementById("updated-at").textContent = formatDate(state.payload.updated_at);
    populateIndustryFilter();
    renderEtfChipBar();
    renderEtfOverview();
    renderChanges();
    renderConsensus();
    render();

    applyHash();  // honour deep-link hash on first paint
  } catch (err) {
    document.getElementById("cross-holdings-table").innerHTML =
      `<p class="loading">載入資料失敗：${escapeHtml(err.message)}</p>`;
    document.getElementById("etf-chip-bar").innerHTML =
      `<span class="loading">ETF 列表載入失敗</span>`;
  }
}

function formatDate(iso) {
  // "2026-04-24T16:00:00+08:00" → "2026-04-24 16:00"
  return iso.replace("T", " ").slice(0, 16);
}

function populateIndustryFilter() {
  const sel = document.getElementById("filter-industry");
  const industries = new Set(state.payload.holdings.map(h => h.industry).filter(Boolean));
  [...industries].sort().forEach(ind => {
    const o = document.createElement("option");
    o.value = ind;
    o.textContent = ind;
    sel.appendChild(o);
  });
}

function render() {
  const container = document.getElementById("cross-holdings-table");
  const rows = filteredHoldings();

  if (rows.length === 0) {
    container.innerHTML = `<p class="loading">沒有符合條件的股票</p>`;
    return;
  }

  const priceDate = (state.prices && state.prices.date) || "";
  const html = `
    <table class="cross">
      <thead>
        <tr>
          <th>股票</th>
          <th>產業</th>
          <th class="center">被幾檔 ETF 持有</th>
          <th class="num">最高權重</th>
          <th class="num" title="今日盤後">收盤 / 漲跌${priceDate ? ` <span class="th-date">(${priceDate.slice(5)})</span>` : ""}</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map(renderRow).join("")}
      </tbody>
    </table>
  `;
  container.innerHTML = html;
  wireRowClicks();
}

function filteredHoldings() {
  const { holdings } = state.payload;
  const q = state.search.toLowerCase();
  return holdings.filter(h => {
    if (h.held_by.length < state.minEtfs) return false;
    if (state.industry && h.industry !== state.industry) return false;
    if (q) {
      const hay = `${h.stock_id} ${h.stock_name}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function renderRow(h) {
  const maxWeight = Math.max(...h.held_by.map(b => b.weight_pct));
  const badge = renderMarketBadge(h.market);
  return `
    <tr data-stock-id="${escapeHtml(h.stock_id)}">
      <td><b>${escapeHtml(h.stock_id)}</b> ${escapeHtml(h.stock_name)}${badge}</td>
      <td>${escapeHtml(h.industry || "—")}</td>
      <td class="center"><span class="count-badge">${h.held_by.length}</span></td>
      <td class="num weight">${maxWeight.toFixed(2)}%</td>
      <td class="num">${renderPriceCell(h.stock_id)}</td>
    </tr>
  `;
}

function renderPriceCell(stockId) {
  const p = state.prices && state.prices.prices && state.prices.prices[stockId];
  if (!p) return `<span class="price-na">—</span>`;
  const up = p.change > 0;
  const down = p.change < 0;
  const cls = up ? "price-up" : down ? "price-down" : "price-flat";
  const arrow = up ? "▲" : down ? "▼" : "·";
  const sign = up ? "+" : "";
  return `<span class="price-close">${p.close.toLocaleString()}</span>` +
         ` <span class="price-change ${cls}">${arrow}${sign}${p.change_pct.toFixed(2)}%</span>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

function wireRowClicks() {
  document.querySelectorAll("table.cross tbody tr[data-stock-id]").forEach(row => {
    row.addEventListener("click", () => toggleDetail(row));
  });
}

function toggleDetail(row) {
  const stockId = row.dataset.stockId;
  const existing = row.nextElementSibling;

  if (existing && existing.classList.contains("detail") && existing.dataset.for === stockId) {
    existing.remove();
    state.expandedStockId = null;
    return;
  }
  document.querySelectorAll("tr.detail").forEach(r => r.remove());

  const holding = state.payload.holdings.find(h => h.stock_id === stockId);
  if (!holding) return;

  const etfMeta = Object.fromEntries(state.payload.etfs.map(e => [e.ticker, e]));
  const items = [...holding.held_by]
    .sort((a, b) => b.weight_pct - a.weight_pct)
    .map(b => {
      const meta = etfMeta[b.etf] || {};
      const name = meta.name ? ` ${escapeHtml(meta.name)}` : "";
      return `<li class="${etfBorderClass(b.etf)}">
        <span class="etf-name">${escapeHtml(b.etf)}${name}</span>
        <span class="weight">${b.weight_pct.toFixed(2)}%</span>
      </li>`;
    }).join("");

  const detailRow = document.createElement("tr");
  detailRow.className = "detail";
  detailRow.dataset.for = stockId;
  detailRow.innerHTML = `<td colspan="4"><ul>${items}</ul></td>`;
  row.after(detailRow);
  state.expandedStockId = stockId;
}

// --- 共識加減碼 tab — cross-ETF top movers (was the original leaderboard, brought back) ---

function renderConsensus() {
  const container = document.getElementById("consensus-panel");
  const lb = state.leaderboard;

  if (!lb || !lb.as_of_baseline || (lb.top_added.length === 0 && lb.top_removed.length === 0)) {
    container.innerHTML = `
      <div class="leaderboard-empty">
        🎯 過去 ${(lb && lb.window_days) || 7} 天 共識加減碼排行
        <span>資料累積中 — 需要 ≥ 2 天的快照才會出現排行</span>
      </div>`;
    return;
  }

  const renderList = (items, polarity) => {
    if (items.length === 0) {
      return `<li class="lb-empty">本期無顯著共識${polarity === "added" ? "加碼" : "減碼"}</li>`;
    }
    return items.map((it, i) => {
      const sign = polarity === "added" ? "+" : "";
      return `<li>
        <span class="lb-rank">${i + 1}</span>
        <span class="lb-stock"><b>${escapeHtml(it.stock_id)}</b> ${escapeHtml(it.stock_name)}</span>
        <span class="lb-meta">
          <span class="lb-count" title="${it.etf_count} 檔 ETF 同向異動">${it.etf_count} 檔</span>
          <span class="lb-delta lb-${polarity}">${sign}${it.total_delta.toFixed(2)}%</span>
        </span>
      </li>`;
    }).join("");
  };

  container.innerHTML = `
    <section class="leaderboard">
      <div class="leaderboard-header">
        🎯 過去 ${lb.window_days} 天 跨 ETF 共識
        <span class="leaderboard-window">${lb.as_of_baseline} → ${lb.as_of_today}</span>
      </div>
      <div class="leaderboard-grid">
        <div class="lb-col lb-col-added">
          <h3>🟢 共識加碼 TOP ${lb.top_added.length}</h3>
          <ol>${renderList(lb.top_added, "added")}</ol>
        </div>
        <div class="lb-col lb-col-removed">
          <h3>🔴 共識減碼 TOP ${lb.top_removed.length}</h3>
          <ol>${renderList(lb.top_removed, "removed")}</ol>
        </div>
      </div>
    </section>
  `;
}

// --- 各 ETF 持股變化 tab — per-ETF added/removed/changed breakdown ---

function renderChanges() {
  const root = document.getElementById("changes-list");
  if (!state.diff) {
    root.innerHTML = `<p class="loading">資料載入中…</p>`;
    return;
  }

  // Period header — shows what dates the diff is comparing against.
  let period;
  if (!state.diff.as_of_baseline) {
    period = `<div class="changes-period changes-period-empty">尚無歷史快照可比對 — 明天 cron 後自動有資料</div>`;
  } else {
    const staleNote = state.diff.is_stale
      ? `<span class="changes-stale-note">⚠️ 今日無最新資料，顯示上次更新比較</span>`
      : "";
    period = `<div class="changes-period">📅 比對期間：<b>${state.diff.as_of_baseline}</b> → <b>${state.diff.as_of_today}</b>${staleNote}</div>`;
  }

  // One card per ETF (ordered by ticker for stability), independent accordion.
  const sortedEtfs = [...state.payload.etfs].sort((a, b) => a.ticker.localeCompare(b.ticker));
  const cards = sortedEtfs.map(etf => buildChangesCardHtml(etf, state.diff.by_etf || {})).join("");

  root.innerHTML = period + cards;
  wireStockTrendClicks();
}

// --- per-stock weight trend sparkline (inline expansion below each stock row) ---

function wireStockTrendClicks() {
  document.querySelectorAll("#changes-list .changes-section-list li[data-stock-id]").forEach(li => {
    li.addEventListener("click", () => toggleStockTrend(li));
  });
}

function toggleStockTrend(li) {
  const stockId = li.dataset.stockId;
  const next = li.nextElementSibling;
  // Toggle off if its own trend row is already open
  if (next && next.classList.contains("trend-row") && next.dataset.for === stockId) {
    next.remove();
    return;
  }
  // Close any other open trend row across the page
  document.querySelectorAll("li.trend-row").forEach(r => r.remove());

  const trendLi = document.createElement("li");
  trendLi.className = "trend-row";
  trendLi.dataset.for = stockId;
  trendLi.innerHTML = drawStockTrend(stockId);
  li.after(trendLi);
}

function drawStockTrend(stockId) {
  const series = state.history && state.history[stockId];
  if (!series) return `<div class="trend-empty">無歷史資料</div>`;

  // Only ETFs with ≥ 2 points form a line — single-point series can't show a trend.
  const lines = Object.entries(series).filter(([_, pts]) => pts.length >= 2);
  if (lines.length === 0) {
    return `<div class="trend-empty">資料點不足（每檔 ETF 至少需 2 個交易日才能畫線）</div>`;
  }

  const W = 640, H = 180, PAD_L = 44, PAD_R = 16, PAD_T = 12, PAD_B = 28;
  // Union of all dates across lines (keeps X axis aligned)
  const allDates = [...new Set(lines.flatMap(([_, pts]) => pts.map(p => p.date)))].sort();
  const xIndex = Object.fromEntries(allDates.map((d, i) => [d, i]));

  let yMin = Infinity, yMax = -Infinity;
  for (const [_, pts] of lines) for (const p of pts) {
    if (p.weight < yMin) yMin = p.weight;
    if (p.weight > yMax) yMax = p.weight;
  }
  // Pad Y range so points don't kiss the edges
  const span = yMax - yMin || 1;
  yMin -= span * 0.1;
  yMax += span * 0.1;

  const xScale = i => PAD_L + (W - PAD_L - PAD_R) * (allDates.length === 1 ? 0.5 : i / (allDates.length - 1));
  const yScale = w => H - PAD_B - (H - PAD_T - PAD_B) * ((w - yMin) / (yMax - yMin));

  let svg = `<svg viewBox="0 0 ${W} ${H}" class="trend-svg" preserveAspectRatio="xMidYMid meet">`;

  // Y gridlines (3 lines: top, middle, bottom of plot area)
  for (let i = 0; i <= 2; i++) {
    const y = PAD_T + (H - PAD_T - PAD_B) * (i / 2);
    const wval = yMax - (yMax - yMin) * (i / 2);
    svg += `<line x1="${PAD_L}" y1="${y}" x2="${W - PAD_R}" y2="${y}" stroke="rgba(48,54,61,0.5)" stroke-width="1"/>`;
    svg += `<text x="${PAD_L - 6}" y="${y + 4}" text-anchor="end" fill="#6e7681" font-size="11" font-family="JetBrains Mono">${wval.toFixed(2)}%</text>`;
  }

  // X labels — first / middle / last date (MM-DD only)
  const xLabelIdx = allDates.length <= 3
    ? allDates.map((_, i) => i)
    : [0, Math.floor(allDates.length / 2), allDates.length - 1];
  for (const i of xLabelIdx) {
    svg += `<text x="${xScale(i)}" y="${H - 8}" text-anchor="middle" fill="#6e7681" font-size="11" font-family="JetBrains Mono">${allDates[i].slice(5)}</text>`;
  }

  // Lines + dots, one path per ETF
  const etfMeta = Object.fromEntries(state.payload.etfs.map(e => [e.ticker, e]));
  for (const [ticker, pts] of lines) {
    const color = (etfMeta[ticker] && etfMeta[ticker].color) || "#58a6ff";
    const path = pts.map((p, idx) => {
      const x = xScale(xIndex[p.date]);
      const y = yScale(p.weight);
      return `${idx === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    }).join(" ");
    svg += `<path d="${path}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;
    for (const p of pts) {
      const x = xScale(xIndex[p.date]);
      const y = yScale(p.weight);
      svg += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="${color}"><title>${ticker} ${p.date} ${p.weight.toFixed(2)}%</title></circle>`;
    }
  }

  svg += `</svg>`;

  // Legend below the chart
  const legend = lines.map(([ticker, _]) => {
    const meta = etfMeta[ticker] || {};
    const color = meta.color || "#58a6ff";
    return `<span class="trend-legend-item"><span class="trend-legend-dot" style="background:${color}"></span>${escapeHtml(ticker)} ${escapeHtml(meta.name || "")}</span>`;
  }).join("");

  // Single-point series get listed as a footer note rather than charted
  const singletons = Object.entries(series).filter(([_, pts]) => pts.length < 2);
  const singletonNote = singletons.length
    ? `<div class="trend-singletons">＊只有今日資料：${singletons.map(([t]) => escapeHtml(t)).join(", ")}（cron 累積中）</div>`
    : "";

  return `
    <div class="trend-container">
      ${svg}
      <div class="trend-legend">${legend}</div>
      ${singletonNote}
    </div>`;
}

function buildChangesCardHtml(etf, byEtf) {
  const ticker = etf.ticker;
  const diff = byEtf[ticker];

  let summaryNote = "";
  let body = "";

  if (!diff) {
    summaryNote = `<span class="card-count card-count-muted">首次出現，累積中</span>`;
    body = `<div class="card-body changes-empty">此 ETF 尚無前次快照可比對，待 cron 累積第二筆資料後自動顯示。</div>`;
  } else {
    const total = diff.added.length + diff.removed.length + diff.changed.length;
    if (total === 0) {
      summaryNote = `<span class="card-count card-count-muted">本期無變動</span>`;
      body = `<div class="card-body changes-empty">本期持股無顯著變動（門檻內）</div>`;
    } else {
      const counts = [];
      if (diff.added.length)   counts.push(`新進 ${diff.added.length}`);
      if (diff.removed.length) counts.push(`移除 ${diff.removed.length}`);
      if (diff.changed.length) counts.push(`加減碼 ${diff.changed.length}`);
      summaryNote = `<span class="card-count">${counts.join(" · ")}</span>`;
      body = `<div class="card-body">
        ${renderChangesAddRemoveSection("🆕 新進", "added", diff.added, "weight_pct")}
        ${renderChangesAddRemoveSection("❌ 移除", "removed", diff.removed, "weight_pct", "前次權重")}
        ${renderChangesChangedSection(diff.changed)}
      </div>`;
    }
  }

  return `
    <details class="etf-card-large ${etfBorderClass(ticker)}" name="changes-overview">
      <summary>
        <div class="card-head-row">
          <span class="card-ticker">${escapeHtml(ticker)}</span>
          <span class="card-name">${escapeHtml(etf.name)}</span>
          ${summaryNote}
          <span class="card-toggle" aria-hidden="true">▾</span>
        </div>
      </summary>
      ${body}
    </details>
  `;
}

function renderChangesAddRemoveSection(label, kind, items, weightField, weightPrefix = "權重") {
  if (items.length === 0) return "";
  const sorted = [...items].sort((a, b) => b[weightField] - a[weightField]);
  const li = sorted.map(it =>
    `<li data-stock-id="${escapeHtml(it.stock_id)}">
      <b>${escapeHtml(it.stock_id)}</b>
      <span class="ch-name">${escapeHtml(it.stock_name)}</span>
      <span class="ch-weight">${weightPrefix} ${it[weightField].toFixed(2)}%</span>
    </li>`
  ).join("");
  return `<h4 class="changes-section-h ch-${kind}">${label} (${items.length})</h4>
          <ul class="changes-section-list">${li}</ul>`;
}

function renderChangesChangedSection(items) {
  if (items.length === 0) return "";
  const prevDate = (state.diff && state.diff.as_of_baseline) || "前次";
  const nowDate = (state.diff && state.diff.as_of_today) || "本次";
  // Sort by abs(delta) desc — biggest movers first regardless of direction.
  const sorted = [...items].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  const li = sorted.map(c => {
    const up = c.delta > 0;
    const sign = up ? "+" : "";
    const dir = up ? "up" : "down";
    const sharesDelta = (c.shares_now || 0) - (c.shares_prev || 0);
    const sharesDeltaSign = sharesDelta > 0 ? "+" : "";
    const sharesLine = (c.shares_now != null && c.shares_prev != null)
      ? `<span class="ch-shares">${Number(c.shares_now).toLocaleString()} 股 <span class="ch-shares-delta ${sharesDelta > 0 ? "shares-up" : sharesDelta < 0 ? "shares-down" : ""}">(${sharesDeltaSign}${sharesDelta.toLocaleString()})</span></span>`
      : `<span class="ch-shares"></span>`;
    return `<li data-stock-id="${escapeHtml(c.stock_id)}" data-dir="${dir}">
      <b>${escapeHtml(c.stock_id)}</b>
      <span class="ch-name">${escapeHtml(c.stock_name)}</span>
      <span class="ch-trans" title="${prevDate} → ${nowDate}">
        <span class="ch-date">(${prevDate.slice(5)})</span> ${c.weight_prev.toFixed(2)}%
        → <span class="ch-date">(${nowDate.slice(5)})</span> <span class="ch-now">${c.weight_now.toFixed(2)}%</span>
      </span>
      <span class="diff-badge diff-${dir}">${sign}${c.delta.toFixed(2)}%</span>
      ${sharesLine}
    </li>`;
  }).join("");
  return `<h4 class="changes-section-h ch-changed">📊 加減碼 (${items.length})  <small style="font-weight:normal;color:var(--text3)">點任一檔看歷史走勢</small></h4>
          <ul class="changes-section-list changes-section-list-changes">${li}</ul>`;
}

// --- Fund-level metadata strip used in the ETF overview cards ---

function renderFundMetaLine(meta) {
  if (!meta || Object.keys(meta).length === 0) return "";
  const parts = [];
  if (meta.as_of_date) {
    parts.push(`📅 截至 <b>${escapeHtml(formatDateShort(meta.as_of_date))}</b>`);
  }
  if (typeof meta.nav_total === "number") {
    parts.push(`💰 規模 <b>${formatYi(meta.nav_total)} 億</b>`);
  }
  if (typeof meta.p_unit === "number") {
    parts.push(`單位淨值 <b>${meta.p_unit.toFixed(2)}</b>`);
  }
  if (typeof meta.units_outstanding === "number") {
    parts.push(`流通 <b>${formatYi(meta.units_outstanding)} 億</b>`);
  }
  if (parts.length === 0) return "";
  return `<div class="fund-meta">${parts.join(" · ")}</div>`;
}

function formatYi(n) {
  return (n / 1e8).toLocaleString("en", { maximumFractionDigits: 0 });
}

function formatDateShort(iso) {
  return String(iso).replace("T", " ").slice(0, 16);
}

// --- ETF chip bar (always visible at top, acts as a deep-link launcher) ---

function renderEtfChipBar() {
  const bar = document.getElementById("etf-chip-bar");
  const sortedEtfs = [...state.payload.etfs].sort((a, b) => a.ticker.localeCompare(b.ticker));
  bar.innerHTML = sortedEtfs.map(e => `
    <button type="button" class="etf-chip ${etfBorderClass(e.ticker)}" data-ticker="${escapeHtml(e.ticker)}">
      <span class="etf-chip-ticker">${escapeHtml(e.ticker)}</span>
      <span class="etf-chip-name">${escapeHtml(e.name)}</span>
    </button>
  `).join("");
  bar.querySelectorAll(".etf-chip").forEach(btn => {
    btn.addEventListener("click", () => {
      // Hash routing handles tab switch + accordion open + scroll
      location.hash = `etfs/${btn.dataset.ticker}`;
    });
  });
}

// --- ETF overview accordion (the "ETF 總覽" tab content) ---

function renderEtfOverview() {
  const root = document.getElementById("etf-overview");
  const sortedEtfs = [...state.payload.etfs].sort((a, b) => a.ticker.localeCompare(b.ticker));
  root.innerHTML = sortedEtfs.map(buildEtfCardHtml).join("");
}

function buildEtfCardHtml(etf) {
  const ticker = etf.ticker;
  const holdings = [...(etf.holdings || [])].sort((a, b) => b.weight_pct - a.weight_pct);

  const diff = (state.diff && state.diff.by_etf && state.diff.by_etf[ticker]) || { added: [], removed: [], changed: [] };
  const addedIds = new Set(diff.added.map(h => h.stock_id));
  const changedById = Object.fromEntries(diff.changed.map(c => [c.stock_id, c]));

  const rows = holdings.map(h => {
    const badges = [];
    if (addedIds.has(h.stock_id)) {
      badges.push(`<span class="diff-badge diff-added" title="今日新進">🆕</span>`);
    }
    const change = changedById[h.stock_id];
    if (change) {
      const up = change.delta > 0;
      const sign = up ? "+" : "";
      const prevDate = (state.diff && state.diff.as_of_baseline) || "前次";
      const nowDate = (state.diff && state.diff.as_of_today) || "本次";
      badges.push(
        `<span class="diff-badge ${up ? "diff-up" : "diff-down"}" title="${prevDate}: ${change.weight_prev.toFixed(2)}% → ${nowDate}: ${change.weight_now.toFixed(2)}%">` +
        `${sign}${change.delta.toFixed(2)}%</span>`
      );
    }
    return `<tr>
      <td><b>${escapeHtml(h.stock_id)}</b></td>
      <td>${escapeHtml(h.stock_name)}${renderMarketBadge(h.market)}${badges.length ? " " + badges.join(" ") : ""}</td>
      <td class="num weight">${h.weight_pct.toFixed(2)}%</td>
      <td class="num">${Number(h.shares).toLocaleString()}</td>
    </tr>`;
  }).join("");

  let removedSection = "";
  if (diff.removed.length > 0) {
    const items = diff.removed.map(r =>
      `<li><b>${escapeHtml(r.stock_id)}</b> ${escapeHtml(r.stock_name)}` +
      ` <span class="weight">${r.weight_pct.toFixed(2)}%</span></li>`
    ).join("");
    removedSection = `
      <div class="diff-removed-section">
        <h3>❌ 本期移除（${diff.removed.length} 檔，前次權重）</h3>
        <ul>${items}</ul>
      </div>`;
  }

  const caveat = TOP10_LIMITED_TICKERS.has(ticker)
    ? `<p class="diff-caveat">* 群益僅提供 top-10 持股，diff badge 可能含偽陽性 (見 docs/known-issues/capital-scraper.md)</p>`
    : "";

  // Use native <details>/<summary> for accordion behaviour — no JS needed
  // for the expand/collapse, hash routing only flips the open attribute.
  // name="etf-overview" makes all cards mutually exclusive (browser closes
  // any other open <details> in the same group when one opens) — keeps the
  // accordion predictable and the page from sprawling.
  // The ticker+name span is wrapped in a target=_blank link to the issuer's
  // page; clicking elsewhere on the summary still toggles the card.
  const titleInner = `
    <span class="card-ticker">${escapeHtml(ticker)}</span>
    <span class="card-name">${escapeHtml(etf.name)}</span>
  `;
  const title = etf.url
    ? `<a class="card-ticker-link" href="${escapeHtml(etf.url)}" target="_blank" rel="noopener noreferrer"
          title="前往官方頁面（新分頁）" onclick="event.stopPropagation()">${titleInner}</a>`
    : titleInner;

  return `
    <details class="etf-card-large ${etfBorderClass(ticker)}" name="etf-overview" data-ticker="${escapeHtml(ticker)}">
      <summary>
        <div class="card-head-row">
          ${title}
          <span class="card-count">${etf.holdings_count} 檔持股</span>
          <span class="card-toggle" aria-hidden="true">▾</span>
        </div>
        ${renderFundMetaLine(etf.fund_meta)}
      </summary>
      <div class="card-body">
        <table class="etf-holdings">
          <thead><tr>
            <th>代號</th><th>名稱</th><th class="num">權重</th><th class="num">股數</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
        ${removedSection}
        ${caveat}
      </div>
    </details>
  `;
}

// --- Tab switching + hash routing (single source of truth: location.hash) ---

function activateTab(name) {
  document.querySelectorAll(".tab-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach(p => {
    p.classList.toggle("active", p.id === `tab-${name}`);
  });
}

// Whitelist so an unrecognised hash doesn't accidentally activate a removed tab.
const VALID_TABS = new Set(["cross", "etfs", "changes", "consensus"]);

function applyHash() {
  const hash = location.hash.slice(1);  // strip leading #
  const [tab, etfTicker] = hash.split("/");

  activateTab(VALID_TABS.has(tab) ? tab : "cross");

  // Sub-routing only matters for the ETF accordion right now.
  if (tab === "etfs" && etfTicker) {
    const card = document.querySelector(`details[data-ticker="${CSS.escape(etfTicker)}"]`);
    if (card) {
      card.open = true;
      // Defer scroll until after the just-opened <details> has reflowed —
      // otherwise smooth scroll computes the target from the still-closed
      // bbox and lands past the summary. scroll-margin-top in CSS handles
      // the sticky tab-nav offset.
      requestAnimationFrame(() => {
        card.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }
}

function wireTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      if (btn.disabled) return;
      // Setting hash triggers hashchange → applyHash; never mutate UI directly.
      location.hash = btn.dataset.tab;
    });
  });
  window.addEventListener("hashchange", applyHash);
}

// --- Wire controls ---

document.getElementById("filter-min-etfs").addEventListener("change", e => {
  state.minEtfs = Number(e.target.value);
  render();
});
document.getElementById("filter-industry").addEventListener("change", e => {
  state.industry = e.target.value;
  render();
});
document.getElementById("filter-search").addEventListener("input", e => {
  state.search = e.target.value.trim();
  render();
});

wireTabs();
load();
