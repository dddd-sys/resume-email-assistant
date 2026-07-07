from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import time


@dataclass(frozen=True)
class CleanupResult:
    removed_files: list[str]
    removed_dirs: list[str]
    skipped_paths: list[str]


def cleanup_once_files(base_dir: Path, days: int, dry_run: bool = False) -> CleanupResult:
    if days < 0:
        raise ValueError("days 必须大于或等于 0。")

    cutoff = time.time() - days * 24 * 60 * 60
    removed_files: list[str] = []
    removed_dirs: list[str] = []
    skipped_paths: list[str] = []

    for directory_name in ("inbox", "outbox"):
        directory = (base_dir / directory_name).resolve()
        if not directory.exists():
            continue
        if not _is_child_of(directory, base_dir.resolve()):
            skipped_paths.append(str(directory))
            continue

        for path in sorted(directory.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_dir():
                if _is_empty_dir(path) and _is_older_than(path, cutoff):
                    removed_dirs.append(str(path))
                    if not dry_run:
                        path.rmdir()
                continue

            if path.is_file() and _is_older_than(path, cutoff):
                removed_files.append(str(path))
                if not dry_run:
                    path.unlink()

        if _is_empty_dir(directory) and _is_older_than(directory, cutoff):
            removed_dirs.append(str(directory))
            if not dry_run:
                directory.rmdir()

    return CleanupResult(
        removed_files=removed_files,
        removed_dirs=removed_dirs,
        skipped_paths=skipped_paths,
    )


def format_cleanup_result(result: CleanupResult, dry_run: bool = False) -> str:
    action = "将清理" if dry_run else "已清理"
    lines = [
        f"{action}文件 {len(result.removed_files)} 个，文件夹 {len(result.removed_dirs)} 个。",
    ]
    if result.skipped_paths:
        lines.append(f"已跳过可疑路径 {len(result.skipped_paths)} 个。")
    return "\n".join(lines)


def _is_older_than(path: Path, cutoff: float) -> bool:
    try:
        return path.stat().st_mtime <= cutoff
    except FileNotFoundError:
        return False


def _is_empty_dir(path: Path) -> bool:
    try:
        return path.is_dir() and not any(path.iterdir())
    except FileNotFoundError:
        return False


def _is_child_of(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
