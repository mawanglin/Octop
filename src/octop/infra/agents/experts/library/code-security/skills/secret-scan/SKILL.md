---
name: secret-scan
description: "密钥与危险写法扫描：secret_scan.py 扫描目录（跳过 .git、node_modules、虚拟环境、二进制和大文件），高风险：AWS / 腾讯云 / 阿里云 / GitHub / GitLab / Slack / Google / OpenAI / Anthropic 密钥、私钥内容、带密码的连接串、写死的密码 Token Secret（过滤 changeme、${VAR}、your_xxx 等占位符和环境变量读取）、已被 git 跟踪的敏感文件；中风险：未被 .gitignore 忽略的 .env / 私钥 / 证书 / 凭证文件，拼接 SQL、eval/exec、shell=True、os.system、pickle/yaml.load、innerHTML、child_process.exec、关闭证书校验；低风险：弱哈希、DEBUG=True、chmod 777、JWT。结果中的密钥打码，可导出 Excel，行尾 nosecret 注释可忽略。发版、开源、交付代码前或怀疑密钥泄露时使用。"
metadata:
  octop:
    emoji: "🔐"
    label:
      zh: "密钥扫描"
      en: "Secret Scan"
    summary:
      zh: "密钥泄露、敏感文件和危险写法分级扫描。"
      en: "Graded scan for leaked secrets, sensitive files and risky code."
---

# 密钥与危险写法扫描

> `scripts/` 路径相对于本技能目录。只读扫描，结果中的密钥会打码。

## 1. 运行

```bash
python scripts/secret_scan.py 项目目录 [-o outputs/security/扫描报告.xlsx] [--exclude "tests/fixtures/*,*.min.js"] [--min-level 中] [--json]
```

- 自动跳过 `.git`、`node_modules`、虚拟环境、构建产物、二进制文件和超过 2MB 的文件；
- 是 git 仓库时，额外检查敏感文件是否已经被 git 跟踪（已跟踪 = 已经进入历史，风险最高）；
- 有高 / 中风险时退出码为 3，可以放进 CI 作为门禁。

## 2. 检查项

| 严重程度 | 内容 |
|----------|------|
| 高 | 云厂商和平台密钥；私钥内容；带密码的数据库 / 消息队列连接串；写死的 password / token / secret / api_key；已被 git 跟踪的 .env、私钥、凭证文件 |
| 中 | 没被 .gitignore 忽略的敏感文件；拼接 SQL；eval / exec；`shell=True`、`os.system`；`pickle.loads`、不带 SafeLoader 的 `yaml.load`；`innerHTML` / `dangerouslySetInnerHTML`；`child_process.exec`；关闭证书校验 |
| 低 | MD5 / SHA1；`DEBUG = True`；`chmod 777`；代码里的 JWT 字符串 |

## 3. 处理误报

- 示例值、测试数据：行尾加 `# nosecret`（或 `// nosecret`），或用 `--exclude` 排除测试夹具目录；
- 占位符（`changeme`、`${DB_PASSWORD}`、`your_token_here`、`<password>`）和从环境变量读取的写法已自动忽略；
- 确认是误报的项在报告的"处理状态"列标注，便于复扫时核对。

## 4. 局限

基于规则匹配：会漏掉自定义格式的密钥和逻辑漏洞，也会把部分示例当成密钥。它适合做提交前和发版前的快速体检，不能替代代码审计和专业安全测试。
