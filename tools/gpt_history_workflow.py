from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_ARCHIVE_ROOT = Path(__file__).resolve().parents[1]


def run_command(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True)
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        print(output.rstrip())
        raise SystemExit(result.returncode)
    return output


def require_file(path: Path, label: str) -> Path:
    if not path.exists():
        raise SystemExit(f"{label} 不存在：{path}")
    return path


def latest_file(directory: Path, pattern: str) -> Path | None:
    rows = sorted(directory.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    return rows[0] if rows else None


def extract_path(output: str, labels: list[str]) -> Path | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[:：]\s*(.+)", output)
        if match:
            return Path(match.group(1).strip())
    return None


def archive_paths(root: Path):
    tools = root / "tools"
    return {
        "prepare": require_file(tools / "prepare_import.py", "prepare_import.py"),
        "packet": require_file(tools / "make_ai_work_packet.py", "make_ai_work_packet.py"),
        "apply": require_file(tools / "apply_ai_work_packet.py", "apply_ai_work_packet.py"),
        "merge": require_file(tools / "merge_classified_import.py", "merge_classified_import.py"),
        "static": tools / "generate_static_view.py",
        "data": root / "data",
    }


def command_prepare(args):
    root = Path(args.archive_root).resolve()
    paths = archive_paths(root)
    source = require_file(Path(args.source).resolve(), "导出 zip/chat.html")

    prepare_output = run_command([sys.executable, str(paths["prepare"]), str(source)])
    pending = extract_path(prepare_output, ["待分类文件", "Pending import"])
    if pending is None:
        pending = latest_file(paths["data"], "pending_import_*.json")
    if pending is None:
        raise SystemExit("未能定位 pending_import_*.json")

    packet_output = run_command([sys.executable, str(paths["packet"]), str(pending)])
    packet_json = extract_path(packet_output, ["AI work packet JSON"])
    packet_md = extract_path(packet_output, ["AI work packet Markdown"])

    print(prepare_output.rstrip())
    print(packet_output.rstrip())
    print("")
    print("下一步：")
    if packet_md:
        print(f"1. 只读取这个 Markdown 工作包：{packet_md}")
    if packet_json:
        print(f"2. 在这个 JSON 工作包里填写 category、summary、keywords：{packet_json}")
    print("3. 填完后运行：")
    print(f'python "{Path(__file__).resolve()}" apply "{pending}" "{packet_json or "<ai_work_packet.json>"}" --merge --archive-root "{root}"')


def command_apply(args):
    root = Path(args.archive_root).resolve()
    paths = archive_paths(root)
    pending = require_file(Path(args.pending_import).resolve(), "pending_import")
    packet = require_file(Path(args.ai_work_packet).resolve(), "ai_work_packet")

    apply_output = run_command([sys.executable, str(paths["apply"]), str(pending), str(packet)])
    classified = extract_path(apply_output, ["Classified import", "已分类导入"])
    if classified is None:
        classified = latest_file(paths["data"], "classified_import_*.json")
    print(apply_output.rstrip())

    if args.merge:
        if classified is None:
            raise SystemExit("未能定位 classified_import_*.json，无法合并")
        merge_output = run_command([sys.executable, str(paths["merge"]), str(classified)])
        print(merge_output.rstrip())
        print(f"已合并：{classified}")
        if paths["static"].exists():
            static_output = run_command([sys.executable, str(paths["static"]), "--root", str(root)])
            print(static_output.rstrip())
    elif classified:
        print("")
        print("未合并。确认后可运行：")
        print(f'python "{paths["merge"]}" "{classified}"')


def command_status(args):
    root = Path(args.archive_root).resolve()
    data = root / "data"
    pending = latest_file(data, "pending_import_*.json")
    packet_md = latest_file(data / "ai_work_packets", "*.md")
    packet_json = latest_file(data / "ai_work_packets", "*.json")
    classified = latest_file(data, "classified_import_*.json")
    library = data / "library.json"
    static_html = root / "GPT聊天记录资料库.html"

    print(f"资料库：{root}")
    print("导入入口：prepare <ChatGPT 导出 zip 或 chat.html>")
    print("ZIP 处理：只解出其中的 chat.html，不展开附件或其它文件")
    print("Codex 读取规则：只读 data\\ai_work_packets\\*.md，不读完整 zip/chat.html/library.json/pending_import_*.json")
    print(f"总库：{library if library.exists() else '未找到'}")
    print(f"静态 HTML：{static_html if static_html.exists() else '未生成'}")
    print(f"最新待分类：{pending or '无'}")
    print(f"最新工作包 Markdown：{packet_md or '无'}")
    print(f"最新工作包 JSON：{packet_json or '无'}")
    print(f"最新已分类导入：{classified or '无'}")


def main():
    parser = argparse.ArgumentParser(description="Low-token GPT history import workflow.")
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT), help="GPT 聊天记录资料库目录")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="解析 ChatGPT 导出 zip 或 chat.html、去重并生成 AI 工作包")
    prepare.add_argument("source", help="ChatGPT 导出 zip 或 chat.html 路径")
    prepare.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT), help="GPT 聊天记录资料库目录")
    prepare.set_defaults(func=command_prepare)

    apply = sub.add_parser("apply", help="把填好的 AI 工作包回写到完整导入")
    apply.add_argument("pending_import", help="pending_import_*.json")
    apply.add_argument("ai_work_packet", help="已填写的 ai_work_packet_*.json")
    apply.add_argument("--merge", action="store_true", help="回写后立刻合并进 library.json")
    apply.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT), help="GPT 聊天记录资料库目录")
    apply.set_defaults(func=command_apply)

    status = sub.add_parser("status", help="查看最新工作流文件")
    status.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT), help="GPT 聊天记录资料库目录")
    status.set_defaults(func=command_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
