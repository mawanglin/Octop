---
name: secure-coding
description: "安全修复指南：泄露密钥的处置顺序（作废重建 → 改为环境变量或密钥服务 → 清理 git 历史 → 检查访问日志），.env 和 .gitignore 规范，pre-commit 提交前扫描配置，常见危险写法的安全改法（参数化 SQL、subprocess 参数列表、safe_load、textContent 与 HTML 净化、证书校验、bcrypt/Argon2 口令哈希），OWASP Top 10 中常见问题的代码层检查要点（越权、注入、敏感数据暴露、依赖漏洞、日志脱敏）。修复扫描结果、制定团队安全规范时使用。"
metadata:
  octop:
    emoji: "🛡️"
    label:
      zh: "安全修复"
      en: "Secure Coding"
    summary:
      zh: "密钥处置、安全写法和提交前检查。"
      en: "Secret response, safe patterns and pre-commit checks."
---

# 安全修复指南

## 1. 密钥泄露处置顺序

1. **作废并重新生成**：到云平台 / 代码托管平台 / 第三方服务后台作废旧密钥，生成新的；
2. **改存放方式**：代码里改为读取环境变量或密钥管理服务，新密钥只放在部署环境；
3. **清理历史**（仓库已推送时）：交给「Git 版本管理助手」用 `git filter-repo` / BFG 清理，通知协作者重新克隆；
4. **查日志**：检查旧密钥在泄露期间的调用记录，确认是否被滥用。

公开仓库里出现过的密钥一律视为已泄露，即使只存在了几分钟。

## 2. .env 规范

```gitignore
.env
.env.*
!.env.example
*.pem
*.key
id_rsa*
credentials*.json
```

仓库里只放 `.env.example`（变量名 + 空值或说明），真实值通过部署平台注入。

## 3. 提交前自动检查（pre-commit）

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: secret-scan
        name: secret scan
        entry: python 工具路径/secret_scan.py . --min-level 高
        language: system
        pass_filenames: false
```

## 4. 危险写法的安全改法

| 问题 | 不安全 | 安全 |
|------|--------|------|
| SQL 注入 | `cur.execute(f"... WHERE name = '{q}'")` | `cur.execute("... WHERE name = %s", (q,))` |
| 命令注入 | `subprocess.run("ls " + path, shell=True)` | `subprocess.run(["ls", path], check=True)` |
| 反序列化 | `pickle.loads(data)` / `yaml.load(text)` | 用 JSON；`yaml.safe_load(text)` |
| XSS | `el.innerHTML = userInput` | `el.textContent = userInput`；必须渲染 HTML 时用 DOMPurify 净化 |
| 证书校验 | `requests.get(url, verify=False)` | 保持校验，自签名证书用 `verify="ca.pem"` |
| 口令存储 | `hashlib.md5(pwd)` | `bcrypt` / `argon2-cffi` / `hashlib.scrypt` |
| 动态代码 | `eval(text)` | `json.loads` / `ast.literal_eval` |

## 5. 代码层常见检查要点

- **越权**：按 id 查询资源时校验当前用户是否有权访问，不只校验"已登录"；
- **输入校验**：服务端校验类型、长度、范围，不信任前端校验；
- **敏感数据**：日志和错误信息不输出密码、Token、完整证件号；接口不返回不需要的敏感字段；
- **依赖漏洞**：定期运行 `pip-audit` / `npm audit`，及时升级有漏洞的依赖；
- **配置**：生产环境关闭 DEBUG、目录列表、详细错误页。
