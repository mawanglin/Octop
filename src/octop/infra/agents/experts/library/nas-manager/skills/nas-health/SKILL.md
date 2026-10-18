---
name: nas-health
description: "NAS 健康巡检：nas_check.py smart 解读 smartctl -a 文本或 -j JSON 输出（机械盘看重映射/待映射/离线不可修复扇区、CRC 错误、温度、通电时间，NVMe 看已用寿命、备用块、介质错误、严重警告），按正常/关注/警告/危险分级并给出处理建议，序列号脱敏；nas_check.py capacity 统计容量，--record 记录历史并按线性增长预测到 90% 和写满的天数；含各 NAS 系统获取 SMART 的方法和巡检清单。检查硬盘健康、空间不够、做定期巡检时使用。"
metadata:
  octop:
    emoji: "🩺"
    label:
      zh: "硬盘与容量体检"
      en: "NAS Health"
    summary:
      zh: "SMART 分级解读和容量写满预测。"
      en: "Graded SMART reports and capacity forecasts."
---

# 硬盘与容量体检

> `scripts/` 和 `references/` 路径相对于本技能目录；示例：`references/example-smart-hdd.txt`（机械盘，有少量重映射扇区）、`references/example-smart-nvme.json`。

## 1. 获取 SMART 报告

| 系统 | 方法 |
|------|------|
| 飞牛 fnOS / Debian / Ubuntu | SSH 登录后 `sudo smartctl -a /dev/sda > sda.txt`；NVMe 用 `/dev/nvme0` |
| 群晖 DSM | 控制面板 → 终端机开启 SSH，`sudo smartctl -a -d sat /dev/sata1 > sata1.txt`（7.x 设备名为 sata1…） |
| 威联通 QTS | SSH 后 `smartctl -a -d sat /dev/sda`；也可在“存储与快照总管 → 磁盘健康”查看 |
| Unraid / TrueNAS | 网页界面的磁盘 SMART 页，或 SSH 运行 smartctl |
| USB 硬盘盒 | 加 `-d sat`，部分盒子不支持透传 SMART |

`smartctl --scan` 可列出所有硬盘；加 `-j` 输出 JSON 更稳。

## 2. 分析

```bash
python scripts/nas_check.py smart inbound/sda.txt inbound/nvme0.json
python scripts/nas_check.py smart --run          # 在 NAS 本机且有 root 权限时
```

| 等级 | 典型情况 | 建议 |
|------|----------|------|
| 正常 | 关键属性为 0，温度和寿命正常 | 按计划巡检 |
| 关注 | 少量重映射扇区、CRC 错误、温度偏高、通电超过 5 年、NVMe 寿命 ≥80% | 确认备份；1–2 周后复查是否增长；CRC 先换数据线 |
| 警告 | 待映射或不可修复扇区、重映射 ≥100、温度 ≥60°C、NVMe 介质错误 | 立即备份重要数据，准备更换 |
| 危险 | SMART 自检 FAILED、NVMe 备用块低于阈值 | 停止写入，优先抢救数据，尽快更换 |

单次报告只能看到现状，**数值是否在增长**更重要：同一块盘隔一两周再取一次对比。

## 3. 容量预测

```bash
python scripts/nas_check.py capacity /vol1 /vol2 --history outputs/nas/容量记录.csv --record
```

每周记录一次（可用定时任务），积累 7 天以上后输出平均每天增长量、到 90% 和写满的天数。使用率超过 80% 时，RAID 重建和快照都可能受影响，应提前清理或扩容。

## 4. 月度巡检清单

- [ ] 所有硬盘 SMART 等级，与上月对比关键属性
- [ ] 存储池 / RAID 状态正常，无降级
- [ ] 容量使用率和预测
- [ ] 最近一次备份成功的时间，抽查恢复一个文件
- [ ] 系统和套件 / 容器镜像是否有安全更新
- [ ] UPS 电池状态、风扇和温度
