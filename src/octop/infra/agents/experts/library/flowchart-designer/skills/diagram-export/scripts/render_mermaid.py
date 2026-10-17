#!/usr/bin/env python3
"""Validate and render Mermaid source to SVG / PNG / PDF with headless Chromium.

Usage:
    python scripts/render_mermaid.py diagram.mmd -o diagram.png [--theme default] [--scale 2]
    python scripts/render_mermaid.py diagram.mmd -o diagram.svg --bg transparent
    python scripts/render_mermaid.py diagram.mmd --check          # syntax check only

Only the Mermaid library is fetched from a public CDN (once, then cached);
diagram content never leaves this machine. Offline: pass --mermaid-js or set
OCTOP_MERMAID_JS to a local ``mermaid.min.js``.

Exit codes: 0 ok, 1 Mermaid syntax / input error, 2 missing runtime
(Playwright, Chromium, or mermaid.min.js).
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

MERMAID_VERSION = "11.13.0"
CDN_URLS = (
    f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js",
    f"https://registry.npmmirror.com/mermaid/{MERMAID_VERSION}/files/dist/mermaid.min.js",
    f"https://unpkg.com/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js",
)
THEMES = ("default", "neutral", "dark", "forest", "base")
FONT_STACK = '"Noto Sans CJK SC","PingFang SC","Microsoft YaHei","Source Han Sans SC",sans-serif'

PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
  html, body { margin: 0; padding: 0; background: %(bg)s; }
  #out { display: inline-block; padding: %(pad)dpx; background: %(bg)s; }
  #out svg { max-width: none !important; height: auto; }
</style></head>
<body><div id="out"></div></body></html>
"""


# Mermaid styles nodes via <style> selectors that PowerPoint / LibreOffice / IM
# previews ignore; bake computed styles into presentation attributes instead.
INLINE_STYLES_JS = """() => {
    const svg = document.querySelector("#out svg");
    const props = ["fill", "stroke", "stroke-width", "stroke-dasharray", "opacity",
        "fill-opacity", "stroke-opacity", "font-family", "font-size", "font-weight",
        "text-anchor", "dominant-baseline"];
    for (const el of svg.querySelectorAll("*")) {
        if (["style", "defs", "title", "desc"].includes(el.tagName)) continue;
        const cs = getComputedStyle(el);
        for (const prop of props) {
            const value = cs.getPropertyValue(prop);
            if (value) el.setAttribute(prop, value);
        }
    }
    return new XMLSerializer().serializeToString(svg);
}"""


class RenderError(RuntimeError):
    """Mermaid rejected the diagram; message is the parser error."""


def _cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "octop-mermaid" / f"mermaid-{MERMAID_VERSION}.min.js"


def resolve_mermaid_js(explicit: str | None) -> Path:
    """Local override → cache → download from the first reachable CDN."""
    override = explicit or os.environ.get("OCTOP_MERMAID_JS")
    if override:
        path = Path(override)
        if not path.is_file():
            raise FileNotFoundError(f"指定的 mermaid.min.js 不存在：{path}")
        return path
    cached = _cache_path()
    if cached.is_file() and cached.stat().st_size > 100_000:
        return cached
    errors: list[str] = []
    for url in CDN_URLS:
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - fixed https URLs
                data = resp.read()
        except OSError as exc:
            errors.append(f"{url}: {exc}")
            continue
        if len(data) > 100_000:
            cached.parent.mkdir(parents=True, exist_ok=True)
            tmp = cached.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(cached)
            return cached
        errors.append(f"{url}: 内容过小（{len(data)} 字节）")
    raise FileNotFoundError(
        "无法获取 mermaid.min.js（离线环境请用 --mermaid-js 或 OCTOP_MERMAID_JS 指定本地文件）：\n"
        + "\n".join(errors)
    )


def render(
    source: str,
    output: Path | None,
    *,
    mermaid_js: Path,
    theme: str = "default",
    background: str = "white",
    scale: float = 2.0,
    padding: int = 16,
) -> str:
    """Render *source*; write *output* (by suffix) unless None. Returns the SVG text."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise FileNotFoundError("缺少 Python 包 playwright：pip install playwright") from exc

    bg = "transparent" if background == "transparent" else background
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch()
            except PlaywrightError as exc:
                raise FileNotFoundError(
                    "Chromium 未安装：在 Octop 设置 → 浏览器 中安装，或运行 `playwright install chromium`"
                ) from exc
            try:
                page = browser.new_page(device_scale_factor=scale)
                page.set_content(PAGE % {"bg": bg, "pad": padding})
                page.add_script_tag(path=str(mermaid_js))
                result = page.evaluate(
                    """async ([code, theme, font, htmlLabels]) => {
                        mermaid.initialize({
                            startOnLoad: false, theme, securityLevel: "strict",
                            fontFamily: font, htmlLabels, flowchart: { htmlLabels },
                        });
                        try {
                            await mermaid.parse(code);
                            const { svg } = await mermaid.render("diagram", code);
                            document.getElementById("out").innerHTML = svg;
                            return { ok: true, svg };
                        } catch (err) {
                            return { ok: false, error: String(err && err.message || err) };
                        }
                    }""",
                    # SVG viewers (PowerPoint, IM previews) often drop foreignObject labels.
                    [source, theme, FONT_STACK, output is None or output.suffix.lower() != ".svg"],
                )
                if not result["ok"]:
                    raise RenderError(result["error"])
                svg: str = result["svg"]
                if output is not None:
                    suffix = output.suffix.lower()
                    output.parent.mkdir(parents=True, exist_ok=True)
                    if suffix == ".svg":
                        output.write_text(
                            '<?xml version="1.0" encoding="UTF-8"?>\n'
                            + page.evaluate(INLINE_STYLES_JS),
                            encoding="utf-8",
                        )
                    elif suffix == ".png":
                        page.locator("#out").screenshot(
                            path=str(output), omit_background=bg == "transparent"
                        )
                    elif suffix == ".pdf":
                        box = page.locator("#out").bounding_box() or {"width": 800, "height": 600}
                        page.pdf(
                            path=str(output),
                            width=f"{int(box['width']) + 2}px",
                            height=f"{int(box['height']) + 2}px",
                            print_background=True,
                            page_ranges="1",
                        )
                    else:
                        raise RenderError(f"不支持的输出格式 {suffix}，可用 .svg / .png / .pdf")
                return svg
            finally:
                browser.close()
    except PlaywrightError as exc:
        raise FileNotFoundError(f"Playwright 运行失败：{exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("input", help=".mmd file, or - for stdin")
    parser.add_argument("-o", "--output", help="output .svg / .png / .pdf")
    parser.add_argument("--check", action="store_true", help="validate syntax only")
    parser.add_argument("--theme", choices=THEMES, default="default")
    parser.add_argument("--bg", default="white", help="background color or 'transparent'")
    parser.add_argument("--scale", type=float, default=2.0, help="PNG pixel ratio")
    parser.add_argument("--mermaid-js", help="local mermaid.min.js (offline use)")
    args = parser.parse_args(argv)
    if not args.check and not args.output:
        parser.error("需要 -o 输出路径，或使用 --check 只做语法检查")

    source = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
    if not source.strip():
        print("输入为空", file=sys.stderr)
        return 1
    output = None if args.check else Path(args.output)
    try:
        js = resolve_mermaid_js(args.mermaid_js)
        render(
            source, output, mermaid_js=js, theme=args.theme, background=args.bg, scale=args.scale
        )
    except RenderError as exc:
        print(f"Mermaid 语法错误：\n{exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"渲染环境不可用：{exc}", file=sys.stderr)
        return 2
    print("语法检查通过" if args.check else f"已导出 {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
