from __future__ import annotations

from dataclasses import dataclass
import re


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
SECTION_HEADERS = {
    "岗位职责",
    "工作职责",
    "岗位要求",
    "任职要求",
    "任职资格",
    "工作内容",
    "工作地",
    "工作地点",
    "到岗时间",
    "到岗工作",
    "邮件投递",
    "简历投递",
    "投递方式",
    "联系方式",
}


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
                subject_format=extract_format(
                    block,
                    ["邮件标题格式", "邮件主题格式", "投递标题格式", "标题格式", "邮件标题", "邮件主题", "投递标题", "主题", "标题"],
                ),
                attachment_format=extract_format(
                    block,
                    ["附件命名格式", "简历命名格式", "文件命名格式", "附件命名", "简历命名", "文件命名", "附件名称", "简历名称"],
                ),
            )
        )
    return posts


def find_posts_without_email(text: str) -> list[str]:
    blocks = _candidate_blocks(text)
    titles = []
    for block in blocks:
        if EMAIL_RE.search(block):
            continue
        if not _looks_like_job_block(block):
            continue
        title = extract_job_title(block)
        if title != "目标岗位":
            titles.append(title)
    return titles


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


def _candidate_blocks(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n+", normalized) if chunk.strip()]
    if EMAIL_RE.search(normalized):
        return _split_blocks(normalized)
    return ["\n\n".join(chunks)] if chunks else []


def _looks_like_job_block(text: str) -> bool:
    return any(word in text for word in ["岗位职责", "工作职责", "岗位要求", "任职资格", "岗位亮点", "投递方式"])


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
                cleaned = _clean_title(match.group(1))
                if pattern == r"(?:【|\[)(.+?)(?:】|\])" and (
                    _is_format_instruction(line) or not _is_likely_bracket_title(cleaned)
                ):
                    continue
                if _is_valid_title(cleaned) and not _looks_like_format(cleaned):
                    return cleaned

    for line in lines[:8]:
        if _is_forwarding_note(line):
            continue
        if EMAIL_RE.search(line):
            continue
        if _is_section_header(line) or any(word in line for word in ["投递", "邮箱", "邮件", "简历"]):
            continue
        cleaned = _clean_title(line)
        if _is_valid_title(cleaned):
            return cleaned

    return "目标岗位"


def extract_format(text: str, labels: list[str]) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        matched_label = next((label for label in labels if label in line), None)
        if not matched_label:
            continue
        after_label = line.split(matched_label, maxsplit=1)[-1]
        value = _unwrap_format_wrapper(_trim_format_value(after_label.strip(" ：:，,。为")))
        if value and not EMAIL_RE.fullmatch(value):
            return value
        bracket_match = re.search(r"[【\[](.+?)[】\]]", after_label)
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
    value = _remove_leading_note(value)
    value = re.sub(r"^.*?招聘\s*", "", value)
    value = re.sub(r"\bbase\s*[A-Za-z\u4e00-\u9fff]+.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"(?:坐标|地点|base|工作地|工作地点)[:：]?[A-Za-z\u4e00-\u9fff]+.*$", "", value, flags=re.IGNORECASE)
    value = _drop_company_prefix(value)
    value = re.sub(r"\s+", "", value)
    value = value.strip(" ：:，,。-—_【】[]")
    return value[:60] or "目标岗位"


def _remove_leading_note(value: str) -> str:
    return re.sub(r"^\s*[（(【\[].*?(?:帮|招|内推|转发|急招).*?[）)】\]]\s*", "", value)


def _drop_company_prefix(value: str) -> str:
    pieces = [piece.strip() for piece in re.split(r"\s*[-－—–]\s*", value) if piece.strip()]
    if len(pieces) < 2:
        return value

    left = pieces[0].strip(" ：:，,。_【】[]（）()")
    right = "-".join(pieces[1:]).strip()
    if _looks_like_company_prefix(left) and _contains_role_signal(right):
        return right
    return value


def _looks_like_company_prefix(value: str) -> bool:
    if len(value) <= 4 and not _contains_role_signal(value):
        return True
    return any(
        word in value
        for word in [
            "公司",
            "集团",
            "银行",
            "科技",
            "互联网",
            "携程",
            "百度",
            "阿里",
            "腾讯",
            "字节",
            "美团",
            "京东",
            "网易",
            "小红书",
            "滴滴",
            "快手",
            "蚂蚁",
            "华为",
        ]
    )


def _contains_role_signal(value: str) -> bool:
    return any(
        word in value
        for word in [
            "实习",
            "校招",
            "社招",
            "产品",
            "运营",
            "分析",
            "研究",
            "战略",
            "经理",
            "GTM",
            "PM",
            "BA",
        ]
    )


def _is_valid_title(value: str) -> bool:
    return 2 <= len(value) <= 40 and not _is_section_header(value)


def _is_section_header(value: str) -> bool:
    normalized = value.strip(" ：:，,。-—_【】[]")
    return normalized in SECTION_HEADERS


def _is_format_instruction(value: str) -> bool:
    return any(word in value for word in ["命名", "名称", "邮件标题", "邮件主题", "投递标题", "标题格式", "简历", "附件"])


def _looks_like_format(value: str) -> bool:
    return "-" in value and any(word in value for word in ["姓名", "学校", "专业", "年级", "岗位", "职位"])


def _is_likely_bracket_title(value: str) -> bool:
    if _is_section_header(value):
        return False
    return _contains_role_signal(value)


def _trim_format_value(value: str) -> str:
    value = EMAIL_RE.sub("", value)
    value = re.split(r"(?:发送到|发送至|投递到|投递至|邮箱|邮件)", value, maxsplit=1)[0]
    return value.strip(" ：:，,。-—_")


def _unwrap_format_wrapper(value: str) -> str:
    bracket_match = re.fullmatch(r"[【\[](.+?)[】\]]", value.strip())
    if bracket_match:
        return bracket_match.group(1).strip()
    return value.strip()


def _is_forwarding_note(line: str) -> bool:
    return line.strip() in {"帮转", "转发", "内推", "招聘", "实习"}
