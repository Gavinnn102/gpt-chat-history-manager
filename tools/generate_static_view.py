from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def html_script_json(data) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return (
        text.replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build_state(root: Path):
    data_dir = root / "data"
    library = read_json(
        data_dir / "library.json",
        {"schema_version": 1, "updated_at": None, "conversations": []},
    )
    conversations = library.get("conversations", [])
    categories = read_json(data_dir / "categories.json", {"categories": []}).get("categories", [])
    imports = read_json(data_dir / "import_log.json", {"imports": []}).get("imports", [])
    return {
        "root": str(root),
        "mode": "static",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stats": {
            "conversation_count": len(conversations),
            "message_count": sum(c.get("message_count", 0) for c in conversations),
            "classified_count": sum(1 for c in conversations if c.get("status") == "classified"),
            "pending_count": sum(1 for c in conversations if c.get("status") != "classified"),
            "updated_at": library.get("updated_at"),
        },
        "categories": categories,
        "imports": imports[-20:],
        "conversations": conversations,
    }


def make_static_js(app_js: str) -> str:
    app_js = app_js.replace(
        'async function loadConversation(id) {\n'
        '  activeConversationId = id;\n'
        '  renderConversationList();\n'
        '  detailPane.innerHTML = `<div class="loading">加载中</div>`;\n'
        '  const res = await fetch(`/api/conversation?id=${encodeURIComponent(id)}`);\n'
        '  if (!res.ok) {\n'
        '    detailPane.innerHTML = `<div class="error">读取会话失败</div>`;\n'
        '    return;\n'
        '  }\n'
        '  renderDetail(await res.json());\n'
        '}\n',
        'async function loadConversation(id) {\n'
        '  activeConversationId = id;\n'
        '  renderConversationList();\n'
        '  const conv = state.conversations.find((item) => item.conversation_id === id);\n'
        '  if (!conv) {\n'
        '    detailPane.innerHTML = `<div class="error">读取会话失败</div>`;\n'
        '    return;\n'
        '  }\n'
        '  renderDetail(conv);\n'
        '}\n',
    )
    app_js = app_js.replace(
        'async function loadState() {\n'
        '  detailPane.innerHTML = `<div class="loading">加载中</div>`;\n'
        '  const res = await fetch("/api/state");\n'
        '  if (!res.ok) {\n'
        '    detailPane.innerHTML = `<div class="error">读取总库失败</div>`;\n'
        '    return;\n'
        '  }\n'
        '  state = await res.json();\n'
        '  rootPath.textContent = state.root;\n'
        '  render();\n'
        '  detailPane.innerHTML = `<div class="empty-state">选择一个会话查看原始问答</div>`;\n'
        '}\n',
        'async function loadState() {\n'
        '  state = window.__CHAT_HISTORY_DATA__;\n'
        '  rootPath.textContent = `${state.root} · 静态版 ${state.generated_at}`;\n'
        '  render();\n'
        '  detailPane.innerHTML = `<div class="empty-state">选择一个会话查看原始问答</div>`;\n'
        '}\n',
    )
    app_js = app_js.replace(
        'document.getElementById("refreshButton").addEventListener("click", loadState);\n'
        'document.getElementById("exportButton").addEventListener("click", () => {\n'
        '  window.location.href = "/api/export";\n'
        '});\n',
        'document.getElementById("refreshButton").addEventListener("click", () => window.location.reload());\n'
        'document.getElementById("exportButton").textContent = "服务版导出";\n'
        'document.getElementById("exportButton").addEventListener("click", () => {\n'
        '  alert("静态 HTML 版不启动后台服务，因此不直接导出 zip。需要导出时，请打开桌面的服务版入口。");\n'
        '});\n',
    )
    return app_js


def make_html(root: Path, state: dict) -> str:
    static_dir = root / "app" / "static"
    styles = (static_dir / "styles.css").read_text(encoding="utf-8-sig")
    app_js = make_static_js((static_dir / "app.js").read_text(encoding="utf-8-sig"))
    data_json = html_script_json(state)
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>GPT 聊天记录资料库</title>
    <style>
{styles}
    </style>
    <script>
      window.MathJax = {{
        tex: {{
          inlineMath: [["\\\\(", "\\\\)"]],
          displayMath: [["\\\\[", "\\\\]"], ["$$", "$$"]],
          processEscapes: true
        }},
        options: {{
          skipHtmlTags: ["script", "noscript", "style", "textarea", "pre", "code"]
        }}
      }};
    </script>
    <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
  </head>
  <body>
    <div class="app-shell">
      <aside class="sidebar">
        <div class="brand">
          <div class="brand-title">GPT 聊天记录资料库</div>
          <div class="brand-subtitle" id="rootPath"></div>
        </div>
        <nav id="categoryList" class="category-list"></nav>
      </aside>

      <main class="main">
        <header class="toolbar">
          <div class="search-wrap">
            <input id="searchInput" type="search" placeholder="搜索标题、摘要、关键词、原回答" />
          </div>
          <button id="categoryButton" class="button">分类管理</button>
          <button id="refreshButton" class="button">刷新</button>
          <button id="exportButton" class="button primary">服务版导出</button>
        </header>

        <section class="stats" id="stats"></section>

        <section class="content">
          <div class="list-pane">
            <div class="list-head">
              <span id="activeLabel">全部会话</span>
              <span id="resultCount"></span>
            </div>
            <div id="conversationList" class="conversation-list"></div>
          </div>

          <article class="detail-pane" id="detailPane">
            <div class="empty-state">选择一个会话查看原始问答</div>
          </article>
        </section>
      </main>
    </div>
    <div id="categoryModal" class="modal-backdrop" hidden>
      <section class="modal">
        <div class="modal-head">
          <div>
            <div class="modal-title">分类管理</div>
            <div class="modal-subtitle">分类保存在 data/categories.json，可直接编辑，也可在这里管理。</div>
          </div>
          <button id="closeCategoryModal" class="icon-button" title="关闭">×</button>
        </div>
        <div id="categoryRows" class="category-editor"></div>
        <div class="category-options">
          <label>
            <input id="moveDeletedCheckbox" type="checkbox" />
            删除仍有会话的分类时，把这些会话移动到待处理
          </label>
        </div>
        <div id="categoryMessage" class="modal-message"></div>
        <div class="modal-actions">
          <button id="addCategoryButton" class="button">新增分类</button>
          <span class="modal-spacer"></span>
          <button id="cancelCategoryButton" class="button">取消</button>
          <button id="saveCategoriesButton" class="button primary">保存</button>
        </div>
      </section>
    </div>
    <script>
      window.__CHAT_HISTORY_DATA__ = {data_json};
    </script>
    <script>
{app_js}
    </script>
  </body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Generate a standalone static HTML viewer for the GPT history library.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="GPT 聊天记录资料库目录")
    parser.add_argument("--output", help="Output HTML path")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    state = build_state(root)
    output = Path(args.output).resolve() if args.output else root / "GPT聊天记录资料库.html"
    output.write_text(make_html(root, state), encoding="utf-8")
    print(f"静态 HTML：{output}")
    print(f"会话：{state['stats']['conversation_count']}")
    print(f"消息：{state['stats']['message_count']}")


if __name__ == "__main__":
    main()
