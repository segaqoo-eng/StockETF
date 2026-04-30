// markdown_view.js — 渲染本機 .md 檔到網頁分頁
// 內含一個極簡 Markdown→HTML 解析器（無外部 framework / CDN）。
// 處理我們自己產生的 .md 檔內容即可，不追求 commonmark 完整。

/* ── Tab 初始化 ───────────────────────────────────────── */

let _signalsLoaded = false;
let _paperLoaded   = false;

async function initSignalsTab() {
  if (_signalsLoaded) return;
  _signalsLoaded = true;
  await _loadMarkdownTo("signals-root", "status_today", "📋 今日訊號");
}

async function initPaperTab() {
  if (_paperLoaded) return;
  _paperLoaded = true;
  await _loadMarkdownTo("paper-root", "paper_status", "📈 Paper 模擬");
}

async function _loadMarkdownTo(rootId, fileName, fallbackTitle) {
  const root = document.getElementById(rootId);
  if (!root) return;
  root.innerHTML = `
    <div class="md-toolbar">
      <button class="md-refresh-btn" data-file="${fileName}" data-root="${rootId}">🔄 重新整理</button>
      <span class="md-loaded-at"></span>
    </div>
    <div class="md-content"><p class="loading">載入 ${fileName}.md…</p></div>
  `;
  await _refreshMarkdown(rootId, fileName, fallbackTitle);

  root.querySelector(".md-refresh-btn").addEventListener("click", () => {
    _refreshMarkdown(rootId, fileName, fallbackTitle);
  });
}

async function _refreshMarkdown(rootId, fileName, fallbackTitle) {
  const root = document.getElementById(rootId);
  if (!root) return;
  const content = root.querySelector(".md-content");
  const tsLabel = root.querySelector(".md-loaded-at");
  if (content) content.innerHTML = `<p class="loading">載入 ${fileName}.md…</p>`;

  try {
    const res = await fetch(`/api/markdown?file=${encodeURIComponent(fileName)}`,
                             { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const text = await res.text();
    const html = renderMarkdown(text);
    if (content) content.innerHTML = html;
    if (tsLabel) tsLabel.textContent = `更新於 ${new Date().toLocaleTimeString("zh-TW")}`;
  } catch (e) {
    if (content) content.innerHTML = `
      <div class="pos-error">
        <p>❌ 載入 ${fileName}.md 失敗：${escapeHtml(String(e))}</p>
        <p>確認你是用 <code>scripts/web_server.py</code> 啟動 server。
           或先執行 <code>update.bat</code> 產生最新 .md 檔。</p>
      </div>
    `;
  }
}

/* ── 極簡 Markdown 解析 ────────────────────────────────────
   支援 (我們自己產生的 .md 檔範圍內)：
     # / ## / ### 標題
     - list (含 nested)
     | tables | 含 |---| 對齊行
     **bold**  _italic_  `code`
     ```fenced code blocks```
     ---  橫線
     段落 (空白行分隔)
*/

function renderMarkdown(md) {
  const lines = md.split(/\r?\n/);
  const out = [];
  let i = 0;

  // inline 處理：bold, italic, code, escape
  const inline = (s) => {
    s = escapeHtml(s);
    s = s.replace(/`([^`]+)`/g, '<code class="md-code-inline">$1</code>');
    s = s.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
    // 避免 _italic_ 吃到中文底線 — 要求兩側為 word boundary
    s = s.replace(/(^|[\s,;:!?(])_([^_\n]+)_(?=[\s,;:!?.)]|$)/g, '$1<i>$2</i>');
    return s;
  };

  while (i < lines.length) {
    const line = lines[i];

    // fenced code
    if (line.startsWith("```")) {
      i++;
      const code = [];
      while (i < lines.length && !lines[i].startsWith("```")) {
        code.push(lines[i]); i++;
      }
      i++; // skip closing ```
      out.push(`<pre class="md-codeblock"><code>${escapeHtml(code.join("\n"))}</code></pre>`);
      continue;
    }

    // headings
    let m;
    if ((m = line.match(/^(#{1,3})\s+(.*)$/))) {
      const level = m[1].length;
      out.push(`<h${level} class="md-h${level}">${inline(m[2])}</h${level}>`);
      i++; continue;
    }

    // hr
    if (/^---+$/.test(line.trim())) { out.push('<hr class="md-hr">'); i++; continue; }

    // table
    if (line.startsWith("|") && line.endsWith("|") && i + 1 < lines.length
        && /^\|[\s\-:|]+\|$/.test(lines[i + 1])) {
      const headerCells = _splitRow(line);
      const aligns = lines[i + 1].slice(1, -1).split("|").map(c => {
        const t = c.trim();
        if (t.startsWith(":") && t.endsWith(":")) return "center";
        if (t.endsWith(":")) return "right";
        if (t.startsWith(":")) return "left";
        return null;
      });
      i += 2; // skip header + separator
      const bodyRows = [];
      while (i < lines.length && lines[i].startsWith("|") && lines[i].endsWith("|")) {
        bodyRows.push(_splitRow(lines[i])); i++;
      }
      const headerHtml = headerCells.map((c, idx) =>
        `<th${aligns[idx] ? ` style="text-align:${aligns[idx]}"` : ""}>${inline(c)}</th>`).join("");
      const bodyHtml = bodyRows.map(row =>
        "<tr>" + row.map((c, idx) =>
          `<td${aligns[idx] ? ` style="text-align:${aligns[idx]}"` : ""}>${inline(c)}</td>`
        ).join("") + "</tr>"
      ).join("");
      out.push(`<table class="md-table"><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`);
      continue;
    }

    // unordered list
    if (line.match(/^- /)) {
      const items = [];
      while (i < lines.length && lines[i].match(/^- /)) {
        items.push(`<li>${inline(lines[i].slice(2))}</li>`);
        i++;
      }
      out.push(`<ul class="md-list">${items.join("")}</ul>`);
      continue;
    }

    // empty line
    if (line.trim() === "") { i++; continue; }

    // paragraph: collect consecutive non-empty non-special lines
    const paraLines = [];
    while (i < lines.length && lines[i].trim() !== "" &&
           !lines[i].match(/^(#{1,3} |- |\|)/) && !lines[i].startsWith("```") &&
           !/^---+$/.test(lines[i].trim())) {
      paraLines.push(lines[i]); i++;
    }
    if (paraLines.length) {
      out.push(`<p>${paraLines.map(inline).join("<br>")}</p>`);
    }
  }

  return out.join("\n");
}

function _splitRow(line) {
  // line 包夾 | 開頭結尾 — 切中間
  return line.slice(1, -1).split("|").map(c => c.trim());
}
