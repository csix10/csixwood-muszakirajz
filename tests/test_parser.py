"""
Első smoke-teszt a parserhez: beolvassuk a mikros.skp fixture-t,
felépítjük a saját Node-fánkat az OpenSKP instanced-scene-je alapján,
és kiírjuk szövegesen a hierarchiát (név, mélység, befoglaló méret mm-ben).
"""

from pathlib import Path
import numpy as np
import pytest

from skp2draw.parser.reader import load_scene
from skp2draw.parser.model import build_tree, Node

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "mikros.skp"


@pytest.fixture(scope="module")
def tree() -> Node:
    scene = load_scene(FIXTURE_PATH)
    return build_tree(scene)


def _bbox_mm(node: Node) -> tuple[float, float, float] | None:
    if node.mesh is None or len(node.mesh.vertices_mm) == 0:
        return None
    pts_local = node.mesh.vertices_mm
    ones = np.ones((pts_local.shape[0], 1))
    pts_h = np.hstack([pts_local, ones])
    pts_world = (node.world_matrix @ pts_h.T).T[:, :3]
    mins = pts_world.min(axis=0)
    maxs = pts_world.max(axis=0)
    size = maxs - mins
    return tuple(round(v, 1) for v in size)


def _print_tree(node: Node, depth: int = 0) -> None:
    indent = "  " * depth
    bbox = _bbox_mm(node)
    bbox_str = f"  bbox(mm)={bbox}" if bbox else ""
    label = node.name if node.name.strip() else f"({node.definition_name})"
    print(f"{indent}- {label}{bbox_str}")
    for child in node.children:
        _print_tree(child, depth + 1)


def test_fixture_exists():
    assert FIXTURE_PATH.exists(), f"Hiányzik a teszt-fájl: {FIXTURE_PATH}"


def test_tree_builds_and_has_children(tree: Node):
    assert tree is not None
    assert len(tree.children) > 0


def test_expected_panels_present(tree: Node):
    all_def_names = set()

    def collect(node: Node):
        all_def_names.add(node.definition_name)
        for c in node.children:
            collect(c)

    collect(tree)

    expected = {"Teteje", "Oldal#1", "Hátfal#1", "Alja#1", "Polc#1"}
    missing = expected - all_def_names
    assert not missing, f"Hiányzó várt panelek: {missing}"


def test_panel_dimensions_are_consistent(tree: Node):
    """
    Az azonos definíciójú panelek (pl. mindkét 'Oldal#1') világkoordinátás
    bbox-ának egyeznie kell egymással, ha a modellben szimmetrikusan lettek
    elhelyezve. Ez a mátrix-feloldás helyességét ellenőrzi.
    """
    bboxes_by_def: dict[str, list[tuple]] = {}

    def collect(node: Node):
        bbox = _bbox_mm(node)
        if bbox is not None:
            bboxes_by_def.setdefault(node.definition_name, []).append(bbox)
        for c in node.children:
            collect(c)

    collect(tree)

    for def_name, boxes in bboxes_by_def.items():
        if len(boxes) > 1:
            first = boxes[0]
            for b in boxes[1:]:
                assert b == first, (
                    f"'{def_name}' eltérő bbox méretekkel szerepel: {boxes} "
                    f"— ez arra utalhat, hogy a mátrix-feloldás hibás"
                )


def test_print_full_tree(tree: Node):
    print()
    _print_tree(tree)


if __name__ == "__main__":
    scene = load_scene(FIXTURE_PATH)
    root = build_tree(scene)
    _print_tree(root)