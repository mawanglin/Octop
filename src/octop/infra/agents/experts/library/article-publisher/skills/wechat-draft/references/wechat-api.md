# 公众号接口说明

`wechat_draft.py` 用到的接口（地址前缀默认 `https://api.weixin.qq.com`，可用环境变量 `WECHAT_API_BASE` 改）。按微信开放文档编写；接口行为、限额和权限以官方文档和你的公众号后台为准，**没有在真实账号上验证过**。

| 步骤 | 接口 | 说明 |
|------|------|------|
| 取 token | `POST /cgi-bin/stable_token` | JSON：`grant_type=client_credential`、`appid`、`secret`；返回 `access_token` |
| 上传封面 | `POST /cgi-bin/material/add_material?access_token=…&type=image` | multipart 字段 `media`；返回永久素材的 `media_id`。`--cover-type thumb` 则 `type=thumb`（缩略图，大小限制更严） |
| 上传正文图片 | `POST /cgi-bin/media/uploadimg?access_token=…` | multipart 字段 `media`；返回微信域名下的图片 `url`，正文里的图片地址要替换成它 |
| 新建草稿 | `POST /cgi-bin/draft/add?access_token=…` | JSON：`articles[0]` 含 `title`、`author`、`digest`、`content`、`thumb_media_id`、`need_open_comment`；中文不转义；返回草稿 `media_id` |

## 前提

1. 公众号后台“设置与开发 → 基本配置”里拿到 AppID 和 AppSecret（AppSecret 只在重置时显示一次，妥善保存）；
2. 把运行本脚本的机器的**出口 IP** 加到 IP 白名单，否则报 40164；
3. 账号要有这些接口的权限。**未认证的个人订阅号通常没有草稿箱相关接口的权限**，会报 48001。这种情况改用 `render` 导出 HTML，到后台编辑器手动粘贴。

## 常见错误码

| 错误码 | 含义 | 处理 |
|--------|------|------|
| 40164 | IP 不在白名单 | 后台添加本机出口 IP（可用 `curl ifconfig.me` 查看；家庭宽带 IP 会变，换了要更新） |
| 40013 | AppID 不正确 | 核对 `WECHAT_APP_ID` |
| 40125 / 40001 | AppSecret 不正确或 token 无效 | 核对 `WECHAT_APP_SECRET`；Secret 被重置过要更新 |
| 42001 / 40014 | access_token 过期 | 脚本会自动重取一次 |
| 48001 | 接口没有权限 | 账号类型不支持；改手动粘贴 |
| 45009 | 调用次数超限 | 稍后再试 |
| 40005 / 40009 | 图片类型或大小不符合要求 | 换成 jpg/png，压缩体积后重试 |
| 45110 | 作者字数超限 | 缩短 `--author` |
| 45166 | 内容不合法 | 正文含不允许的标签或外链，退回写作专家 |

## 限制和提醒

- 正文里的外链在公众号里不可点击；参考来源的网址以文字形式出现在文末，读者可复制。
- 本脚本只存草稿。群发、定时发布和对外发布需要用户在后台操作。
- 同一个 AppID 的 access_token 全局有效期内取新 token 会让旧 token 失效；`stable_token` 接口避免了这个问题，但不要同时用别的工具频繁强制刷新。
- 微信的字数、图片大小等限制会调整，格式检查里的数值是经验值，发布前以后台提示为准。
