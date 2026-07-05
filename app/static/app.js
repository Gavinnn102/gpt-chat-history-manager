let state = null;
let activeCategory = "全部会话";
let activeConversationId = null;
let categoryDraft = [];
let categoryOriginal = [];

const SYSTEM_PENDING = "待处理";
const categoryList = document.getElementById("categoryList");
const conversationList = document.getElementById("conversationList");
const detailPane = document.getElementById("detailPane");
const searchInput = document.getElementById("searchInput");
const statsEl = document.getElementById("stats");
const resultCount = document.getElementById("resultCount");
const activeLabel = document.getElementById("activeLabel");
const rootPath = document.getElementById("rootPath");
const categoryButton = document.getElementById("categoryButton");
const categoryModal = document.getElementById("categoryModal");
const categoryRows = document.getElementById("categoryRows");
const categoryMessage = document.getElementById("categoryMessage");
const moveDeletedCheckbox = document.getElementById("moveDeletedCheckbox");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderInlineMarkdown(value) {
  let text = value;
  const codeParts = [];
  text = text.replace(/`([^`\n]+)`/g, (_, code) => {
    const token = `@@CODE_${codeParts.length}@@`;
    codeParts.push(`<code>${code}</code>`);
    return token;
  });
  text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  codeParts.forEach((html, index) => {
    text = text.replace(`@@CODE_${index}@@`, html);
  });
  return text;
}

function renderMarkdown(raw) {
  if (!raw) return "";
  const codeBlocks = [];
  let text = String(raw).replace(/\r\n/g, "\n");
  text = text.replace(/```([\w+-]*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const token = `\n@@BLOCK_${codeBlocks.length}@@\n`;
    codeBlocks.push(`<pre><code>${escapeHtml(code.trimEnd())}</code></pre>`);
    return token;
  });
  text = escapeHtml(text);

  const lines = text.split("\n");
  const html = [];
  let paragraph = [];
  let listType = null;
  let tableBuffer = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    html.push(`<p>${renderInlineMarkdown(paragraph.join("<br>"))}</p>`);
    paragraph = [];
  };
  const flushList = () => {
    if (!listType) return;
    html.push(`</${listType}>`);
    listType = null;
  };
  const isTableSeparator = (line) => /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
  const splitTableRow = (line) => {
    const cells = [];
    let current = "";
    let escaped = false;
    let source = line.trim();
    if (source.startsWith("|")) source = source.slice(1);
    if (source.endsWith("|") && !source.endsWith("\\|")) source = source.slice(0, -1);
    for (const char of source) {
      if (escaped) {
        current += char;
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === "|") {
        cells.push(current);
        current = "";
      } else {
        current += char;
      }
    }
    cells.push(current);
    return cells.map((cell) => renderInlineMarkdown(cell.trim()));
  };
  const flushTable = () => {
    if (!tableBuffer.length) return;
    if (tableBuffer.length < 2 || !isTableSeparator(tableBuffer[1])) {
      for (const row of tableBuffer) paragraph.push(row);
      tableBuffer = [];
      return;
    }
    const headers = splitTableRow(tableBuffer[0]);
    const bodyRows = tableBuffer.slice(2).map(splitTableRow);
    html.push('<div class="table-wrap"><table><thead><tr>');
    html.push(headers.map((cell) => `<th>${cell}</th>`).join(""));
    html.push("</tr></thead><tbody>");
    for (const row of bodyRows) {
      html.push("<tr>");
      html.push(row.map((cell) => `<td>${cell}</td>`).join(""));
      html.push("</tr>");
    }
    html.push("</tbody></table></div>");
    tableBuffer = [];
  };

  for (const line of lines) {
    if (line.startsWith("@@BLOCK_")) {
      flushParagraph();
      flushList();
      flushTable();
      const index = Number(line.match(/@@BLOCK_(\d+)@@/)?.[1]);
      html.push(codeBlocks[index] || "");
      continue;
    }

    if (line.includes("|") && line.trim().split("|").length >= 3) {
      flushParagraph();
      flushList();
      tableBuffer.push(line);
      continue;
    }
    if (tableBuffer.length) flushTable();

    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const quote = line.match(/^&gt;\s?(.*)$/);
    if (quote) {
      flushParagraph();
      flushList();
      html.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
      continue;
    }

    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    if (unordered) {
      flushParagraph();
      if (listType !== "ul") {
        flushList();
        html.push("<ul>");
        listType = "ul";
      }
      html.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`);
      continue;
    }

    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (ordered) {
      flushParagraph();
      if (listType !== "ol") {
        flushList();
        html.push("<ol>");
        listType = "ol";
      }
      html.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`);
      continue;
    }

    paragraph.push(line);
  }
  flushTable();
  flushParagraph();
  flushList();
  return html.join("\n");
}

function typesetMath(container) {
  if (!window.MathJax) return;
  const run = () => {
    if (window.MathJax.typesetPromise) {
      window.MathJax.typesetPromise([container]).catch(() => {});
    }
  };
  if (window.MathJax.startup && window.MathJax.startup.promise) {
    window.MathJax.startup.promise.then(run).catch(() => {});
  } else {
    setTimeout(run, 300);
  }
}

function fmtDate(value) {
  if (!value) return "";
  return String(value).slice(0, 10);
}

function countByCategory() {
  const counts = {"全部会话": state.conversations.length};
  for (const item of state.conversations) {
    counts[item.category || SYSTEM_PENDING] = (counts[item.category || SYSTEM_PENDING] || 0) + 1;
  }
  counts[SYSTEM_PENDING] = state.conversations.filter((c) => c.status !== "classified").length;
  return counts;
}

function renderStats() {
  const stats = state.stats;
  statsEl.innerHTML = [
    ["会话", stats.conversation_count],
    ["消息", stats.message_count],
    ["已分类", stats.classified_count],
    [SYSTEM_PENDING, stats.pending_count],
  ]
    .map(
      ([label, value]) => `
        <div class="stat">
          <div class="stat-label">${label}</div>
          <div class="stat-value">${value}</div>
        </div>
      `
    )
    .join("");
}

function renderCategories() {
  const counts = countByCategory();
  const categories = [
    {name: "全部会话", id: "all"},
    ...state.categories,
    {name: SYSTEM_PENDING, id: "pending"},
  ];
  categoryList.innerHTML = categories
    .map((category) => {
      const name = category.name;
      const active = name === activeCategory ? "active" : "";
      return `
        <button class="category-button ${active}" data-category="${escapeHtml(name)}">
          <span>${escapeHtml(name)}</span>
          <span class="category-count">${counts[name] || 0}</span>
        </button>
      `;
    })
    .join("");

  categoryList.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      activeCategory = button.dataset.category;
      render();
    });
  });
}

function getFilteredConversations() {
  const query = searchInput.value.trim().toLowerCase();
  return state.conversations.filter((conv) => {
    const categoryOk =
      activeCategory === "全部会话" ||
      (activeCategory === SYSTEM_PENDING && conv.status !== "classified") ||
      conv.category === activeCategory;
    if (!categoryOk) return false;
    if (!query) return true;
    const text = [
      conv.title,
      conv.category,
      conv.summary,
      ...(conv.keywords || []),
    ]
      .join(" ")
      .toLowerCase();
    return text.includes(query);
  });
}

function renderConversationList() {
  const rows = getFilteredConversations();
  activeLabel.textContent = activeCategory;
  resultCount.textContent = `${rows.length} 条`;
  if (!rows.length) {
    conversationList.innerHTML = `<div class="empty-state">没有匹配的会话</div>`;
    return;
  }
  conversationList.innerHTML = rows
    .map((conv) => {
      const active = conv.conversation_id === activeConversationId ? "active" : "";
      const keywords = (conv.keywords || []).slice(0, 4).join(" / ");
      return `
        <button class="conversation-item ${active}" data-id="${escapeHtml(conv.conversation_id)}">
          <div class="conversation-title">${escapeHtml(conv.title)}</div>
          <div class="conversation-meta">
            <span>${escapeHtml(fmtDate(conv.created_at))}</span>
            <span>${escapeHtml(conv.category || SYSTEM_PENDING)}</span>
            <span>${conv.message_count || 0} 条消息</span>
            ${keywords ? `<span>${escapeHtml(keywords)}</span>` : ""}
          </div>
          <div class="conversation-summary">${escapeHtml(conv.summary || "暂无摘要")}</div>
        </button>
      `;
    })
    .join("");
  conversationList.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => loadConversation(button.dataset.id));
  });
}

function renderDetail(conv) {
  const keywords = (conv.keywords || [])
    .map((keyword) => `<span class="badge">${escapeHtml(keyword)}</span>`)
    .join("");
  const messages = (conv.messages || [])
    .map((msg) => {
      const role = msg.role === "user" ? "用户" : msg.role === "assistant" ? "助手" : msg.role;
      return `
        <div class="message ${escapeHtml(msg.role)}">
          <div class="message-role">${escapeHtml(role)} ${msg.time ? "· " + escapeHtml(msg.time) : ""}</div>
          <div class="message-text rendered">${renderMarkdown(msg.text)}</div>
        </div>
      `;
    })
    .join("");
  detailPane.innerHTML = `
    <div class="detail-header">
      <div class="detail-title">${escapeHtml(conv.title || "未命名会话")}</div>
      <div class="detail-meta">
        <span class="badge">${escapeHtml(conv.category || SYSTEM_PENDING)}</span>
        <span class="badge">${escapeHtml(fmtDate(conv.created_at))}</span>
        <span class="badge">${conv.message_count || 0} 条消息</span>
        <span class="badge">${escapeHtml(conv.status || "pending")}</span>
      </div>
    </div>
    <div class="detail-body">
      <div class="section-title">摘要</div>
      <div class="summary-text rendered">${renderMarkdown(conv.summary || "暂无摘要")}</div>
      <div class="section-title">关键词</div>
      <div class="keywords">${keywords || '<span class="badge">暂无</span>'}</div>
      <div class="section-title">原始问答</div>
      ${messages || '<div class="empty-state">没有可见消息</div>'}
    </div>
  `;
  typesetMath(detailPane);
}

function slugify(value, fallback) {
  const text = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return text || fallback;
}

function uniqueId(base, rows, currentIndex) {
  let candidate = base;
  let suffix = 2;
  const used = new Set(rows.map((row, index) => (index === currentIndex ? "" : row.id)));
  while (used.has(candidate)) {
    candidate = `${base}-${suffix}`;
    suffix += 1;
  }
  return candidate;
}

function openCategoryModal() {
  if (!categoryModal) return;
  if (state.mode === "static") {
    alert("静态 HTML 版不能保存分类。请打开服务版后再管理分类。");
    return;
  }
  categoryOriginal = (state.categories || []).map((item) => ({...item}));
  categoryDraft = categoryOriginal.map((item) => ({...item}));
  moveDeletedCheckbox.checked = false;
  categoryMessage.textContent = "";
  renderCategoryEditor();
  categoryModal.hidden = false;
}

function closeCategoryModal() {
  if (categoryModal) categoryModal.hidden = true;
}

function renderCategoryEditor() {
  categoryRows.innerHTML = categoryDraft
    .map((category, index) => `
      <div class="category-editor-row" data-index="${index}">
        <input type="text" value="${escapeHtml(category.name)}" aria-label="分类名称" />
        <div class="category-editor-actions">
          <button class="icon-button" data-action="up" title="上移">↑</button>
          <button class="icon-button" data-action="down" title="下移">↓</button>
          <button class="icon-button danger" data-action="delete" title="删除">×</button>
        </div>
      </div>
    `)
    .join("");
  if (!categoryDraft.length) {
    categoryRows.innerHTML = `<div class="empty-state compact">还没有分类</div>`;
  }
}

function syncDraftFromInputs() {
  categoryRows.querySelectorAll(".category-editor-row").forEach((row) => {
    const index = Number(row.dataset.index);
    const input = row.querySelector("input");
    if (categoryDraft[index]) {
      categoryDraft[index].name = input.value.trim();
    }
  });
}

function addCategory() {
  syncDraftFromInputs();
  const number = categoryDraft.length + 1;
  const id = uniqueId(`category-${number}`, categoryDraft, -1);
  categoryDraft.push({id, name: `Category ${number}`});
  renderCategoryEditor();
}

function moveCategory(index, offset) {
  syncDraftFromInputs();
  const next = index + offset;
  if (next < 0 || next >= categoryDraft.length) return;
  const [item] = categoryDraft.splice(index, 1);
  categoryDraft.splice(next, 0, item);
  renderCategoryEditor();
}

function deleteCategory(index) {
  syncDraftFromInputs();
  categoryDraft.splice(index, 1);
  renderCategoryEditor();
}

function buildCategoryPayload() {
  syncDraftFromInputs();
  const names = new Set();
  const categories = categoryDraft.map((row, index) => {
    const name = row.name.trim();
    if (!name) throw new Error("分类名称不能为空。");
    if (name === SYSTEM_PENDING) throw new Error(`${SYSTEM_PENDING} 是系统分类，不能手动创建。`);
    if (names.has(name)) throw new Error(`分类名称重复：${name}`);
    names.add(name);
    const id = uniqueId(row.id || slugify(name, `category-${index + 1}`), categoryDraft, index);
    return {id, name};
  });
  const originalById = new Map(categoryOriginal.map((row) => [row.id, row.name]));
  const renames = categories
    .map((row) => ({from: originalById.get(row.id), to: row.name}))
    .filter((row) => row.from && row.from !== row.to);
  return {
    categories,
    renames,
    delete_action: moveDeletedCheckbox.checked ? "move_to_pending" : "reject",
  };
}

async function saveCategories() {
  categoryMessage.textContent = "";
  let payload;
  try {
    payload = buildCategoryPayload();
  } catch (error) {
    categoryMessage.textContent = error.message;
    return;
  }
  const res = await fetch("/api/categories", {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const result = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 409 && result.in_use) {
      categoryMessage.textContent = `这些分类仍有会话：${result.in_use.join("、")}。勾选下方选项后可移动到待处理。`;
    } else {
      categoryMessage.textContent = result.error || result.message || "保存失败";
    }
    return;
  }
  state = result.state;
  const allowed = new Set(["全部会话", SYSTEM_PENDING, ...state.categories.map((item) => item.name)]);
  if (!allowed.has(activeCategory)) activeCategory = "全部会话";
  closeCategoryModal();
  render();
}

async function loadConversation(id) {
  activeConversationId = id;
  renderConversationList();
  detailPane.innerHTML = `<div class="loading">加载中</div>`;
  const res = await fetch(`/api/conversation?id=${encodeURIComponent(id)}`);
  if (!res.ok) {
    detailPane.innerHTML = `<div class="error">读取会话失败</div>`;
    return;
  }
  renderDetail(await res.json());
}

function render() {
  renderStats();
  renderCategories();
  renderConversationList();
}

async function loadState() {
  detailPane.innerHTML = `<div class="loading">加载中</div>`;
  const res = await fetch("/api/state");
  if (!res.ok) {
    detailPane.innerHTML = `<div class="error">读取总库失败</div>`;
    return;
  }
  state = await res.json();
  rootPath.textContent = state.root;
  render();
  detailPane.innerHTML = `<div class="empty-state">选择一个会话查看原始问答</div>`;
}

searchInput.addEventListener("input", renderConversationList);
document.getElementById("refreshButton").addEventListener("click", loadState);
document.getElementById("exportButton").addEventListener("click", () => {
  window.location.href = "/api/export";
});
if (categoryButton) categoryButton.addEventListener("click", openCategoryModal);
document.getElementById("closeCategoryModal")?.addEventListener("click", closeCategoryModal);
document.getElementById("cancelCategoryButton")?.addEventListener("click", closeCategoryModal);
document.getElementById("addCategoryButton")?.addEventListener("click", addCategory);
document.getElementById("saveCategoriesButton")?.addEventListener("click", saveCategories);
categoryRows?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const row = button.closest(".category-editor-row");
  const index = Number(row.dataset.index);
  const action = button.dataset.action;
  if (action === "up") moveCategory(index, -1);
  if (action === "down") moveCategory(index, 1);
  if (action === "delete") deleteCategory(index);
});

loadState();
