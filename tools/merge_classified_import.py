from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="合并已经由 Codex 分类好的导入文件。")
    parser.add_argument("classified_import", help="已分类的 pending_import JSON")
    args = parser.parse_args()

    import_path = Path(args.classified_import).resolve()
    payload = read_json(import_path, {})
    rows = payload.get("conversations", [])
    if not rows:
        raise SystemExit("导入文件里没有 conversations")

    library = read_json(DATA_DIR / "library.json", {"schema_version": 1, "conversations": []})
    by_id = {item.get("conversation_id"): item for item in library.get("conversations", [])}

    new_count = 0
    updated_count = 0
    for row in rows:
        conv_id = row.get("conversation_id")
        if not conv_id:
            continue
        if not row.get("category") or row.get("category") == "待处理":
            row["status"] = "pending"
        else:
            row["status"] = "classified"
        if conv_id in by_id:
            by_id[conv_id].update(row)
            updated_count += 1
        else:
            by_id[conv_id] = row
            new_count += 1

    conversations = list(by_id.values())
    conversations.sort(key=lambda item: item.get("created_at") or "")
    library["conversations"] = conversations
    library["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_json(DATA_DIR / "library.json", library)

    import_log = read_json(DATA_DIR / "import_log.json", {"imports": []})
    import_log.setdefault("imports", []).append(
        {
            "id": payload.get("id") or import_path.stem,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": payload.get("source") or str(import_path),
            "new_count": new_count,
            "updated_count": updated_count,
            "skipped_count": payload.get("skipped_count", 0),
            "note": "合并已分类导入",
        }
    )
    write_json(DATA_DIR / "import_log.json", import_log)
    print(f"新增：{new_count}")
    print(f"更新：{updated_count}")


if __name__ == "__main__":
    main()
