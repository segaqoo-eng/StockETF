// positions.js — 「我的部位」分頁
// 依賴：app.js（escapeHtml）+ scripts/web_server.py 提供 /api/positions
// 純前端 + API call，不用 CLI 也能 add/close 部位。

let _positionsLoaded = false;
let _positionsData   = null;     // { open, closed, summary }

async function initPositionsTab() {
  const root = document.getElementById("positions-root");
  if (!root) return;
  if (_positionsLoaded) {
    _renderPositions();
    return;
  }
  _positionsLoaded = true;
  await _refreshPositions();
}

async function _refreshPositions() {
  const root = document.getElementById("positions-root");
  if (!root) return;
  root.innerHTML = `<p class="loading">載入持倉中…</p>`;
  try {
    const res = await fetch("/api/positions", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    _positionsData = await res.json();
    _renderPositions();
  } catch (e) {
    root.innerHTML = `
      <div class="pos-error">
        <p>❌ 抓不到持倉資料：${escapeHtml(String(e))}</p>
        <p>確認你是用 <code>scripts/web_server.py</code> 啟動的 server，
           不是 <code>python -m http.server</code>（後者無 API）。</p>
        <p>解法：關掉現在的 server，改執行 <code>update.bat</code> 或
           <code>python scripts/web_server.py</code></p>
      </div>
    `;
  }
}

function _renderPositions() {
  const root = document.getElementById("positions-root");
  if (!root || !_positionsData) return;

  const { open, closed, summary } = _positionsData;
  root.innerHTML = `
    ${_buildSummaryHTML(summary)}
    ${_buildAddFormHTML()}
    ${_buildOpenTableHTML(open)}
    ${_buildClosedTableHTML(closed)}
  `;

  document.getElementById("pos-add-form")?.addEventListener("submit", _onAddSubmit);
  _wireAddFormAutofill();
  document.querySelectorAll(".pos-close-btn").forEach(btn => {
    btn.addEventListener("click", () => _onCloseClick(btn));
  });
  document.getElementById("pos-refresh")?.addEventListener("click", _refreshPositions);
}

function _buildSummaryHTML(s) {
  if (!s) return "";
  const sign = (n) => n >= 0 ? "+" : "";
  const totalCls = s.total >= 0 ? "pos-pnl-up" : "pos-pnl-down";
  const pct = s.progress_pct;
  const barW = Math.max(0, Math.min(100, pct));
  return `
    <div class="pos-summary">
      <div class="pos-stat">
        <div class="pos-stat-lbl">已實現</div>
        <div class="pos-stat-val ${s.realized >= 0 ? 'pos-pnl-up':'pos-pnl-down'}">${sign(s.realized)}${s.realized.toLocaleString()}</div>
      </div>
      <div class="pos-stat">
        <div class="pos-stat-lbl">浮動</div>
        <div class="pos-stat-val ${s.unrealized >= 0 ? 'pos-pnl-up':'pos-pnl-down'}">${sign(s.unrealized)}${s.unrealized.toLocaleString()}</div>
      </div>
      <div class="pos-stat">
        <div class="pos-stat-lbl">合計</div>
        <div class="pos-stat-val ${totalCls}">${sign(s.total)}${s.total.toLocaleString()}</div>
      </div>
      <div class="pos-stat pos-target">
        <div class="pos-stat-lbl">🎯 回本進度（USD ${s.target_usd} ≈ NTD ${s.target_ntd.toLocaleString()}）</div>
        <div class="pos-progress-bar"><div class="pos-progress-fill" style="width:${barW}%"></div></div>
        <div class="pos-stat-val pos-progress-pct">${sign(pct)}${pct.toFixed(1)}%</div>
      </div>
      <button id="pos-refresh" class="pos-btn-refresh">🔄 重新整理</button>
    </div>
  `;
}

function _buildAddFormHTML() {
  const today = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Taipei" }))
    .toISOString().slice(0, 10);

  // 從已載入的持股清單組 datalist (可下拉選 + 自動補名稱)
  const allStocks = (window.state?.payload?.holdings || []);
  const datalistOpts = allStocks.map(h =>
    `<option value="${escapeHtml(h.stock_id)}">${escapeHtml(h.stock_name)}</option>`
  ).join("");

  return `
    <div class="pos-card">
      <h3>➕ 新增買進</h3>
      <form id="pos-add-form" class="pos-form">
        <input type="text"   name="stock_id"   placeholder="代號 e.g. 7769"
               required maxlength="10" list="pos-stock-list" autocomplete="off">
        <input type="text"   name="stock_name" placeholder="名稱（自動帶入）"
               required maxlength="20">
        <input type="number" name="buy_price"  placeholder="進場價" step="0.01" required min="0.01">
        <input type="number" name="shares"     placeholder="股數"   step="1"   required min="1">
        <input type="date"   name="buy_date"   value="${today}">
        <button type="submit" class="pos-btn-primary">加入</button>
        <textarea name="buy_reason" class="pos-form-reason" placeholder="買進理由（選填）— 例如：分數 78、法人連買三天、PCB 強勢..." maxlength="200" rows="2"></textarea>
      </form>
      <datalist id="pos-stock-list">${datalistOpts}</datalist>
      <small class="pos-hint">輸入股號 → 自動帶入名稱（${allStocks.length} 檔可選；不在清單中的可手動打）。理由先寫，將來複盤時很有用。</small>
    </div>
  `;
}

function _wireAddFormAutofill() {
  const f = document.getElementById("pos-add-form");
  if (!f) return;
  const idInput   = f.stock_id;
  const nameInput = f.stock_name;
  let nameManuallyEdited = false;

  nameInput.addEventListener("input", (e) => {
    // user 自己改了名字，之後不再覆蓋
    if (e.isTrusted) nameManuallyEdited = true;
  });

  idInput.addEventListener("input", () => {
    if (nameManuallyEdited && nameInput.value.trim()) return;
    const sid = idInput.value.trim();
    const all = window.state?.payload?.holdings || [];
    const match = all.find(h => h.stock_id === sid);
    if (match) {
      nameInput.value = match.stock_name;
      nameManuallyEdited = false;  // 重置 (等同於用 datalist 帶入)
    }
  });

  f.addEventListener("reset", () => { nameManuallyEdited = false; });
}

function _buildOpenTableHTML(open) {
  if (!open || !open.length) {
    return `<div class="pos-card"><h3>📦 目前持倉（0 檔）</h3><p class="pos-empty">尚無持倉。從「買進評分」找訊號、上面表單記錄一筆。</p></div>`;
  }
  const sorted = [...open].sort((a, b) => (b.pnl_pct_net ?? -Infinity) - (a.pnl_pct_net ?? -Infinity));

  const rows = sorted.map(p => {
    const cur = p.current_price;
    const pct = p.pnl_pct_net;
    const ntd = p.pnl_ntd;
    const sign = (n) => n >= 0 ? "+" : "";
    const cls = pct >= 0 ? "pos-pnl-up" : pct < 0 ? "pos-pnl-down" : "";

    let action = "持有";
    if (cur != null) {
      if (cur >= p.tp_price) action = "<b class='pos-pnl-up'>🟢 賣出（達標）</b>";
      else if (cur <= p.sl_price) action = "<b class='pos-pnl-down'>🔴 賣出（停損）</b>";
      else if (pct >= 4) action = "🟡 接近 TP";
      else if (pct <= -4) action = "🟡 接近 SL";
    }

    const reasonHtml = p.buy_reason
      ? `<div class="pos-reason" title="${escapeHtml(p.buy_reason)}">💡 ${escapeHtml(p.buy_reason)}</div>`
      : "";
    return `
      <tr>
        <td>
          <b>${escapeHtml(p.stock_id)}</b> ${escapeHtml(p.stock_name)}
          ${reasonHtml}
        </td>
        <td>${p.buy_date}</td>
        <td class="r">${p.buy_price.toFixed(1)}</td>
        <td class="r">${cur != null ? cur.toFixed(1) : "—"}</td>
        <td class="r ${cls}">${cur != null ? sign(pct) + pct.toFixed(2) + "%" : "—"}</td>
        <td class="r">${p.shares.toLocaleString()}</td>
        <td class="r ${cls}">${ntd != null ? sign(ntd) + ntd.toLocaleString() : "—"}</td>
        <td class="r">${p.tp_price.toFixed(1)}</td>
        <td class="r">${p.sl_price.toFixed(1)}</td>
        <td>${action}</td>
        <td>
          <button class="pos-close-btn pos-btn-danger"
                  data-id="${escapeHtml(p.stock_id)}"
                  data-name="${escapeHtml(p.stock_name)}"
                  data-buyprice="${p.buy_price}">平倉</button>
        </td>
      </tr>
    `;
  }).join("");

  return `
    <div class="pos-card">
      <h3>📦 目前持倉（${open.length} 檔）</h3>
      <div class="pos-table-wrap">
        <table class="pos-table">
          <thead><tr>
            <th>股票</th><th>進場日</th>
            <th class="r">進價</th><th class="r">現價</th>
            <th class="r">浮動%</th><th class="r">股數</th>
            <th class="r">浮動損益</th>
            <th class="r">TP</th><th class="r">SL</th>
            <th>動作</th><th>—</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `;
}

function _buildClosedTableHTML(closed) {
  if (!closed || !closed.length) {
    return `<div class="pos-card"><h3>💰 已實現紀錄（0 筆）</h3><p class="pos-empty">尚無平倉紀錄。</p></div>`;
  }
  const wins = closed.filter(c => (c.pnl_ntd || 0) > 0).length;
  const losses = closed.length - wins;
  const rows = closed.slice(0, 30).map(c => {
    const pnl = c.pnl_ntd || 0;
    const sign = pnl >= 0 ? "+" : "";
    const cls  = pnl >= 0 ? "pos-pnl-up" : "pos-pnl-down";
    return `
      <tr>
        <td><b>${escapeHtml(c.stock_id)}</b> ${escapeHtml(c.stock_name)}</td>
        <td>${c.buy_date} → ${c.sell_date || "—"}</td>
        <td class="r">${c.buy_price.toFixed(1)}</td>
        <td class="r">${(c.sell_price || 0).toFixed(1)}</td>
        <td class="r">${(c.shares || 0).toLocaleString()}</td>
        <td class="r ${cls}"><b>${sign}${pnl.toLocaleString()}</b></td>
      </tr>
    `;
  }).join("");
  return `
    <div class="pos-card">
      <h3>💰 已實現紀錄（${closed.length} 筆，${wins} 勝 / ${losses} 負）</h3>
      <div class="pos-table-wrap">
        <table class="pos-table">
          <thead><tr>
            <th>股票</th><th>進出</th>
            <th class="r">進</th><th class="r">出</th>
            <th class="r">股數</th><th class="r">損益</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      ${closed.length > 30 ? `<p class="pos-hint">＊只顯示最近 30 筆</p>` : ""}
    </div>
  `;
}

async function _onAddSubmit(e) {
  e.preventDefault();
  const f = e.target;
  const data = {
    stock_id:   f.stock_id.value.trim(),
    stock_name: f.stock_name.value.trim(),
    buy_price:  Number(f.buy_price.value),
    shares:     Number(f.shares.value),
    buy_date:   f.buy_date.value || undefined,
    buy_reason: f.buy_reason?.value?.trim() || "",
  };
  if (!data.stock_id || !data.stock_name || !(data.buy_price > 0) || !(data.shares > 0)) {
    alert("欄位都要填且為正數");
    return;
  }
  try {
    const res = await fetch("/api/positions/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const json = await res.json();
    if (!json.ok) throw new Error(json.error || "新增失敗");
    f.reset();
    f.buy_date.value = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Taipei" }))
      .toISOString().slice(0, 10);
    await _refreshPositions();
  } catch (err) {
    alert("加入失敗：" + err);
  }
}

async function _onCloseClick(btn) {
  const sid  = btn.dataset.id;
  const name = btn.dataset.name;
  const bp   = btn.dataset.buyprice;
  const priceStr = prompt(`平倉 ${name}（${sid}）\n進場價 ${bp}\n\n請輸入賣出價：`);
  if (!priceStr) return;
  const sell_price = Number(priceStr);
  if (!(sell_price > 0)) { alert("價格無效"); return; }
  try {
    const res = await fetch("/api/positions/close", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stock_id: sid, sell_price }),
    });
    const json = await res.json();
    if (!json.ok) throw new Error(json.error || "平倉失敗");
    await _refreshPositions();
  } catch (err) {
    alert("平倉失敗：" + err);
  }
}
