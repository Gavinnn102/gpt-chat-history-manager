from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from chat_export import parse_chat_html


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
BACKUP_DIR = ROOT / "backups" / "incremental"
LATEST_RAW_DIR = ROOT / "backups" / "latest_raw"


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def find_chat_html_in_zip(zf: zipfile.ZipFile) -> zipfile.ZipInfo | None:
    candidates = [
        info
        for info in zf.infolist()
        if not info.is_dir()
        and PurePosixPath(info.filename.replace("\\", "/")).name.lower() == "chat.html"
    ]
    candidates.sort(key=lambda item: (item.filename.replace("\\", "/").count("/"), item.filename))
    return candidates[0] if candidates else None


def extract_chat_html_from_zip(zip_path: Path) -> tuple[Path, str]:
    LATEST_RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = LATEST_RAW_DIR / "latest_chat.html"
    try:
        with zipfile.ZipFile(zip_path) as zf:
            member = find_chat_html_in_zip(zf)
            if member is None:
                raise SystemExit(f"ZIP 中没有找到 chat.html：{zip_path}")
            with zf.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            return target, member.filename
    except zipfile.BadZipFile as exc:
        raise SystemExit(f"不是有效的 ZIP 文件：{zip_path}") from exc


def resolve_source(source_path: Path) -> tuple[Path, str, str, str]:
    if not source_path.exists():
        raise SystemExit(f"输入文件不存在：{source_path}")
    if source_path.suffix.lower() == ".zip":
        html_path, member_name = extract_chat_html_from_zip(source_path)
        return html_path, str(source_path), "zip", member_name
    return source_path, str(source_path), "chat_html", ""


def main():
    parser = argparse.ArgumentParser(description="解析 ChatGPT 导出的 zip 或 chat.html，生成待分类增量。")
    parser.add_argument("source", help="ChatGPT 导出的 zip 或 chat.html")
    args = parser.parse_args()

    source_path = Path(args.source).resolve()
    html_path, source_label, source_type, source_member = resolve_source(source_path)
    conversations = parse_chat_html(html_path)
    library = read_json(DATA_DIR / "library.json", {"conversations": []})
    existing = {item.get("conversation_id"): item for item in library.get("conversations", [])}

    new_rows = []
    updated_rows = []
    skipped = 0
    for conv in conversations:
        conv_id = conv.get("conversation_id")
        old = existing.get(conv_id)
        if not old:
            new_rows.append(conv)
            continue
        if (conv.get("updated_at") or "") > (old.get("updated_at") or ""):
            updated_rows.append(conv)
        else:
            skipped += 1

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    pending = {
        "id": f"pending_{now}",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source_label,
        "source_type": source_type,
        "source_chat_html": str(html_path),
        "source_member": source_member,
        "new_count": len(new_rows),
        "updated_count": len(updated_rows),
        "skipped_count": skipped,
        "conversations": [
            {
                **conv,
                "category": "待处理",
                "status": "pending",
                "summary": "",
                "keywords": [],
                "source_exports": [f"pending_{now}"],
            }
            for conv in [*new_rows, *updated_rows]
        ],
    }

    pending_path = DATA_DIR / f"pending_import_{now}.json"
    write_json(pending_path, pending)

    backup_path = BACKUP_DIR / f"incremental_{now}.json"
    write_json(backup_path, pending)

    LATEST_RAW_DIR.mkdir(parents=True, exist_ok=True)
    latest_chat_html = LATEST_RAW_DIR / "latest_chat.html"
    if html_path.resolve() != latest_chat_html.resolve():
        shutil.copy2(html_path, latest_chat_html)

    if source_type == "zip":
        print(f"输入 ZIP：{source_path}")
        print(f"ZIP 内 chat.html：{source_member}")
        print(f"已解出 chat.html：{html_path}")
    print(f"新增：{len(new_rows)}")
    print(f"更新：{len(updated_rows)}")
    print(f"跳过：{skipped}")
    print(f"待分类文件：{pending_path}")
    print(f"增量备份：{backup_path}")


if __name__ == "__main__":
    main()
