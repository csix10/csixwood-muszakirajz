"""
Parancssori belépési pont: egy .skp fájlból legenerálja
  1) az összes EGYEDI MÉRETŰ panel-változat (alkatrész-szintű) DXF rajzát,
  2) az összes EGYEDI MÉRETŰ bútorelem-modul (összeállítás-szintű) DXF rajzát,
  3) a teljes bútorzat áttekintő rajzát (felülnézet + elölnézet, pozíciókkal
     és fő méretekkel).
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

from skp2draw.parser.reader import load_scene
from skp2draw.parser.model import build_tree
from skp2draw.hierarchy import collect_unique_panels, collect_unique_assemblies
from skp2draw.geometry.projection import panel_views, assembly_construction_views
from skp2draw.drawing.dxf_export import export_views, export_construction_views, export_full_layout


def _safe_filename(name: str) -> str:
    """Fájlnévben problémás karakterek (szóköz, /, \\) cseréje aláhúzásra."""
    name = name.strip() or "nevtelen"
    return re.sub(r"[^\w#.-]+", "_", name, flags=re.UNICODE)


def _unique_filename(base: str, width, height, thickness, used_filenames: set) -> str:
    """Egyedi, ütközés-mentes fájlnevet épít a név+méret alapján."""
    w, h, t = round(width), round(height), round(thickness)
    filename = f"{base}_{w}x{h}x{t}.dxf"
    suffix = 2
    while filename in used_filenames:
        filename = f"{base}_{w}x{h}x{t}_v{suffix}.dxf"
        suffix += 1
    used_filenames.add(filename)
    return filename


def generate_all_panels(skp_path, output_dir) -> list[Path]:
    """Minden egyedi méretű panel-változat (alkatrész-szintű rajz)."""
    scene = load_scene(skp_path)
    root = build_tree(scene)
    panels = collect_unique_panels(root)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written = []
    used_filenames: set[str] = set()

    for node, count in panels:
        views = panel_views(node)
        base = _safe_filename(node.definition_name)
        filename = _unique_filename(base, views[0].width, views[0].height, views[1].height, used_filenames)
        path = output_dir / filename
        export_views(views, node.definition_name, path, count=count)
        written.append(path)

    return written


def generate_all_assemblies(skp_path, output_dir) -> list[Path]:
    """Minden egyedi méretű bútorelem-modul (összeállítás-szintű, szerkezeti rajz)."""
    scene = load_scene(skp_path)
    root = build_tree(scene)
    assemblies = collect_unique_assemblies(root)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written = []
    used_filenames: set[str] = set()

    for node, count in assemblies:
        views_data = assembly_construction_views(node)
        front = views_data["elölnézet"]["view"]
        top = views_data["felülnézet"]["view"]
        base = _safe_filename(node.definition_name)
        filename = _unique_filename(base, front.width, front.height, top.height, used_filenames)
        path = output_dir / filename
        export_construction_views(node, node.definition_name, path, count=count, views_data=views_data)
        written.append(path)

    return written


def generate_layout(skp_path, output_dir) -> Path:
    """A teljes bútorzat áttekintő rajza (felülnézet + elölnézet, pozíciókkal és fő méretekkel)."""
    scene = load_scene(skp_path)
    root = build_tree(scene)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    path = output_dir / "konyha_attekintes.dxf"
    export_full_layout(root, path)
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Műszaki rajzok generálása .skp fájlból (alkatrész + bútorelem + elrendezés)."
    )
    parser.add_argument("skp_file", help="A bemeneti .skp fájl elérési útja")
    parser.add_argument(
        "-o", "--output", default="output",
        help="A kimeneti mappa (alapértelmezett: ./output)",
    )
    args = parser.parse_args()

    panels = generate_all_panels(args.skp_file, args.output)
    print(f"{len(panels)} alkatrész-szintű rajz elkészült ({args.output}/):")
    for p in panels:
        print(f"  - {p.name}")

    print()
    assemblies = generate_all_assemblies(args.skp_file, args.output + "/butorelemek")
    print(f"{len(assemblies)} bútorelem-szintű rajz elkészült ({args.output}/butorelemek/):")
    for p in assemblies:
        print(f"  - {p.name}")

    print()
    layout = generate_layout(args.skp_file, args.output)
    print(f"Áttekintő elrendezés-rajz elkészült: {layout}")


if __name__ == "__main__":
    main()