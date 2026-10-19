---
name: onboarding-doc
description: "上手文档与代码导读：推荐的阅读顺序（README → 依赖和脚本 → 入口 → 路由 / 命令 → 业务层 → 数据层 → 测试），追踪一条请求或命令的调用链并用“文件:行号”标注，上手指南模板（项目简介、技术栈、目录说明、本地运行、核心流程、模块关系图、常见改动入口、注意事项），回答“某功能在哪里实现”的查找方法（搜索关键词、路由表、测试用例反查）。写上手文档、给新人讲项目、定位功能时使用。"
metadata:
  octop:
    emoji: "🧭"
    label:
      zh: "上手文档"
      en: "Onboarding Doc"
    summary:
      zh: "阅读路线、调用链追踪和上手指南模板。"
      en: "Reading paths, call tracing and onboarding guides."
---

# 上手文档与代码导读

## 1. 阅读顺序

1. README、CONTRIBUTING、docs/：项目定位、运行方式、约定；
2. 依赖清单和脚本（`repo-scan` 的 scan 结果）：技术栈和常用命令；
3. 入口文件：main / app / server / index、CLI 入口；
4. 路由或命令注册：Web 框架的路由表、CLI 的子命令；
5. 业务层：service / domain / usecase；
6. 数据层：model / repository / migration；
7. 测试：测试用例是最好的"用法说明"。

## 2. 追踪一条调用链

选一个典型功能（如"用户登录"），从入口开始逐层记录：

```text
POST /api/auth/login
  → api/routers/auth.py:42  login()          参数校验
  → infra/users/manager.py:118  authenticate()  查用户、校验密码
  → infra/db/repos/users.py:76  get_by_username()  SQL
```

查找方法：搜索接口路径或界面文案 → 找到路由 → 跟函数调用；反过来也可以从测试用例或数据库表名反查。

## 3. 上手指南模板（保存为 `outputs/repo/上手指南.md`）

```markdown
# 项目上手指南

## 一句话介绍
## 技术栈（语言 / 框架 / 数据库 / 部署）
## 目录说明（只列重要的 8–12 个目录）
## 本地运行（安装、配置、启动、测试命令）
## 核心流程（1–3 条调用链，带文件:行号）
## 模块关系图（Mermaid）
## 常见改动从哪里下手（加接口、加页面、加配置、加表）
## 注意事项（约定、坑、敏感配置位置——不写真实密钥）
```

## 4. 回答"某功能在哪里"

- 先给结论：文件路径和行号；
- 再说调用关系：谁调用它、它调用谁；
- 最后提示相关测试和配置。不确定时列出 2–3 个候选位置，说明判断依据。
