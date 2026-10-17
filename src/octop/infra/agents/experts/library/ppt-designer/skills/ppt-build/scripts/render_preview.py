#!/usr/bin/env python3
"""Render a .pptx to per-slide PNGs plus one contact-sheet grid for visual QA.

Usage:
    python scripts/render_preview.py deck.pptx [-o preview_dir] [--cols 3]

Needs LibreOffice (``soffice``) to convert to PDF; PDF→PNG uses PyMuPDF when
installed, else ``pdftoppm``. Exit code 2 means no renderer is available — fall
back to ``inspect_deck.py`` text checks and tell the user preview was skipped.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def to_pdf(pptx: Path, out_dir: Path) -> Path:
    exe = _soffice()
    if exe is None:
        raise FileNotFoundError("soffice")
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [
                exe,
                f"-env:UserInstallation={Path(profile).as_uri()}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(out_dir),
                str(pptx),
            ],
            check=True,
            capture_output=True,
            timeout=180,
        )
    pdf = out_dir / f"{pptx.stem}.pdf"
    if not pdf.is_file():
        raise RuntimeError("LibreOffice 未生成 PDF")
    return pdf


def pdf_to_pngs(pdf: Path, out_dir: Path, dpi: int) -> list[Path]:
    try:
        import fitz  # PyMuPDF

        pages: list[Path] = []
        with fitz.open(pdf) as doc:
            for i, page in enumerate(doc, start=1):
                target = out_dir / f"slide-{i:02d}.png"
                page.get_pixmap(dpi=dpi).save(target)
                pages.append(target)
        return pages
    except ImportError:
        pass
    if shutil.which("pdftoppm") is None:
        raise FileNotFoundError("pdftoppm")
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), str(pdf), str(out_dir / "slide")],
        check=True,
        capture_output=True,
        timeout=180,
    )
    pages = sorted(out_dir.glob("slide-*.png"))
    for i, page in enumerate(pages, start=1):
        normalized = out_dir / f"slide-{i:02d}.png"
        if page != normalized:
            page.rename(normalized)
    return sorted(out_dir.glob("slide-*.png"))


def contact_sheet(pages: list[Path], target: Path, cols: int) -> Path | None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    images = [Image.open(p) for p in pages]
    if not images:
        return None
    thumb_w = 480
    ratio = images[0].height / images[0].width
    thumb_h = int(thumb_w * ratio)
    rows = -(-len(images) // cols)
    pad, label = 16, 24
    sheet = Image.new(
        "RGB",
        (cols * (thumb_w + pad) + pad, rows * (thumb_h + pad + label) + pad),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for i, img in enumerate(images):
        r, c = divmod(i, cols)
        x = pad + c * (thumb_w + pad)
        y = pad + r * (thumb_h + pad + label)
        draw.text((x, y), f"{i + 1}", fill="black")
        sheet.paste(img.convert("RGB").resize((thumb_w, thumb_h)), (x, y + label))
        img.close()
    sheet.save(target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("pptx")
    parser.add_argument("-o", "--out-dir", help="default: <deck>_preview/")
    parser.add_argument("--cols", type=int, default=3)
    parser.add_argument("--dpi", type=int, default=80)
    args = parser.parse_args(argv)
    pptx = Path(args.pptx)
    if not pptx.is_file():
        print(f"文件不存在：{pptx}", file=sys.stderr)
        return 1
    out_dir = Path(args.out_dir) if args.out_dir else pptx.with_name(f"{pptx.stem}_preview")
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        pdf = to_pdf(pptx, out_dir)
        pages = pdf_to_pngs(pdf, out_dir, args.dpi)
    except FileNotFoundError as exc:
        print(
            f"无法预览：缺少 {exc.args[0]}。请改用 inspect_deck.py 做文字检查，并告知用户未做视觉预览。",
            file=sys.stderr,
        )
        return 2
    except (subprocess.SubprocessError, RuntimeError) as exc:
        print(f"预览失败：{exc}", file=sys.stderr)
        return 1
    sheet = contact_sheet(pages, out_dir / "grid.png", args.cols)
    print(f"PDF：{pdf}")
    print(f"单页图：{len(pages)} 张，位于 {out_dir}")
    if sheet:
        print(f"总览图：{sheet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
