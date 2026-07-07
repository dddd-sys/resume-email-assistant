from __future__ import annotations

from dataclasses import dataclass
import re


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


@dataclass(frozen=True)
class JobPost:
    raw_text: str
    emails: list[str]
    title: str
    subject_format: str | None
    attachment_format: str | None


def parse_job_posts(text: str) -> list[JobPost]:
    blocks = _split_blocks(text)
    posts = []
    for block in blocks:
        emails = sorted(set(EMAIL_RE.findall(block)))
        if not emails:
            continue
        posts.append(
            JobPost(
                raw_text=block.strip(),
                emails=emails,
                title=extract_job_title(block),
                subject_format=extract_format(block, ["邮件标题", "邮件主题", "投递标题", "主题", "标题"]),
                attachment_format=extract_format(block, ["附件命名", "简历命名", "文件命名", "附件名称", "简历名称"]),
            )
        )
    return posts


def _split_blocks(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks = re.split(r"\n\s*\n+", normalized)
    merged = []
    current = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        current.append(chunk)
        if EMAIL_RE.search(chunk):
            merged.append("\n\n".join(current))
            current = []
    if current:
        tail = "\n\n".join(current)
        if EMAIL_RE.search(tail):
            merged.append(tail)
    return merged


def extract_job_title(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    label_patterns = [
        r"(?:岗位|职位|招聘岗位|招聘职位|应聘岗位|投递岗位)\s*[:：]\s*(.+)",
        r"(?:【|\[)(.+?)(?:】|\])",
    ]
    for line in lines[:12]:
        if _is_forwarding_note(line):
            continue
        if "|" in line or "｜" in line:
            right_side = re.split(r"[|｜]", line, maxsplit=1)[-1]
            cleaned = _clean_title(right_side)
            if 2 <= len(cleaned) <= 40:
                return cleaned
        for pattern in label_patterns:
            match = re.search(pattern, line)
            if match:
                return _clean_title(match.group(1))

    for line in lines[:8]:
        if _is_forwarding_note(line):
            continue
        if EMAIL_RE.search(line):
            continue
        if any(word in line for word in ["岗位职责", "任职要求", "投递", "邮箱", "邮件", "简历"]):
            continue
        cleaned = _clean_title(line)
        if 2 <= len(cleaned) <= 40:
            return cleaned

    return "目标岗位"


def extract_format(text: str, labels: list[str]) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if not any(label in line for label in labels):
            continue
        bracket_match = re.search(r"[【\[](.+?)[】\]]", line)
        if bracket_match:
            return bracket_match.group(1).strip()
        match = re.search(r"[:：]\s*(.+)$", line)
        if match:
            value = _trim_format_value(match.group(1).strip())
            if value and not EMAIL_RE.fullmatch(value):
                return value
        pieces = re.split(r"(?:为|格式|命名|名称)", line, maxsplit=1)
        if len(pieces) > 1:
            value = _trim_format_value(pieces[-1].strip(" ：:，,。"))
            if value:
                return value
    return None


def _clean_title(value: str) -> str:
    value = re.sub(r"\bbase\s*[A-Za-z\u4e00-\u9fff]+.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"(?:坐标|地点|base|工作地|工作地点)[:：]?[A-Za-z\u4e00-\u9fff]+.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", "", value)
    value = value.strip(" ：:，,。-—_【】[]")
    return value[:60] or "目标岗位"


def _trim_format_value(value: str) -> str:
    value = EMAIL_RE.sub("", value)
    value = re.split(r"(?:发送到|发送至|投递到|投递至|邮箱|邮件)", value, maxsplit=1)[0]
    return value.strip(" ：:，,。-—_【】[]")


def _is_forwarding_note(line: str) -> bool:
    return line.strip() in {"帮转", "转发", "内推", "招聘", "实习"}
