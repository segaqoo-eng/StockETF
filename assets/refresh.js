// refresh.js — 強制刷新按鈕邏輯
// 依賴 toast.js + app.js (window.StockETF.renderSourceBadge / setBadgeRunning)

(function () {
  const POLL_INTERVAL_MS = 2000;
  let pollTimer = null;

  function setButtonsDisabled(disabled) {
    document.getElementById("btn-refresh-prices").disabled = disabled;
    document.getElementById("btn-refresh-etfs").disabled = disabled;
  }

  async function startJob(endpoint) {
    setButtonsDisabled(true);
    if (window.StockETF && window.StockETF.setBadgeRunning) {
      window.StockETF.setBadgeRunning();
    }
    try {
      const res = await fetch(endpoint, { method: "POST" });
      if (res.status === 409) {
        const body = await res.json();
        toast(`⏳ ${body.error || "已有任務在跑"}`, { level: "info" });
        setButtonsDisabled(false);
        if (window.StockETF) window.StockETF.renderSourceBadge();
        return;
      }
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      pollStatus();
    } catch (e) {
      toast(`刷新失敗：${e.message || e}`, { level: "error" });
      setButtonsDisabled(false);
      if (window.StockETF) window.StockETF.renderSourceBadge();
    }
  }

  function pollStatus() {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(async () => {
      try {
        const res = await fetch("/api/refresh/status", { cache: "no-store" });
        const status = await res.json();
        if (status.running) {
          pollStatus();
        } else {
          await onJobComplete(status);
        }
      } catch (e) {
        toast(`狀態查詢失敗：${e.message || e}`, { level: "error" });
        setButtonsDisabled(false);
      }
    }, POLL_INTERVAL_MS);
  }

  async function onJobComplete(status) {
    if (status.last_error) {
      toast(`刷新失敗：${status.last_error}`, { level: "error" });
      setButtonsDisabled(false);
      if (window.StockETF) window.StockETF.renderSourceBadge();
      return;
    }

    try {
      const pricesRes = await fetch("data/prices_today.json", { cache: "no-store" });
      if (pricesRes.ok && window.state) {
        window.state.prices = await pricesRes.json();
      }
      if (status.last_result && status.last_result.job === "etfs") {
        const latestRes = await fetch("data/latest.json", { cache: "no-store" });
        if (latestRes.ok && window.state) {
          window.state.payload = await latestRes.json();
        }
      }
    } catch (e) {
      toast(`資料重載失敗：${e.message || e}`, { level: "error" });
    }

    if (window.StockETF) window.StockETF.renderSourceBadge();
    if (typeof window.render === "function") window.render();

    const r = status.last_result || {};
    const msgs = [];
    if (r.missing_count) {
      msgs.push(`${r.missing_count} 檔股票今日抓不到`);
    }
    if (r.partial_failures && r.partial_failures.length) {
      const issuers = r.partial_failures.map(p => p.issuer).filter(Boolean);
      msgs.push(`${issuers.join("、")} 爬蟲失敗，相關 ETF 用前一天資料`);
    }
    if (msgs.length) {
      toast("⚠️ " + msgs.join("；"), { level: "warn" });
    }

    setButtonsDisabled(false);
  }

  function init() {
    document.getElementById("btn-refresh-prices")
      ?.addEventListener("click", () => startJob("/api/refresh/prices"));
    document.getElementById("btn-refresh-etfs")
      ?.addEventListener("click", () => startJob("/api/refresh/etfs"));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
