"""
Méretvonal-elhelyezési szabályok panel-nézetekhez: minden téglalap alakú
nézethez KÉT méretvonalat generálunk (alsó: szélesség, bal: magasság) -
így a vastagság-nézeteken (felülnézet/oldalnézet) is valódi méretvonal
jelöli a vastagságot, nem csak felirat.
"""
from __future__ import annotations
from skp2draw.dimensioning.dimension_line import DimensionLine

DEFAULT_OFFSET_MM = 15.0


def rectangle_dimensions(x0: float, y0: float, width: float, height: float,
                          offset: float = DEFAULT_OFFSET_MM):
    horiz = DimensionLine(
        kind="horizontal",
        p1=(x0, y0),
        p2=(x0 + width, y0),
        base=(x0, y0 - offset),
        value=width,
    )
    vert = DimensionLine(
        kind="vertical",
        p1=(x0, y0),
        p2=(x0, y0 + height),
        base=(x0 - offset, y0),
        value=height,
    )
    return [horiz, vert]

def chain_dimensions(coords, kind: str, fixed: float, offset: float):
    """
    Láncolt (egymást követő) méretvonalak egy koordináta-sorozatból: minden
    szomszédos, KÜLÖNBÖZŐ pár közé egy külön méretvonal-szakaszt tesz -
    így egy sor egymás melletti alkatrész-határ mind megjelenik, nem csak
    az össz-méret.

    `kind`: "horizontal" (fixed = y koordináta, a lánc alul fut) vagy
    "vertical" (fixed = x koordináta, a lánc oldalt fut).
    `offset`: milyen távol fusson a lánc a fixed vonaltól.
    Túl közeli (< 5mm-re eső) koordinátákat összevonjuk, hogy ne
    keletkezzenek 0 hosszú, zsúfolt méretvonalak.
    """
    rounded = sorted(set(round(c, 1) for c in coords))
    merged = []
    for c in rounded:
        if merged and c - merged[-1] < 5.0:
            continue
        merged.append(c)

    dims = []
    for a, b in zip(merged, merged[1:]):
        if kind == "horizontal":
            dims.append(DimensionLine(
                kind="horizontal", p1=(a, fixed), p2=(b, fixed),
                base=(a, fixed - offset), value=b - a,
            ))
        else:
            dims.append(DimensionLine(
                kind="vertical", p1=(fixed, a), p2=(fixed, b),
                base=(fixed - offset, a), value=b - a,
            ))
    return dims