"""
Adatstruktúra egyetlen méretvonalhoz - még nem függ semmilyen rajzoló
könyvtártól (a drawing/ réteg alakítja át pl. DXF LinearDimension-né).
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class DimensionLine:
    kind: str                      # "horizontal" vagy "vertical"
    p1: tuple[float, float]         # mérendő szakasz kezdőpontja
    p2: tuple[float, float]         # mérendő szakasz végpontja
    base: tuple[float, float]       # hova kerüljön maga a méretvonal (eltolva)
    value: float                    # a tényleges méret, mm