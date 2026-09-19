"""
A generált DXF rajzokból egy összefűzött, A4-es ÁLLÓ tájolású PDF
előállítása - minden rajz KÉPKÉNT (raszterizálva) kerül az adott
oldalra, a margókon belülre skálázva, középre igazítva.

Ez a modul csak a "DXF -> PNG" és "képek -> egy PDF" lépéseket adja -
hogy PONTOSAN mely rajzok, milyen sorrendben kerülnek bele, azt
skp2draw.cli állítja össze (lásd: generate_full_report).
"""
from __future__ import annotations
from pathlib import Path

import ezdxf
from ezdxf.addons.drawing.matplotlib import qsave
from PIL import Image, ImageChops
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

A4_WIDTH_MM = 210.0
A4_HEIGHT_MM = 297.0
PAGE_MARGIN_MM = 10.0
RENDER_DPI = 200
AUTOCROP_PADDING_PX = 20


def _autocrop(img: Image.Image, padding_px: int = AUTOCROP_PADDING_PX) -> Image.Image:
    """
    A rajz körüli felesleges fehér margót vágja le: a qsave/matplotlib
    kirajzolás (a DXF-ben a cím/felirat-szövegek elhelyezéséből adódóan)
    gyakran sokkal nagyobb üres területet ad a képhez, mint amennyit a
    tényleges rajz elfoglal - enélkül a rajz a PDF oldalon jóval kisebbnek
    tűnne, mint amennyire a rendelkezésre álló hely engedné.
    """
    rgb = img.convert("RGB")
    background = Image.new("RGB", rgb.size, (255, 255, 255))
    diff = ImageChops.difference(rgb, background)
    bbox = diff.getbbox()
    if bbox is None:
        return img
    left, top, right, bottom = bbox
    left = max(0, left - padding_px)
    top = max(0, top - padding_px)
    right = min(img.width, right + padding_px)
    bottom = min(img.height, bottom + padding_px)
    return img.crop((left, top, right, bottom))


def render_dxf_to_png(dxf_path, png_path, dpi: int = RENDER_DPI) -> Path:
    """
    Egy DXF rajz (modeltér) PNG képpé alakítása (fehér háttér, fekete
    vonalak), a rajz természetes méretarányát megtartva, majd a felesleges
    fehér margók levágása (lásd _autocrop), hogy a rajz a PDF oldalon a
    lehető legnagyobbra kerülhessen.
    """
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    qsave(msp, str(png_path), bg="#FFFFFF", fg="#000000", dpi=dpi)
    with Image.open(png_path) as img:
        cropped = _autocrop(img)
        cropped.save(png_path)
    return png_path


def _draw_image_page(c: canvas.Canvas, png_path) -> None:
    """
    Egy A4 ÁLLÓ oldal: a `png_path` kép a margókon belülre skálázva
    (a képarány megtartásával), az oldalon középre igazítva.
    """
    img = Image.open(png_path)
    img_w_px, img_h_px = img.size

    page_w = A4_WIDTH_MM * mm
    page_h = A4_HEIGHT_MM * mm
    margin = PAGE_MARGIN_MM * mm
    avail_w = page_w - 2 * margin
    avail_h = page_h - 2 * margin

    scale = min(avail_w / img_w_px, avail_h / img_h_px)
    draw_w = img_w_px * scale
    draw_h = img_h_px * scale
    x = (page_w - draw_w) / 2
    y = (page_h - draw_h) / 2

    c.drawImage(
        str(png_path), x, y, width=draw_w, height=draw_h,
        preserveAspectRatio=True, mask="auto",
    )
    c.showPage()


def build_pdf_from_images(image_paths: list, output_path) -> Path:
    """
    Egy A4 ÁLLÓ tájolású PDF, minden `image_paths`-beli kép a saját,
    külön oldalán (ugyanabban a sorrendben, ahogy meg vannak adva).
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(output_path), pagesize=(A4_WIDTH_MM * mm, A4_HEIGHT_MM * mm))
    for png_path in image_paths:
        _draw_image_page(c, png_path)
    c.save()
    return output_path
