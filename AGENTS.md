# Codex Instructions for GPT Chat History Manager

This repository is a local ChatGPT `chat.html` archive manager. When helping a user import or classify history, keep the workflow low-token and privacy-first.

## Data Rules

- Do not read full ChatGPT export zip files or full `chat.html` files unless a user explicitly asks for targeted debugging.
- Do not manually expand the whole zip for import; use `prepare`, which extracts only `chat.html`.
- Do not read full `data/library.json`.
- Do not read full `data/pending_import_*.json`.
- Read only generated Markdown packets in `data/ai_work_packets/*.md`.
- Inspect full messages only for a specific ambiguous `conversation_id` with `tools/inspect_conversation.py`.

## Standard Import Workflow

1. Initialize the archive if needed:

```powershell
python ".\tools\init_archive.py" --root "."
```

2. Prepare an import from a ChatGPT export zip or a standalone `chat.html`:

```powershell
python ".\tools\gpt_history_workflow.py" prepare "<path-to-export.zip-or-chat.html>" --archive-root "."
```

3. Read only the generated Markdown packet shown by the command.

4. Fill the matching JSON packet's `decisions` fields:

```json
{
  "category": "one category from data/categories.json",
  "summary": "One concise sentence.",
  "keywords": ["keyword1", "keyword2", "keyword3"]
}
```

5. Apply and merge:

```powershell
python ".\tools\gpt_history_workflow.py" apply "<pending_import.json>" "<ai_work_packet.json>" --merge --archive-root "."
```

## Classification Rules

- Use categories from `data/categories.json`.
- `待处理` is a system fallback category; use it only when the compact packet is insufficient and targeted inspection still cannot decide.
- Classify by the user's main intent, especially title and user messages.
- Use assistant snippets only to disambiguate broad or unclear user prompts.
- Keep summaries to one sentence.
- Keep keywords to 3-8 useful terms.
- For attachment/image conversations, classify by the user's question, not by the attachment type alone.

## Privacy

Never commit or package private archive data:

- `data/`
- `inbox/`
- `backups/`
- `exports/`
- `reports/`
- `logs/`
- generated static HTML snapshots
- `pending_import_*`, `classified_import_*`, and `ai_work_packets`
