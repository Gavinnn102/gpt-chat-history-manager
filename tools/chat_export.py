from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path


def clean_text(value: str, preserve_lines: bool = False) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\ue200.*?\ue201", "", value)
    if preserve_lines:
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        value = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in value.split("\n"))
        value = re.sub(r"\n{3,}", "\n\n", value).strip()
    else:
        value = re.sub(r"\s+", " ", value).strip()
    return value


def load_json_data(html_path: Path):
    text = html_path.read_text(encoding="utf-8-sig")
    match = re.search(r"var\s+jsonData\s*=\s*", text)
    if not match:
        raise ValueError("chat.html 中没有找到 jsonData")
    start = text.find("[", match.end())
    if start < 0:
        raise ValueError("chat.html 中没有找到 jsonData 数组")

    in_string = False
    escape = False
    depth = 0
    end = None
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise ValueError("chat.html 中没有找到 jsonData 结尾")
    return json.loads(text[start:end])


def timestamp_text(ts):
    if not ts:
        return ""
    return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")


def get_message_text(message):
    if not message:
        return ""
    content = message.get("content") or {}
    content_type = content.get("content_type")
    if content_type in {"thoughts", "reasoning_recap"}:
        return ""
    if "parts" in content and isinstance(content["parts"], list):
        parts = []
        for part in content["parts"]:
            if part is None:
                continue
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                if part.get("content_type") == "image_asset_pointer":
                    parts.append("[图片/附件]")
                elif part.get("text"):
                    parts.append(str(part.get("text")))
                elif part.get("name"):
                    parts.append(f"[附件: {part.get('name')}]")
                else:
                    parts.append("[附件]")
            else:
                parts.append(str(part))
        return clean_text("\n".join(parts), preserve_lines=True)
    if "text" in content:
        return clean_text(str(content["text"]), preserve_lines=True)
    return ""


def ordered_messages(conversation):
    mapping = conversation.get("mapping") or {}
    rows = []
    for node in mapping.values():
        message = node.get("message")
        if not message:
            continue
        role = ((message.get("author") or {}).get("role") or "").strip()
        if role not in {"user", "assistant", "system", "tool"}:
            continue
        text = get_message_text(message)
        if not text:
            continue
        create_time = message.get("create_time") or conversation.get("create_time") or 0
        rows.append(
            {
                "role": role,
                "time": timestamp_text(create_time),
                "text": text,
                "id": message.get("id") or node.get("id") or "",
                "sort_time": create_time,
            }
        )
    rows.sort(key=lambda item: (item["sort_time"] or 0, item["id"]))
    for row in rows:
        row.pop("sort_time", None)
    return rows


def parse_chat_html(html_path: Path):
    data = load_json_data(html_path)
    conversations = []
    for item in data:
        messages = ordered_messages(item)
        user_count = sum(1 for msg in messages if msg["role"] == "user")
        assistant_count = sum(1 for msg in messages if msg["role"] == "assistant")
        conversations.append(
            {
                "conversation_id": item.get("conversation_id") or item.get("id") or "",
                "title": clean_text(item.get("title") or "未命名会话"),
                "created_at": timestamp_text(item.get("create_time")),
                "updated_at": timestamp_text(item.get("update_time")),
                "message_count": len(messages),
                "user_message_count": user_count,
                "assistant_message_count": assistant_count,
                "messages": messages,
            }
        )
    conversations.sort(key=lambda item: item.get("created_at") or "")
    return conversations
