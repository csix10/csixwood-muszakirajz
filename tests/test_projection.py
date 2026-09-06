"""
Smoke-teszt a geometry/projection.py és hierarchy.py modulokhoz:
ellenőrzi, hogy a mikros.skp ismert komponensei helyesen lesznek
panel/hardware kategóriába sorolva, és hogy a panel-nézetek méretei
egyeznek az egymáshoz illő, kerek várt értékekkel.
"""

from pathlib import Path
import pytest

from skp2draw.parser.reader import load_scene
from skp2draw.parser.model import build_tree, Node
from skp2draw.geometry.projection import panel_views
from skp2draw.hierarchy import classify_kind

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "mikros.skp"


@pytest.fixture(scope="module")
def tree() -> Node:
    scene = load_scene(FIXTURE_PATH)
    return build_tree(scene)


def _first_by_def_name(node: Node, def_name: str) -> Node | None:
    if node.definition_name == def_name:
        return node
    for c in node.children:
        found = _first_by_def_name(c, def_name)
        if found is not None:
            return found
    return None


@pytest.mark.parametrize("def_name", ["Teteje", "Oldal#1", "Hátfal#1", "Alja#1", "Polc#1"])
def test_panels_classified_as_panel(tree: Node, def_name: str):
    node = _first_by_def_name(tree, def_name)
    assert node is not None, f"Nem található: {def_name}"
    assert classify_kind(node) == "panel"


@pytest.mark.parametrize("def_name", [
    "Lamello 20-as", "Hátfalrögzítő sarok elem", "polctartó fém 5x16",
])
def test_hardware_classified_as_hardware(tree: Node, def_name: str):
    node = _first_by_def_name(tree, def_name)
    assert node is not None, f"Nem található: {def_name}"
    assert classify_kind(node) == "hardware"


def test_oldal_panel_dimensions(tree: Node):
    """
    Az Oldal#1 helyi mesh-e egy 1000mm magas 'sablon', amit a világmátrix
    0.55-ös szorzóval zsugorít 550mm-re. Ha ez a teszt elbukik, az azt
    jelzi, hogy a skálázás-korrekció (scaled_local_sizes) elromlott.
    """
    node = _first_by_def_name(tree, "Oldal#1")
    views = panel_views(node)
    by_label = {v.label: v for v in views}

    front = by_label["elölnézet"]
    assert round(front.width) == 550
    assert round(front.height) == 320

    side = by_label["felülnézet"]
    assert round(side.height) == 18  # vastagság