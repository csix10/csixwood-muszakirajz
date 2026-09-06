"""
Saját, egyszerűsített fa-struktúra az OpenSKP instanced-scene kimenete fölött.

FONTOS: az InstancedNode.matrix mezője az OpenSKP saját dokumentációja
szerint a csomópont transzformációja A SAJÁT SZÜLŐJÉHEZ KÉPEST van
megadva (nem a teljes világhoz képest!) - "The root node's matrix is the
identity." Ezért a fa bejárásakor VÉGIG KELL SZOROZNUNK a már kiszámolt
szülő-világmátrixot minden gyerek saját (szülőhöz képesti) mátrixával,
különben a mélyebben beágyazott elemek (pl. egy szekrényen belüli panel)
hibásan az origó közelébe kerülnének számításilag, a valós világpozíciójuk
helyett.

A geometriát (mesh_resources) egyszer alakítjuk Mesh-sze definíciónként,
mert az OpenSKP is deduplikáltan tárolja (egy közös alkatrészt nem
másol le minden előfordulásnál újra).
"""

from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

M_TO_MM = 1000.0


@dataclass
class Mesh:
    vertices_mm: np.ndarray               # (N, 3) float64, HELYI koordinátában, mm
    faces: list[tuple[int, int, int]]     # háromszögek, vertices_mm sorindexeivel


@dataclass
class Node:
    name: str
    definition_name: str
    local_matrix: np.ndarray              # 4x4, a SAJÁT SZÜLŐHÖZ képest, mm
    world_matrix: np.ndarray              # 4x4, HELYI-mm -> VILÁG-mm (összefűzve!)
    mesh: Mesh | None
    children: list["Node"] = field(default_factory=list)

    @property
    def has_geometry(self) -> bool:
        return self.mesh is not None and len(self.mesh.faces) > 0


def _matrix_16_to_4x4(values) -> np.ndarray:
    """
    Az InstancedNode.matrix 16 elemű, OSZLOP-major elrendezésű, A SAJÁT
    SZÜLŐHÖZ KÉPEST értelmezve:
    [oszlop0(3)+0, oszlop1(3)+0, oszlop2(3)+0, eltolás(3)+1].
    Az eltolás méterben van -> mm-re konvertáljuk; a forgatás/skálázás
    (a bal-felső 3x3 blokk) mértékegység-független, azt nem szorozzuk.
    """
    m = np.array(values, dtype=np.float64).reshape(4, 4, order="F")
    m[0:3, 3] *= M_TO_MM
    return m


def _build_mesh(primitives) -> Mesh | None:
    """Egy mesh_resource `primitives` listájából (LocalPrimitive-ok) épít egy Mesh-et."""
    all_vertices = []
    all_faces = []
    offset = 0
    for prim in primitives:
        pos = np.asarray(prim.positions, dtype=np.float64).reshape(-1, 3) * M_TO_MM
        idx = np.asarray(prim.indices, dtype=np.int64).reshape(-1, 3)
        all_vertices.append(pos)
        all_faces.extend((idx + offset).tolist())
        offset += len(pos)

    if not all_vertices:
        return None

    vertices_mm = np.vstack(all_vertices)
    faces = [tuple(f) for f in all_faces]
    return Mesh(vertices_mm=vertices_mm, faces=faces)


def build_tree(scene) -> Node:
    """
    Bejárja az InstancedScene.scene_hierarchy fát, és felépíti a saját
    Node-fánkat, minden csomóponthoz hozzárendelve a (deduplikált) geometriát
    ÉS a helyesen ÖSSZEFŰZÖTT (kumulatív) VILÁG-transzformációt.
    """
    mesh_by_id = {mr.id: _build_mesh(mr.primitives) for mr in scene.mesh_resources}

    def walk(inode, parent_world: np.ndarray) -> Node:
        local = _matrix_16_to_4x4(inode.matrix)
        world = parent_world @ local
        mesh = mesh_by_id.get(inode.mesh_resource_id) if inode.mesh_resource_id else None
        node = Node(
            name=inode.name or inode.definition_name or "(névtelen)",
            definition_name=inode.definition_name,
            local_matrix=local,
            world_matrix=world,
            mesh=mesh,
            children=[],
        )
        node.children = [walk(c, world) for c in inode.children]
        return node

    return walk(scene.scene_hierarchy, np.eye(4))