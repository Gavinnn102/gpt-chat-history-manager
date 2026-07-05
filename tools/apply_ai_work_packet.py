from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_keywords(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
    return []


def main():
    parser = argparse.ArgumentParser(description="Apply compact AI decisions to a full pending GPT history import.")
    parser.add_argument("pending_import", help="Path to data/pending_import_*.json")
    parser.add_argument("ai_work_packet", help="Filled AI packet JSON")
    parser.add_argument("--output", help="Output classified_import JSON path")
    args = parser.parse_args()

    pending_path = Path(args.pending_import).resolve()
    packet_path = Path(args.ai_work_packet).resolve()
    pending = read_json(pending_path, {})
    packet = read_json(packet_path, {})
    rows = pending.get("conversations") or []
    decisions = packet.get("decisions") or packet.get("classifications") or []
    by_id = {item.get("conversation_id"): item for item in decisions if item.get("conversation_id")}

    if not rows:
        raise SystemExit("Pending import has no conversations.")
    if not by_id:
        raise SystemExit("AI packet has no decisions.")

    classified = []
    classified_count = 0
    pending_count = 0
    missing_count = 0
    for row in rows:
        conv_id = row.get("conversation_id")
        decision = by_id.get(conv_id, {})
        category = (decision.get("category") or row.get("category") or "待处理").strip()
        summary = (decision.get("summary") or row.get("summary") or "").strip()
        keywords = normalize_keywords(decision.get("keywords") or row.get("keywords") or [])
        row = dict(row)
        row["category"] = category
        row["summary"] = summary
        row["keywords"] = keywords
        row["status"] = "classified" if category and category != "待处理" and summary else "pending"
        if row["status"] == "classified":
            classified_count += 1
        else:
            pending_count += 1
        if conv_id not in by_id:
            missing_count += 1
        classified.append(row)

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.output).resolve() if args.output else pending_path.parent / f"classified_import_{now}.json"
    output = {
        "schema_version": pending.get("schema_version", 1),
        "id": pending.get("id") or pending_path.stem,
        "created_at": pending.get("created_at") or "",
        "classified_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": pending.get("source") or "",
        "source_pending": str(pending_path),
        "source_packet": str(packet_path),
        "new_count": pending.get("new_count", 0),
        "updated_count": pending.get("updated_count", 0),
        "skipped_count": pending.get("skipped_count", 0),
        "conversations": classified,
    }
    write_json(out_path, output)
    print(f"Classified import: {out_path}")
    print(f"Classified rows: {classified_count}")
    print(f"Pending rows: {pending_count}")
    print(f"Missing decisions: {missing_count}")


if __name__ == "__main__":
    main()
