"""
Smoke-teszt a teljes bútorzat áttekintő rajzához: ellenőrzi, hogy a
mikros.skp fixture-ből legenerálódik egy nem-üres, panel-szintű,
mindhárom nézetet (felül-, oldal-, elölnézet) tartalmazó DXF fájl
(export_full_layout), és hogy az egyszerű, csak-téglalap felülnézet
(export_layout) is működik.
"""

from pathlib import Path
import ezdxf

from skp2draw.parser.reader import load_scene
from skp2draw.parser.model import build_tree
from skp2draw.drawing.dxf_export import export_full_layout, export_layout

FIXTURE = Path(__file__).parent / "fixtures" / "mikros.skp"


def test_export_full_layout_writes_dxf(tmp_path):
    scene = load_scene(FIXTURE)
    root = build_tree(scene)

    out_path = tmp_path / "attekintes.dxf"
    export_full_layout(root, out_path)

    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_export_full_layout_has_three_views_and_hidden_lines(tmp_path):
    """
    A panel-szintű rajznak LINE entitásokat kell tartalmaznia (a
    rejtett-vonal számítás egyenes szakaszokat ad vissza, nem
    téglalapokat), és mindhárom nézet feliratának szerepelnie kell.
    """
    scene = load_scene(FIXTURE)
    root = build_tree(scene)

    out_path = tmp_path / "attekintes.dxf"
    export_full_layout(root, out_path)

    doc = ezdxf.readfile(str(out_path))
    msp = doc.modelspace()

    lines = list(msp.query("LINE"))
    assert lines, "Nincs LINE entitás - a panel-szintű élek nem rajzolódtak ki"

    texts = {t.dxf.text for t in msp.query("TEXT")}
    for label in ("felülnézet", "oldalnézet", "elölnézet"):
        assert label in texts, f"Hiányzik a(z) '{label}' felirat"


def test_export_layout_top_view_writes_dxf(tmp_path):
    scene = load_scene(FIXTURE)
    root = build_tree(scene)

    out_path = tmp_path / "felulnezet.dxf"
    export_layout(root, out_path)

    assert out_path.exists()
    assert out_path.stat().st_size > 0