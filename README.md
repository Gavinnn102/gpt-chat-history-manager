# GPT Chat History Manager / GPT 聊天记录管理器

A local, privacy-first archive for ChatGPT export zip files or standalone `chat.html` files. It keeps your conversations on your own machine, supports searching and category browsing, and can generate a standalone static HTML viewer.

本工具用于在本地管理 ChatGPT 导出的 zip 或单独的 `chat.html`。数据保存在你自己的电脑上，支持搜索、分类浏览，并可生成一个可直接打开的静态 HTML 页面。

## Features / 功能

- Accept a ChatGPT export zip or standalone `chat.html`; zip import extracts only `chat.html`.
- Deduplicate conversations by `conversation_id`.
- Keep visible user and assistant messages while filtering reasoning/thought artifacts.
- Render Markdown, code blocks, LaTeX via MathJax, and Markdown tables.
- Manage categories in `data/categories.json` or in the service UI.
- Use a Codex-friendly low-token workflow: generate compact packets, let Codex fill category/summary/keywords, then merge.

- 可直接传入 ChatGPT 导出的 zip 或单独的 `chat.html`；zip 导入只解出 `chat.html`。
- 按 `conversation_id` 去重。
- 保留可见用户消息和助手回答，过滤 reasoning/thought 类中间内容。
- 支持 Markdown、代码块、MathJax LaTeX 和 Markdown 表格。
- 可通过 `data/categories.json` 或服务版页面自定义分类。
- 支持 Codex 友好的低 token 工作流：生成紧凑工作包，让 Codex 填写分类、摘要、关键词后合并。

## Quick Start / 快速开始

Requirements: Python 3.10+.

需要 Python 3.10 或更新版本。

```powershell
python ".\tools\init_archive.py" --root "."
```

Then start the local service UI:

然后启动本地服务界面：

```powershell
python ".\app\server.py"
```

On Windows, you can double-click:

Windows 下也可以双击：

```text
start.bat
```

`start_service.bat` is kept as a compatibility alias and does the same thing as `start.bat`.

`start_service.bat` 仅作为兼容别名保留，效果和 `start.bat` 相同。

## Custom Categories / 自定义分类

The private category file is:

分类配置文件是：

```text
data/categories.json
```

Format:

格式：

```json
{
  "categories": [
    {"id": "work", "name": "Work"},
    {"id": "learning", "name": "Learning"},
    {"id": "projects", "name": "Projects"},
    {"id": "writing", "name": "Writing"},
    {"id": "other", "name": "Other"}
  ]
}
```

`待处理` is a built-in virtual category. Do not add it to `data/categories.json`.

`待处理` 是系统内置虚拟分类，不要写入 `data/categories.json`。

You can also open the service UI and use the **分类管理** button to add, rename, reorder, or delete categories. Renaming a category updates existing conversations. Deleting a category that still has conversations is blocked unless you choose to move those conversations to `待处理`.

也可以在服务版页面点击 **分类管理**，新增、重命名、排序或删除分类。重命名会同步已有会话；删除仍有会话的分类时，默认会被阻止，除非选择把这些会话移动到 `待处理`。

## Codex Classification / 用 Codex 分类

Codex is not bundled with this project. Users need their own Codex/OpenAI access. If they have Codex, they can open this repository folder in Codex; the included `AGENTS.md` tells Codex how to classify without reading large private files.

Codex 不会随本项目一起打包。用户需要自己拥有 Codex/OpenAI 使用权限。只要用户可以使用 Codex，就可以把本仓库目录交给 Codex；仓库里的 `AGENTS.md` 已写好低 token 分类规则，避免读取完整私有文件。

Recommended prompt after running `prepare`:

运行 `prepare` 后，推荐对 Codex 说：

```text
Please read only the generated Markdown packet in data/ai_work_packets, fill the matching JSON packet with category, summary, and keywords using data/categories.json, then run the apply command with --merge.
```

If one conversation is unclear, Codex should inspect only that conversation:

如果某条会话分类不明确，Codex 只应定点查看那一条：

```powershell
python ".\tools\inspect_conversation.py" "<pending_import.json>" "<conversation_id>"
```

## Import Workflow / 导入流程

Put a ChatGPT export zip or standalone `chat.html` anywhere, then run:

把 ChatGPT 导出的 zip 或单独的 `chat.html` 放在任意位置，然后运行：

```powershell
python ".\tools\gpt_history_workflow.py" prepare "<path-to-export.zip-or-chat.html>" --archive-root "."
```

If the input is a zip file, `prepare` locates `chat.html` inside it and does not extract attachments or other files.

如果输入是 zip，`prepare` 只定位并解出里面的 `chat.html`，不会展开附件或其它文件。

Read only the generated Markdown work packet in:

只读取生成的 Markdown 工作包：

```text
data/ai_work_packets/
```

Fill the matching JSON packet with:

在对应 JSON 工作包里填写：

```json
{
  "category": "Work",
  "summary": "One sentence summary.",
  "keywords": ["keyword1", "keyword2", "keyword3"]
}
```

Apply and merge:

回写并合并：

```powershell
python ".\tools\gpt_history_workflow.py" apply "<pending_import.json>" "<ai_work_packet.json>" --merge --archive-root "."
```

`--merge` also refreshes the static HTML viewer when `tools/generate_static_view.py` is available.

使用 `--merge` 时，如果存在 `tools/generate_static_view.py`，会自动刷新静态 HTML。

## Optional Static Snapshot / 可选静态快照

The normal UI is the local service started by `start.bat`. The standalone static HTML is only an optional offline snapshot. It does not run a server, so it cannot export reports or save category changes.

正常使用请通过 `start.bat` 启动本地服务。独立静态 HTML 只是可选的离线快照；它不启动服务，因此不能导出报告，也不能保存分类修改。

Generate or refresh the snapshot when needed:

需要时可生成或刷新静态快照：

```powershell
python ".\tools\generate_static_view.py" --root "."
```

## Release Package / 发布包

Build a clean zip package:

生成干净的 zip 包：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\build_release.ps1"
```

The release script excludes private data directories, generated HTML snapshots, import artifacts, logs, shortcuts, caches, and local runtime files. It writes a relative-path manifest and runs a sensitive-term scan before creating the zip.

发布脚本会排除私有数据目录、生成的 HTML 快照、导入中间文件、日志、快捷方式、缓存和本地运行文件，并生成只含相对路径的 manifest，同时在打包前执行敏感词扫描。

## Privacy / 隐私

This repository should not contain your exported conversations or generated archive data. Keep these files private:

这个仓库不应包含你的导出聊天记录或生成后的资料库数据。以下文件应保持私有：

```text
data/
inbox/
backups/
exports/
reports/
logs/
GPT聊天记录资料库.html
```

## License / 许可证

MIT
