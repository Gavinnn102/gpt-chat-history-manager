from __future__ import annotations

import csv
import json
import mimetypes
import os
import re
import socket
import subprocess
import sys
import threading
import webbrowser
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


ROOT = Path(os.environ.get("CHAT_HISTORY_HOME", Path(__file__).resolve().parents[1])).resolve()
DATA_DIR = ROOT / "data"
STATIC_DIR = Path(__file__).resolve().parent / "static"
EXPORTS_DIR = ROOT / "exports"
REPORTS_DIR = ROOT / "reports"
SYSTEM_PENDING = "待处理"


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def default_library():
    return {"schema_version": 1, "updated_at": None, "conversations": []}


def load_library():
    return read_json(DATA_DIR / "library.json", default_library())


def save_library(library):
    library["updated_at"] = now_text()
    write_json(DATA_DIR / "library.json", library)


def load_categories():
    return read_json(DATA_DIR / "categories.json", {"categories": []}).get("categories", [])


def save_categories(categories):
    write_json(DATA_DIR / "categories.json", {"categories": categories})


def safe_filename(value: str):
    bad = '<>:"/\\|?*'
    for char in bad:
        value = value.replace(char, "_")
    return value.strip() or "untitled"


def slugify(value: str, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip().lower()).strip("-")
    return text or fallback


def normalize_categories(payload):
    rows = payload.get("categories") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("categories must be a list")

    categories = []
    used_ids = set()
    used_names = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError("each category must be an object")
        name = str(row.get("name") or "").strip()
        if not name:
            raise ValueError("category name cannot be empty")
        if name == SYSTEM_PENDING:
            raise ValueError(f"{SYSTEM_PENDING} is a system category")
        if name in used_names:
            raise ValueError(f"duplicate category name: {name}")
        category_id = slugify(str(row.get("id") or name), f"category-{index}")
        base_id = category_id
        suffix = 2
        while category_id in used_ids:
            category_id = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(category_id)
        used_names.add(name)
        categories.append({"id": category_id, "name": name})
    return categories


def light_conversation(conv):
    return {
        "conversation_id": conv.get("conversation_id"),
        "title": conv.get("title") or "未命名会话",
        "category": conv.get("category") or SYSTEM_PENDING,
        "status": conv.get("status") or "pending",
        "created_at": conv.get("created_at") or "",
        "updated_at": conv.get("updated_at") or "",
        "message_count": conv.get("message_count", 0),
        "user_message_count": conv.get("user_message_count", 0),
        "assistant_message_count": conv.get("assistant_message_count", 0),
        "summary": conv.get("summary") or "",
        "keywords": conv.get("keywords") or [],
        "source_exports": conv.get("source_exports") or [],
    }


def build_state():
    library = load_library()
    conversations = library.get("conversations", [])
    categories = load_categories()
    stats = {
        "conversation_count": len(conversations),
        "message_count": sum(c.get("message_count", 0) for c in conversations),
        "classified_count": sum(1 for c in conversations if c.get("status") == "classified"),
        "pending_count": sum(1 for c in conversations if c.get("status") != "classified"),
        "updated_at": library.get("updated_at"),
    }
    imports = read_json(DATA_DIR / "import_log.json", {"imports": []}).get("imports", [])
    return {
        "root": str(ROOT),
        "mode": "service",
        "stats": stats,
        "categories": categories,
        "imports": imports[-20:],
        "conversations": [light_conversation(c) for c in conversations],
    }


def find_conversation(conversation_id: str):
    for conv in load_library().get("conversations", []):
        if conv.get("conversation_id") == conversation_id:
            return conv
    return None


def apply_category_update(payload):
    categories = normalize_categories(payload)
    new_names = {item["name"] for item in categories}
    renames = {}
    rename_rows = payload.get("renames", []) if isinstance(payload, dict) else []
    for item in rename_rows:
        old_name = str(item.get("from") or "").strip()
        new_name = str(item.get("to") or "").strip()
        if old_name and new_name and old_name != new_name and new_name in new_names:
            renames[old_name] = new_name

    delete_action = payload.get("delete_action") if isinstance(payload, dict) else None
    library = load_library()
    conversations = library.get("conversations", [])
    library_changed = False

    for conv in conversations:
        category = conv.get("category") or SYSTEM_PENDING
        if category in renames:
            conv["category"] = renames[category]
            if conv.get("status") != "classified":
                conv["status"] = "classified"
            library_changed = True

    in_use_removed = sorted(
        {
            conv.get("category")
            for conv in conversations
            if conv.get("category")
            and conv.get("category") != SYSTEM_PENDING
            and conv.get("category") not in new_names
        }
    )
    if in_use_removed and delete_action != "move_to_pending":
        return {
            "ok": False,
            "status": 409,
            "payload": {
                "error": "categories in use",
                "message": "Some removed categories still have conversations.",
                "in_use": in_use_removed,
            },
        }

    if in_use_removed:
        for conv in conversations:
            if conv.get("category") in in_use_removed:
                conv["category"] = SYSTEM_PENDING
                conv["status"] = "pending"
                library_changed = True

    save_categories(categories)
    if library_changed:
        save_library(library)

    static_result = refresh_static_html()
    return {
        "ok": True,
        "status": 200,
        "payload": {
            "categories": categories,
            "state": build_state(),
            "static_refresh": static_result,
        },
    }


def refresh_static_html():
    script = ROOT / "tools" / "generate_static_view.py"
    if not script.exists():
        return {"ok": False, "reason": "generate_static_view.py not found"}
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--root", str(ROOT)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}
    return {"ok": result.returncode == 0, "output": (result.stdout or result.stderr or "").strip()}


def category_rows_for_reports(categories, conversations):
    rows = [{"id": item.get("id") or safe_filename(item["name"]), "name": item["name"]} for item in categories]
    known = {item["name"] for item in rows}
    for conv in conversations:
        name = conv.get("category") or SYSTEM_PENDING
        if name not in known:
            rows.append({"id": safe_filename(name), "name": name})
            known.add(name)
    return rows


def generate_reports():
    library = load_library()
    categories = load_categories()
    conversations = library.get("conversations", [])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = REPORTS_DIR / f"chat_history_reports_{timestamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    by_category = {}
    for category in category_rows_for_reports(categories, conversations):
        by_category[category["name"]] = []
    for conv in conversations:
        by_category.setdefault(conv.get("category") or SYSTEM_PENDING, []).append(conv)

    overview_lines = [
        "# Chat History Archive Overview",
        "",
        f"- Generated at: {now_text()}",
        f"- Conversations: {len(conversations)}",
        f"- Messages: {sum(c.get('message_count', 0) for c in conversations)}",
        "",
        "| Category | Conversations | Messages |",
        "|---|---:|---:|",
    ]
    for name, rows in by_category.items():
        overview_lines.append(
            f"| {name} | {len(rows)} | {sum(c.get('message_count', 0) for c in rows)} |"
        )
    (report_dir / "00_overview.md").write_text("\n".join(overview_lines), encoding="utf-8")

    index_path = report_dir / "conversation_index.csv"
    with index_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "conversation_id",
                "title",
                "category",
                "status",
                "created_at",
                "updated_at",
                "message_count",
                "summary",
                "keywords",
            ],
        )
        writer.writeheader()
        for conv in conversations:
            writer.writerow(
                {
                    "conversation_id": conv.get("conversation_id"),
                    "title": conv.get("title"),
                    "category": conv.get("category"),
                    "status": conv.get("status"),
                    "created_at": conv.get("created_at"),
                    "updated_at": conv.get("updated_at"),
                    "message_count": conv.get("message_count"),
                    "summary": conv.get("summary"),
                    "keywords": ", ".join(conv.get("keywords") or []),
                }
            )

    for category in category_rows_for_reports(categories, conversations):
        name = category["name"]
        rows = by_category.get(name, [])
        lines = [
            f"# {name}",
            "",
            f"Conversations: {len(rows)}",
            "",
            "| Date | Title | Messages | Summary |",
            "|---|---|---:|---|",
        ]
        for conv in rows:
            summary = (conv.get("summary") or "").replace("|", "\\|").replace("\n", " ")
            title = (conv.get("title") or "").replace("|", "\\|")
            lines.append(
                f"| {conv.get('created_at','')[:10]} | {title} | {conv.get('message_count', 0)} | {summary} |"
            )
        file_name = f"{category['id']}_{safe_filename(name)}.md"
        (report_dir / file_name).write_text("\n".join(lines), encoding="utf-8")

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = EXPORTS_DIR / f"chat_history_reports_{timestamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(report_dir.rglob("*")):
            zf.write(path, path.relative_to(report_dir.parent))
    return zip_path


class Handler(BaseHTTPRequestHandler):
    server_version = "ChatHistoryManager/1.0"

    def log_message(self, format, *args):
        return

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_file(self, path: Path, download_name: str | None = None):
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if download_name:
            encoded = quote(download_name)
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{encoded}")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/":
            self.send_file(STATIC_DIR / "index.html")
            return
        if path == "/api/state":
            self.send_json(build_state())
            return
        if path == "/api/categories":
            self.send_json({"categories": load_categories()})
            return
        if path == "/api/conversation":
            query = parse_qs(parsed.query)
            conv_id = (query.get("id") or [""])[0]
            conv = find_conversation(conv_id)
            if not conv:
                self.send_json({"error": "conversation not found"}, status=404)
                return
            self.send_json(conv)
            return
        if path == "/api/export":
            zip_path = generate_reports()
            self.send_file(zip_path, zip_path.name)
            return
        if path.startswith("/static/"):
            relative = path.removeprefix("/static/").replace("/", os.sep)
            target = (STATIC_DIR / relative).resolve()
            if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
                self.send_error(403)
                return
            self.send_file(target)
            return
        self.send_error(404)

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path != "/api/categories":
            self.send_error(404)
            return
        try:
            result = apply_category_update(self.read_json_body())
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
            return
        except json.JSONDecodeError:
            self.send_json({"error": "invalid JSON"}, status=400)
            return
        self.send_json(result["payload"], status=result["status"])


def find_port(start=8765):
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No available local port found")


def ensure_data_files():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not (DATA_DIR / "library.json").exists():
        write_json(DATA_DIR / "library.json", default_library())
    if not (DATA_DIR / "categories.json").exists():
        write_json(DATA_DIR / "categories.json", {"categories": []})


def main():
    ensure_data_files()
    port = int(os.environ.get("CHAT_HISTORY_PORT") or find_port())
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    if os.environ.get("CHAT_HISTORY_OPEN_BROWSER", "1") != "0":
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"Chat history manager started: {url}")
    print(f"Archive root: {ROOT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped")


if __name__ == "__main__":
    main()
