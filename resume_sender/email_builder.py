from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re

from .config import AppConfig, Candidate
from .parser import JobPost
from .resume import ResumeMatch, extract_pdf_text


@dataclass(frozen=True)
class BuiltEmail:
    to: list[str]
    subject: str
    body: str
    attachment_name: str
    attachment_source: Path
    resume_label: str
    match_score: float
    matched_terms: list[str]
    body_source: str


def build_email(config: AppConfig, post: JobPost, match: ResumeMatch) -> BuiltEmail:
    subject_format = post.subject_format or post.attachment_format
    subject = fill_format(
        subject_format,
        post.title,
        config.candidate,
        default_without_extension=True,
    )
    attachment_stem = fill_format(
        post.attachment_format,
        post.title,
        config.candidate,
        default_without_extension=True,
    )
    attachment_name = ensure_pdf_name(attachment_stem)
    body, body_source = generate_body(config, post, match)

    return BuiltEmail(
        to=post.emails,
        subject=subject,
        body=body,
        attachment_name=attachment_name,
        attachment_source=match.resume.path,
        resume_label=match.resume.label,
        match_score=match.score,
        matched_terms=match.matched_terms,
        body_source=body_source,
    )


def fill_format(format_text: str | None, job_title: str, candidate: Candidate, default_without_extension: bool) -> str:
    if not format_text:
        result = f"{job_title}-{candidate.name}-{candidate.school}-{candidate.availability}-{candidate.duration}"
    else:
        result = format_text
        replacements = {
            "岗位名称": job_title,
            "岗位名": job_title,
            "职位名称": job_title,
            "职位": job_title,
            "姓名": candidate.name,
            "名字": candidate.name,
            "学校": candidate.school,
            "院校": candidate.school,
            "最快到岗时间": candidate.availability,
            "到岗时间": candidate.availability,
            "可到岗时间": candidate.availability,
            "每周到岗": candidate.weekly_attendance,
            "每周出勤": candidate.weekly_attendance,
            "出勤时间": candidate.weekly_attendance,
            "实习时长": candidate.duration,
            "实习周期": candidate.duration,
            "实习时间": candidate.duration,
            "时长": candidate.duration,
            "专业": candidate.major,
            "年级": candidate.grade,
        }
        for key, value in replacements.items():
            result = result.replace(key, value)
        result = re.sub(r"\s+", "", result)
    result = sanitize_filename_piece(result)
    if default_without_extension and result.lower().endswith(".pdf"):
        result = result[:-4]
    return result


def ensure_pdf_name(value: str) -> str:
    value = sanitize_filename_piece(value)
    if not value.lower().endswith(".pdf"):
        value += ".pdf"
    return value


def generate_body(config: AppConfig, post: JobPost, match: ResumeMatch) -> tuple[str, str]:
    if config.openai.enabled:
        generated = _generate_body_with_openai(config, post, match)
        if generated:
            return ensure_body_greeting(generated), "ai"
    return ensure_body_greeting(_generate_body_locally(config, post, match)), "local_template"


def _generate_body_with_openai(config: AppConfig, post: JobPost, match: ResumeMatch) -> str | None:
    api_key = os.getenv(config.openai.api_key_env)
    if not api_key:
        return None

    try:
        from openai import OpenAI
    except ImportError:
        return None

    candidate = config.candidate
    resume_text = prepare_resume_context(extract_pdf_text(match.resume.path), post.raw_text)
    prompt = f"""
请为一封中文求职投递邮件写正文，要求简洁、自然、职业化。

非常重要：
- 正文第一行必须固定为：hr您好：
- 必须优先使用“简历原文”里的真实经历、项目、工具、方法、成果来写优势。
- 每一点优势都要对应 JD 的一个需求，并尽量带出具体经历名称、任务、工具、研究对象或产出。
- 不要写空泛套话，比如“学习能力强”“沟通高效”“执行力强”，除非能接上简历里的具体证据。
- 不要编造简历原文中没有的公司、项目、数据、奖项、实习经历或量化成果。
- 如果简历原文没有足够细节，就保守表达，不要夸张。
- 不要使用 Markdown 格式，不要输出星号、加粗、标题符号或代码块。

候选人：
- 姓名：{candidate.name}
- 学校：{candidate.school}
- 专业：{candidate.major}
- 年级：{candidate.grade}
- 到岗：{candidate.availability}
- 每周到岗：{candidate.weekly_attendance}
- 实习时长：{candidate.duration}

匹配简历版本：{match.resume.label}
简历摘要：{match.resume.summary}
匹配关键词：{"、".join(match.matched_terms) if match.matched_terms else "无"}

简历原文：
{resume_text or "未能从 PDF 提取到简历原文。"}

岗位 JD：
{post.raw_text}

正文结构：
1. 称呼固定写：hr您好：
2. 说明投递岗位，并用一句话介绍姓名、学校、专业、年级、可以随时到岗、每周到岗时间和实习时长。
3. 写三点优势，必须严格使用 1. 2. 3. 编号列举。每点都必须是“JD要求 + 简历中的具体经历/能力证据”的组合。
4. 说明附件已附简历，并礼貌收尾。
控制在 250-380 字，只输出纯文本邮件正文，不要输出标题，不要使用 Markdown。
""".strip()

    try:
        client_kwargs = {"api_key": api_key}
        if config.openai.base_url:
            client_kwargs["base_url"] = config.openai.base_url
        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=config.openai.model,
            messages=[
                {"role": "system", "content": "你是严谨的中文求职邮件写作助手，会基于简历事实改写，不编造经历。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
        )
        return clean_ai_body(response.choices[0].message.content or "")
    except Exception:
        return None


def _generate_body_locally(config: AppConfig, post: JobPost, match: ResumeMatch) -> str:
    candidate = config.candidate
    terms = match.matched_terms[:6]
    term_text = "、".join(terms) if terms else match.resume.label
    advantages = _build_advantages(match.resume.label, term_text, match.resume.summary)
    bullets = "\n".join(f"{idx}. {item}" for idx, item in enumerate(advantages, start=1))
    return f"""hr您好：

冒昧来信，想投递贵方发布的「{post.title}」岗位。我是{candidate.school}{candidate.major}{candidate.grade}学生{candidate.name}，可{candidate.availability}，{candidate.weekly_attendance}，预计可实习{candidate.duration}。

结合岗位 JD 和我的经历，我认为自己有以下几点匹配优势：
{bullets}

随信附上我的简历，烦请查收。期待有机会进一步沟通，谢谢！

{candidate.name}"""


def _build_advantages(label: str, term_text: str, summary: str) -> list[str]:
    summary = summary.rstrip("。；;，, ")
    if "AI" in label or "产品" in label:
        return [
            f"对 {term_text} 等方向有持续关注，能够把用户需求、业务目标和 AI 能力边界结合起来思考产品方案。",
            "具备需求分析、竞品研究、原型/文档表达和跨团队沟通意识，能支持从调研到落地跟进的产品工作。",
            f"{summary}，与岗位中对产品理解、数据反馈和协作推进的要求较为匹配。",
        ]
    if "金融" in label or "战略" in label:
        return [
            f"具备围绕 {term_text} 展开资料搜集、逻辑拆解和研究表达的能力，适合支持行业/公司/战略类分析工作。",
            "能够从商业模式、财务数据、行业趋势和竞争格局等角度形成结构化判断，并沉淀为清晰报告。",
            f"{summary}，与岗位中对研究能力、分析框架和文字表达的要求较为匹配。",
        ]
    return [
        f"具备围绕 {term_text} 做数据整理、指标拆解和业务分析的能力，能够从问题出发形成可执行洞察。",
        "熟悉用结构化方法理解业务目标，并通过数据分析、报告呈现和沟通协作支持决策。",
        f"{summary}，与岗位中对分析能力、业务理解和结果表达的要求较为匹配。",
    ]


def sanitize_filename_piece(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[\\/:*?\"<>|]", "-", value)
    value = re.sub(r"\s+", "", value)
    value = value.strip(". ")
    return value or "简历"


def clean_ai_body(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\*\*(.*?)\*\*", r"\1", value)
    value = re.sub(r"__(.*?)__", r"\1", value)
    value = re.sub(r"`{1,3}", "", value)
    value = normalize_advantage_markers(value)
    value = value.replace("*", "")
    return value.strip()


def ensure_body_greeting(value: str) -> str:
    body = value.strip()
    if not body:
        return "hr您好："

    lines = body.splitlines()
    first_content_index = next((idx for idx, line in enumerate(lines) if line.strip()), 0)
    first_line = lines[first_content_index].strip()
    greeting_pattern = r"^(?:hr|HR|Hr)?\s*(?:您好|你好|老师您好|招聘负责人您好|尊敬的HR|尊敬的hr)[，,：:！!。.\s]*$"
    if re.match(greeting_pattern, first_line):
        lines[first_content_index] = "hr您好："
    elif first_line != "hr您好：":
        lines.insert(first_content_index, "hr您好：")
    return "\n".join(lines).strip()


def normalize_advantage_markers(value: str) -> str:
    lines = value.splitlines()
    item_index = 0
    normalized = []
    for line in lines:
        if re.match(r"^\s*[-•]\s+", line):
            item_index += 1
            normalized.append(re.sub(r"^\s*[-•]\s+", f"{item_index}. ", line))
            continue
        numbered = re.match(r"^\s*([一二三123])\s*[、.)）]\s*(.+)", line)
        if numbered:
            item_index += 1
            normalized.append(f"{item_index}. {numbered.group(2)}")
            continue
        normalized.append(line)
    return "\n".join(normalized)


def prepare_resume_context(resume_text: str, job_text: str, max_chars: int = 6000) -> str:
    text = re.sub(r"[ \t]+", " ", resume_text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= max_chars:
        return text

    keywords = _important_terms(job_text)
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n|\n(?=[^\n]{2,18}[：:])", text) if chunk.strip()]
    scored_chunks = []
    for index, chunk in enumerate(chunks):
        normalized = chunk.lower()
        score = sum(normalized.count(term.lower()) for term in keywords)
        if score:
            scored_chunks.append((score, index, chunk))

    selected = [chunk for _, _, chunk in sorted(scored_chunks, key=lambda item: (-item[0], item[1]))[:10]]
    compact = "\n\n".join(selected)
    if len(compact) < max_chars // 2:
        compact = text[:max_chars]
    return compact[:max_chars]


def _important_terms(text: str) -> list[str]:
    terms = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]{1,}", text)
    terms += re.findall(r"[\u4e00-\u9fff]{2,}", text)
    stop_terms = {"工作职责", "任职资格", "岗位职责", "岗位要求", "优先", "相关", "能力"}
    return [term for term in terms if term not in stop_terms][:80]
