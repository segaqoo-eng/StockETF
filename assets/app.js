// StockETF frontend — v1: cross-holdings table with filters.

const DATA_URL = "data/latest.json";

// 0050 is the passive benchmark; everything else in v1.5 is an active ETF.
// Keep the rule by code (not type) so a future config tweak doesn't silently
// flip the visual treatment.
const PASSIVE_ETF_CODES = new Set(["0050"]);
function etfBorderClass(code) {
  return PASSIVE_ETF_CODES.has(code) ? "etf-card etf-card--passive" : "etf-card etf-card--active";
}

// Foreign-market badge for per-ETF holdings views. Cross-table is TW-only
// (see normalizer), so this is currently a no-op there but reused by the
// per-ETF modal added in the next commit.
const MARKET_BADGES = { US: "🇺🇸", JP: "🇯🇵", OTHER: "🌐" };
function renderMarketBadge(market) {
  const label = MARKET_BADGES[market];
  return label ? ` <span class="market-badge">${label}</span>` : "";
}

const state = {
  payload: null,
  diff: null,           // {ticker: {added, removed, changed}} or null on first-ever / fetch failure
  leaderboard: null,    // {window_days, as_of_today, as_of_baseline, top_added, top_removed}
  minEtfs: 3,
  industry: "",
  search: "",
  expandedStockId: null,
};

// Capital scrapes only top-10 of 00982A / 00992A. Their diffs may contain
// false 🆕/❌ when stocks shuffle in/out of the top-10 cutoff while the ETF
// still holds them. Footnote marker shown in the ETF modal.
const TOP10_LIMITED_TICKERS = new Set(["00982A", "00992A"]);

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

    document.getElementById("updated-at").textContent = formatDate(state.payload.updated_at);
    populateIndustryFilter();
    renderEtfChipBar();
    renderLeaderboard();
    render();
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

  const html = `
    <table class="cross">
      <thead>
        <tr>
          <th>股票</th>
          <th>產業</th>
          <th class="center">被幾檔 ETF 持有</th>
          <th class="num">最高權重</th>
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
  // h.market is absent on cross-table holdings (always TW after normalizer
  // filtering); fall back accordingly so the badge helper handles both.
  const badge = renderMarketBadge(h.market);
  return `
    <tr data-stock-id="${escapeHtml(h.stock_id)}">
      <td><b>${escapeHtml(h.stock_id)}</b> ${escapeHtml(h.stock_name)}${badge}</td>
      <td>${escapeHtml(h.industry || "—")}</td>
      <td class="center"><span class="count-badge">${h.held_by.length}</span></td>
      <td class="num weight">${maxWeight.toFixed(2)}%</td>
    </tr>
  `;
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

  // If the detail row for *this* stock is already open, close it
  if (existing && existing.classList.contains("detail") && existing.dataset.for === stockId) {
    existing.remove();
    state.expandedStockId = null;
    return;
  }
  // Close any other open detail row first
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

// --- 過去 N 天 top-movers leaderboard ---

function renderLeaderboard() {
  const container = document.getElementById("leaderboard");
  const lb = state.leaderboard;

  // No baseline available yet (first daily-run cycles after the format change)
  if (!lb || !lb.as_of_baseline || (lb.top_added.length === 0 && lb.top_removed.length === 0)) {
    container.innerHTML = `
      <div class="leaderboard-empty">
        📈 過去 ${(lb && lb.window_days) || 7} 天動向
        <span>資料累積中 — 需要 ≥ 2 天的新格式 snapshot 才會出現排行（每天 cron 會自動累積）</span>
      </div>`;
    return;
  }

  const renderList = (items, polarity) => {
    if (items.length === 0) {
      return `<li class="lb-empty">本期無顯著${polarity === "added" ? "加碼" : "減碼"}</li>`;
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
    <div class="leaderboard-header">
      📈 過去 ${lb.window_days} 天動向
      <span class="leaderboard-window">${lb.as_of_baseline} → ${lb.as_of_today}</span>
    </div>
    <div class="leaderboard-grid">
      <div class="lb-col lb-col-added">
        <h3>🟢 加碼 TOP ${lb.top_added.length}</h3>
        <ol>${renderList(lb.top_added, "added")}</ol>
      </div>
      <div class="lb-col lb-col-removed">
        <h3>🔴 減碼 TOP ${lb.top_removed.length}</h3>
        <ol>${renderList(lb.top_removed, "removed")}</ol>
      </div>
    </div>
  `;
}

// Fund-level metadata line shown at the top of the per-ETF modal body.
// Renders only the keys the scraper actually populated — different issuers
// expose different subsets, by design (see ScrapeResult.fund_meta).
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
  // 232,148,514,804 → "2,321"  (integer 億 — Taiwan convention)
  return (n / 1e8).toLocaleString("en", { maximumFractionDigits: 0 });
}

function formatDateShort(iso) {
  // "2026-04-27T15:33:01" → "2026-04-27 15:33"; safe for plain date strings too
  return String(iso).replace("T", " ").slice(0, 16);
}

// --- Per-ETF holdings drill-down ---

function renderEtfChipBar() {
  const bar = document.getElementById("etf-chip-bar");
  // Sort by ticker so the chip order is stable across reloads regardless of
  // payload.etfs ordering.
  const sortedEtfs = [...state.payload.etfs].sort((a, b) => a.ticker.localeCompare(b.ticker));
  bar.innerHTML = sortedEtfs.map(e => `
    <button type="button" class="etf-chip ${etfBorderClass(e.ticker)}" data-ticker="${escapeHtml(e.ticker)}">
      <span class="etf-chip-ticker">${escapeHtml(e.ticker)}</span>
      <span class="etf-chip-name">${escapeHtml(e.name)}</span>
    </button>
  `).join("");
  bar.querySelectorAll(".etf-chip").forEach(btn => {
    btn.addEventListener("click", () => openEtfModal(btn.dataset.ticker));
  });
}

function openEtfModal(ticker) {
  const etf = state.payload.etfs.find(e => e.ticker === ticker);
  if (!etf) return;

  // Defensive sort by weight desc — most scrapers return that order, but
  // don't rely on it.
  const holdings = [...(etf.holdings || [])].sort((a, b) => b.weight_pct - a.weight_pct);

  // Pull this ETF's diff slice (may be undefined on first run or for ETFs
  // not in yesterday's lineup).
  const diff = (state.diff && state.diff[ticker]) || { added: [], removed: [], changed: [] };
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
      badges.push(
        `<span class="diff-badge ${up ? "diff-up" : "diff-down"}" title="昨日 ${change.weight_yesterday.toFixed(2)}% → 今日 ${change.weight_today.toFixed(2)}%">` +
        `${up ? "▲" : "▼"} ${sign}${change.delta.toFixed(2)}%</span>`
      );
    }
    return `<tr>
      <td><b>${escapeHtml(h.stock_id)}</b></td>
      <td>${escapeHtml(h.stock_name)}${renderMarketBadge(h.market)}${badges.length ? " " + badges.join(" ") : ""}</td>
      <td class="num weight">${h.weight_pct.toFixed(2)}%</td>
      <td class="num">${Number(h.shares).toLocaleString()}</td>
    </tr>`;
  }).join("");

  // Removed stocks live in a separate footer section since they're absent
  // from today's holdings list.
  let removedSection = "";
  if (diff.removed.length > 0) {
    const items = diff.removed.map(r =>
      `<li><b>${escapeHtml(r.stock_id)}</b> ${escapeHtml(r.stock_name)}` +
      ` <span class="weight">${r.weight_pct.toFixed(2)}%</span></li>`
    ).join("");
    removedSection = `
      <div class="diff-removed-section">
        <h3>❌ 本日移除（${diff.removed.length} 檔，昨日權重）</h3>
        <ul>${items}</ul>
      </div>`;
  }

  // Capital top-10 caveat — false 🆕/❌ are likely.
  const caveat = TOP10_LIMITED_TICKERS.has(ticker)
    ? `<p class="diff-caveat">* 群益僅提供 top-10 持股，diff badge 可能含偽陽性 (見 docs/known-issues/capital-scraper.md)</p>`
    : "";

  document.getElementById("etf-modal-dialog").className =
    `modal-dialog ${etfBorderClass(etf.ticker)}`;
  document.getElementById("etf-modal-title").innerHTML =
    `<span class="ticker">${escapeHtml(etf.ticker)}</span>${escapeHtml(etf.name)}` +
    `<span class="modal-subtitle">· ${etf.holdings_count} 檔持股</span>`;
  document.getElementById("etf-modal-body").innerHTML = `
    ${renderFundMetaLine(etf.fund_meta)}
    <table class="etf-holdings">
      <thead><tr>
        <th>代號</th><th>名稱</th><th class="num">權重</th><th class="num">股數</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
    ${removedSection}
    ${caveat}
  `;
  document.getElementById("etf-modal").classList.remove("hidden");
}

function closeEtfModal() {
  document.getElementById("etf-modal").classList.add("hidden");
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

document.getElementById("etf-modal-close").addEventListener("click", closeEtfModal);
document.getElementById("etf-modal").addEventListener("click", e => {
  // Close on backdrop click but not on dialog click.
  if (e.target.id === "etf-modal") closeEtfModal();
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && !document.getElementById("etf-modal").classList.contains("hidden")) {
    closeEtfModal();
  }
});

load();
