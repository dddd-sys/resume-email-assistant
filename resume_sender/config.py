from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class Candidate:
    name: str
    school: str
    major: str
    grade: str
    availability: str
    weekly_attendance: str
    duration: str


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    use_ssl: bool
    username: str
    password_env: str
    from_name: str


@dataclass(frozen=True)
class OpenAIConfig:
    enabled: bool
    model: str
    api_key_env: str
    provider: str = "openai"
    base_url: str | None = None


@dataclass(frozen=True)
class ResumeProfile:
    id: str
    label: str
    path: Path
    keywords: list[str]
    summary: str


@dataclass(frozen=True)
class AppConfig:
    base_dir: Path
    candidate: Candidate
    email: EmailConfig
    openai: OpenAIConfig
    resumes: list[ResumeProfile]


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    candidate_raw = {
        "weekly_attendance": "每周到岗5天",
        **raw["candidate"],
    }
    candidate = Candidate(**candidate_raw)
    email = EmailConfig(**raw["email"])
    openai_raw = {
        "enabled": False,
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "api_key_env": "OPENAI_API_KEY",
        "base_url": None,
        **raw.get("openai", {}),
    }
    if openai_raw.get("provider") == "bailian" and not openai_raw.get("base_url"):
        openai_raw["base_url"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    openai = OpenAIConfig(**openai_raw)
    resumes = [
        ResumeProfile(
            id=item["id"],
            label=item["label"],
            path=_resolve_path(config_path.parent, item["path"]),
            keywords=list(item.get("keywords", [])),
            summary=item.get("summary", ""),
        )
        for item in raw["resumes"]
    ]

    if not resumes:
        raise ValueError("config.json 中至少需要配置一份简历。")

    return AppConfig(
        base_dir=config_path.parent,
        candidate=candidate,
        email=email,
        openai=openai,
        resumes=resumes,
    )


def _resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()
