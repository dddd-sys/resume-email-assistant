# 自动投递简历邮箱助手

这个项目用于把微信群里的岗位 JD 文本转换成可发送的求职邮件：

1. 从群消息文本中提取岗位、投递邮箱、邮件标题格式、附件命名格式。
2. 在三份简历中选择最匹配岗位 JD 的版本。
3. 根据 JD、候选人信息和简历亮点生成邮件正文。
4. 默认生成预览文件，确认后可通过 SMTP 发送邮件。

> 建议先用预览模式跑几次，确认解析和正文风格都符合你的预期后，再使用 `--send`。

## 快速开始

### 1. 准备配置

复制配置模板：

```bash
cp config.example.json config.json
```

然后编辑 `config.json`：

- 把 `candidate.major` 和 `candidate.grade` 改成你的专业和年级。
- 把三份简历 PDF 放到 `resumes/` 目录，并修改配置中的 `path`。
- 补充每份简历的 `keywords` 和 `summary`，匹配和正文生成会用到。
- 如果要发邮件，填写 SMTP 信息，并把邮箱授权码放进环境变量。

常见邮箱 SMTP：

- QQ 邮箱：`smtp.qq.com`，端口 `465`，通常需要邮箱授权码。
- 163 邮箱：`smtp.163.com`，端口 `465`，通常需要客户端授权码。
- Gmail：`smtp.gmail.com`，端口 `465`，通常需要应用专用密码。

### 2. 准备群消息文本

把微信群里某条或多条岗位消息复制到文本文件，例如：

```bash
mkdir -p inbox resumes
cp samples/group_messages.txt inbox/today.txt
```

你也可以直接把当天群消息复制到 `inbox/today.txt`。

### 3. 生成预览

```bash
python3 -m resume_sender --config config.json --messages inbox/today.txt
```

程序会在 `outbox/` 下生成：

- `.eml` 邮件预览文件
- 按 JD 要求或默认规则重命名后的简历 PDF
- `run_summary.json` 本次运行摘要

也可以直接从 macOS 剪贴板读取 JD：

```bash
python3 -m resume_sender --config config.json --from-clipboard
```

更省事的方式是复制微信群 JD 后运行：

```bash
./生成预览
```

这个脚本会读取剪贴板、保存到 `inbox/clipboard.txt`，并生成邮件预览。

打开最新 `.eml` 预览：

```bash
./查看预览
```

等同于：

```bash
python3 -m resume_sender --config config.json --latest-preview
```

如果系统没有可自动打开 `.eml` 的应用，程序会直接在终端显示邮件标题、收件人、正文和附件名。

### 4. 真正发送邮件

先设置授权码环境变量，名字要和 `config.json` 里的 `password_env` 一致：

```bash
export SMTP_PASSWORD="你的邮箱授权码"
python3 -m resume_sender --config config.json --messages inbox/today.txt --send
```

如果刚刚是用 `./生成预览` 生成的预览，确认无误后可以运行：

```bash
./确认发送
```

它会发送 `inbox/clipboard.txt` 对应的那条 JD，不会重新读取剪贴板，避免误发。

## 可选：使用阿里云百炼生成更贴合的正文

如果你希望邮件正文更自然、更贴合 JD，可以使用阿里云百炼的 OpenAI 兼容接口。在 `config.json` 中配置：

```json
"openai": {
  "enabled": true,
  "provider": "bailian",
  "model": "qwen-plus",
  "api_key_env": "DASHSCOPE_API_KEY",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
}
```

然后设置：

```bash
export DASHSCOPE_API_KEY="你的百炼 API Key"
```

如果没有设置 API Key、网络不可用或模型调用失败，程序会自动回退到本地模板生成正文。

如果你想换模型，只改 `model`，例如换成你在百炼控制台开通的其他通义模型。

生成正文时，程序会把自动选中的 PDF 简历文本一起提供给模型，让正文尽量结合真实项目、实习、工具和成果来写。每次运行的 `run_summary.json` 里会有 `body_source` 字段：

- `ai`：正文来自百炼模型。
- `local_template`：正文来自本地模板，通常是未设置 API Key 或模型调用失败。

## 默认标题和附件名规则

如果 JD 没有要求邮件标题，默认使用：

```text
岗位名称-姓名-学校-随时到岗-6个月及以上
```

如果 JD 没有要求附件命名，默认也使用同样格式，并加上 `.pdf` 后缀。

## 清理一次性文件

程序只会清理一次性文件夹：

- `inbox/`：复制进来的群消息文本。
- `outbox/`：生成的 `.eml` 预览、重命名 PDF 附件和摘要。

不会清理 `resumes/`，也就是不会删除最初的三份模板简历。

手动清理 7 天前的一次性文件：

```bash
python3 -m resume_sender --config config.json --cleanup-only --cleanup-days 7
```

先预览会清理多少文件，不实际删除：

```bash
python3 -m resume_sender --config config.json --cleanup-only --cleanup-days 7 --cleanup-dry-run
```

也可以在每次生成邮件前顺手清理 7 天前的一次性文件：

```bash
python3 -m resume_sender --config config.json --messages inbox/today.txt --cleanup-days 7
```

如果想让 macOS 每 7 天自动执行一次，可以用 `crontab -e` 加入类似下面这一行：

```cron
0 9 */7 * * cd "/Users/你的用户名/Documents/自动投简历邮箱" && /usr/bin/python3 -m resume_sender --config config.json --cleanup-only --cleanup-days 7
```

## 安全说明

- 默认不会发送邮件，只生成预览。
- 使用 `--send` 才会连接 SMTP 并发送。
- 不会自动读取微信数据库。建议使用复制群消息文本的方式，避免账号风险。
- 请避免对同一岗位重复发送；可以用 `outbox/run_summary.json` 核对本次处理记录。
