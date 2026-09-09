"""
Egyszerűsített rejtett-vonal számítás téglalap alakú (sík bútorlap)
elemekhez: minden alkatrészt egy 2D téglalapként vetítünk egy adott
nézetre, és a nézőponthoz legközelebb álló (előrébb lévő) téglalapok
eltakarják a mögöttük lévők éleit.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Rect:
    u0: float
    v0: float
    u1: float
    v1: float
    distance: float   # távolság a nézőponttól - KISEBB = KÖZELEBB (előrébb)
    label: str = ""


@dataclass
class Segment:
    u0: float
    v0: float
    u1: float
    v1: float
    visible: bool


def _split_by_hidden(a0: float, a1: float, hidden_intervals, horizontal: bool, fixed: float):
    if a0 > a1:
        a0, a1 = a1, a0
    if not hidden_intervals:
        return [_make_segment(a0, a1, horizontal, fixed, True)]

    merged = []
    for h0, h1 in sorted(hidden_intervals):
        h0, h1 = max(h0, a0), min(h1, a1)
        if h0 >= h1:
            continue
        if merged and h0 <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], h1))
        else:
            merged.append((h0, h1))

    segments = []
    cursor = a0
    for h0, h1 in merged:
        if cursor < h0:
            segments.append(_make_segment(cursor, h0, horizontal, fixed, True))
        segments.append(_make_segment(h0, h1, horizontal, fixed, False))
        cursor = h1
    if cursor < a1:
        segments.append(_make_segment(cursor, a1, horizontal, fixed, True))
    return segments


def _make_segment(a0: float, a1: float, horizontal: bool, fixed: float, visible: bool) -> Segment:
    if horizontal:
        return Segment(u0=a0, v0=fixed, u1=a1, v1=fixed, visible=visible)
    return Segment(u0=fixed, v0=a0, u1=fixed, v1=a1, visible=visible)


def _clip_horizontal(y: float, x0: float, x1: float, occluders):
    hidden = []
    for r in occluders:
        if r.v0 < y < r.v1:
            ox0, ox1 = max(r.u0, x0), min(r.u1, x1)
            if ox0 < ox1:
                hidden.append((ox0, ox1))
    return _split_by_hidden(x0, x1, hidden, horizontal=True, fixed=y)


def _clip_vertical(x: float, y0: float, y1: float, occluders):
    hidden = []
    for r in occluders:
        if r.u0 < x < r.u1:
            oy0, oy1 = max(r.v0, y0), min(r.v1, y1)
            if oy0 < oy1:
                hidden.append((oy0, oy1))
    return _split_by_hidden(y0, y1, hidden, horizontal=False, fixed=x)


def compute_visible_segments(rects: list[Rect]) -> list[Segment]:
    """
    Minden téglalap 4 éléhez kiszámolja a látható/rejtett szakaszokat:
    egy él egy pontja akkor rejtett, ha van olyan MÁSIK, KÖZELEBBI (kisebb
    distance-ú) téglalap, aminek a BELSEJÉBEN van (a nézet irányában
    takarja azt a pontot).
    """
    all_segments: list[Segment] = []
    for r in rects:
        closer = [o for o in rects if o is not r and o.distance < r.distance]
        all_segments += _clip_horizontal(r.v0, r.u0, r.u1, closer)
        all_segments += _clip_horizontal(r.v1, r.u0, r.u1, closer)
        all_segments += _clip_vertical(r.u0, r.v0, r.v1, closer)
        all_segments += _clip_vertical(r.u1, r.v0, r.v1, closer)
    return all_segments

def convex_hull_2d(points):
    """
    Andrew monotone chain algoritmus 2D konvex burokhoz - nincs külső
    függőség (nem kell scipy). `points`: lista (u,v) párokról.
    """
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def point_in_rect(u: float, v: float, r: Rect) -> bool:
    """Egy (u,v) pont szigorúan a r téglalap BELSEJÉBEN van-e."""
    return r.u0 < u < r.u1 and r.v0 < v < r.v1