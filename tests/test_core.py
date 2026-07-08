from pathlib import Path
from email.message import EmailMessage
import json
import os
import tempfile
import time
import unittest

from resume_sender.cleanup import cleanup_once_files
from resume_sender.clipboard import read_saved_ai_prompt, save_ai_prompt, save_clipboard_text
from resume_sender.config import AppConfig, Candidate, EmailConfig, OpenAIConfig, ResumeProfile, load_config
from resume_sender.email_builder import build_email, build_openai_body_prompt, clean_ai_body, ensure_body_greeting
from resume_sender.parser import find_posts_without_email, parse_job_posts
from resume_sender.preview import find_latest_preview, render_preview
from resume_sender.resume import choose_resume


class CoreFlowTest(unittest.TestCase):
    def test_ensure_body_greeting_normalizes_first_line(self) -> None:
        body = ensure_body_greeting("您好，\n\n我是张三。")
        self.assertTrue(body.startswith("hr您好："))
        self.assertNotIn("您好，", body.splitlines()[0])

    def test_ensure_body_greeting_inserts_when_missing(self) -> None:
        body = ensure_body_greeting("我是张三。")
        self.assertTrue(body.startswith("hr您好：\n我是张三。"))

    def test_find_latest_preview_returns_newest_eml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox_dir = Path(temp_dir) / "outbox"
            older = outbox_dir / "old" / "mail.eml"
            newer = outbox_dir / "new" / "mail.eml"
            older.parent.mkdir(parents=True)
            newer.parent.mkdir(parents=True)
            older.write_text("old", encoding="utf-8")
            newer.write_text("new", encoding="utf-8")
            old_time = time.time() - 60
            new_time = time.time()
            os.utime(older, (old_time, old_time))
            os.utime(newer, (new_time, new_time))

            self.assertEqual(find_latest_preview(outbox_dir), newer)

    def test_render_preview_decodes_eml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            message = EmailMessage()
            message["From"] = "me@example.com"
            message["To"] = "hr@example.com"
            message["Subject"] = "测试标题"
            message.set_content("您好，这是正文。")
            message.add_attachment(
                b"pdf",
                maintype="application",
                subtype="pdf",
                filename="resume.pdf",
            )
            path = Path(temp_dir) / "mail.eml"
            path.write_bytes(message.as_bytes())

            preview = render_preview(path)

        self.assertIn("测试标题", preview)
        self.assertIn("您好，这是正文。", preview)
        self.assertIn("resume.pdf", preview)

    def test_save_clipboard_text_writes_inbox_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = save_clipboard_text(Path(temp_dir), "岗位：测试\n邮箱：hr@example.com")

            self.assertEqual(path.name, "clipboard.txt")
            self.assertEqual(path.parent.name, "inbox")
            self.assertIn("hr@example.com", path.read_text(encoding="utf-8"))

    def test_save_clipboard_text_rejects_empty_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                save_clipboard_text(Path(temp_dir), "  ")

    def test_save_and_read_ai_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)

            save_ai_prompt(base_dir, "请强调脉冲 Web3 交易所经历")

            self.assertEqual(read_saved_ai_prompt(base_dir), "请强调脉冲 Web3 交易所经历")

    def test_find_posts_without_email_for_web_apply_jd(self) -> None:
        text = """
美团Keeta中东配送商业分析实习生
岗位职责:
1. 进行业务经营数据建设工作，包括数据提取、看板构建等工作。
岗位要求:
1. 有管理咨询、O2O、电商、即时配送物流等相关行业商业分析实习经验。
【投递方式】
streetintern.com
https://mp.weixin.qq.com/s/P1E5bCl-u_AbYBZsW3nbig
""".strip()

        self.assertEqual(parse_job_posts(text), [])
        self.assertEqual(find_posts_without_email(text), ["美团Keeta中东配送商业分析实习生"])

    def test_build_openai_body_prompt_includes_extra_instruction(self) -> None:
        text = "岗位：Web3 产品实习生\n职责：交易所业务分析、用户增长。\n邮箱：hr@example.com"
        post = parse_job_posts(text)[0]
        config = _config()
        match = choose_resume(post.raw_text, config.resumes)

        prompt = build_openai_body_prompt(
            config,
            post,
            match,
            resume_text="脉冲计算科技 Web3 交易所业务分析经历",
            ai_prompt="可以强调我在脉冲 Web3 交易所的经历符合 JD 要求的 Web3",
        )

        self.assertIn("本次额外写作提示", prompt)
        self.assertIn("脉冲 Web3 交易所", prompt)
        self.assertIn("不编造经历", prompt)

    def test_cleanup_removes_old_once_files_but_keeps_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            old_outbox_dir = base_dir / "outbox" / "old-run"
            old_outbox_dir.mkdir(parents=True)
            old_outbox_file = old_outbox_dir / "preview.eml"
            old_outbox_file.write_text("mail", encoding="utf-8")
            old_inbox_file = base_dir / "inbox" / "today.txt"
            old_inbox_file.parent.mkdir()
            old_inbox_file.write_text("jd", encoding="utf-8")
            resume_file = base_dir / "resumes" / "template.pdf"
            resume_file.parent.mkdir()
            resume_file.write_text("resume", encoding="utf-8")

            old_time = time.time() - 8 * 24 * 60 * 60
            for path in (old_outbox_file, old_outbox_dir, old_inbox_file, old_inbox_file.parent, resume_file):
                os.utime(path, (old_time, old_time))

            result = cleanup_once_files(base_dir, days=7)

            self.assertFalse(old_outbox_file.exists())
            self.assertFalse(old_inbox_file.exists())
            self.assertTrue(resume_file.exists())
            self.assertIn(str(old_outbox_file.resolve()), result.removed_files)

    def test_clean_ai_body_removes_markdown(self) -> None:
        body = clean_ai_body("一、**行业研究能力**：使用 `Python` 完成分析\n- **竞品对标**：输出报告")
        self.assertNotIn("*", body)
        self.assertNotIn("`", body)
        self.assertIn("1. 行业研究能力", body)
        self.assertIn("2. 竞品对标", body)
        self.assertIn("行业研究能力", body)
        self.assertIn("Python", body)

    def test_bailian_provider_sets_default_base_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "candidate": {
                            "name": "张三",
                            "school": "示例大学",
                            "major": "金融学",
                            "grade": "研一",
                            "availability": "随时到岗",
                            "duration": "6个月及以上",
                        },
                        "email": {
                            "smtp_host": "smtp.example.com",
                            "smtp_port": 465,
                            "use_ssl": True,
                            "username": "me@example.com",
                            "password_env": "SMTP_PASSWORD",
                            "from_name": "张三",
                        },
                        "openai": {
                            "enabled": True,
                            "provider": "bailian",
                            "model": "qwen-plus",
                            "api_key_env": "DASHSCOPE_API_KEY",
                        },
                        "resumes": [
                            {
                                "id": "business_analysis",
                                "label": "商业分析",
                                "path": "ba.pdf",
                                "keywords": ["商业分析"],
                                "summary": "商业分析摘要",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.openai.base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.assertEqual(config.candidate.weekly_attendance, "每周到岗5天")

    def test_parse_match_and_build_email(self) -> None:
        text = """
【商业分析实习生】
岗位职责：负责经营分析、指标体系搭建、SQL 取数和周报输出。
投递邮箱：ba@example.com

岗位：AI产品经理实习生
职责：参与大模型应用、用户调研、PRD、原型设计。
邮件标题：岗位名称-姓名-学校-最快到岗时间-实习时长
附件命名：岗位名称-姓名-学校.pdf
邮箱：pm@example.com
""".strip()
        posts = parse_job_posts(text)
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0].title, "商业分析实习生")
        self.assertEqual(posts[1].title, "AI产品经理实习生")

        config = _config()
        match = choose_resume(posts[1].raw_text, config.resumes)
        self.assertEqual(match.resume.id, "ai_product_manager")

        built = build_email(config, posts[1], match)
        self.assertEqual(built.subject, "AI产品经理实习生-张三-示例大学-随时到岗-6个月及以上")
        self.assertEqual(built.attachment_name, "AI产品经理实习生-张三-示例大学.pdf")
        self.assertIn("AI产品经理实习生", built.body)
        self.assertTrue(built.body.startswith("hr您好："))

    def test_subject_uses_attachment_format_when_subject_format_is_missing(self) -> None:
        text = """
百度|大模型商业分析实习生 base北京
工作职责：行业研究、战略分析、商业模式研究。
请把简历命名为【大模型商分-姓名-学校-专业-年级-实习时间】发送到recruiting@example.com
""".strip()
        post = parse_job_posts(text)[0]
        config = _config()
        match = choose_resume(post.raw_text, config.resumes)

        built = build_email(config, post, match)

        self.assertEqual(built.subject, "大模型商分-张三-示例大学-金融学-研一-6个月及以上")
        self.assertEqual(built.attachment_name, "大模型商分-张三-示例大学-金融学-研一-6个月及以上.pdf")

    def test_title_skips_section_headers(self) -> None:
        text = """
深圳头部互联网银行招聘AI产品运营日常实习生
【岗位职责】
1、协助产品运营的基础工作，包括用户调研、需求分析、需求文档撰写。
【岗位要求】
有 web3 相关经验优先
【邮件投递】recruiting@example.com
""".strip()

        post = parse_job_posts(text)[0]

        self.assertEqual(post.title, "AI产品运营日常实习生")

    def test_title_skips_work_location_section_header(self) -> None:
        text = """
深圳头部互联网银行招聘AI产品运营日常实习生
【岗位职责】
协助产品运营、用户调研、需求分析。
【岗位要求】
有 web3 相关经验优先
【工作地】深圳前海
【到岗工作】尽快到岗，一周工作至少4天。
【邮件投递】oliviaguan@example.com
""".strip()

        post = parse_job_posts(text)[0]

        self.assertEqual(post.title, "AI产品运营日常实习生")

    def test_title_drops_forwarding_note_and_company_prefix(self) -> None:
        text = """
（帮组内招实习生）携程-产品实习生（国际）
岗位职责：支持国际产品需求分析和用户调研。
投递邮箱：recruiting@example.com
""".strip()

        post = parse_job_posts(text)[0]

        self.assertEqual(post.title, "产品实习生（国际）")

    def test_format_replaces_job_duty_placeholder_with_title(self) -> None:
        text = """
海外线下业务 GTM 实习生
岗位职责：支持海外线下业务增长。
请将简历命名为【岗位职责-姓名-学校-专业-年级】发送至recruiting@example.com
""".strip()
        post = parse_job_posts(text)[0]
        config = _config()
        match = choose_resume(post.raw_text, config.resumes)

        built = build_email(config, post, match)

        self.assertEqual(built.subject, "海外线下业务GTM实习生-张三-示例大学-金融学-研一")
        self.assertEqual(built.attachment_name, "海外线下业务GTM实习生-张三-示例大学-金融学-研一.pdf")
        self.assertIn("海外线下业务GTM实习生", built.body)

    def test_subject_format_fills_loose_x_placeholders(self) -> None:
        text = """
AI产品运营日常实习生
岗位职责：支持用户调研、需求分析和产品运营。
邮件标题：姓名-学校-大x-一周x天-实习x个月
附件命名：岗位名称-姓名-学校-每周到岗x天-x个月
邮箱：recruiting@example.com
""".strip()
        post = parse_job_posts(text)[0]
        config = _config()
        match = choose_resume(post.raw_text, config.resumes)

        built = build_email(config, post, match)

        self.assertEqual(built.subject, "张三-示例大学-研一-一周5天-实习6个月及以上")
        self.assertEqual(built.attachment_name, "AI产品运营日常实习生-张三-示例大学-每周到岗5天-6个月及以上.pdf")

    def test_title_format_with_literal_prefix_is_filled_for_subject_and_attachment(self) -> None:
        text = """
产品经理实习生
岗位职责
1、负责门店履约全链路优化。
投递：简历至zhangmingqing062@hellobike.com，标题格式【实习】姓名-学校-年级
""".strip()
        post = parse_job_posts(text)[0]
        config = _config()
        match = choose_resume(post.raw_text, config.resumes)

        built = build_email(config, post, match)

        self.assertEqual(post.subject_format, "【实习】姓名-学校-年级")
        self.assertIsNone(post.attachment_format)
        self.assertEqual(built.subject, "【实习】张三-示例大学-研一")
        self.assertEqual(built.attachment_name, "【实习】张三-示例大学-研一.pdf")


def _config() -> AppConfig:
    base_dir = Path(tempfile.gettempdir())
    return AppConfig(
        base_dir=base_dir,
        candidate=Candidate(
            name="张三",
            school="示例大学",
            major="金融学",
            grade="研一",
            availability="随时到岗",
            weekly_attendance="每周到岗5天",
            duration="6个月及以上",
        ),
        email=EmailConfig(
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
            username="me@example.com",
            password_env="SMTP_PASSWORD",
            from_name="张三",
        ),
        openai=OpenAIConfig(enabled=False, model="gpt-4.1-mini", api_key_env="OPENAI_API_KEY"),
        resumes=[
            ResumeProfile(
                id="business_analysis",
                label="商业分析",
                path=base_dir / "ba.pdf",
                keywords=["商业分析", "经营分析", "指标体系", "SQL"],
                summary="商业分析摘要",
            ),
            ResumeProfile(
                id="ai_product_manager",
                label="AI产品经理",
                path=base_dir / "pm.pdf",
                keywords=["AI产品", "产品经理", "大模型", "用户调研", "PRD", "原型"],
                summary="AI产品经理摘要",
            ),
        ],
    )


if __name__ == "__main__":
    unittest.main()
