from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def compact_text(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "..."


def unique_snippets(messages, role: str, limit: int, count: int):
    rows = []
    seen = set()
    for msg in messages:
        if msg.get("role") != role:
            continue
        text = compact_text(msg.get("text") or "", limit)
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
        if len(rows) >= count:
            break
    return rows


def keyword_candidates(text: str, max_items: int = 12):
    stop = {
        "这个", "一下", "为什么", "怎么", "什么", "详细", "解释", "帮我",
        "图片", "附件", "问题", "回答", "老师", "作业", "可以", "需要",
    }
    words = []
    for item in re.findall(r"[A-Za-z][A-Za-z0-9+#.]{1,}|[\u4e00-\u9fff]{2,}", text or ""):
        if item in stop or item in words:
            continue
        words.append(item)
        if len(words) >= max_items:
            break
    return words


def build_row(conv):
    messages = conv.get("messages") or []
    user_messages = [m for m in messages if m.get("role") == "user"]
    assistant_messages = [m for m in messages if m.get("role") == "assistant"]
    first_users = unique_snippets(messages, "user", 360, 2)
    last_user = ""
    for msg in reversed(user_messages):
        last_user = compact_text(msg.get("text") or "", 360)
        if last_user:
            break
    assistant_hint = ""
    for msg in assistant_messages:
        assistant_hint = compact_text(msg.get("text") or "", 260)
        if assistant_hint:
            break
    context_text = " ".join([conv.get("title") or "", *first_users, last_user, assistant_hint])
    return {
        "conversation_id": conv.get("conversation_id") or "",
        "title": conv.get("title") or "未命名会话",
        "created_at": conv.get("created_at") or "",
        "updated_at": conv.get("updated_at") or "",
        "message_count": conv.get("message_count", 0),
        "user_message_count": conv.get("user_message_count", 0),
        "assistant_message_count": conv.get("assistant_message_count", 0),
        "first_user_messages": first_users,
        "last_user_message": last_user if last_user not in first_users else "",
        "assistant_hint": assistant_hint,
        "keyword_candidates": keyword_candidates(context_text),
        "category": "",
        "summary": "",
        "keywords": [],
    }


def render_markdown(packet):
    lines = [
        "# GPT 历史导入工作包",
        "",
        f"- 工作包 ID: `{packet['packet_id']}`",
        f"- 待导入文件: `{packet['source_pending']}`",
        f"- 来源: `{packet.get('source') or ''}`",
        f"- 新增: {packet['counts']['new']}；更新: {packet['counts']['updated']}；跳过: {packet['counts']['skipped']}；需处理: {packet['counts']['included']}",
        "",
        "## 分类",
        "",
    ]
    for category in packet.get("categories", []):
        lines.append(f"- {category}")
    lines.extend(
        [
            "",
            "## 填写规则",
            "",
            "只需要在 JSON 工作包里为每条 `decisions` 填 `category`、`summary`、`keywords`。",
            "不要读取完整 pending JSON；只有分类不确定时，才按 conversation_id 定点查看完整消息。",
            "",
            "## 待分类会话",
            "",
        ]
    )
    for index, row in enumerate(packet.get("decisions", []), start=1):
        lines.extend(
            [
                f"### {index}. {row['title']}",
                "",
                f"- id: `{row['conversation_id']}`",
                f"- created: {row.get('created_at') or ''}",
                f"- updated: {row.get('updated_at') or ''}",
                f"- messages: {row.get('message_count', 0)}；user: {row.get('user_message_count', 0)}；assistant: {row.get('assistant_message_count', 0)}",
                f"- keyword candidates: {', '.join(row.get('keyword_candidates') or [])}",
                "",
            ]
        )
        for sample_index, text in enumerate(row.get("first_user_messages") or [], start=1):
            lines.extend([f"用户片段 {sample_index}：", "", f"> {text}", ""])
        if row.get("last_user_message"):
            lines.extend(["最后用户片段：", "", f"> {row['last_user_message']}", ""])
        if row.get("assistant_hint"):
            lines.extend(["助手提示片段：", "", f"> {row['assistant_hint']}", ""])
    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description="Create a compact AI work packet from a pending GPT history import.")
    parser.add_argument("pending_import", help="Path to data/pending_import_*.json")
    parser.add_argument("--out-dir", help="Output directory. Defaults to data/ai_work_packets beside the archive.")
    args = parser.parse_args()

    pending_path = Path(args.pending_import).resolve()
    payload = read_json(pending_path, {})
    rows = payload.get("conversations") or []
    if not rows:
        raise SystemExit("No conversations found in pending import.")

    root = pending_path.parents[1] if pending_path.parent.name == "data" else pending_path.parent
    categories_path = root / "data" / "categories.json"
    categories_payload = read_json(categories_path, {"categories": []})
    categories = [item.get("name") for item in categories_payload.get("categories", []) if item.get("name")]
    if "待处理" not in categories:
        categories.append("待处理")

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    packet_id = f"ai_work_packet_{now}"
    out_dir = Path(args.out_dir).resolve() if args.out_dir else root / "data" / "ai_work_packets"
    packet = {
        "schema_version": 1,
        "packet_id": packet_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_pending": str(pending_path),
        "source": payload.get("source") or "",
        "pending_import_id": payload.get("id") or pending_path.stem,
        "counts": {
            "new": payload.get("new_count", 0),
            "updated": payload.get("updated_count", 0),
            "skipped": payload.get("skipped_count", 0),
            "included": len(rows),
        },
        "categories": categories,
        "decisions": [build_row(conv) for conv in rows],
    }

    json_path = out_dir / f"{packet_id}.json"
    md_path = out_dir / f"{packet_id}.md"
    write_json(json_path, packet)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(packet), encoding="utf-8")
    print(f"AI work packet JSON: {json_path}")
    print(f"AI work packet Markdown: {md_path}")
    print(f"Rows: {len(rows)}")


if __name__ == "__main__":
    main()
