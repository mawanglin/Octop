#!/usr/bin/env python3
"""保留格式翻译 Word：抽取段落 → 逐段翻译 → 回填生成译文 docx，并检查漏译、数字、标签和术语。

Usage:
    python scripts/docx_segments.py extract 原文.docx -o 段落.json
    python scripts/docx_segments.py fill 原文.docx 段落.json -o 译文.docx
    python scripts/docx_segments.py check 段落.json [--glossary 术语表.csv]

extract：正文、表格（含嵌套表格）、文本框、页眉页脚中的每个段落是一个片段（JSON 列表，字段 id/where/text/translation）。
  - 段落内有加粗、斜体、颜色等特殊格式的文字用 <n>…</n> 标出，翻译时保留标签、可以调整语序；
  - 只有数字和符号的段落不抽取；与前面完全相同的段落标 dup_of，只需翻译第一次出现的。
fill：把 translation 写回原位置，段落样式、编号、表格、图片、页眉页脚都不动；未翻译的片段保留原文并报告。
check：未翻译、原文数字在译文中缺失、标签不匹配、术语表（两列：原文,译文）没有按约定翻译、同一原文多种译法。
脚注、批注、图片里的文字、SmartArt 不在处理范围内。Exit codes: 0 ok, 1 输入错误或检查发现问题, 2 缺少 python-docx。
"""

from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from docx import Document
    from docx.oxml.ns import qn
    from lxml import etree
except ImportError:  # pragma: no cover - environment check
    print("缺少依赖 python-docx：请运行 `pip install python-docx`", file=sys.stderr)
    sys.exit(2)

TAG = re.compile(r"<(\d+)>(.*?)</\1>", re.S)
HAS_WORD = re.compile(r"[^\W\d_]", re.U)
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


class SegError(ValueError):
    pass


def _parts(doc: Any) -> list[tuple[str, Any]]:
    parts: list[tuple[str, Any]] = [("正文", doc.element.body)]
    seen: set[int] = set()
    for sec in doc.sections:
        for kind, label in (("header", "页眉"), ("first_page_header", "页眉"), ("even_page_header", "页眉"),
                            ("footer", "页脚"), ("first_page_footer", "页脚"), ("even_page_footer", "页脚")):  # fmt: skip
            hf = getattr(sec, kind)
            if hf.is_linked_to_previous:
                continue
            el = hf._element
            if id(el) not in seen:
                seen.add(id(el))
                parts.append((label, el))
    return parts


def _runs(p: Any) -> list[Any]:
    """Text runs that belong to paragraph *p* itself (incl. hyperlinks), not to nested text boxes."""
    wrappers = (qn("w:hyperlink"), qn("w:smartTag"))
    return [r for r in p.iter(qn("w:r"))
            if r.getparent() is p or (r.getparent().tag in wrappers and r.getparent().getparent() is p)]  # fmt: skip


def _run_text(r: Any) -> str:
    return "".join(t.text or "" for t in r.findall(qn("w:t")))


def _fmt(r: Any) -> bytes:
    rpr = r.find(qn("w:rPr"))
    if rpr is None:
        return b""
    clone = copy.deepcopy(rpr)
    for tag in (
        "w:lang",
        "w:noProof",
        "w:rFonts",
    ):  # differences that don't matter visually for translation
        for el in clone.findall(qn(tag)):
            clone.remove(el)
    return bytes(etree.tostring(clone))


def _spans(p: Any) -> list[list[Any]]:
    spans: list[list[Any]] = []
    last: bytes | None = None
    for r in _runs(p):
        if r.find(qn("w:t")) is None:
            continue
        f = _fmt(r)
        if spans and f == last:
            spans[-1].append(r)
        else:
            spans.append([r])
            last = f
    return [s for s in spans if "".join(_run_text(r) for r in s)]


def iter_paragraphs(doc: Any) -> list[tuple[str, Any]]:
    out = []
    for label, root in _parts(doc):
        for p in root.iter(qn("w:p")):
            where = label
            anc = p.getparent()
            while anc is not None and anc is not root:
                if anc.tag == qn("w:tc"):
                    where = label + "·表格" if label == "正文" else label
                    break
                if anc.tag == qn("w:txbxContent"):
                    where = label + "·文本框"
                    break
                anc = anc.getparent()
            out.append((where, p))
    return out


def _simple(p: Any, spans: list[list[Any]]) -> bool:
    return all(r.getparent() is p for sp in spans for r in sp)


def _base(spans: list[list[Any]]) -> int:
    """Index of the span with the most text: its format is the paragraph's "plain" format."""
    lengths = [sum(len(_run_text(r)) for r in sp) for sp in spans]
    return lengths.index(max(lengths))


def segment_text(p: Any, spans: list[list[Any]]) -> str:
    """Plain text for one span; otherwise only spans formatted differently from the base are tagged <n>…</n>.

    Paragraphs whose runs sit inside hyperlinks keep every span tagged and are filled in place (no reordering).
    """
    texts = ["".join(_run_text(r) for r in s) for s in spans]
    if len(texts) == 1:
        return texts[0]
    if not _simple(p, spans):
        return "".join(f"<{i}>{t}</{i}>" for i, t in enumerate(texts, start=1))
    base = _fmt(spans[_base(spans)][0])
    return "".join(
        t if _fmt(sp[0]) == base else f"<{i}>{t}</{i}>"
        for i, (sp, t) in enumerate(zip(spans, texts, strict=True), 1)
    )


def cmd_extract(src: Path, out: Path) -> int:
    doc = Document(str(src))
    segs: list[dict[str, str]] = []
    first: dict[str, str] = {}
    for n, (where, p) in enumerate(iter_paragraphs(doc), start=1):
        spans = _spans(p)
        if not spans:
            continue
        text = segment_text(p, spans)
        if not HAS_WORD.search(TAG.sub(r"\2", text)):
            continue
        seg = {"id": f"p{n}", "where": where, "text": text, "translation": ""}
        if text in first:
            seg["dup_of"] = first[text]
        else:
            first[text] = seg["id"]
        segs.append(seg)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(segs, ensure_ascii=False, indent=1), encoding="utf-8")
    todo = [s for s in segs if "dup_of" not in s]
    chars = sum(len(TAG.sub(r"\2", s["text"])) for s in todo)
    tagged = sum(1 for s in todo if TAG.search(s["text"]))
    print(
        f"已抽取 {out}：{len(segs)} 个片段，其中需要翻译 {len(todo)} 个（约 {chars} 字），{len(segs) - len(todo)} 个与前文重复"
    )
    if tagged:
        print(f"{tagged} 个片段带格式标签 <n>…</n>，翻译时请保留标签")
    return 0


def load_segments(path: Path) -> list[dict[str, str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SegError(f"{path} 不是有效的 JSON：{exc}") from None
    if not isinstance(data, list) or not all(
        isinstance(s, dict) and "id" in s and "text" in s for s in data
    ):
        raise SegError(f"{path} 格式不对：应为 extract 生成的片段列表")
    return data


def resolved(segs: list[dict[str, str]]) -> dict[str, str]:
    by_id = {s["id"]: s for s in segs}
    out = {}
    for s in segs:
        tr = (s.get("translation") or "").strip()
        if not tr and s.get("dup_of") in by_id:
            tr = (by_id[s["dup_of"]].get("translation") or "").strip()
        if tr:
            out[s["id"]] = tr
    return out


def _write_span(span: list[Any], text: str) -> None:
    ts = [t for r in span for t in r.findall(qn("w:t"))]
    ts[0].text = text
    ts[0].set(XML_SPACE, "preserve")
    for t in ts[1:]:
        t.text = ""


def _chunks(text: str) -> list[tuple[int | None, str]]:
    out: list[tuple[int | None, str]] = []
    pos = 0
    for m in TAG.finditer(text):
        if m.start() > pos:
            out.append((None, text[pos : m.start()]))
        out.append((int(m.group(1)), m.group(2)))
        pos = m.end()
    if pos < len(text):
        out.append((None, text[pos:]))
    return [(k, re.sub(r"</?\d+>", "", t)) for k, t in out if t]


def _rebuild(spans: list[list[Any]], translation: str) -> bool:
    """Write *translation* as fresh runs in its own order, each cloned from the span its tag points to.

    Returns False when the tags don't match the source (the text is still written, untagged parts in base format).
    """
    base = _base(spans)
    tagged = {i for i, sp in enumerate(spans, start=1) if _fmt(sp[0]) != _fmt(spans[base][0])}
    chunks = _chunks(translation)
    ok = {k for k, _ in chunks if k is not None} == tagged
    anchor = spans[0][0]
    for k, text in chunks:
        template = spans[k - 1][0] if k in tagged else spans[base][0]
        run = copy.deepcopy(template)
        for child in list(run):
            if child.tag != qn("w:rPr"):
                run.remove(child)
        t = etree.SubElement(run, qn("w:t"))
        t.text = text
        t.set(XML_SPACE, "preserve")
        anchor.addprevious(run)
    for sp in spans:
        for r in sp:
            for t in r.findall(qn("w:t")):
                r.remove(t)
            if all(c.tag == qn("w:rPr") for c in r):
                r.getparent().remove(r)
    return ok


def cmd_fill(src: Path, seg_path: Path, out: Path) -> int:
    segs = load_segments(seg_path)
    trans = resolved(segs)
    doc = Document(str(src))
    paras = {f"p{n}": p for n, (_w, p) in enumerate(iter_paragraphs(doc), start=1)}
    done, missing, tag_issues = 0, [], []
    for s in segs:
        p = paras.get(s["id"])
        if p is None:
            raise SegError(f"片段 {s['id']} 在原文中找不到：请用同一份原文 docx 重新 extract")
        spans = _spans(p)
        if segment_text(p, spans) != s["text"]:
            raise SegError(
                f"片段 {s['id']} 与原文不一致：原文 docx 在 extract 之后被修改过，请重新 extract"
            )
        tr = trans.get(s["id"])
        if not tr:
            missing.append(s["id"])
            continue
        if len(spans) == 1:
            _write_span(spans[0], re.sub(r"</?\d+>", "", tr))
        elif _simple(p, spans):
            if not _rebuild(spans, tr):
                tag_issues.append(s["id"])
        else:
            parts = {int(k): v for k, v in TAG.findall(tr)}
            if set(parts) != set(range(1, len(spans) + 1)):
                tag_issues.append(s["id"])
                _write_span(spans[0], re.sub(r"</?\d+>", "", tr))
                for sp in spans[1:]:
                    _write_span(sp, "")
            else:
                for i, sp in enumerate(spans, start=1):
                    _write_span(sp, parts[i])
        done += 1
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    print(f"已生成 {out}：回填 {done} 个片段，未翻译 {len(missing)} 个（保留原文）")
    if missing:
        print("未翻译：" + "、".join(missing[:20]) + ("…" if len(missing) > 20 else ""))
    if tag_issues:
        print(
            f"{len(tag_issues)} 个片段的格式标签与原文不一致，已尽量回填，请在 Word 中核对："
            + "、".join(tag_issues[:20])
        )
    return 0


def _numbers(text: str) -> list[str]:
    return [n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]


def read_glossary(path: Path) -> list[tuple[str, str]]:
    raw = path.read_bytes()
    text = next((raw.decode(e) for e in ("utf-8-sig", "gb18030") if _decodes(raw, e)), None)
    if text is None:
        raise SegError(f"{path} 编码无法识别")
    rows = [r for r in csv.reader(io.StringIO(text)) if len(r) >= 2 and r[0].strip()]
    if rows and rows[0][0].strip() in ("原文", "source", "术语"):
        rows = rows[1:]
    return [(r[0].strip(), r[1].strip()) for r in rows]


def _decodes(raw: bytes, enc: str) -> bool:
    try:
        raw.decode(enc)
        return True
    except UnicodeDecodeError:
        return False


def cmd_check(seg_path: Path, glossary: Path | None) -> int:
    segs = load_segments(seg_path)
    trans = resolved(segs)
    problems: list[str] = []
    todo = [s for s in segs if "dup_of" not in s]
    untranslated = [s["id"] for s in todo if s["id"] not in trans]
    if untranslated:
        problems.append(
            f"未翻译 {len(untranslated)} 个："
            + "、".join(untranslated[:15])
            + ("…" if len(untranslated) > 15 else "")
        )
    terms = read_glossary(glossary) if glossary else []
    variants: dict[str, set[str]] = defaultdict(set)
    for s in todo:
        tr = trans.get(s["id"])
        if not tr:
            continue
        src_plain = TAG.sub(r"\2", s["text"])
        tr_plain = TAG.sub(r"\2", tr)
        variants[src_plain.strip()].add(tr_plain.strip())
        if sorted(k for k, _ in TAG.findall(s["text"])) != sorted(k for k, _ in TAG.findall(tr)):
            problems.append(f"{s['id']}：格式标签与原文不一致")
        lost = [n for n in _numbers(src_plain) if n not in _numbers(tr_plain)]
        if lost:
            problems.append(f"{s['id']}：原文数字 {', '.join(lost)} 在译文中没有出现，请核对")
        if (
            tr_plain.strip() == src_plain.strip()
            and re.search(r"[一-鿿]", src_plain)
            and len(src_plain) > 4
        ):
            problems.append(f"{s['id']}：译文与原文相同，可能漏译")
        for a, b in terms:
            if a.lower() in src_plain.lower() and b.lower() not in tr_plain.lower():
                problems.append(f"{s['id']}：术语「{a}」应译为「{b}」")
    for src, outs in variants.items():
        if len(outs) > 1 and len(src) <= 40:
            problems.append(f"同一原文「{src[:20]}」有 {len(outs)} 种译法，请统一")
    print(
        f"检查 {seg_path.name}：{len(todo)} 个待译片段，已翻译 {len(todo) - len(untranslated)} 个，发现 {len(problems)} 个问题"
    )
    for p in problems:
        print(f"- {p}")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("input")
    e.add_argument("-o", "--output", required=True)
    f = sub.add_parser("fill")
    f.add_argument("input")
    f.add_argument("segments")
    f.add_argument("-o", "--output", required=True)
    c = sub.add_parser("check")
    c.add_argument("segments")
    c.add_argument("--glossary")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "extract":
            return cmd_extract(Path(args.input), Path(args.output))
        if args.cmd == "fill":
            if Path(args.output).resolve() == Path(args.input).resolve():
                raise SegError("译文不能覆盖原文，请换一个输出文件名")
            return cmd_fill(Path(args.input), Path(args.segments), Path(args.output))
        return cmd_check(Path(args.segments), Path(args.glossary) if args.glossary else None)
    except (OSError, SegError, ValueError, KeyError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
