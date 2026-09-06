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