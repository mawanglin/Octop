---
name: code-check
description: "代码自检：code_check.py 自动识别项目里的 Python / Node / Go / Rust / Java 工具链，依次运行语法检查、代码规范（ruff / flake8 / npm run lint / go vet / clippy）、类型检查（mypy / tsc）、测试（pytest / unittest / npm test / go test / cargo test / mvn test）和构建，汇总通过、失败、跳过并摘出关键报错；优先使用项目自己的虚拟环境，不修改源代码、不自动安装依赖。每次写完或改完代码、交付前使用。"
metadata:
  octop:
    emoji: "✅"
    label:
      zh: "代码自检"
      en: "Code Check"
    summary:
      zh: "自动跑语法、规范、类型、测试和构建并汇总报错。"
      en: "Runs syntax, lint, type, test and build checks and summarises failures."
---

# 代码自检

> `scripts/` 路径相对于本技能目录。

## 1. 运行

```bash
python scripts/code_check.py detect 项目目录          # 先看会运行哪些检查、缺哪些工具
python scripts/code_check.py run 项目目录             # 全部运行
python scripts/code_check.py run 项目目录 --only test # 只跑测试；可选 lint,type,test,build
python scripts/code_check.py run 项目目录 --stack node --tail 50 --json
```

| 技术栈 | 识别依据 | 运行的检查 |
|--------|----------|------------|
| Python | `.py` 文件、pyproject.toml、requirements.txt | 语法（内置）、ruff 或 flake8、mypy（项目配置了才跑）、pytest 或 unittest |
| Node | package.json | `lint`、`typecheck` / `type-check`、`test`、`build` 脚本；有 tsconfig.json 但没有类型检查脚本时跑 `tsc --noEmit` |
| Go | go.mod | `go vet ./...`、`go test ./...` |
| Rust | Cargo.toml | `cargo check`、`cargo clippy`（已安装时）、`cargo test` |
| Java | pom.xml、build.gradle | `mvnw` / `mvn test`、`gradlew` / `gradle test` |

- Python 优先使用项目目录下的 `.venv` / `venv` 解释器，否则用当前解释器；
- 包管理器按锁文件选择 pnpm / yarn / npm；
- 单项检查默认 600 秒超时（`--timeout`）；
- 退出码：0 没有失败，3 有失败或超时，1 输入错误或没识别到项目。

## 2. 读结果

- **失败**：显示输出的最后几行（`--tail`），前面出现的 error / failed 行也会摘出来。按报错修，修完再跑一次，直到没有失败。
- **跳过**：缺工具或依赖没装。跳过的项没有运行，**不能算通过**。告诉用户缺什么、怎么装（如 `pip install ruff pytest`、`npm install`），装好后再跑。
- **超时**：通常是测试在等网络、等输入或进入了监听模式（脚本已设置 `CI=1` 关闭大多数监听模式）。

## 3. 规则

- 交付时如实报告结果：哪些通过、哪些失败、哪些因为什么跳过；**没跑过的检查不要说"已通过"**。
- 不为了让检查通过而删测试、加 `# noqa` / `@ts-ignore` / `skip`、放宽类型；确实需要时说明原因。
- 项目自己有 `make check`、`npm run verify` 之类的统一命令时，以项目命令为准，本脚本作为补充。
- 纯静态网页没有可识别的工具链，用「网页小工具专家」的 `html_check.py` 检查。
