"""
Parancssori belépési pont: egy .skp fájlból legenerálja
  1) az összes EGYEDI MÉRETŰ panel-változat (alkatrész-szintű) DXF rajzát,
  2) az összes EGYEDI MÉRETŰ bútorelem-modul (összeállítás-szintű) DXF rajzát,
  3) a teljes bútorzat áttekintő rajzát (felülnézet + elölnézet, pozíciókkal
     és fő méretekkel).

Ha meg van adva egy OpenCutList CSV export (--csv), MINDHÁROM szint
(alkatrész, bútorelem, elrendezés) szűrése a Badges (nem üres) mezőn
alapul: csak azok az elemek kerülnek be, amiket ténylegesen megcímkéztél
az OpenCutList-ben - lásd: skp2draw.badges,
skp2draw.hierarchy.collect_unique_panels,
skp2draw.hierarchy.collect_unique_assemblies.
"""
from __future__ import annotations
import argparse
import re
import tempfile
from pathlib import Path

from skp2draw.parser.reader import load_scene
from skp2draw.parser.model import build_tree
from skp2draw.hierarchy import collect_unique_panels, collect_unique_assemblies
from skp2draw.geometry.projection import (
    panel_views, assembly_construction_views, find_touching_hardware, panel_hardware_overlays,
)
from skp2draw.drawing.dxf_export import (
    export_views, export_construction_views, export_full_layout, export_full_layout_view,
)
from skp2draw.drawing.pdf_export import render_dxf_to_png, build_pdf_from_images
from skp2draw.badges import load_badge_keys


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


def generate_all_panels(skp_path, output_dir, badge_keys=None) -> list[Path]:
    """
    Minden egyedi méretű panel-változat (alkatrész-szintű rajz).
    `badge_keys`: lásd skp2draw.badges.load_badge_keys - ha meg van adva,
    csak a CSV-ben nem üres Badges-szel szereplő panelek kerülnek be (pl.
    egy konyhai gép panel-szerű, de nem vágandó lapja - mint egy főzőlap
    üveglapja - enélkül tévesen bekerülne, mert geometriailag ugyanúgy
    "panelnek" néz ki, mint egy valódi bútorlap).

    Minden panel MINDHÁROM nézetén megjelennek a VELE EGY MODULBAN lévő,
    ténylegesen ÉRINTKEZŐ, ÉS mindhárom oldalán 10cm-nél kisebb kötőelemek
    (zsanér, dűbel, polctartó stb.) is, a középpontjuktól a legközelebbi
    alkatrész-élig futó méretvonalakkal - lásd:
    skp2draw.geometry.projection.find_touching_hardware /
    panel_hardware_overlays.
    """
    scene = load_scene(skp_path)
    root = build_tree(scene)
    panels = collect_unique_panels(root, badge_keys)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written = []
    used_filenames: set[str] = set()

    for node, count in panels:
        views = panel_views(node)
        base = _safe_filename(node.definition_name)
        filename = _unique_filename(base, views[0].width, views[0].height, views[1].height, used_filenames)
        path = output_dir / filename

        touching_hardware = find_touching_hardware(root, node)
        hardware_by_view = panel_hardware_overlays(node, touching_hardware)

        export_views(views, node.definition_name, path, count=count, hardware_by_view=hardware_by_view)
        written.append(path)

    return written


def generate_all_assemblies(skp_path, output_dir, badge_keys=None) -> list[Path]:
    """
    Minden egyedi méretű, valódi bútorelem-modul (összeállítás-szintű,
    szerkezeti rajz). `badge_keys`: lásd skp2draw.badges.load_badge_keys -
    ha meg van adva, csak a legalább egy Badges-elt alkatrészt/leszármazottat
    tartalmazó modulok kerülnek be (lásd: collect_unique_assemblies).
    """
    scene = load_scene(skp_path)
    root = build_tree(scene)
    assemblies = collect_unique_assemblies(root, badge_keys)

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


def generate_layout(skp_path, output_dir, badge_keys=None) -> Path:
    """
    A teljes bútorzat áttekintő rajza (felülnézet + oldalnézet +
    elölnézet, pozíciókkal és fő méretekkel). `badge_keys`: lásd
    generate_all_assemblies.
    """
    scene = load_scene(skp_path)
    root = build_tree(scene)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    path = output_dir / "konyha_attekintes.dxf"
    export_full_layout(root, path, badge_keys=badge_keys)
    return path


def generate_pdf_report(skp_path, output_dir, badge_keys=None) -> Path:
    """
    Egy összefűzött, A4-es ÁLLÓ tájolású PDF, ami MINDEN rajzot KÉPKÉNT
    tartalmaz, a következő sorrendben:

      1. Az áttekintő rajz HÁROM nézete (felülnézet, oldalnézet,
         elölnézet), egy-egy KÜLÖN oldalon.
      2. Minden bútorelem (összeállítás) a `collect_unique_assemblies`
         sorrendjében:
         a) a bútorelem szerkezeti rajza (mindhárom nézet EGY oldalon,
            mint eddig is),
         b) az EHHEZ a bútorelemhez tartozó egyedi (név+méret szerint,
            de csak EZEN a bútorelemen belül deduplikált) alkatrészek,
            egyenként egy-egy oldalon.

    `badge_keys`: lásd skp2draw.badges.load_badge_keys.

    Megjegyzés: egy olyan panel, ami NEM tartozik semmilyen
    bútorelemhez (pl. egy önálló, csoportba nem rendezett lap közvetlenül
    a modell gyökerén), nem kerül bele ebbe a PDF-be - lásd
    skp2draw.hierarchy.collect_unique_assemblies docstringjét arról,
    hogy mi számít "bútorelemnek".
    """
    scene = load_scene(skp_path)
    root = build_tree(scene)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / "muszaki_dokumentacio.pdf"

    with tempfile.TemporaryDirectory(prefix="skp2draw_pdf_") as tmp_dir:
        tmp_dir = Path(tmp_dir)
        image_paths: list[Path] = []
        seq = 0

        def _next_paths(base: str) -> tuple[Path, Path]:
            nonlocal seq
            seq += 1
            stem = f"{seq:04d}_{_safe_filename(base)}"
            return tmp_dir / f"{stem}.dxf", tmp_dir / f"{stem}.png"

        # 1) Áttekintő - mindhárom nézet külön oldalon.
        for view_label in ("felülnézet", "oldalnézet", "elölnézet"):
            dxf_path, png_path = _next_paths(f"attekintes_{view_label}")
            export_full_layout_view(root, view_label, dxf_path, badge_keys=badge_keys)
            image_paths.append(render_dxf_to_png(dxf_path, png_path))

        # 2) Bútorelemek + a hozzájuk tartozó alkatrészek.
        for assembly_node, assembly_count in collect_unique_assemblies(root, badge_keys):
            views_data = assembly_construction_views(assembly_node)
            dxf_path, png_path = _next_paths(f"butorelem_{assembly_node.definition_name}")
            export_construction_views(
                assembly_node, assembly_node.definition_name, dxf_path,
                count=assembly_count, views_data=views_data,
            )
            image_paths.append(render_dxf_to_png(dxf_path, png_path))

            panels = collect_unique_panels(assembly_node, badge_keys)
            for panel_node, panel_count in panels:
                panel_views_ = panel_views(panel_node)
                touching_hardware = find_touching_hardware(root, panel_node)
                hardware_by_view = panel_hardware_overlays(panel_node, touching_hardware)

                panel_dxf_path, panel_png_path = _next_paths(f"alkatresz_{panel_node.definition_name}")
                export_views(
                    panel_views_, panel_node.definition_name, panel_dxf_path,
                    count=panel_count, hardware_by_view=hardware_by_view,
                )
                image_paths.append(render_dxf_to_png(panel_dxf_path, panel_png_path))

        build_pdf_from_images(image_paths, pdf_path)

    return pdf_path


def main():
    parser = argparse.ArgumentParser(
        description="Műszaki rajzok generálása .skp fájlból (alkatrész + bútorelem + elrendezés)."
    )
    parser.add_argument("skp_file", help="A bemeneti .skp fájl elérési útja")
    parser.add_argument(
        "-o", "--output", default="output",
        help="A kimeneti mappa (alapértelmezett: ./output)",
    )
    parser.add_argument(
        "--csv", default=None,
        help=(
            "OpenCutList CSV export elérési útja. Ha meg van adva, a "
            "bútorelem-szintű és az elrendezés-rajzhoz tartozó szűrés a "
            "Badges (nem üres) mezőn alapul, nem a darabszámon."
        ),
    )
    args = parser.parse_args()

    badge_keys = load_badge_keys(args.csv) if args.csv else None

    panels = generate_all_panels(args.skp_file, args.output, badge_keys)
    print(f"{len(panels)} alkatrész-szintű rajz elkészült ({args.output}/):")
    for p in panels:
        print(f"  - {p.name}")

    print()
    assemblies = generate_all_assemblies(args.skp_file, args.output + "/butorelemek", badge_keys)
    print(f"{len(assemblies)} bútorelem-szintű rajz elkészült ({args.output}/butorelemek/):")
    for p in assemblies:
        print(f"  - {p.name}")

    print()
    layout = generate_layout(args.skp_file, args.output, badge_keys)
    print(f"Áttekintő elrendezés-rajz elkészült: {layout}")

    print()
    pdf_path = generate_pdf_report(args.skp_file, args.output, badge_keys)
    print(f"Összefűzött PDF dokumentáció elkészült: {pdf_path}")


if __name__ == "__main__":
    main()