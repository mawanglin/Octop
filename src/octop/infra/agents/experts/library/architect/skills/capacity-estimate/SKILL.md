---
name: capacity-estimate
description: "容量和可用性估算：capacity.py 的 estimate 由日活、人均请求数、峰值系数、读写比例、响应和记录大小、保留期、副本数、单节点 QPS、余量推算平均和峰值 QPS、读写峰值、出口带宽、每天新增和总存储、应用节点数（含 N+1 冗余）、热数据缓存，并可对比一年后增长；sla 把几个九换算成每天、每月、每年允许停机的时间；compose 计算串联和并联后的整体可用性。每个假设都列在结果里。做方案设计、选型、评审容量余量时使用。"
metadata:
  octop:
    emoji: "🧮"
    label:
      zh: "容量估算"
      en: "Capacity Estimate"
    summary:
      zh: "由用户量推算 QPS、带宽、存储和节点数，换算可用性和停机时间。"
      en: "Derive QPS, bandwidth, storage and node counts from user numbers; convert availability to downtime."
---

# 容量和可用性估算

> `scripts/` 路径相对于本技能目录。

估算是为了**知道量级**：是每秒几十次还是几万次，是几十 GB 还是几十 TB。量级不同，架构完全不同。它不是承诺，真实容量靠压测。

## 1. 容量估算

```bash
python scripts/capacity.py estimate --dau 100000
python scripts/capacity.py estimate --dau 500000 --requests-per-user 40 --peak-factor 5 --read-ratio 0.8 \
    --payload-kb 20 --record-kb 4 --retention-days 180 --qps-per-node 300 --growth 1.0
python scripts/capacity.py estimate --dau 100000 --json
```

| 参数 | 含义 | 默认 | 怎么定 |
|------|------|------|--------|
| `--dau` | 日活用户数 | 必填 | 业务给的目标，或现有数据乘以增长 |
| `--requests-per-user` | 人均每天请求数 | 20 | 看同类产品或埋点；移动端 App 通常 20～100 |
| `--peak-factor` | 峰值 QPS ÷ 平均 QPS | 3 | 工具类 2～3，有早晚高峰 3～5，有整点活动或秒杀 10 以上 |
| `--read-ratio` | 读请求占比 | 0.9 | 内容类 0.9～0.99，交易类 0.7～0.8 |
| `--payload-kb` | 平均响应大小 | 5 | 看真实接口；带图片或大列表会大很多 |
| `--writes-per-user` | 人均每天写入条数 | 请求数 ×（1−读占比） | 有明确数据时直接给 |
| `--record-kb` | 单条记录大小 | 2 | 含索引前的行大小；日志类可能很大 |
| `--retention-days` | 数据保留天数 | 365 | 合规或业务要求 |
| `--replicas` | 存储副本数 | 3 | 数据库主从加备份通常 2～3 |
| `--qps-per-node` | 单节点能扛的 QPS | 500 | **要压测**，别照抄；简单接口可上千，复杂业务只有几十 |
| `--headroom` | 预留余量 | 0.3 | 保证峰值时单节点不超过 70% 负载 |
| `--hot-ratio` | 热数据占每天新增的比例 | 0.2 | 缓存要放多少 |
| `--growth` | 一年后日活增长比例 | 0 | 0.5 表示增长 50%，会多输出一年后的结果 |

## 2. 结果怎么用

- **峰值 QPS**：决定应用节点数和数据库压力；数据库要单独评估（读写峰值、连接数、慢查询）。
- **带宽**：只算了出口响应，没算协议开销、压缩和回源；CDN 能分担静态资源。
- **存储**：已含副本，没算索引（通常再加 30%～100%）和备份；按 1.5～2 倍留余量。
- **节点数**：满足峰值的最少台数 + 至少 1 台冗余（N+1），坏一台峰值也能扛。
- **缓存**：只是热数据的粗估，实际看命中率和访问分布。
- 和现有资源对比：余量不到 30% 就该扩容，不要等到打满。

## 3. 可用性换算

```bash
python scripts/capacity.py sla                       # 常见目标 99% ~ 99.999%
python scripts/capacity.py sla 99.9 99.95
python scripts/capacity.py compose --serial 99.9,99.95,99.99
python scripts/capacity.py compose --serial 99.9 --parallel 99,99
```

- `sla`：每天、每月（30 天）、每年允许停机多久；
- `compose --serial`：缺一不可的部件**相乘**（应用、数据库、网络都得活着）；
- `compose --parallel`：互相冗余的部件，只要有一个活着就行：`1 − ∏(1 − 可用性)`；
- 两个同时给：并联组算作串联链里的一环。

**注意**

- 并联公式假设故障**互相独立**。共用机房、电源、网络、部署流水线、配置中心、同一个云账号时，实际要低很多；
- 先定义“什么算不可用”（哪些接口、多高错误率、多长响应时间），再谈几个九；
- 计划内维护算不算停机，要写进 SLA；
- 多数故障来自变更，不是硬件：灰度发布和快速回滚比多加一台机器更能提高可用性。

## 4. 交付时要说明

- 列出所有假设，标出哪些是用户给的、哪些是默认值或经验值；
- 说明估算的局限：不含数据库内部、突发流量、数据倾斜、冷启动；
- 建议上线前压测验证单节点 QPS，并在上线后用真实监控数据回头校准。
