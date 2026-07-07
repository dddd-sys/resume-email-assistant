from __future__ import annotations

from email import policy
from email.parser import BytesParser
from pathlib import Path
import subprocess


def find_latest_preview(outbox_dir: Path) -> Path:
    if not outbox_dir.exists():
        raise FileNotFoundError(f"找不到预览目录：{outbox_dir}")

    previews = [path for path in outbox_dir.rglob("*.eml") if path.is_file()]
    if not previews:
        raise FileNotFoundError(f"没有在 {outbox_dir} 下找到 .eml 预览文件。")

    return max(previews, key=lambda path: path.stat().st_mtime)


def open_preview(path: Path) -> bool:
    commands = [
        ["open", "-a", "/System/Applications/Mail.app", str(path)],
        ["open", "-a", "Mail.app", str(path)],
        ["open", str(path)],
    ]
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0:
            return True
    return False


def render_preview(path: Path) -> str:
    with path.open("rb") as f:
        message = BytesParser(policy=policy.default).parse(f)

    body_part = message.get_body(preferencelist=("plain",))
    body = body_part.get_content().strip() if body_part else ""
    attachments = [
        part.get_filename()
        for part in message.iter_attachments()
        if part.get_filename()
    ]

    lines = [
        f"预览文件：{path}",
        f"发件人：{message.get('From', '')}",
        f"收件人：{message.get('To', '')}",
        f"标题：{message.get('Subject', '')}",
    ]
    if attachments:
        lines.append("附件：" + "、".join(attachments))
    lines.extend(["", "正文：", body])
    return "\n".join(lines)
