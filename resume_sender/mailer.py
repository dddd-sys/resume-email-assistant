from __future__ import annotations

from dataclasses import asdict
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
import json
import os
import shutil
import smtplib
from datetime import datetime

from .config import AppConfig
from .email_builder import BuiltEmail


def prepare_outbox(config: AppConfig, emails: list[BuiltEmail], outbox_dir: Path) -> list[dict]:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = outbox_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for index, built in enumerate(emails, start=1):
        attachment_path = run_dir / f"{index:02d}-{built.attachment_name}"
        if built.attachment_source.exists():
            shutil.copy2(built.attachment_source, attachment_path)

        message = build_message(config, built, attachment_path if attachment_path.exists() else built.attachment_source)
        eml_path = run_dir / f"{index:02d}-{safe_subject(built.subject)}.eml"
        eml_path.write_bytes(message.as_bytes())

        records.append(
            {
                "to": built.to,
                "subject": built.subject,
                "resume": built.resume_label,
                "match_score": built.match_score,
                "matched_terms": built.matched_terms,
                "body_source": built.body_source,
                "attachment": str(attachment_path),
                "eml": str(eml_path),
                "attachment_exists": attachment_path.exists(),
            }
        )

    summary_path = run_dir / "run_summary.json"
    summary_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


def send_emails(config: AppConfig, emails: list[BuiltEmail]) -> None:
    password = os.getenv(config.email.password_env)
    if not password:
        raise RuntimeError(f"未找到环境变量 {config.email.password_env}，无法发送邮件。")

    if config.email.use_ssl:
        smtp = smtplib.SMTP_SSL(config.email.smtp_host, config.email.smtp_port, timeout=30)
    else:
        smtp = smtplib.SMTP(config.email.smtp_host, config.email.smtp_port, timeout=30)
        smtp.starttls()

    with smtp:
        smtp.login(config.email.username, password)
        for built in emails:
            message = build_message(config, built, built.attachment_source)
            smtp.send_message(message)


def build_message(config: AppConfig, built: BuiltEmail, attachment_path: Path) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr((config.email.from_name, config.email.username))
    message["To"] = ", ".join(built.to)
    message["Subject"] = built.subject
    message.set_content(built.body)

    if attachment_path.exists():
        message.add_attachment(
            attachment_path.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=built.attachment_name,
        )
    return message


def safe_subject(subject: str) -> str:
    value = "".join("-" if char in '\\/:*?"<>|' else char for char in subject)
    return value[:80] or "mail"
