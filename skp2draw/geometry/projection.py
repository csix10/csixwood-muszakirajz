"""
Panel-komponensek (sík bútorlapok) 2D vetítése műszaki nézetekhez.

Feltételezés: a panel-komponensek (Teteje, Oldal, Hátfal, Alja, Polc stb.)
egyszerű, téglatest alakú síklapok - a legkisebb (skálázással korrigált)
kiterjedésű tengely a lap VASTAGSÁGA, a másik két tengely feszíti ki a
lap SÍKJÁT.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from skp2draw.parser.model import Node
from skp2draw.geometry.bbox import scaled_local_sizes


@dataclass
class View:
    label: str
    width: float
    height: float


def panel_views(node: Node):
    sizes = scaled_local_sizes(node)
    if sizes is None:
        return None

    t_axis = int(np.argmin(sizes))
    plane_axes = [i for i in range(3) if i != t_axis]
    u_axis, v_axis = plane_axes
    thickness = sizes[t_axis]
    width = sizes[u_axis]
    height = sizes[v_axis]

    return [
        View(label="elölnézet", width=width, height=height),
        View(label="felülnézet", width=width, height=thickness),
        View(label="oldalnézet", width=height, height=thickness),
    ]