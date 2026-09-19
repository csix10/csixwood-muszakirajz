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

def edge_distance_dimensions(width: float, height: float, center: tuple[float, float]):
    """
    Egy pont (pl. egy kötőelem - furat, zsanér, dűbel - középpontja) és a
    hozzá KÉT LEGKÖZELEBBI, EGYMÁSRA MERŐLEGES alkatrész-él távolsága, egy
    width x height méretű téglalapon belül, aminek a bal-alsó sarka a
    (0,0) origó:
      - vízszintes méretvonal: a ponttól a legközelebbi FÜGGŐLEGES élig
        (u=0 vagy u=width),
      - függőleges méretvonal: a ponttól a legközelebbi VÍZSZINTES élig
        (v=0 vagy v=height).

    A méretvonal MAGÁTÓL a mért ponttól fut az élig (nincs eltolás, mint
    egy rendes furat-pozíció méretezésnél) - ezért a `base` ugyanarra a
    vonalra esik, mint a mért szakasz (p1, p2).

    A 0mm-re kerekedő (a rajz egész mm-es kerekítése mellett látszólag
    "0"-t mutató) méretvonalakat KIHAGYJUK - nincs értelme kirajzolni egy
    méretvonalat, ami a szélén ülő kötőelemnél úgyis 0-t írna ki.
    """
    cu, cv = center
    dims = []

    if cu <= width / 2:
        _append_if_nonzero(dims, DimensionLine(
            kind="horizontal", p1=(0.0, cv), p2=(cu, cv), base=(0.0, cv), value=cu,
        ))
    else:
        _append_if_nonzero(dims, DimensionLine(
            kind="horizontal", p1=(cu, cv), p2=(width, cv), base=(cu, cv), value=width - cu,
        ))

    if cv <= height / 2:
        _append_if_nonzero(dims, DimensionLine(
            kind="vertical", p1=(cu, 0.0), p2=(cu, cv), base=(cu, 0.0), value=cv,
        ))
    else:
        _append_if_nonzero(dims, DimensionLine(
            kind="vertical", p1=(cu, cv), p2=(cu, height), base=(cu, cv), value=height - cv,
        ))

    return dims


def _append_if_nonzero(dims: list, dim: DimensionLine) -> None:
    """Csak akkor adja hozzá a méretvonalat, ha egész mm-re kerekítve nem 0."""
    if round(dim.value) != 0:
        dims.append(dim)


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