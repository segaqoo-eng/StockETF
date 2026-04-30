// toast.js — 簡易 toast lib（manual close 模式）
// API: toast(message, { level: "info" | "warn" | "error" })
// 多次呼叫會堆疊在右上角，使用者按 ✕ 關閉

(function () {
  function ensureContainer() {
    let c = document.getElementById("toast-container");
    if (!c) {
      c = document.createElement("div");
      c.id = "toast-container";
      document.body.appendChild(c);
    }
    return c;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, ch => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[ch]);
  }

  window.toast = function (message, opts) {
    opts = opts || {};
    const level = opts.level || "info";
    const c = ensureContainer();

    const el = document.createElement("div");
    el.className = `toast toast-${level}`;
    el.innerHTML =
      `<span class="toast-msg">${escapeHtml(message)}</span>` +
      `<button class="toast-close" aria-label="關閉">✕</button>`;
    el.querySelector(".toast-close").addEventListener("click", () => el.remove());
    c.appendChild(el);
  };

  window.dismissAllToasts = function () {
    const c = document.getElementById("toast-container");
    if (c) c.innerHTML = "";
  };
})();
