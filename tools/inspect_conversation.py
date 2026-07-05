from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def compact(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "..."


def find_conversations(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("conversations"), list):
            return payload["conversations"]
        if isinstance(payload.get("decisions"), list):
            return payload["decisions"]
    return []


def main():
    parser = argparse.ArgumentParser(description="Print one conversation from a GPT history JSON by id.")
    parser.add_argument("json_file", help="library.json, pending_import_*.json, classified_import_*.json, or ai_work_packet_*.json")
    parser.add_argument("conversation_id", help="Conversation id to inspect")
    parser.add_argument("--max-message-chars", type=int, default=1600, help="Maximum characters per message")
    parser.add_argument("--role", choices=["user", "assistant", "system", "tool"], help="Only print one role")
    args = parser.parse_args()

    path = Path(args.json_file).resolve()
    payload = read_json(path)
    rows = find_conversations(payload)
    target = next((row for row in rows if row.get("conversation_id") == args.conversation_id), None)
    if target is None:
        raise SystemExit(f"没有找到 conversation_id：{args.conversation_id}")

    print(f"文件：{path}")
    print(f"ID：{target.get('conversation_id')}")
    print(f"标题：{target.get('title')}")
    print(f"分类：{target.get('category') or ''}")
    print(f"创建：{target.get('created_at') or ''}")
    print(f"更新：{target.get('updated_at') or ''}")
    print(f"消息数：{target.get('message_count') or len(target.get('messages') or [])}")
    if target.get("summary"):
        print(f"摘要：{target.get('summary')}")
    if target.get("keywords"):
        print(f"关键词：{', '.join(target.get('keywords') or [])}")
    print("")

    messages = target.get("messages")
    if not messages:
        for key in ("first_user_messages", "last_user_message", "assistant_hint"):
            value = target.get(key)
            if not value:
                continue
            print(f"{key}:")
            if isinstance(value, list):
                for item in value:
                    print(compact(str(item), args.max_message_chars))
            else:
                print(compact(str(value), args.max_message_chars))
            print("")
        return

    for index, msg in enumerate(messages, start=1):
        role = msg.get("role") or ""
        if args.role and role != args.role:
            continue
        print(f"--- {index}. {role} {msg.get('time') or ''}".rstrip())
        print(compact(msg.get("text") or "", args.max_message_chars))
        print("")


if __name__ == "__main__":
    main()
