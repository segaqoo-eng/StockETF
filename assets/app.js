// StockETF frontend — v1: cross-holdings table with filters.

const DATA_URL = "data/latest.json";
const state = {
  payload: null,
  minEtfs: 2,
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
    render();
  } catch (err) {
    document.getElementById("cross-holdings-table").innerHTML =
      `<p class="loading">載入資料失敗：${err.message}</p>`;
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
  return `
    <tr data-stock-id="${h.stock_id}">
      <td><b>${h.stock_id}</b> ${escapeHtml(h.stock_name)}</td>
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
  // Filled in Task 10.
}

// Wire filter controls
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

load();
