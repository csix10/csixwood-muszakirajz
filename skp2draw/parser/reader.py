"""
Vékony réteg az OpenSKP könyvtár fölött.

A `build_instanced_scene()`-t használjuk a `parse()` helyett, mert ez már
validáltan feloldja a komponens/csoport beágyazást, és minden csomóponthoz
kiszámolja a VILÁG-koordinátás transzformációt (méterben, oszlop-major
4x4 mátrixként) – így nekünk nem kell a nyers .skp mátrix-konvenciót
(oszlop/sor major, mértékegység) saját kézzel kitalálnunk és kockáztatnunk,
hogy elrontjuk.
"""

from pathlib import Path
from openskp import SkpFile


def load_scene(path: str | Path):
    """
    Beolvas egy .skp fájlt, és visszaadja az OpenSKP "instanced scene"
    objektumát:
      - scene.scene_hierarchy: a fa gyökere (InstancedNode), minden
        csomóponton a VILÁG-koordinátás transzformációval
      - scene.mesh_resources: a deduplikált geometria definíciónként
        (egy közösen használt alkatrész geometriáját csak egyszer tárolja)
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Nem található a fájl: {path}")

    skp = SkpFile.open(str(path))
    return skp.build_instanced_scene()