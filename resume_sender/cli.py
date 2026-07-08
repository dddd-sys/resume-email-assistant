from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

from .cleanup import cleanup_once_files, format_cleanup_result
from .clipboard import read_clipboard_text, read_saved_ai_prompt, save_ai_prompt, save_clipboard_text
from .config import load_config
from .email_builder import build_email
from .mailer import prepare_outbox, send_emails
from .parser import find_posts_without_email, parse_job_posts
from .preview import find_latest_preview, open_preview, render_preview
from .resume import choose_resume


def main() -> None:
    parser = argparse.ArgumentParser(description="根据群消息自动生成并发送简历投递邮件。")
    parser.add_argument("--config", default="config.json", help="配置文件路径，默认 config.json")
    parser.add_argument("--messages", help="微信群消息文本文件路径")
    parser.add_argument("--from-clipboard", action="store_true", help="从 macOS 剪贴板读取 JD 并保存到 inbox/clipboard.txt")
    parser.add_argument("--outbox", default="outbox", help="预览输出目录，默认 outbox")
    parser.add_argument("--send", action="store_true", help="真正发送邮件；不加时只生成预览")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少条岗位消息，0 表示不限制")
    parser.add_argument("--cleanup-days", type=int, default=None, help="清理多少天前的一次性文件，例如 7")
    parser.add_argument("--cleanup-only", action="store_true", help="只执行清理，不生成邮件")
    parser.add_argument("--cleanup-dry-run", action="store_true", help="只展示会清理的数量，不实际删除")
    parser.add_argument("--latest-preview", action="store_true", help="打开最新生成的 .eml 邮件预览")
    parser.add_argument("--ai-prompt", default="", help="本次生成邮件时额外交给 AI 的写作提示词")
    parser.add_argument(
        "prompt_words",
        nargs="*",
        help="本次生成邮件时额外交给 AI 的写作提示词，可直接写在命令末尾",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    ai_prompt = " ".join([args.ai_prompt.strip(), " ".join(args.prompt_words).strip()]).strip()

    if args.latest_preview:
        try:
            preview_path = find_latest_preview(Path(args.outbox).expanduser().resolve())
            opened = open_preview(preview_path)
            print(render_preview(preview_path))
        except FileNotFoundError as exc:
            raise SystemExit(str(exc)) from exc
        if opened:
            print(f"\n已尝试打开最新预览：{preview_path}")
        else:
            print(f"\n系统没有可自动打开 .eml 的应用，已在终端显示预览内容：{preview_path}")
        return

    if args.cleanup_days is not None:
        cleanup_result = cleanup_once_files(config.base_dir, args.cleanup_days, dry_run=args.cleanup_dry_run)
        print(format_cleanup_result(cleanup_result, dry_run=args.cleanup_dry_run))
        if args.cleanup_only:
            return

    if args.cleanup_only:
        raise SystemExit("--cleanup-only 需要同时指定 --cleanup-days。")

    if args.from_clipboard:
        try:
            clipboard_text = read_clipboard_text()
            message_path = save_clipboard_text(config.base_dir, clipboard_text)
            prompt_path = save_ai_prompt(config.base_dir, ai_prompt)
        except (RuntimeError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
        print(f"已从剪贴板读取 JD，并保存到：{message_path}")
        if ai_prompt:
            print(f"已保存本次 AI 提示词：{prompt_path}")
    elif args.messages:
        message_path = Path(args.messages).expanduser().resolve()
        if not ai_prompt and message_path.name == "clipboard.txt":
            ai_prompt = read_saved_ai_prompt(config.base_dir)
    else:
        raise SystemExit("生成邮件需要指定 --messages；如果只清理，请使用 --cleanup-only --cleanup-days 7。")

    if not message_path.exists():
        raise SystemExit(f"找不到消息文件：{message_path}")

    text = message_path.read_text(encoding="utf-8")
    posts = parse_job_posts(text)
    if args.limit:
        posts = posts[: args.limit]
    if not posts:
        missing_email_titles = find_posts_without_email(text)
        if missing_email_titles:
            title_text = "、".join(missing_email_titles[:3])
            raise SystemExit(
                f"识别到岗位「{title_text}」，但没有找到投递邮箱，无法生成邮件。\n"
                "这类 JD 可能是网页投递。请复制包含邮箱的 JD，或手动补一行：投递邮箱：xxx@example.com"
            )
        raise SystemExit("没有从消息中识别到包含邮箱的岗位信息。")

    built_emails = []
    for post in posts:
        match = choose_resume(post.raw_text, config.resumes)
        built_emails.append(build_email(config, post, match, ai_prompt=ai_prompt))

    records = prepare_outbox(config, built_emails, Path(args.outbox).expanduser().resolve())
    print(json.dumps(records, ensure_ascii=False, indent=2))

    missing_attachments = [item for item in records if not item["attachment_exists"]]
    if missing_attachments:
        print("\n警告：有简历附件源文件不存在，已生成邮件预览但没有附上 PDF。", file=sys.stderr)
        if args.send:
            raise SystemExit("存在缺失附件，已取消发送。请先检查 config.json 中的简历路径。")

    if ai_prompt and any(item.get("body_source") != "ai" for item in records):
        print("\n提示：本次写了额外 AI 提示词，但正文没有使用 AI 生成；请检查 DASHSCOPE_API_KEY 是否已设置。", file=sys.stderr)

    if args.send:
        send_emails(config, built_emails)
        print(f"\n已发送 {len(built_emails)} 封邮件。")
    else:
        print(f"\n预览已生成，共 {len(built_emails)} 封。确认无误后可加 --send 发送。")
