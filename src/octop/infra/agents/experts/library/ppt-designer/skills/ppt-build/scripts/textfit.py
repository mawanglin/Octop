"""Rough text-size estimation shared by build_deck.py and inspect_deck.py.

python-pptx cannot measure rendered text, so we approximate: CJK / full-width
glyphs are 1 em wide, ASCII letters ~0.55 em, spaces ~0.3 em. Good enough to
pick a font size and to flag likely overflow; not a layout engine.
"""

from __future__ import annotations

import math
import unicodedata

LINE_SPACING = 1.25
"""Line height as a multiple of font size."""

PARA_GAP_EM = 0.35
"""Extra space between paragraphs, in em."""


def char_em(ch: str) -> float:
    if ch == " ":
        return 0.3
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 1.0
    if ch.isupper() or ch.isdigit():
        return 0.62
    return 0.52


def text_em(text: str) -> float:
    return sum(char_em(ch) for ch in text)


def paragraph_lines(text: str, size_pt: float, width_in: float) -> int:
    """Number of wrapped lines one paragraph needs inside *width_in* inches."""
    if width_in <= 0:
        return 1
    width_pt = width_in * 72
    lines = 0
    for chunk in text.split("\n") or [""]:
        em = text_em(chunk)
        lines += max(1, math.ceil(em * size_pt / width_pt))
    return lines


def text_height_in(paragraphs: list[str], size_pt: float, width_in: float) -> float:
    """Estimated rendered height (inches) of *paragraphs* at *size_pt*."""
    if not paragraphs:
        return 0.0
    lines = sum(paragraph_lines(p, size_pt, width_in) for p in paragraphs)
    gaps = max(0, len(paragraphs) - 1) * PARA_GAP_EM
    return (lines * LINE_SPACING + gaps) * size_pt / 72


def fit_size(
    paragraphs: list[str],
    width_in: float,
    height_in: float,
    max_pt: float,
    min_pt: float,
) -> float:
    """Largest whole-point size in [min_pt, max_pt] whose estimate fits the box."""
    size = max_pt
    while size > min_pt:
        if text_height_in(paragraphs, size, width_in) <= height_in:
            return size
        size -= 1
    return min_pt
