"""
Parancssori belépési pont: egy .skp fájlból legenerálja az összes EGYEDI
MÉRETŰ panel-változat méretezett DXF rajzát.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

from skp2draw.parser.reader import load_scene
from skp2draw.parser.model import build_tree
from skp2draw.hierarchy import collect_unique_panels
from skp2draw.geometry.projection import panel_views
from skp2draw.drawing.dxf_export import export_panel_views


def _safe_filename(name: str) -> str:
    """Fájlnévben problémás karakterek (szóköz, /, \\) cseréje aláhúzásra."""
    name = name.strip() or "nevtelen"
    return re.sub(r"[^\w#.-]+", "_", name, flags=re.UNICODE)


def generate_all_panels(skp_path, output_dir) -> list[Path]:
    scene = load_scene(skp_path)
    root = build_tree(scene)
    panels = collect_unique_panels(root)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written = []
    used_filenames: set[str] = set()

    for node, count in panels:
        views = panel_views(node)
        width = round(views[0].width)
        height = round(views[0].height)
        thickness = round(views[1].height)

        base = _safe_filename(node.definition_name)
        filename = f"{base}_{width}x{height}x{thickness}.dxf"

        # biztonsági háló: ha KETTŐNÉL TÖBB, teljesen azonosra kerekedő
        # méretű változat lenne ugyanazzal a névvel (elvileg nem fordulhat
        # elő, de inkább ne írjunk felül csendben egy fájlt)
        suffix = 2
        while filename in used_filenames:
            filename = f"{base}_{width}x{height}x{thickness}_v{suffix}.dxf"
            suffix += 1
        used_filenames.add(filename)

        path = output_dir / filename
        export_panel_views(views, node.definition_name, path, count=count)
        written.append(path)

    return written


def main():
    parser = argparse.ArgumentParser(
        description="Panel-komponensek műszaki rajzainak generálása .skp fájlból."
    )
    parser.add_argument("skp_file", help="A bemeneti .skp fájl elérési útja")
    parser.add_argument(
        "-o", "--output", default="output",
        help="A kimeneti mappa (alapértelmezett: ./output)",
    )
    args = parser.parse_args()

    written = generate_all_panels(args.skp_file, args.output)
    print(f"{len(written)} panel rajza elkészült:")
    for p in written:
        print(f"  - {p}")


if __name__ == "__main__":
    main()