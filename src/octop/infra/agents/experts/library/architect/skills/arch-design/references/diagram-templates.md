# 架构图模板（Mermaid）

把 `［…］` 里的内容换成真实名称。Mermaid 可在 Markdown 预览、GitHub、Gitea、多数文档工具里直接渲染。

## 1. 系统上下文图

回答“这个系统和谁交互”。系统只画一个框。

```mermaid
flowchart LR
    user(["顾客<br/>下单、支付"])
    ops(["运营人员<br/>管理商品和活动"])
    sys["［商城系统］<br/>提供下单、支付、订单查询"]
    pay[["［支付平台］<br/>（外部）"]]
    sms[["［短信服务］<br/>（外部）"]]
    erp[["［ERP］<br/>（外部，同步库存）"]]
    user -->|HTTPS| sys
    ops -->|HTTPS| sys
    sys -->|下单、回调| pay
    sys -->|验证码、通知| sms
    sys <-->|库存、订单同步| erp
```

## 2. 容器图

回答“系统由哪些可部署单元组成”。线上写协议。

```mermaid
flowchart TB
    subgraph clients["客户端"]
        web["Web 前端<br/>React"]
        app["移动 App"]
    end
    subgraph backend["后端（K8s 集群）"]
        gw["API 网关<br/>鉴权、限流"]
        order["订单服务<br/>Python / FastAPI"]
        user["用户服务"]
        worker["异步任务<br/>积分、短信"]
    end
    db[("PostgreSQL<br/>订单、用户")]
    cache[("Redis<br/>缓存、会话")]
    mq{{"RabbitMQ<br/>订单事件"}}
    oss[("对象存储<br/>图片、附件")]
    web -->|HTTPS/JSON| gw
    app -->|HTTPS/JSON| gw
    gw --> order
    gw --> user
    order -->|SQL| db
    order -->|读写缓存| cache
    order -->|发布事件| mq
    mq -->|消费| worker
    worker -->|SQL| db
    user -->|SQL| db
    order -->|预签名上传| oss
```

## 3. 组件图（一个容器的内部）

```mermaid
flowchart LR
    api["接口层<br/>路由、参数校验"] --> svc["业务层<br/>订单规则、状态机"]
    svc --> repo["数据访问层<br/>仓储"]
    svc --> evt["事件发布"]
    svc --> ext["外部适配器<br/>支付、库存"]
    repo --> db[("数据库")]
    evt --> mq{{"消息队列"}}
```

依赖方向只能从上到下；如果箭头出现回头，就是分层问题。

## 4. 时序图（关键流程，含失败分支）

```mermaid
sequenceDiagram
    autonumber
    actor U as 顾客
    participant G as API 网关
    participant O as 订单服务
    participant S as 库存服务
    participant P as 支付平台
    participant Q as 消息队列
    U->>G: 提交订单
    G->>O: 创建订单（已鉴权）
    O->>S: 锁定库存
    alt 库存不足
        S-->>O: 失败
        O-->>U: 提示库存不足
    else 库存足够
        S-->>O: 已锁定
        O-->>U: 返回支付链接
        U->>P: 完成支付
        P-->>O: 支付回调（验签）
        O->>O: 订单置为已支付（幂等）
        O->>Q: 发布“订单已支付”事件
        O-->>P: 返回 200
    end
```

要点：标出同步和异步（实线和虚线）、鉴权位置、失败分支、幂等位置。

## 5. 部署图

```mermaid
flowchart TB
    internet(("互联网")) --> lb["负载均衡<br/>HTTPS 终结"]
    subgraph az1["可用区 A"]
        app1["应用 ×2"]
        db1[("数据库主")]
    end
    subgraph az2["可用区 B"]
        app2["应用 ×2"]
        db2[("数据库从")]
    end
    lb --> app1
    lb --> app2
    app1 --> db1
    app2 --> db1
    db1 -. 同步复制 .-> db2
```

## 6. 数据流图（数据去哪了，合规评审常用）

```mermaid
flowchart LR
    form["用户填写<br/>姓名、手机号"] -->|TLS| api["接口"]
    api -->|加密存储| db[("用户库")]
    api -->|脱敏后| log["日志"]
    db -->|每日脱敏导出| dw[("数据仓库")]
    dw --> bi["报表"]
```

## 7. 画图检查清单

- [ ] 一张图只讲一件事，框不超过 15 个
- [ ] 每个框有名称和一句职责，外部系统用不同形状标出
- [ ] 每条线有方向，容器图的线标了协议
- [ ] 同步和异步区分清楚
- [ ] 有数据存储，有谁读谁写
- [ ] 关键安全边界（公网、内网、认证位置）画出来了
- [ ] 图和代码核对过，写明日期和版本
