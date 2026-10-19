#!/usr/bin/env python3
"""网页检查：用无头 Chromium 打开 HTML 文件或网址，收集控制台报错和加载失败的资源，检查基础规范，按桌面和手机尺寸截图。

Usage:
    python scripts/html_check.py 页面.html|URL [-o 截图目录] [--viewports desktop,mobile] [--wait 500]

检查项：
  错误：页面脚本报错（uncaught exception）、console.error、资源加载失败（脚本 / 样式 / 图片 / 接口）；
  警告：手机宽度下出现横向滚动条、缺少 <meta name="viewport">、缺少 <title>、图片没有 alt、
        表单输入框没有关联 label、通过 http:// 加载外部资源、页面引用的外部脚本数量；
  截图：desktop 1280×800、tablet 820×1180、mobile 390×844，整页截图保存为 PNG。
需要 playwright 和 Chromium（pip install playwright && playwright install chromium）。
Exit codes: 0 无错误, 3 有错误, 1 输入错误, 2 缺少 playwright / Chromium。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

VIEWPORTS = {"desktop": (1280, 800), "tablet": (820, 1180), "mobile": (390, 844)}

STATIC_JS = """
() => {
  const out = {};
  out.title = document.title || "";
  out.viewport = !!document.querySelector('meta[name="viewport"]');
  out.imgNoAlt = [...document.images].filter(i => !i.hasAttribute('alt')).map(i => i.getAttribute('src') || '(inline)').slice(0, 10);
  const inputs = [...document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea')];
  out.unlabeled = inputs.filter(el => {
    if (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.closest('label')) return false;
    return !(el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`));
  }).map(el => el.name || el.id || el.tagName.toLowerCase()).slice(0, 10);
  out.httpRes = [...document.querySelectorAll('script[src],link[href],img[src],iframe[src]')]
    .map(e => e.getAttribute('src') || e.getAttribute('href')).filter(u => u && u.startsWith('http://')).slice(0, 10);
  out.extScripts = [...document.querySelectorAll('script[src]')].map(s => s.getAttribute('src')).filter(u => /^https?:/.test(u));
  out.overflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  return out;
}
"""


class CheckError(ValueError):
    pass


def target_url(source: str) -> str:
    if source.startswith(("http://", "https://", "file://")):
        return source
    p = Path(source).resolve()
    if not p.is_file():
        raise CheckError(f"找不到 {source}")
    return p.as_uri()


def run(url: str, out_dir: Path | None, viewports: list[str], wait_ms: int) -> dict[str, Any]:
    try:
        from playwright.sync_api import Error as PwError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "缺少 playwright：请运行 `pip install playwright && playwright install chromium`",
            file=sys.stderr,
        )
        sys.exit(2)
    result: dict[str, Any] = {"url": url, "errors": [], "warnings": [], "screenshots": []}
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except PwError as exc:
            print(
                f"无法启动 Chromium：{str(exc).splitlines()[0]}\n请运行 `playwright install chromium`",
                file=sys.stderr,
            )
            sys.exit(2)
        try:
            for vp in viewports:
                w, h = VIEWPORTS[vp]
                ctx = browser.new_context(
                    viewport={"width": w, "height": h},
                    device_scale_factor=1,
                    is_mobile=vp == "mobile",
                )
                page = ctx.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda exc, errors=errors: errors.append(f"脚本报错：{exc}"))
                # "Failed to load resource" duplicates the requestfailed / response events below.
                page.on("console", lambda msg, errors=errors: errors.append(f"console.error：{msg.text}")
                        if msg.type == "error" and not msg.text.startswith("Failed to load resource") else None)  # fmt: skip
                page.on(
                    "requestfailed",
                    lambda req, errors=errors: errors.append(
                        f"资源加载失败：{req.url}（{req.failure}）"
                    ),
                )
                page.on(
                    "response",
                    lambda resp, errors=errors: (
                        errors.append(f"资源返回 {resp.status}：{resp.url}")
                        if resp.status >= 400
                        else None
                    ),
                )
                try:
                    page.goto(url, wait_until="load", timeout=30000)
                except PwError as exc:
                    raise CheckError(f"打开页面失败：{str(exc).splitlines()[0]}") from None
                page.wait_for_timeout(wait_ms)
                info = page.evaluate(STATIC_JS)
                for e in errors:
                    if e not in result["errors"]:
                        result["errors"].append(e)
                if vp == "mobile" and info["overflow"] > 2:
                    result["warnings"].append(
                        f"手机宽度（{w}px）下内容超出 {info['overflow']}px，出现横向滚动条；检查固定宽度、长单词和表格"
                    )
                if vp == viewports[0]:
                    if not info["viewport"]:
                        result["warnings"].append(
                            '缺少 <meta name="viewport" content="width=device-width, initial-scale=1">，手机上会被缩小显示'
                        )
                    if not info["title"]:
                        result["warnings"].append("缺少 <title>")
                    if info["imgNoAlt"]:
                        result["warnings"].append(
                            f"{len(info['imgNoAlt'])} 张图片没有 alt：{'、'.join(info['imgNoAlt'][:3])}"
                        )
                    if info["unlabeled"]:
                        result["warnings"].append(
                            f"{len(info['unlabeled'])} 个输入框没有关联 label：{'、'.join(info['unlabeled'][:5])}"
                        )
                    if info["httpRes"]:
                        result["warnings"].append(
                            f"通过 http:// 加载的外部资源（在 https 页面会被拦截）：{'、'.join(info['httpRes'][:3])}"
                        )
                    result["external_scripts"] = info["extScripts"]
                if out_dir:
                    out_dir.mkdir(parents=True, exist_ok=True)
                    shot = out_dir / f"{vp}.png"
                    page.screenshot(path=str(shot), full_page=True)
                    result["screenshots"].append(str(shot))
                ctx.close()
        finally:
            browser.close()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("source")
    parser.add_argument("-o", "--output", help="截图保存目录")
    parser.add_argument("--viewports", default="desktop,mobile")
    parser.add_argument(
        "--wait", type=int, default=500, help="页面加载后再等待的毫秒数（等脚本渲染）"
    )
    args = parser.parse_args(argv)
    try:
        vps = [v.strip() for v in args.viewports.split(",") if v.strip()]
        bad = [v for v in vps if v not in VIEWPORTS]
        if bad or not vps:
            raise CheckError(f"--viewports 可选 {', '.join(VIEWPORTS)}")
        res = run(
            target_url(args.source), Path(args.output) if args.output else None, vps, args.wait
        )
    except CheckError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    print(f"检查 {res['url']}：错误 {len(res['errors'])}，警告 {len(res['warnings'])}")
    for e in res["errors"]:
        print(f"- [错误] {e}")
    for w in res["warnings"]:
        print(f"- [警告] {w}")
    ext = res.get("external_scripts") or []
    if ext:
        print(
            f"外部脚本 {len(ext)} 个：{'、'.join(ext[:5])}（断网或 CDN 不可用时页面会失效，确认版本号已固定）"
        )
    for s in res["screenshots"]:
        print(f"截图：{s}")
    if not res["errors"] and not res["warnings"]:
        print("没有发现问题。")
    return 3 if res["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
