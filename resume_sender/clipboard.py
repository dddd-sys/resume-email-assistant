from __future__ import annotations

from pathlib import Path
import subprocess


def read_clipboard_text() -> str:
    try:
        result = subprocess.run(
            ["pbpaste"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("当前系统不支持 pbpaste，无法读取剪贴板。") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("读取剪贴板失败。") from exc
    return result.stdout.strip()


def save_clipboard_text(base_dir: Path, text: str, filename: str = "clipboard.txt") -> Path:
    if not text.strip():
        raise ValueError("剪贴板为空，请先复制一条岗位 JD。")

    inbox_dir = base_dir / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    message_path = inbox_dir / filename
    message_path.write_text(text.strip() + "\n", encoding="utf-8")
    return message_path
