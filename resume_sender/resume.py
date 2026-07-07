from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .config import ResumeProfile


@dataclass(frozen=True)
class ResumeMatch:
    resume: ResumeProfile
    score: float
    matched_terms: list[str]


def choose_resume(job_text: str, resumes: list[ResumeProfile]) -> ResumeMatch:
    scored = [score_resume(job_text, resume) for resume in resumes]
    return max(scored, key=lambda item: item.score)


def score_resume(job_text: str, resume: ResumeProfile) -> ResumeMatch:
    normalized = _normalize(job_text)
    matched_terms = []
    score = 0.0

    for keyword in resume.keywords:
        keyword_norm = _normalize(keyword)
        if not keyword_norm:
            continue
        count = normalized.count(keyword_norm)
        if count:
            matched_terms.append(keyword)
            score += min(3, count) * (2.5 if len(keyword_norm) >= 4 else 1.5)

    resume_text = extract_pdf_text(resume.path)
    if resume_text:
        score += _overlap_score(job_text, resume_text) * 0.2

    if resume.label in job_text:
        score += 4

    return ResumeMatch(resume=resume, score=round(score, 2), matched_terms=matched_terms[:12])


def extract_pdf_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""

    try:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages[:5]]
        return "\n".join(pages)
    except Exception:
        return ""


def _overlap_score(left: str, right: str) -> float:
    left_terms = set(_terms(left))
    right_terms = set(_terms(right))
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / max(1, len(left_terms)) * 20


def _terms(text: str) -> list[str]:
    english = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]{1,}", text.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    return english + chinese


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()
