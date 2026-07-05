from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATEGORIES = ROOT / "examples" / "categories.example.json"
SYSTEM_PENDING = "待处理"


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def slugify(value: str, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip().lower()).strip("-")
    return text or fallback


def normalize_categories(payload: dict) -> dict:
    rows = payload.get("categories") or []
    categories = []
    used_ids = set()
    used_names = set()
    for index, row in enumerate(rows, start=1):
        name = str(row.get("name") or "").strip()
        if not name or name == SYSTEM_PENDING or name in used_names:
            continue
        category_id = slugify(str(row.get("id") or name), f"category-{index}")
        base_id = category_id
        suffix = 2
        while category_id in used_ids:
            category_id = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(category_id)
        used_names.add(name)
        categories.append({"id": category_id, "name": name})
    return {"categories": categories}


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a local ChatGPT history archive.")
    parser.add_argument(
        "--root",
        default=str(ROOT),
        help="Archive root directory. Defaults to this repository directory.",
    )
    parser.add_argument(
        "--categories",
        default=str(DEFAULT_CATEGORIES),
        help="Initial categories JSON. Defaults to examples/categories.example.json.",
    )
    args = parser.parse_args()

    archive_root = Path(args.root).resolve()
    categories_source = Path(args.categories).resolve()
    if not categories_source.exists():
        raise SystemExit(f"Categories file not found: {categories_source}")

    for relative in [
        "data",
        "inbox",
        "backups",
        "backups/incremental",
        "backups/latest_raw",
        "exports",
        "reports",
        "logs",
    ]:
        (archive_root / relative).mkdir(parents=True, exist_ok=True)

    categories_path = archive_root / "data" / "categories.json"
    if not categories_path.exists():
        categories = normalize_categories(read_json(categories_source, {"categories": []}))
        write_json(categories_path, categories)

    library_path = archive_root / "data" / "library.json"
    if not library_path.exists():
        write_json(
            library_path,
            {
                "schema_version": 1,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "conversations": [],
            },
        )

    import_log_path = archive_root / "data" / "import_log.json"
    if not import_log_path.exists():
        write_json(import_log_path, {"imports": []})

    print(f"Archive root: {archive_root}")
    print(f"Categories: {categories_path}")
    print(f"Library: {library_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
