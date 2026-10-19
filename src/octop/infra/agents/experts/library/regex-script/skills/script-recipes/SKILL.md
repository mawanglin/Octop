---
name: script-recipes
description: "办公脚本模板：Python / PowerShell / Bash 三种写法的批量重命名（带预览和撤销记录）、按扩展名或日期整理文件、批量替换文件内容、合并多个 CSV / Excel、按列拆分表格、批量转换编码（GBK 转 UTF-8）、定时备份目录（压缩、保留最近 N 份），以及定时任务配置（Windows 任务计划程序、Linux/macOS cron）；脚本安全约定（默认 --dry-run、先备份、路径带空格和中文的处理、错误时退出）。写办公自动化小脚本时使用。"
metadata:
  octop:
    emoji: "📜"
    label:
      zh: "脚本模板"
      en: "Script Recipes"
    summary:
      zh: "批量改名、整理文件、合并表格和定时备份。"
      en: "Batch renames, file tidying, merging sheets, backups."
---

# 办公脚本模板

## 1. 安全约定

- 默认预览：脚本带 `--dry-run`（或 PowerShell 的 `-WhatIf`），先打印将要做什么，确认后去掉参数再执行；
- 先备份要处理的目录，先在几个文件上试；
- 路径用引号包起来，支持空格和中文；遇到错误立即停止（Bash `set -euo pipefail`，PowerShell `$ErrorActionPreference = "Stop"`）。

## 2. 批量重命名（Python，跨平台，推荐）

```python
"""把 照片 (1).jpg 这类文件改名为 2026-旅行-001.jpg；默认只预览，加 --apply 才执行。"""
import argparse, csv, pathlib, re

p = argparse.ArgumentParser()
p.add_argument("folder"); p.add_argument("--prefix", default="2026-旅行"); p.add_argument("--apply", action="store_true")
a = p.parse_args()
files = sorted(f for f in pathlib.Path(a.folder).iterdir() if f.is_file() and f.suffix.lower() in {".jpg", ".png"})
plan = [(f, f.with_name(f"{a.prefix}-{i:03d}{f.suffix.lower()}")) for i, f in enumerate(files, 1)]
for src, dst in plan:
    print(f"{src.name} -> {dst.name}")
if a.apply:
    with open(pathlib.Path(a.folder) / "rename-log.csv", "w", newline="", encoding="utf-8-sig") as log:
        w = csv.writer(log); w.writerow(["原名", "新名"])
        for src, dst in plan:
            if dst.exists():
                print(f"跳过：{dst.name} 已存在"); continue
            src.rename(dst); w.writerow([src.name, dst.name])
```

改名记录 `rename-log.csv` 可以用来撤销。

## 3. PowerShell（Windows）

```powershell
# 批量把 .txt 改成 .md，先用 -WhatIf 预览
Get-ChildItem "D:\笔记" -Filter *.txt | Rename-Item -NewName { $_.BaseName + ".md" } -WhatIf

# GBK 文本转 UTF-8（另存到新目录）
Get-ChildItem "D:\旧文本" -Filter *.txt | ForEach-Object {
  $text = [IO.File]::ReadAllText($_.FullName, [Text.Encoding]::GetEncoding("GBK"))
  [IO.File]::WriteAllText("D:\新文本\$($_.Name)", $text, [Text.UTF8Encoding]::new($false))
}
```

## 4. Bash（Linux / macOS / 飞牛等 NAS）

```bash
#!/usr/bin/env bash
set -euo pipefail
# 每天备份目录，保留最近 7 份
src="/vol1/文档"; dst="/vol2/备份"; mkdir -p "$dst"
tar -czf "$dst/文档-$(date +%Y%m%d).tar.gz" -C "$(dirname "$src")" "$(basename "$src")"
ls -1t "$dst"/文档-*.tar.gz | tail -n +8 | xargs -r rm --
```

## 5. 合并多个 Excel / CSV（Python + openpyxl）

```python
import pathlib
from openpyxl import Workbook, load_workbook

out = Workbook(); ws = out.active; header_done = False
for f in sorted(pathlib.Path("各部门").glob("*.xlsx")):
    rows = list(load_workbook(f, read_only=True, data_only=True).active.iter_rows(values_only=True))
    if not rows: continue
    if not header_done:
        ws.append(["来源文件", *rows[0]]); header_done = True
    for r in rows[1:]:
        ws.append([f.stem, *r])
out.save("合并结果.xlsx")
```

## 6. 定时运行

| 系统 | 做法 |
|------|------|
| Windows | 任务计划程序 → 创建基本任务 → 触发器（每天）→ 操作"启动程序"填 `powershell.exe`，参数 `-File "D:\脚本\备份.ps1"` |
| Linux / macOS | `crontab -e` 添加 `0 2 * * * /bin/bash /home/me/backup.sh >> /home/me/backup.log 2>&1`（每天 2 点） |
| 飞牛 / 群晖 | 系统自带的"计划任务"里添加用户定义脚本 |

也可以直接在 Octop 里用定时任务让专家定期执行。
