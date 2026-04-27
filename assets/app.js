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
    document.getElementById("updated-at").textContent = formatDate(state.payload.updated_at);
    populateIndustryFilter();
    renderEtfChipBar();
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

  const rows = holdings.map(h => `
    <tr>
      <td><b>${escapeHtml(h.stock_id)}</b></td>
      <td>${escapeHtml(h.stock_name)}${renderMarketBadge(h.market)}</td>
      <td class="num weight">${h.weight_pct.toFixed(2)}%</td>
      <td class="num">${Number(h.shares).toLocaleString()}</td>
    </tr>
  `).join("");

  document.getElementById("etf-modal-dialog").className =
    `modal-dialog ${etfBorderClass(etf.ticker)}`;
  document.getElementById("etf-modal-title").innerHTML =
    `<span class="ticker">${escapeHtml(etf.ticker)}</span>${escapeHtml(etf.name)}` +
    `<span class="modal-subtitle">· ${etf.holdings_count} 檔持股</span>`;
  document.getElementById("etf-modal-body").innerHTML = `
    <table class="etf-holdings">
      <thead><tr>
        <th>代號</th><th>名稱</th><th class="num">權重</th><th class="num">股數</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
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
