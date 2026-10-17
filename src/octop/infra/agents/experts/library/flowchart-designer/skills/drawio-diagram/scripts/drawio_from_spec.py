#!/usr/bin/env python3
"""Turn a small JSON flow spec into an editable draw.io file (and optionally Mermaid).

Usage:
    python scripts/drawio_from_spec.py flow.json -o flow.drawio [--mermaid flow.mmd]

Spec (see SKILL.md for details):
    {
      "title": "报销流程",
      "direction": "TB",                       # TB (top→bottom) or LR (left→right)
      "lanes": [{"id": "emp", "label": "员工"}],   # optional swimlanes
      "nodes": [{"id": "a", "label": "开始", "type": "start", "lane": "emp"}],
      "edges": [{"from": "a", "to": "b", "label": "是", "dashed": false}]
    }
Node types: start, end, process, decision, io, document, database, subprocess, note.

Layout is automatic (layered by longest path, back edges ignored for ranking);
open the .drawio in draw.io / diagrams.net to fine-tune.
Exit codes: 0 ok, 1 spec error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

SHAPES: dict[str, tuple[str, int, int]] = {
    # type: (style, width, height)
    "start": ("rounded=1;arcSize=50;fillColor=#d5e8d4;strokeColor=#82b366;", 120, 50),
    "end": ("rounded=1;arcSize=50;fillColor=#f8cecc;strokeColor=#b85450;", 120, 50),
    "process": ("rounded=1;arcSize=12;fillColor=#dae8fc;strokeColor=#6c8ebf;", 160, 60),
    "decision": ("rhombus;fillColor=#fff2cc;strokeColor=#d6b656;", 160, 90),
    "io": (
        "shape=parallelogram;perimeter=parallelogramPerimeter;fixedSize=1;fillColor=#e1d5e7;strokeColor=#9673a6;",
        170,
        60,
    ),
    "document": (
        "shape=document;boundedLbl=1;size=0.2;fillColor=#ffe6cc;strokeColor=#d79b00;",
        160,
        70,
    ),
    "database": (
        "shape=cylinder3;boundedLbl=1;size=10;fillColor=#f5f5f5;strokeColor=#666666;",
        120,
        80,
    ),
    "subprocess": (
        "shape=process;backgroundOutline=1;size=0.08;fillColor=#dae8fc;strokeColor=#6c8ebf;",
        170,
        60,
    ),
    "note": (
        "shape=note;size=14;fillColor=#ffffff;strokeColor=#999999;align=left;spacingLeft=8;",
        170,
        60,
    ),
}
COMMON = "whiteSpace=wrap;html=1;fontSize=13;fontFamily=Helvetica;"
EDGE = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;strokeColor=#555555;fontSize=12;labelBackgroundColor=#ffffff;"
RANK_GAP = 70
CROSS_GAP = 50
LANE_HEADER = 36
LANE_PAD = 30

MERMAID_SHAPES = {
    "start": ('(["', '"])'),
    "end": ('(["', '"])'),
    "process": ('["', '"]'),
    "decision": ('{"', '"}'),
    "io": ('[/"', '"/]'),
    "document": ('["', '"]'),
    "database": ('[("', '")]'),
    "subprocess": ('[["', '"]]'),
    "note": ('>"', '"]'),
}


class SpecError(ValueError):
    pass


def validate(
    spec: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = spec.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise SpecError("nodes 必须是非空数组")
    lanes = spec.get("lanes") or []
    lane_ids = {lane["id"] for lane in lanes}
    seen: set[str] = set()
    for i, node in enumerate(nodes):
        nid = node.get("id")
        if not isinstance(nid, str) or not nid:
            raise SpecError(f"nodes[{i}] 缺少 id")
        if nid in seen:
            raise SpecError(f"节点 id 重复：{nid}")
        seen.add(nid)
        node.setdefault("type", "process")
        if node["type"] not in SHAPES:
            raise SpecError(
                f"节点 {nid} 的 type {node['type']!r} 不支持，可选：{', '.join(SHAPES)}"
            )
        if lanes and node.get("lane") not in lane_ids:
            raise SpecError(f"节点 {nid} 的 lane {node.get('lane')!r} 不在 lanes 中")
    edges = spec.get("edges") or []
    for i, edge in enumerate(edges):
        for end in ("from", "to"):
            if edge.get(end) not in seen:
                raise SpecError(f"edges[{i}].{end} 指向不存在的节点 {edge.get(end)!r}")
    if spec.get("direction", "TB") not in ("TB", "LR"):
        raise SpecError("direction 只支持 TB 或 LR")
    return nodes, edges, lanes


def rank_nodes(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, int]:
    """Longest-path layering; edges closing a cycle (found by DFS) are ignored."""
    order = [n["id"] for n in nodes]
    succ: dict[str, list[str]] = {nid: [] for nid in order}
    for e in edges:
        succ[e["from"]].append(e["to"])
    state: dict[str, int] = {}
    forward: dict[str, list[str]] = {nid: [] for nid in order}

    def dfs(start: str) -> None:
        stack: list[tuple[str, int]] = [(start, 0)]
        state[start] = 1
        while stack:
            node, i = stack.pop()
            if i < len(succ[node]):
                stack.append((node, i + 1))
                nxt = succ[node][i]
                if state.get(nxt) == 1:
                    continue  # back edge
                forward[node].append(nxt)
                if nxt not in state:
                    state[nxt] = 1
                    stack.append((nxt, 0))
            else:
                state[node] = 2

    for nid in order:
        if nid not in state:
            dfs(nid)
    rank = dict.fromkeys(order, 0)
    # Kahn over the forward DAG.
    indeg = dict.fromkeys(order, 0)
    for src in order:
        for dst in forward[src]:
            indeg[dst] += 1
    queue = [nid for nid in order if indeg[nid] == 0]
    while queue:
        cur = queue.pop(0)
        for dst in forward[cur]:
            rank[dst] = max(rank[dst], rank[cur] + 1)
            indeg[dst] -= 1
            if indeg[dst] == 0:
                queue.append(dst)
    return rank


def layout(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    lanes: list[dict[str, Any]],
    direction: str,
) -> tuple[dict[str, tuple[int, int, int, int]], list[tuple[str, int, int, int, int]]]:
    """Return node boxes {id: (x, y, w, h)} and lane boxes [(label, x, y, w, h)]."""
    rank = rank_nodes(nodes, edges)
    max_w = max(SHAPES[n["type"]][1] for n in nodes)
    max_h = max(SHAPES[n["type"]][2] for n in nodes)
    along = (max_h if direction == "TB" else max_w) + RANK_GAP
    across = (max_w if direction == "TB" else max_h) + CROSS_GAP
    lane_keys = [lane["id"] for lane in lanes] or [""]
    # slot[(lane, rank)] -> nodes stacked across the flow inside that lane
    slots: dict[tuple[str, int], list[str]] = {}
    for n in nodes:
        slots.setdefault((n.get("lane", ""), rank[n["id"]]), []).append(n["id"])
    lane_width = {
        key: max((len(v) for (lane, _), v in slots.items() if lane == key), default=1)
        for key in lane_keys
    }
    boxes: dict[str, tuple[int, int, int, int]] = {}
    lane_boxes: list[tuple[str, int, int, int, int]] = []
    # Lane headers sit at the start of the flow axis (top for TB, left for LR).
    head = LANE_HEADER + LANE_PAD // 2 if lanes else 0
    offset = 0
    n_ranks = max(rank.values()) + 1
    flow_len = n_ranks * along + (LANE_HEADER + LANE_PAD if lanes else 0)
    by_id = {n["id"]: n for n in nodes}
    for key in lane_keys:
        span = lane_width[key] * across
        for (lane, r), ids in slots.items():
            if lane != key:
                continue
            for i, nid in enumerate(ids):
                _, w, h = SHAPES[by_id[nid]["type"]]
                # centre each node in its cell
                cross_c = offset + i * across + across // 2 + (span - len(ids) * across) // 2
                along_c = head + r * along + along // 2
                if direction == "TB":
                    boxes[nid] = (cross_c - w // 2, along_c - h // 2, w, h)
                else:
                    boxes[nid] = (along_c - w // 2, cross_c - h // 2, w, h)
        if lanes:
            label = next(lane["label"] for lane in lanes if lane["id"] == key)
            if direction == "TB":
                lane_boxes.append((label, offset, 0, span, flow_len))
            else:
                lane_boxes.append((label, 0, offset, flow_len, span))
        offset += span
    return boxes, lane_boxes


def to_drawio(spec: dict[str, Any]) -> str:
    nodes, edges, lanes = validate(spec)
    direction = spec.get("direction", "TB")
    boxes, lane_boxes = layout(nodes, edges, lanes, direction)
    rank = rank_nodes(nodes, edges)
    # Loop-back edges leave and re-enter on the outer side so they don't cut through nodes.
    back_style = (
        "exitX=1;exitY=0.5;entryX=1;entryY=0.5;"
        if direction == "TB"
        else "exitX=0.5;exitY=1;entryX=0.5;entryY=1;"
    )
    cells = ['<mxCell id="0" />', '<mxCell id="1" parent="0" />']
    horizontal = "1" if direction == "TB" else "0"
    for i, (label, x, y, w, h) in enumerate(lane_boxes):
        style = (
            f"swimlane;horizontal={horizontal};startSize={LANE_HEADER};html=1;fontStyle=1;"
            "fillColor=#f5f5f5;strokeColor=#999999;swimlaneFillColor=#ffffff;fontSize=14;"
        )
        cells.append(
            f'<mxCell id="lane-{i}" value="{escape(label, {chr(34): "&quot;"})}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" /></mxCell>'
        )
    for n in nodes:
        style, _, _ = SHAPES[n["type"]]
        x, y, w, h = boxes[n["id"]]
        label = escape(str(n.get("label", n["id"])), {'"': "&quot;", "\n": "&#xa;"})
        cells.append(
            f'<mxCell id="n-{escape(n["id"])}" value="{label}" style="{style}{COMMON}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" /></mxCell>'
        )
    for i, e in enumerate(edges):
        style = EDGE + ("dashed=1;" if e.get("dashed") else "")
        geometry = '<mxGeometry relative="1" as="geometry" />'
        lo, hi = rank[e["to"]], rank[e["from"]]
        if lo <= hi:
            style += back_style
            # Route outside every node the loop spans (staying inside the lane band).
            gap = CROSS_GAP // 2 - 5 if lanes else 30
            spanned = [boxes[n["id"]] for n in nodes if lo <= rank[n["id"]] <= hi]
            sx, sy, sw, sh = boxes[e["from"]]
            tx, ty, tw, th = boxes[e["to"]]
            if direction == "TB":
                outer = max(x + w for x, _, w, _ in spanned) + gap
                points = [(outer, sy + sh // 2), (outer, ty + th // 2)]
            else:
                outer = max(y + h for _, y, _, h in spanned) + gap
                points = [(sx + sw // 2, outer), (tx + tw // 2, outer)]
            pts = "".join(f'<mxPoint x="{px}" y="{py}" />' for px, py in points)
            geometry = f'<mxGeometry relative="1" as="geometry"><Array as="points">{pts}</Array></mxGeometry>'
        label = escape(str(e.get("label", "")), {'"': "&quot;"})
        cells.append(
            f'<mxCell id="e-{i}" value="{label}" style="{style}" edge="1" parent="1" '
            f'source="n-{escape(e["from"])}" target="n-{escape(e["to"])}">'
            f"{geometry}</mxCell>"
        )
    title = escape(str(spec.get("title", "流程图")), {'"': "&quot;"})
    body = "\n        ".join(cells)
    return (
        '<mxfile host="Octop" type="device">\n'
        f'  <diagram id="flow" name="{title}">\n'
        '    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" '
        'connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1169" '
        'pageHeight="827" math="0" shadow="0">\n'
        "      <root>\n"
        f"        {body}\n"
        "      </root>\n"
        "    </mxGraphModel>\n"
        "  </diagram>\n"
        "</mxfile>\n"
    )


def _mermaid_label(text: str) -> str:
    return text.replace('"', "#quot;").replace("\n", "<br/>")


def to_mermaid(spec: dict[str, Any]) -> str:
    nodes, edges, lanes = validate(spec)
    lines = [f"flowchart {spec.get('direction', 'TB')}"]
    # Spec ids may be Mermaid keywords (end, subgraph, …); emit safe ids instead.
    ids = {n["id"]: f"n{i}" for i, n in enumerate(nodes, start=1)}

    def node_line(n: dict[str, Any], indent: str) -> str:
        left, right = MERMAID_SHAPES[n["type"]]
        return f"{indent}{ids[n['id']]}{left}{_mermaid_label(str(n.get('label', n['id'])))}{right}"

    if lanes:
        for i, lane in enumerate(lanes, start=1):
            lines.append(f'  subgraph lane{i}["{_mermaid_label(lane["label"])}"]')
            lines.extend(node_line(n, "    ") for n in nodes if n.get("lane") == lane["id"])
            lines.append("  end")
    else:
        lines.extend(node_line(n, "  ") for n in nodes)
    for e in edges:
        arrow = "-.->" if e.get("dashed") else "-->"
        label = f'|"{_mermaid_label(str(e["label"]))}"|' if e.get("label") else ""
        lines.append(f"  {ids[e['from']]} {arrow}{label} {ids[e['to']]}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("spec")
    parser.add_argument("-o", "--output", required=True, help="output .drawio path")
    parser.add_argument("--mermaid", help="also write equivalent Mermaid source here")
    args = parser.parse_args(argv)
    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        xml = to_drawio(spec)
        mermaid = to_mermaid(spec) if args.mermaid else None
    except (OSError, json.JSONDecodeError, SpecError, KeyError) as exc:
        print(f"spec 错误：{exc}", file=sys.stderr)
        return 1
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(xml, encoding="utf-8")
    print(f"已生成 {out}（{len(spec['nodes'])} 个节点，{len(spec.get('edges') or [])} 条连线）")
    if mermaid is not None:
        Path(args.mermaid).write_text(mermaid, encoding="utf-8")
        print(f"已生成 {args.mermaid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
