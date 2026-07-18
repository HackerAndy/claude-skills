#!/usr/bin/env python3
"""
render_bpmn.py — Render a standards-compliant BPMN 2.0 diagram as an SVG.

The input is a JSON process definition (file path or stdin). The output is an
SVG file. The renderer follows the BPMN 2.0 visual conventions closely so the
result reads correctly to anyone who knows the notation:

  * Start / end / intermediate events   -> circles (thin / thick / double ring)
  * Tasks and sub-processes             -> rounded rectangles (with type marker)
  * Gateways                            -> diamonds (with X / + / O / pentagon marker)
  * Data objects                        -> dog-eared page
  * Sequence flows                      -> solid arrows
  * Message flows                       -> dashed arrows with open circle + open head
  * Pools / lanes                       -> labelled containers (swimlanes)

LAYOUT MODEL
------------
You place each node on a grid. `col` is the horizontal step (0,1,2,...) and the
node's vertical position is derived from the lane it belongs to. This keeps the
authoring burden low: you describe *what connects to what and in what order*,
and the script handles pixel geometry, lane sizing, and routing. You can still
nudge anything with an explicit `col` (fractional allowed, e.g. 2.5) or a
`row` offset within a lane when two nodes share a column.

See references/bpmn-notation.md for the full schema and worked examples.
"""

import json
import sys
import argparse
from collections import defaultdict

# ---- Visual constants (BPMN-ish proportions) -------------------------------
COL_W = 150          # horizontal distance between grid columns
EVENT_R = 18         # event circle radius
TASK_W = 110         # task box width
TASK_H = 70          # task box height
GW_R = 25            # gateway half-diagonal
DATA_W = 45
DATA_H = 58
LANE_PAD_TOP = 28
LANE_LABEL_W = 34    # width of the rotated lane label strip
POOL_LABEL_W = 34
MARGIN = 40
FONT = "Segoe UI, Helvetica, Arial, sans-serif"

# Palette — muted, print-friendly, high-contrast text
C_STROKE = "#2c3e50"
C_TASK_FILL = "#eef3f8"
C_TASK_STROKE = "#4a6785"
C_EVENT_START = "#e8f5e9"
C_EVENT_START_STROKE = "#4a944e"
C_EVENT_END = "#fdecea"
C_EVENT_END_STROKE = "#c0392b"
C_EVENT_INT = "#fff8e1"
C_EVENT_INT_STROKE = "#c9930a"
C_GW_FILL = "#fef9e7"
C_GW_STROKE = "#c9930a"
C_LANE_LABEL = "#34495e"
C_POOL_LABEL = "#2c3e50"
C_FLOW = "#34495e"
C_DATA_FILL = "#ffffff"
C_TEXT = "#1a2530"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def wrap(text, max_chars):
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def text_block(cx, cy, text, max_chars=15, size=11, weight="normal", fill=C_TEXT):
    lines = wrap(text, max_chars)
    lh = size + 2
    start_y = cy - (len(lines) - 1) * lh / 2
    out = []
    for i, ln in enumerate(lines):
        out.append(
            f'<text x="{cx:.1f}" y="{start_y + i*lh:.1f}" text-anchor="middle" '
            f'dominant-baseline="central" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}">{esc(ln)}</text>'
        )
    return "\n".join(out)


# ---- Event / task / gateway type markers -----------------------------------
def event_marker(cx, cy, etype, stroke):
    """Small glyph inside an event circle (message, timer, error, etc.)."""
    m = ""
    if etype == "message":
        m = (f'<rect x="{cx-8:.1f}" y="{cy-6:.1f}" width="16" height="12" rx="1" '
             f'fill="none" stroke="{stroke}" stroke-width="1.4"/>'
             f'<path d="M{cx-8:.1f},{cy-6:.1f} L{cx:.1f},{cy+1:.1f} L{cx+8:.1f},{cy-6:.1f}" '
             f'fill="none" stroke="{stroke}" stroke-width="1.4"/>')
    elif etype == "timer":
        m = (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="8" fill="none" stroke="{stroke}" stroke-width="1.4"/>'
             f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx:.1f}" y2="{cy-6:.1f}" stroke="{stroke}" stroke-width="1.4"/>'
             f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx+5:.1f}" y2="{cy+2:.1f}" stroke="{stroke}" stroke-width="1.4"/>')
    elif etype == "error":
        m = (f'<path d="M{cx-7:.1f},{cy+6:.1f} L{cx-2:.1f},{cy-5:.1f} L{cx+1:.1f},{cy+1:.1f} '
             f'L{cx+7:.1f},{cy-6:.1f} L{cx+2:.1f},{cy+6:.1f} L{cx-1:.1f},{cy:.1f} Z" '
             f'fill="none" stroke="{stroke}" stroke-width="1.4"/>')
    elif etype == "signal":
        m = (f'<path d="M{cx:.1f},{cy-7:.1f} L{cx+7:.1f},{cy+6:.1f} L{cx-7:.1f},{cy+6:.1f} Z" '
             f'fill="none" stroke="{stroke}" stroke-width="1.4"/>')
    return m


def draw_event(node):
    cx, cy = node["_x"], node["_y"]
    kind = node.get("kind", "start")  # start | end | intermediate
    if kind == "end":
        fill, stroke, sw = C_EVENT_END, C_EVENT_END_STROKE, 3.2
        rings = f'<circle cx="{cx}" cy="{cy}" r="{EVENT_R}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
    elif kind == "intermediate":
        fill, stroke = C_EVENT_INT, C_EVENT_INT_STROKE
        rings = (f'<circle cx="{cx}" cy="{cy}" r="{EVENT_R}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>'
                 f'<circle cx="{cx}" cy="{cy}" r="{EVENT_R-4}" fill="none" stroke="{stroke}" stroke-width="1.6"/>')
    else:  # start
        fill, stroke = C_EVENT_START, C_EVENT_START_STROKE
        rings = f'<circle cx="{cx}" cy="{cy}" r="{EVENT_R}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>'
    marker = event_marker(cx, cy, node.get("event_type", ""), stroke)
    label = ""
    if node.get("label"):
        label = text_block(cx, cy + EVENT_R + 14, node["label"], max_chars=16, size=10)
    return f'<g>{rings}{marker}{label}</g>'


TASK_MARKERS = {
    "user": lambda x, y: (f'<circle cx="{x+8}" cy="{y+7}" r="4" fill="none" stroke="{C_TASK_STROKE}" stroke-width="1.2"/>'
                          f'<path d="M{x+3},{y+15} Q{x+8},{y+10} {x+13},{y+15}" fill="none" stroke="{C_TASK_STROKE}" stroke-width="1.2"/>'),
    "service": lambda x, y: (f'<circle cx="{x+8}" cy="{y+9}" r="5" fill="none" stroke="{C_TASK_STROKE}" stroke-width="1.2"/>'
                             f'<circle cx="{x+8}" cy="{y+9}" r="2" fill="none" stroke="{C_TASK_STROKE}" stroke-width="1.2"/>'),
    "manual": lambda x, y: (f'<path d="M{x+3},{y+12} q2,-6 6,-6 l4,0 q2,0 2,2 l0,4 q0,2 -2,2 l-8,0 z" '
                            f'fill="none" stroke="{C_TASK_STROKE}" stroke-width="1.2"/>'),
    "script": lambda x, y: (f'<rect x="{x+3}" y="{y+4}" width="11" height="12" fill="none" stroke="{C_TASK_STROKE}" stroke-width="1.2"/>'
                            f'<line x1="{x+5}" y1="{y+7}" x2="{x+12}" y2="{y+7}" stroke="{C_TASK_STROKE}" stroke-width="1"/>'
                            f'<line x1="{x+5}" y1="{y+10}" x2="{x+12}" y2="{y+10}" stroke="{C_TASK_STROKE}" stroke-width="1"/>'
                            f'<line x1="{x+5}" y1="{y+13}" x2="{x+10}" y2="{y+13}" stroke="{C_TASK_STROKE}" stroke-width="1"/>'),
    "send": lambda x, y: (f'<rect x="{x+3}" y="{y+5}" width="14" height="10" fill="{C_TASK_STROKE}" stroke="{C_TASK_STROKE}" stroke-width="1"/>'
                          f'<path d="M{x+3},{y+5} L{x+10},{y+11} L{x+17},{y+5}" fill="none" stroke="#fff" stroke-width="1.2"/>'),
    "receive": lambda x, y: (f'<rect x="{x+3}" y="{y+5}" width="14" height="10" fill="none" stroke="{C_TASK_STROKE}" stroke-width="1.2"/>'
                             f'<path d="M{x+3},{y+5} L{x+10},{y+11} L{x+17},{y+5}" fill="none" stroke="{C_TASK_STROKE}" stroke-width="1.2"/>'),
}


def draw_task(node):
    x = node["_x"] - TASK_W / 2
    y = node["_y"] - TASK_H / 2
    is_sub = node.get("kind") == "subprocess"
    sw = 2.0 if is_sub else 1.4
    body = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{TASK_W}" height="{TASK_H}" rx="10" '
            f'fill="{C_TASK_FILL}" stroke="{C_TASK_STROKE}" stroke-width="{sw}"/>')
    marker = ""
    ttype = node.get("task_type")
    if ttype in TASK_MARKERS:
        marker = TASK_MARKERS[ttype](x, y)
    sub_marker = ""
    if is_sub:
        cx, cy = node["_x"], y + TASK_H - 10
        sub_marker = (f'<rect x="{cx-6:.1f}" y="{cy-6:.1f}" width="12" height="12" fill="none" '
                      f'stroke="{C_TASK_STROKE}" stroke-width="1.2"/>'
                      f'<line x1="{cx-3:.1f}" y1="{cy:.1f}" x2="{cx+3:.1f}" y2="{cy:.1f}" stroke="{C_TASK_STROKE}" stroke-width="1.2"/>'
                      f'<line x1="{cx:.1f}" y1="{cy-3:.1f}" x2="{cx:.1f}" y2="{cy+3:.1f}" stroke="{C_TASK_STROKE}" stroke-width="1.2"/>')
    label = text_block(node["_x"], node["_y"], node.get("label", ""), max_chars=16, size=11, weight="500")
    return f'<g>{body}{marker}{sub_marker}{label}</g>'


GW_MARKERS = {
    "exclusive": lambda cx, cy: (f'<line x1="{cx-7}" y1="{cy-7}" x2="{cx+7}" y2="{cy+7}" stroke="{C_GW_STROKE}" stroke-width="2.4"/>'
                                 f'<line x1="{cx-7}" y1="{cy+7}" x2="{cx+7}" y2="{cy-7}" stroke="{C_GW_STROKE}" stroke-width="2.4"/>'),
    "parallel": lambda cx, cy: (f'<line x1="{cx}" y1="{cy-9}" x2="{cx}" y2="{cy+9}" stroke="{C_GW_STROKE}" stroke-width="2.4"/>'
                                f'<line x1="{cx-9}" y1="{cy}" x2="{cx+9}" y2="{cy}" stroke="{C_GW_STROKE}" stroke-width="2.4"/>'),
    "inclusive": lambda cx, cy: f'<circle cx="{cx}" cy="{cy}" r="8" fill="none" stroke="{C_GW_STROKE}" stroke-width="2.2"/>',
    "event": lambda cx, cy: (f'<circle cx="{cx}" cy="{cy}" r="9" fill="none" stroke="{C_GW_STROKE}" stroke-width="1.4"/>'
                             f'<circle cx="{cx}" cy="{cy}" r="6" fill="none" stroke="{C_GW_STROKE}" stroke-width="1.4"/>'),
}


def draw_gateway(node):
    cx, cy = node["_x"], node["_y"]
    pts = f"{cx},{cy-GW_R} {cx+GW_R},{cy} {cx},{cy+GW_R} {cx-GW_R},{cy}"
    body = f'<polygon points="{pts}" fill="{C_GW_FILL}" stroke="{C_GW_STROKE}" stroke-width="1.6"/>'
    marker = GW_MARKERS.get(node.get("gateway_type", "exclusive"), GW_MARKERS["exclusive"])(cx, cy)
    label = ""
    if node.get("label"):
        label = text_block(cx, cy - GW_R - 12, node["label"], max_chars=18, size=10)
    return f'<g>{body}{marker}{label}</g>'


def draw_data(node):
    x = node["_x"] - DATA_W / 2
    y = node["_y"] - DATA_H / 2
    fold = 12
    path = (f'M{x},{y} L{x+DATA_W-fold},{y} L{x+DATA_W},{y+fold} L{x+DATA_W},{y+DATA_H} '
            f'L{x},{y+DATA_H} Z')
    foldpath = f'M{x+DATA_W-fold},{y} L{x+DATA_W-fold},{y+fold} L{x+DATA_W},{y+fold}'
    label = text_block(node["_x"], y + DATA_H + 12, node.get("label", ""), max_chars=14, size=9)
    return (f'<g><path d="{path}" fill="{C_DATA_FILL}" stroke="{C_STROKE}" stroke-width="1.3"/>'
            f'<path d="{foldpath}" fill="none" stroke="{C_STROKE}" stroke-width="1.3"/>{label}</g>')


# ---- Node dispatch ---------------------------------------------------------
def node_dims(node):
    t = node["type"]
    if t == "event":
        return EVENT_R * 2, EVENT_R * 2
    if t in ("task", "subprocess"):
        return TASK_W, TASK_H
    if t == "gateway":
        return GW_R * 2, GW_R * 2
    if t == "data":
        return DATA_W, DATA_H
    return TASK_W, TASK_H


def draw_node(node):
    t = node["type"]
    if t == "event":
        return draw_event(node)
    if t in ("task", "subprocess"):
        return draw_task(node)
    if t == "gateway":
        return draw_gateway(node)
    if t == "data":
        return draw_data(node)
    return draw_task(node)


def anchor(node, side):
    x, y = node["_x"], node["_y"]
    w, h = node_dims(node)
    if node["type"] == "gateway":
        if side == "l": return (x - GW_R, y)
        if side == "r": return (x + GW_R, y)
        if side == "t": return (x, y - GW_R)
        if side == "b": return (x, y + GW_R)
    if node["type"] == "event":
        if side == "l": return (x - EVENT_R, y)
        if side == "r": return (x + EVENT_R, y)
        if side == "t": return (x, y - EVENT_R)
        if side == "b": return (x, y + EVENT_R)
    if side == "l": return (x - w / 2, y)
    if side == "r": return (x + w / 2, y)
    if side == "t": return (x, y - h / 2)
    if side == "b": return (x, y + h / 2)
    return (x, y)


def route(src, dst, label, kind="sequence", waypoints=None):
    """Draw a connector between two nodes with automatic side selection."""
    dx = dst["_x"] - src["_x"]
    dy = dst["_y"] - src["_y"]
    if abs(dx) >= abs(dy):
        s_side = "r" if dx >= 0 else "l"
        d_side = "l" if dx >= 0 else "r"
    else:
        s_side = "b" if dy >= 0 else "t"
        d_side = "t" if dy >= 0 else "b"
    sx, sy = anchor(src, s_side)
    ex, ey = anchor(dst, d_side)

    pts = [(sx, sy)]
    if waypoints:
        pts += [(p[0], p[1]) for p in waypoints]
    else:
        # simple orthogonal elbow when there is both horizontal and vertical travel
        if abs(dx) > 2 and abs(dy) > 2:
            if s_side in ("r", "l"):
                midx = (sx + ex) / 2
                pts += [(midx, sy), (midx, ey)]
            else:
                midy = (sy + ey) / 2
                pts += [(sx, midy), (ex, midy)]
    pts.append((ex, ey))

    d = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    if kind == "message":
        line = (f'<path d="{d}" fill="none" stroke="{C_FLOW}" stroke-width="1.4" '
                f'stroke-dasharray="6,4" marker-start="url(#msgstart)" marker-end="url(#msghead)"/>')
    else:
        line = f'<path d="{d}" fill="none" stroke="{C_FLOW}" stroke-width="1.5" marker-end="url(#arrow)"/>'

    lbl = ""
    if label:
        # place the label on the longest segment so parallel branches
        # (e.g. Yes/No out of one gateway) don't collide on a shared stub
        best_i, best_len = 0, -1.0
        for i in range(len(pts) - 1):
            seg = ((pts[i+1][0]-pts[i][0])**2 + (pts[i+1][1]-pts[i][1])**2) ** 0.5
            if seg > best_len:
                best_len, best_i = seg, i
        lx = (pts[best_i][0] + pts[best_i+1][0]) / 2
        ly = (pts[best_i][1] + pts[best_i+1][1]) / 2 - 6
        lbl = (f'<rect x="{lx-len(label)*3-3:.1f}" y="{ly-8:.1f}" width="{len(label)*6+6}" height="14" '
               f'fill="#ffffff" opacity="0.85"/>'
               f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" dominant-baseline="central" '
               f'font-family="{FONT}" font-size="9.5" fill="{C_TEXT}">{esc(label)}</text>')
    return line + lbl


def build_multipool(defn):
    """Render two or more pools (participants) stacked vertically, joined by
    message flows. Activated when the definition supplies a top-level `pools`
    array (each pool having its own `lanes`). Single-pool definitions use the
    legacy `build()` path unchanged."""
    title = defn.get("title", "")
    pools = defn["pools"]
    nodes = {n["id"]: n for n in defn["nodes"]}
    flows = defn.get("flows", [])
    lane_h = defn.get("lane_height", 120)
    POOL_GAP = 36

    # Flatten lanes, remembering which pool each belongs to (in reading order).
    lanes = []
    lane_pool_id = {}
    for p in pools:
        plns = p.get("lanes") or [{"id": p["id"], "label": p.get("label", "")}]
        for ln in plns:
            lanes.append(ln)
            lane_pool_id[ln["id"]] = p["id"]

    any_lane_label = any(l.get("label") for l in lanes)
    any_pool_label = any(p.get("label") for p in pools)
    pool_strip_w = POOL_LABEL_W if any_pool_label else 0
    lane_strip_w = LANE_LABEL_W if any_lane_label else 0
    left_offset = MARGIN + pool_strip_w + lane_strip_w

    title_h = 34 if title else 8
    top = title_h
    lanes_top = top + LANE_PAD_TOP - 20

    # Vertical layout: assign each lane a top-y, inserting a gap between pools.
    lane_top = {}
    pool_span = {}
    y = lanes_top
    prev_pid = None
    for ln in lanes:
        pid = lane_pool_id[ln["id"]]
        if prev_pid is not None and pid != prev_pid:
            y += POOL_GAP
        if pid not in pool_span:
            pool_span[pid] = [y, y]
        lane_top[ln["id"]] = y
        y += lane_h
        pool_span[pid][1] = y
        prev_pid = pid
    bottom = y

    max_col = max((n.get("col", 0) for n in nodes.values()), default=0)
    for n in nodes.values():
        lt = lane_top.get(n.get("lane"), lanes_top)
        row = n.get("row", 0)
        n["_x"] = left_offset + 30 + n.get("col", 0) * COL_W + TASK_W / 2
        n["_y"] = lt + lane_h / 2 + row * 55

    diagram_w = MARGIN + (max_col + 1) * COL_W + MARGIN
    diagram_w = max(diagram_w, max((n["_x"] for n in nodes.values()), default=0) + TASK_W)
    total_w = diagram_w + MARGIN
    total_h = bottom + MARGIN

    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w:.0f} {total_h:.0f}" '
        f'font-family="{FONT}">'
    )
    svg.append(f'''<defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="{C_FLOW}"/>
      </marker>
      <marker id="msghead" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="10" markerHeight="10" orient="auto-start-reverse">
        <path d="M1,1 L11,6 L1,11" fill="none" stroke="{C_FLOW}" stroke-width="1.4"/>
      </marker>
      <marker id="msgstart" viewBox="0 0 12 12" refX="6" refY="6" markerWidth="9" markerHeight="9">
        <circle cx="6" cy="6" r="4" fill="#ffffff" stroke="{C_FLOW}" stroke-width="1.3"/>
      </marker>
    </defs>''')
    svg.append(f'<rect x="0" y="0" width="{total_w:.0f}" height="{total_h:.0f}" fill="#ffffff"/>')

    if title:
        svg.append(f'<text x="{total_w/2:.0f}" y="22" text-anchor="middle" font-family="{FONT}" '
                   f'font-size="16" font-weight="700" fill="{C_TEXT}">{esc(title)}</text>')

    pool_x = MARGIN
    for p in pools:
        pid = p["id"]
        ptop, pbot = pool_span[pid]
        # outer pool box
        svg.append(f'<rect x="{pool_x}" y="{ptop:.0f}" width="{total_w-MARGIN-pool_x:.0f}" '
                   f'height="{pbot-ptop:.0f}" fill="none" stroke="{C_STROKE}" stroke-width="1.4"/>')
        if p.get("label"):
            svg.append(f'<rect x="{pool_x}" y="{ptop:.0f}" width="{POOL_LABEL_W}" '
                       f'height="{pbot-ptop:.0f}" fill="#f4f6f8" stroke="{C_STROKE}" stroke-width="1.4"/>')
            pcx = pool_x + POOL_LABEL_W / 2
            pcy = (ptop + pbot) / 2
            svg.append(f'<text x="{pcx:.0f}" y="{pcy:.0f}" text-anchor="middle" dominant-baseline="central" '
                       f'font-family="{FONT}" font-size="12" font-weight="700" fill="{C_POOL_LABEL}" '
                       f'transform="rotate(-90 {pcx:.0f} {pcy:.0f})">{esc(p["label"])}</text>')
        plns = [ln for ln in lanes if lane_pool_id[ln["id"]] == pid]
        for i, ln in enumerate(plns):
            ly = lane_top[ln["id"]]
            if i > 0:
                svg.append(f'<line x1="{pool_x + pool_strip_w:.0f}" y1="{ly:.0f}" '
                           f'x2="{total_w-MARGIN:.0f}" y2="{ly:.0f}" stroke="{C_STROKE}" stroke-width="1"/>')
            if ln.get("label"):
                lbx = pool_x + pool_strip_w
                svg.append(f'<rect x="{lbx:.0f}" y="{ly:.0f}" width="{LANE_LABEL_W}" height="{lane_h}" '
                           f'fill="#fafbfc" stroke="{C_STROKE}" stroke-width="1"/>')
                lcx = lbx + LANE_LABEL_W / 2
                lcy = ly + lane_h / 2
                svg.append(f'<text x="{lcx:.0f}" y="{lcy:.0f}" text-anchor="middle" dominant-baseline="central" '
                           f'font-family="{FONT}" font-size="11" font-weight="600" fill="{C_LANE_LABEL}" '
                           f'transform="rotate(-90 {lcx:.0f} {lcy:.0f})">{esc(ln["label"])}</text>')

    flow_svg = []
    for f in flows:
        src = nodes.get(f["from"])
        dst = nodes.get(f["to"])
        if not src or not dst:
            sys.stderr.write(f"warning: flow references unknown node {f}\n")
            continue
        flow_svg.append(route(src, dst, f.get("label", ""), f.get("type", "sequence"),
                              f.get("waypoints")))
    svg.extend(flow_svg)

    for n in nodes.values():
        svg.append(draw_node(n))

    svg.append("</svg>")
    return "\n".join(svg)


def build(defn):
    if defn.get("pools"):
        return build_multipool(defn)
    title = defn.get("title", "")
    lanes = defn.get("lanes", [])
    pool = defn.get("pool")
    nodes = {n["id"]: n for n in defn["nodes"]}
    flows = defn.get("flows", [])

    # --- Determine grid extents ---
    max_col = max((n.get("col", 0) for n in nodes.values()), default=0)
    diagram_w = MARGIN + (max_col + 1) * COL_W + MARGIN

    # --- Lane vertical layout ---
    lane_h = defn.get("lane_height", 120)
    if not lanes:
        lanes = [{"id": "_default", "label": ""}]
    lane_index = {ln["id"]: i for i, ln in enumerate(lanes)}
    has_pool = bool(pool) or len([l for l in lanes if l.get("label")]) > 1
    left_offset = MARGIN + (POOL_LABEL_W if has_pool else 0) + (LANE_LABEL_W if any(l.get("label") for l in lanes) else 0)

    title_h = 34 if title else 8
    top = title_h

    # assign pixel centers
    for n in nodes.values():
        li = lane_index.get(n.get("lane", lanes[0]["id"]), 0)
        row = n.get("row", 0)
        n["_x"] = left_offset + 30 + n.get("col", 0) * COL_W + TASK_W / 2
        n["_y"] = top + LANE_PAD_TOP + li * lane_h + lane_h / 2 + row * 55

    diagram_w = max(diagram_w, max((n["_x"] for n in nodes.values()), default=0) + TASK_W)
    total_w = diagram_w + MARGIN
    lanes_top = top + LANE_PAD_TOP - 20
    total_h = lanes_top + len(lanes) * lane_h + MARGIN

    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w:.0f} {total_h:.0f}" '
        f'font-family="{FONT}">'
    )
    # defs: arrow heads
    svg.append(f'''<defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="{C_FLOW}"/>
      </marker>
      <marker id="msghead" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="10" markerHeight="10" orient="auto-start-reverse">
        <path d="M1,1 L11,6 L1,11" fill="none" stroke="{C_FLOW}" stroke-width="1.4"/>
      </marker>
      <marker id="msgstart" viewBox="0 0 12 12" refX="6" refY="6" markerWidth="9" markerHeight="9">
        <circle cx="6" cy="6" r="4" fill="#ffffff" stroke="{C_FLOW}" stroke-width="1.3"/>
      </marker>
    </defs>''')
    svg.append(f'<rect x="0" y="0" width="{total_w:.0f}" height="{total_h:.0f}" fill="#ffffff"/>')

    if title:
        svg.append(f'<text x="{total_w/2:.0f}" y="22" text-anchor="middle" font-family="{FONT}" '
                   f'font-size="16" font-weight="700" fill="{C_TEXT}">{esc(title)}</text>')

    # --- Pool + lane containers ---
    pool_x = MARGIN
    lane_area_x = left_offset
    lane_area_w = total_w - MARGIN - lane_area_x
    if has_pool or any(l.get("label") for l in lanes):
        # outer pool box
        pool_top = lanes_top
        pool_bot = lanes_top + len(lanes) * lane_h
        svg.append(f'<rect x="{pool_x}" y="{pool_top}" width="{total_w-MARGIN-pool_x:.0f}" '
                   f'height="{pool_bot-pool_top:.0f}" fill="none" stroke="{C_STROKE}" stroke-width="1.4"/>')
        if pool:
            svg.append(f'<rect x="{pool_x}" y="{pool_top}" width="{POOL_LABEL_W}" '
                       f'height="{pool_bot-pool_top:.0f}" fill="#f4f6f8" stroke="{C_STROKE}" stroke-width="1.4"/>')
            pcy = (pool_top + pool_bot) / 2
            pcx = pool_x + POOL_LABEL_W / 2
            svg.append(f'<text x="{pcx:.0f}" y="{pcy:.0f}" text-anchor="middle" dominant-baseline="central" '
                       f'font-family="{FONT}" font-size="12" font-weight="700" fill="{C_POOL_LABEL}" '
                       f'transform="rotate(-90 {pcx:.0f} {pcy:.0f})">{esc(pool)}</text>')
        # lane dividers + labels
        for i, ln in enumerate(lanes):
            ly = lanes_top + i * lane_h
            if i > 0:
                svg.append(f'<line x1="{pool_x + (POOL_LABEL_W if pool else 0):.0f}" y1="{ly:.0f}" '
                           f'x2="{total_w-MARGIN:.0f}" y2="{ly:.0f}" stroke="{C_STROKE}" stroke-width="1"/>')
            if ln.get("label"):
                lbx = pool_x + (POOL_LABEL_W if pool else 0)
                svg.append(f'<rect x="{lbx:.0f}" y="{ly:.0f}" width="{LANE_LABEL_W}" height="{lane_h}" '
                           f'fill="#fafbfc" stroke="{C_STROKE}" stroke-width="1"/>')
                lcx = lbx + LANE_LABEL_W / 2
                lcy = ly + lane_h / 2
                svg.append(f'<text x="{lcx:.0f}" y="{lcy:.0f}" text-anchor="middle" dominant-baseline="central" '
                           f'font-family="{FONT}" font-size="11" font-weight="600" fill="{C_LANE_LABEL}" '
                           f'transform="rotate(-90 {lcx:.0f} {lcy:.0f})">{esc(ln["label"])}</text>')

    # --- Flows (draw before nodes so arrowheads tuck under borders cleanly) ---
    flow_svg = []
    for f in flows:
        src = nodes.get(f["from"])
        dst = nodes.get(f["to"])
        if not src or not dst:
            sys.stderr.write(f"warning: flow references unknown node {f}\n")
            continue
        flow_svg.append(route(src, dst, f.get("label", ""), f.get("type", "sequence"),
                              f.get("waypoints")))
    svg.extend(flow_svg)

    # --- Nodes on top ---
    for n in nodes.values():
        svg.append(draw_node(n))

    svg.append("</svg>")
    return "\n".join(svg)


def main():
    ap = argparse.ArgumentParser(description="Render a BPMN 2.0 process definition to SVG.")
    ap.add_argument("input", nargs="?", help="JSON file (or - for stdin)")
    ap.add_argument("-o", "--output", required=True, help="output SVG path")
    args = ap.parse_args()

    if args.input in (None, "-"):
        defn = json.load(sys.stdin)
    else:
        with open(args.input) as fh:
            defn = json.load(fh)

    svg = build(defn)
    with open(args.output, "w") as fh:
        fh.write(svg)
    print(f"Wrote {args.output} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
