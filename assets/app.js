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
  // Stub — filled in next task.
  document.getElementById("cross-holdings-table").innerHTML =
    `<p class="loading">已載入 ${state.payload.holdings.length} 筆股票資料 · 渲染邏輯待實作</p>`;
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
