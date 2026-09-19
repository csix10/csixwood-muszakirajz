"""
Az OpenCutList-ből exportált vágólista CSV beolvasása.

Ez adja a megbízható jelet arra, hogy egy komponenst ténylegesen
legyártandó, "kész" elemnek szánsz-e: az OpenCutList "Badges" mezője
KÉZZEL, Nálad rárakott címke minden egyes vágott alkatrészen/szerelvényen
(nem valami, amit a geometriából ki lehetne találni) - így ha egy elem
szerepel a CSV-ben NEM ÜRES Badges-szel, az azt jelenti, hogy Te
ténylegesen foglalkoztál vele az OpenCutList-ben (kategorizáltad, pl.
"butorlap", "munkalap", "fuggeszto", "kotoelem", "lab", "MDF", "HDF"
stb.) - tehát valódi, a modellhez tartozó alkatrész. Az olyan elemek,
amiket nem címkéztél (pl. a "Dishwasher" vagy a "MICROONDAS+CONSUL"
gyártói minta-komponensek), üres Badges-szel szerepelnek - vagy egyáltalán
nem is szerepelnek a CSV-ben.

FONTOS: a CSV "Instance names" oszlopa üresen jön (legalábbis a
mintában, amit kaptunk), úgyhogy NEM lehet rá névvel párosítani. Ehelyett
a "Designation" (a komponens neve) + a végleges Length/Width/Thickness
hármas adja a párosítási kulcsot - RENDEZETT (növekvő) sorrendben, hogy
független legyen attól, az OpenCutList és a mi modellünk ugyanazt a
tengelyt hívja-e "hossznak"/"szélességnek"/"vastagságnak". Ugyanez az elv
adja a program saját (definíció-név, méret) alapú deduplikálását is
máshol (collect_unique_panels, collect_unique_assemblies).

A CSV-t az OpenCutList PONTOSVESSZŐVEL (;) tagolva exportálja, nem
vesszővel - ezt figyelembe vesszük a beolvasásnál.
"""
from __future__ import annotations
import csv
from pathlib import Path

MM_SUFFIX = " mm"

# Az OpenCutList CSV exportja pontosvesszővel tagol, nem vesszővel.
CSV_DELIMITER = ";"


def _parse_mm(value: str | None) -> float | None:
    """'2000 mm' -> 2000.0. Üres/hibás érték esetén None."""
    value = (value or "").strip()
    if not value:
        return None
    if value.endswith(MM_SUFFIX):
        value = value[: -len(MM_SUFFIX)].strip()
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def load_badge_keys(csv_path) -> set[tuple[str, tuple[float, float, float]]]:
    """
    Beolvassa az OpenCutList CSV exportot, és visszaadja azoknak a
    (Designation, méret) pároknak a halmazát, ahol a Badges oszlop NEM
    üres. A méretet a végleges Length/Width/Thickness oszlopokból
    olvassuk (nem a "- raw" változatból), RENDEZETT (növekvő) hármasként.

    Egy sor kimarad, ha a Designation üres, vagy a három méret bármelyike
    nem olvasható be számként (pl. hiányzik) - ilyenkor nincs mire
    párosítani, tehát nem tud badge-forrásként szolgálni.
    """
    path = Path(csv_path)
    keys: set[tuple[str, tuple[float, float, float]]] = set()

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
        for row in reader:
            badges = (row.get("Badges") or "").strip()
            if not badges:
                continue

            designation = (row.get("Designation") or "").strip()
            if not designation:
                continue

            length = _parse_mm(row.get("Length"))
            width = _parse_mm(row.get("Width"))
            thickness = _parse_mm(row.get("Thickness"))
            if length is None or width is None or thickness is None:
                continue

            size_key = tuple(round(v, 1) for v in sorted((length, width, thickness)))
            keys.add((designation, size_key))

    return keys