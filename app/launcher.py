from __future__ import annotations

import ctypes
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path


ROOT = Path(os.environ.get("CHAT_HISTORY_HOME", Path(__file__).resolve().parents[1])).resolve()
SERVER = ROOT / "app" / "server.py"
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
RUNTIME = DATA_DIR / "runtime.json"
PORT_START = 8765
PORT_LIMIT = 50


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def message_box(title: str, text: str) -> None:
    if os.name != "nt":
        return
    ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def url_for(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def service_is_ready(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.08):
            pass
    except OSError:
        return False
    try:
        with urllib.request.urlopen(url_for(port) + "/api/state", timeout=0.45) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return "stats" in payload and "conversations" in payload
    except Exception:
        return False


def open_browser(port: int) -> None:
    if os.environ.get("CHAT_HISTORY_LAUNCHER_OPEN", "1") != "0":
        webbrowser.open(url_for(port))


def running_port() -> int | None:
    runtime = read_json(RUNTIME, {})
    ports: list[int] = []
    if isinstance(runtime.get("port"), int):
        ports.append(runtime["port"])
    ports.extend(range(PORT_START, PORT_START + PORT_LIMIT))
    seen = set()
    for port in ports:
        if port in seen:
            continue
        seen.add(port)
        if service_is_ready(port):
            write_json(
                RUNTIME,
                {
                    "port": port,
                    "url": url_for(port),
                    "root": str(ROOT),
                    "last_seen_at": now_text(),
                    "status": "running",
                },
            )
            return port
    return None


def find_free_port() -> int:
    for port in range(PORT_START, PORT_START + PORT_LIMIT):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No available local port found.")


def pythonw_executable() -> Path:
    current = Path(sys.executable)
    if current.name.lower() == "pythonw.exe":
        return current
    sibling = current.with_name("pythonw.exe")
    if sibling.exists():
        return sibling
    return current


def start_server(port: int) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "server.log"
    log_file = log_path.open("a", encoding="utf-8")
    log_file.write(f"\n--- launcher start {now_text()} port={port} ---\n")
    log_file.flush()

    env = os.environ.copy()
    env["CHAT_HISTORY_HOME"] = str(ROOT)
    env["CHAT_HISTORY_PORT"] = str(port)
    env["CHAT_HISTORY_OPEN_BROWSER"] = "0"

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW

    process = subprocess.Popen(
        [str(pythonw_executable()), str(SERVER)],
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=log_file,
        creationflags=creationflags,
    )
    write_json(
        RUNTIME,
        {
            "pid": process.pid,
            "port": port,
            "url": url_for(port),
            "root": str(ROOT),
            "started_at": now_text(),
            "status": "starting",
            "log": str(log_path),
        },
    )
    return process.pid


def wait_until_ready(port: int, seconds: float = 6.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if service_is_ready(port):
            runtime = read_json(RUNTIME, {})
            runtime.update({"status": "running", "last_seen_at": now_text(), "url": url_for(port)})
            write_json(RUNTIME, runtime)
            return True
        time.sleep(0.25)
    return False


def main() -> int:
    if not SERVER.exists():
        message_box("GPT聊天记录资料库", f"找不到服务文件：\n{SERVER}")
        return 1

    port = running_port()
    if port is not None:
        open_browser(port)
        return 0

    port = find_free_port()
    start_server(port)
    if wait_until_ready(port):
        open_browser(port)
        return 0

    message_box(
        "GPT聊天记录资料库",
        f"后台服务启动失败。\n请查看日志：\n{LOG_DIR / 'server.log'}",
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
