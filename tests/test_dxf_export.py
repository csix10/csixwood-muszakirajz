from pathlib import Path

from skp2draw.parser.reader import load_scene
from skp2draw.parser.model import build_tree
from skp2draw.geometry.projection import panel_views
from skp2draw.drawing.dxf_export import export_panel_views

FIXTURE = Path(__file__).parent / "fixtures" / "mikros.skp"


def _find(node, name):
    if node.definition_name == name:
        return node
    for c in node.children:
        r = _find(c, name)
        if r:
            return r
    return None


def test_export_panel_views_writes_dxf(tmp_path):
    scene = load_scene(FIXTURE)
    root = build_tree(scene)
    node = _find(root, "Oldal#1")
    assert node is not None, "Nem található az 'Oldal#1' panel a fixture-ben"

    out_path = tmp_path / "oldal1.dxf"
    export_panel_views(panel_views(node), "Oldal#1", out_path)

    assert out_path.exists()
    assert out_path.stat().st_size > 0