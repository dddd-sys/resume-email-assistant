from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

from .config import load_config
from .email_builder import build_email
from .mailer import prepare_outbox, send_emails
from .parser import parse_job_posts
from .resume import choose_resume


def main() -> None:
    parser = argparse.ArgumentParser(description="根据群消息自动生成并发送简历投递邮件。")
    parser.add_argument("--config", default="config.json", help="配置文件路径，默认 config.json")
    parser.add_argument("--messages", required=True, help="微信群消息文本文件路径")
    parser.add_argument("--outbox", default="outbox", help="预览输出目录，默认 outbox")
    parser.add_argument("--send", action="store_true", help="真正发送邮件；不加时只生成预览")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少条岗位消息，0 表示不限制")
    args = parser.parse_args()

    config = load_config(args.config)
    message_path = Path(args.messages).expanduser().resolve()
    if not message_path.exists():
        raise SystemExit(f"找不到消息文件：{message_path}")

    text = message_path.read_text(encoding="utf-8")
    posts = parse_job_posts(text)
    if args.limit:
        posts = posts[: args.limit]
    if not posts:
        raise SystemExit("没有从消息中识别到包含邮箱的岗位信息。")

    built_emails = []
    for post in posts:
        match = choose_resume(post.raw_text, config.resumes)
        built_emails.append(build_email(config, post, match))

    records = prepare_outbox(config, built_emails, Path(args.outbox).expanduser().resolve())
    print(json.dumps(records, ensure_ascii=False, indent=2))

    missing_attachments = [item for item in records if not item["attachment_exists"]]
    if missing_attachments:
        print("\n警告：有简历附件源文件不存在，已生成邮件预览但没有附上 PDF。", file=sys.stderr)
        if args.send:
            raise SystemExit("存在缺失附件，已取消发送。请先检查 config.json 中的简历路径。")

    if args.send:
        send_emails(config, built_emails)
        print(f"\n已发送 {len(built_emails)} 封邮件。")
    else:
        print(f"\n预览已生成，共 {len(built_emails)} 封。确认无误后可加 --send 发送。")
