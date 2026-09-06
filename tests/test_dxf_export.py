from skp2draw.parser.reader import load_scene
from skp2draw.parser.model import build_tree
from skp2draw.geometry.projection import panel_views
from skp2draw.drawing.dxf_export import export_panel_views
from pathlib import Path

FIXTURE = Path("tests/fixtures/mikros.skp")

def find(node, name):
    if node.definition_name == name:
        return node
    for c in node.children:
        r = find(c, name)
        if r:
            return r
    return None

scene = load_scene(FIXTURE)
root = build_tree(scene)
node = find(root, "Oldal#1")
export_panel_views(panel_views(node), "Oldal#1", "output/oldal1.dxf")
print("Kész: output/oldal1.dxf")