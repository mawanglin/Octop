# Mermaid 语法速查（v11）

## 流程图 flowchart

```mermaid
flowchart TD
  a([开始]) --> b[步骤]
  b --> c{判断？}
  c -->|是| d[(数据库)]
  c -->|否| e[[子流程]]
  e -.->|重试| b
  d ==> f[/输出报表/]
  f --> z([结束])
  classDef key fill:#fff2cc,stroke:#d6b656
  class c key
```

方向：`TD`/`TB` 上→下，`LR` 左→右，`BT`、`RL` 反向。
子图：`subgraph id["标题"] ... end`；子图内可写 `direction LR`。
多目标：`a --> b & c`。注释：`%% 这是注释`。

## 时序图 sequenceDiagram

```mermaid
sequenceDiagram
  autonumber
  actor U as 用户
  participant W as 前端
  participant S as 服务端
  participant D as 数据库
  U->>W: 点击下单
  W->>S: POST /orders
  activate S
  S->>D: 写入订单
  D-->>S: OK
  alt 库存充足
    S-->>W: 201 已创建
  else 库存不足
    S-->>W: 409 库存不足
  end
  deactivate S
  Note over W,S: 超时 3 秒重试一次
```

箭头：`->>` 实线请求，`-->>` 虚线返回，`-x` 失败，`-)` 异步。
分组：`alt/else/end`、`opt/end`、`loop 条件/end`、`par/and/end`。

## 状态图 stateDiagram-v2

```mermaid
stateDiagram-v2
  [*] --> 待支付
  待支付 --> 已支付: 支付成功
  待支付 --> 已取消: 超时 30 分钟
  已支付 --> 已发货: 仓库出库
  已发货 --> 已完成: 确认收货
  已完成 --> [*]
  已取消 --> [*]
```

## 思维导图 mindmap

```mermaid
mindmap
  root((年度计划))
    增长
      新客获取
      老客复购
    效率
      流程自动化
    团队
      招聘
```

缩进决定层级；根节点 `root((文字))`。

## 甘特图 gantt

```mermaid
gantt
  title 项目排期
  dateFormat YYYY-MM-DD
  axisFormat %m-%d
  section 设计
    需求评审      :done, a1, 2026-10-01, 3d
    原型设计      :active, a2, after a1, 5d
  section 开发
    后端开发      :b1, after a2, 10d
    联调测试      :crit, b2, after b1, 5d
```

## ER 图 erDiagram

```mermaid
erDiagram
  USER ||--o{ ORDER : places
  ORDER ||--|{ ORDER_ITEM : contains
  USER {
    int id PK
    string name
  }
```

## 常见报错

| 现象 | 原因 | 修正 |
|------|------|------|
| `got 'STADIUMSTART'` / `Expecting ... got 'end'` | 用了关键字做节点 ID（`end`、`graph` 等） | 换成 `done`、`finish` |
| `Parse error ... got 'PS'` | 文字里有未加引号的括号 | 加双引号：`A["说明（备注）"]` |
| 文字里 `>` 消失 | ASCII 尖括号被当作标记 | 改用"超过"或 `＞` |
| 中文标点导致断行异常 | 文字过长 | 缩短到 15 字内，或用 `<br/>` 手动换行 |
| subgraph 连线位置混乱 | 跨泳道连线写在 subgraph 内部 | 跨泳道连线统一写在所有 subgraph 之后 |
