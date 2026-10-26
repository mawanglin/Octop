#!/usr/bin/env python3
"""竞品素材采集：抓取官网网址、产品介绍页链接、产品介绍图和截图，生成可直接放进报告的“竞品档案”。

Usage:
    python scripts/product_assets.py 产品名 [--site 官网] [--appstore 应用ID] [--country cn]
                                     [--screenshot] [--full-page] [--max-images 6] -o 报告目录

对每个产品，在 报告目录/assets/产品名/ 下保存：
  site-og.*            官网分享图（og:image / twitter:image），通常就是产品主视觉
  site-logo.*          网站图标或 Logo（apple-touch-icon、logo 图片）
  site-image-N.*       官网页面里尺寸较大的产品介绍图
  appstore-icon.*      App Store 图标
  appstore-shot-N.*    App Store 截图（产品界面）
  page-home.png        --screenshot：用无头浏览器截取官网首屏（--full-page 截整页）
  page-pricing.png     --screenshot 且找到定价页时截取定价页
  assets.json          每个文件的来源网址、获取时间和尺寸
  profile.md           竞品档案：官网、产品介绍页、定价页、下载和应用商店链接、运营主体、
                       官方介绍语和图片引用（图片路径相对于报告目录，报告请放在同一目录）
只下载公开页面上的图片，用于内部分析报告；对外发布前确认版权。截图需要 playwright 和 Chromium。
Exit codes: 0 ok, 1 输入错误, 2 所有来源都获取失败。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import urllib.parse
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import product_search as ps  # noqa: E402 - sibling script

MIN_W, MIN_H = 400, 200
SKIP_SRC = re.compile(
    r"(?i)^data:|\.svg(?:$|\?)|pixel|tracking|spacer|blank\.|1x1|beacon|analytics"
)


class _ImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.icons: list[str] = []
        self.logos: list[str] = []
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"} and a.get(
                "content"
            ):
                self.meta.setdefault("image", a["content"])
        elif tag == "link" and "icon" in a.get("rel", "").lower() and a.get("href"):
            if "apple-touch" in a["rel"].lower():
                self.icons.insert(0, a["href"])
            else:
                self.icons.append(a["href"])
        elif tag in {"img", "source"}:
            src = a.get("src") or a.get("data-src") or a.get("data-original") or ""
            if not src and a.get("srcset"):
                src = a["srcset"].split(",")[-1].strip().split(" ")[0]
            if not src:
                return
            hint = f"{a.get('alt', '')} {a.get('class', '')} {a.get('id', '')} {src}".lower()
            (self.logos if "logo" in hint else self.images).append(src)


class Collector:
    def __init__(self, name: str, root: Path) -> None:
        self.name = name
        self.root = root
        self.dir = root / "assets" / safe_name(name)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.records: list[dict[str, Any]] = []
        self.seen: set[str] = set()
        self.warnings: list[str] = []

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def save_image(
        self,
        url: str,
        stem: str,
        *,
        min_size: tuple[int, int] = (0, 0),
        label: str = "",
        source: str = "官网",
    ) -> Path | None:
        try:
            body, headers, final = ps.fetch(url, accept="image/*", limit=10_000_000)
        except ps.SearchError as exc:
            self.warnings.append(f"下载失败 {url}：{exc}")
            return None
        digest = hashlib.sha1(body).hexdigest()
        if digest in self.seen:
            return None
        try:
            from PIL import Image

            with Image.open(io.BytesIO(body)) as im:
                width, height, fmt = im.width, im.height, (im.format or "png").lower()
        except Exception:  # noqa: BLE001 - not a raster image (svg, html error page…)
            return None
        if width < min_size[0] or height < min_size[1]:
            return None
        self.seen.add(digest)
        ext = {"jpeg": "jpg"}.get(fmt, fmt)
        path = self.dir / f"{stem}.{ext}"
        path.write_bytes(body)
        self.records.append(
            {
                "类型": label or stem,
                "文件": self.rel(path),
                "来源": final,
                "出处": source,
                "尺寸": f"{width}×{height}",
                "获取日期": date.today().isoformat(),
            }
        )
        return path


def safe_name(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "-", name).strip("-.")
    return cleaned or "product"


def collect_site(c: Collector, url: str, max_images: int) -> dict[str, Any]:
    info = ps.site_info(url, history=False)
    body, _, final = ps.fetch(info["网址"], accept="text/html")
    parser = _ImageParser()
    parser.feed(ps._decode(body, {}))

    def absolute(src: str) -> str:
        return urllib.parse.urljoin(final, src.strip())

    if parser.meta.get("image"):
        c.save_image(absolute(parser.meta["image"]), "site-og", label="官网分享图")
    for src in [*parser.icons, *parser.logos][:6]:
        if c.save_image(absolute(src), "site-logo", label="网站图标"):
            break
    count = 0
    for src in parser.images:
        if count >= max_images:
            break
        if SKIP_SRC.search(src):
            continue
        if c.save_image(
            absolute(src), f"site-image-{count + 1}", min_size=(MIN_W, MIN_H), label="官网产品图"
        ):
            count += 1
    return info


def collect_appstore(c: Collector, app_id: str, country: str, max_images: int) -> dict[str, Any]:
    url = f"{ps.ITUNES}/lookup?{urllib.parse.urlencode({'id': app_id, 'country': country})}"
    results = [a for a in ps.fetch_json(url).get("results", []) if a.get("trackId")]
    if not results:
        raise ps.SearchError(f"没有查到应用 {app_id}（检查 ID 和 --country）", 1)
    app = results[0]
    icon = app.get("artworkUrl512") or app.get("artworkUrl100")
    if icon:
        c.save_image(icon, "appstore-icon", label="App Store 图标", source="App Store")
    shots = (app.get("screenshotUrls") or []) + (app.get("ipadScreenshotUrls") or [])
    for i, shot in enumerate(shots[:max_images], 1):
        # The API returns 320x480 thumbnails; the image server renders any width on request.
        large = re.sub(r"/\d+x\d+bb\.(?:jpg|png)$", "/600x0w.jpg", shot)
        if not c.save_image(
            large, f"appstore-shot-{i}", label=f"App Store 截图 {i}", source="App Store"
        ):
            c.save_image(
                shot, f"appstore-shot-{i}", label=f"App Store 截图 {i}", source="App Store"
            )
    return ps._app_row(app, detail=True)


def page_screenshots(c: Collector, pages: dict[str, str], full_page: bool) -> str:
    """Screenshot each page; returns the rendered HTML of the first one (JS-built footers)."""
    rendered = ""
    try:
        from playwright.sync_api import Error as PwError
        from playwright.sync_api import sync_playwright
    except ImportError:
        c.warnings.append(
            "没有安装 playwright，跳过网页截图（pip install playwright && playwright install chromium）"
        )
        return rendered
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page(
                    viewport={"width": 1440, "height": 900}, device_scale_factor=1
                )
                for stem, url in pages.items():
                    try:
                        page.goto(url, wait_until="load", timeout=30000)
                        page.wait_for_timeout(1500)
                        path = c.dir / f"{stem}.png"
                        page.screenshot(path=str(path), full_page=full_page)
                        rendered = rendered or page.content()
                    except PwError as exc:
                        c.warnings.append(f"截图失败 {url}：{str(exc).splitlines()[0]}")
                        continue
                    c.records.append(
                        {
                            "类型": {"page-home": "官网首页截图", "page-pricing": "定价页截图"}.get(
                                stem, "网页截图"
                            ),
                            "文件": c.rel(path),
                            "来源": url,
                            "出处": urllib.parse.urlparse(url).netloc,
                            "尺寸": "1440 宽",
                            "获取日期": date.today().isoformat(),
                        }
                    )
            finally:
                browser.close()
    except PwError as exc:
        c.warnings.append(
            f"无法启动浏览器截图：{str(exc).splitlines()[0]}（运行 playwright install chromium）"
        )
    return rendered


def profile_md(c: Collector, site: dict[str, Any] | None, app: dict[str, Any] | None) -> str:
    today = date.today().isoformat()
    lines = [f"### {c.name}", ""]
    if site:
        lines.append(f"- 官网：[{site['网址']}]({site['网址']})")
        pages = site.get("关键页面", {})
        for key in ("产品介绍", "定价", "下载", "文档", "更新日志"):
            links = pages.get(key) or []
            if links:
                lines.append(f"- {key}页：" + "、".join(f"[{u}]({u})" for u in links[:2]))
        intro = site.get("描述") or site.get("标题")
        if intro:
            lines.append(f"- 官方介绍：“{intro}”（官网，{today}）")
        owner = "、".join(site.get("页脚主体") or []) or ""
        icp = "、".join(site.get("ICP备案") or [])
        if owner or icp:
            lines.append(f"- 运营主体：{owner or '未在首页标注'}" + (f"（{icp}）" if icp else ""))
    if app:
        lines.append(
            f"- App Store：[{app['名称']}]({app['链接']})，{app['开发者']}，评分 {app['评分']}"
            f"（{app['评分人数']} 人评分），版本 {app['版本']}，最近更新 {app['最近更新']}，上架 {app['上架时间']}"
        )
    lines.append("")
    for r in c.records:
        lines.append(f"![{c.name} {r['类型']}（来源：{r['出处']}，{r['获取日期']}）]({r['文件']})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("name", help="产品名称（用作文件夹名和档案标题）")
    parser.add_argument("--site", help="官网网址")
    parser.add_argument("--appstore", help="App Store 应用 ID（链接里 id 后面的数字）")
    parser.add_argument("--country", default="cn")
    parser.add_argument(
        "--screenshot", action="store_true", help="用无头浏览器截取官网首页和定价页"
    )
    parser.add_argument("--full-page", action="store_true", help="截整页（默认只截首屏）")
    parser.add_argument("--max-images", type=int, default=6)
    parser.add_argument(
        "-o", "--output", required=True, help="报告目录（素材保存到其下 assets/产品名/）"
    )
    args = parser.parse_args(argv)
    if not args.site and not args.appstore:
        print("失败：至少提供 --site 或 --appstore", file=sys.stderr)
        return 1
    if args.appstore and not args.appstore.isdigit():
        print("失败：--appstore 是应用 ID 数字，如 id414478124 → 414478124", file=sys.stderr)
        return 1

    c = Collector(args.name, Path(args.output))
    site = app = None
    failures = 0
    if args.site:
        try:
            site = collect_site(c, args.site, max(0, args.max_images))
        except ps.SearchError as exc:
            failures += 1
            c.warnings.append(f"官网获取失败：{exc}")
    if args.appstore:
        try:
            app = collect_appstore(c, args.appstore, args.country, max(0, args.max_images))
        except ps.SearchError as exc:
            if exc.code == 1:
                print(f"失败：{exc}", file=sys.stderr)
                return 1
            failures += 1
            c.warnings.append(f"App Store 获取失败：{exc}")
    if site and args.screenshot:
        pages = {"page-home": site["网址"]}
        pricing = (site.get("关键页面", {}).get("定价") or [None])[0]
        if pricing:
            pages["page-pricing"] = pricing
        rendered = page_screenshots(c, pages, args.full_page)
        # Many sites build the footer (ICP filing, operating company) with JavaScript.
        if rendered:
            site["ICP备案"] = site.get("ICP备案") or sorted(set(ps.ICP.findall(rendered)))
            site["页脚主体"] = site.get("页脚主体") or sorted(
                {m.group(1) for m in ps.COMPANY.finditer(rendered)}
            )
    if failures and not (site or app):
        for w in c.warnings:
            print(f"失败：{w}", file=sys.stderr)
        return 2

    (c.dir / "assets.json").write_text(
        json.dumps(
            {"产品": args.name, "官网": site, "AppStore": app, "素材": c.records},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    profile = profile_md(c, site, app)
    (c.dir / "profile.md").write_text(profile, encoding="utf-8")
    print(f"{args.name}：保存 {len(c.records)} 个素材到 {c.dir}")
    for r in c.records:
        print(f"- {r['类型']}：{r['文件']}（{r['尺寸']}）")
    for w in c.warnings:
        print(f"注意：{w}")
    print(f"\n竞品档案（{c.rel(c.dir / 'profile.md')}，可直接粘贴进放在 {c.root} 的报告）：\n")
    print(profile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
