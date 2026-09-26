"""Generate the labelled test catalogues in this folder.

    python tests/fixtures/catalogue/generate.py

Every product gets a true_product_id; each is written one to four times in
different ways (word order, abbreviations, Arabic, missing brand or part
number), next to deliberate look-alikes (same series with another seal or
brand, same bolt in another material, same light at another wattage). The
files are made up; none of them is customer data.

blind.csv uses a different seed and product mix. Don't tune thresholds on
it: it exists to show whether rules tuned on the other files generalise.
"""

from __future__ import annotations

import csv
import pathlib
import random

HERE = pathlib.Path(__file__).resolve().parent
AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def ar(value: object) -> str:
    return str(value).translate(AR)


# ---------------------------------------------------------------- product families

BEARING_BRANDS = {"SKF": "اس كي اف", "FAG": "فاج", "NSK": "ان اس كيه", "NTN": "ان تي ان", "TIMKEN": "تيمكن"}
SERIES = ["6000", "6001", "6002", "6003", "6004", "6200", "6201", "6202", "6203", "6204", "6205", "6206", "6207", "6208", "6300", "6302", "6305", "6306", "6310"]
BEARING_VARIANTS = {"2RS": "٢ار اس", "ZZ": "زد زد", "": "", "2RS/C3": "٢ار اس سي ٣"}


def bearing_names(brand: str, series: str, variant: str) -> list[str]:
    v = variant
    joined = v.replace("/", "")
    ar_v = BEARING_VARIANTS[v]
    return [
        f"{brand} {series}-{v} Deep Groove Ball Bearing" if v else f"{brand} {series} Deep Groove Ball Bearing open",
        f"{series} {v.replace('/', ' ')} {brand} bearing".replace("  ", " "),
        f"Bearing {series}-{v} ({brand})" if v else f"Bearing {series} open ({brand})",
        f"BRG {series}{joined} {brand.lower()}",
        f"رولمان بلي {ar(series)} {ar_v} {BEARING_BRANDS[brand]}".replace("  ", " "),
        f"Ball brg {series} {v} {brand}".replace("  ", " "),
    ]


FASTENER_MATERIALS = {
    "A2": ("A2 SS", "STAINLESS A2", "stainless A2", "ستانلس A2"),
    "A4": ("A4 stainless", "STAINLESS A4", "A4 inox", "ستانلس A4"),
    "8.8Z": ("8.8 zinc plated", "ZINC 8.8", "zp 8.8", "زنك 8.8"),
}


def bolt_names(d: int, length: int, mat: str) -> list[str]:
    m = FASTENER_MATERIALS[mat]
    return [
        f"Hex bolt M{d}x{length} {m[0]}",
        f"M{d} X {length}MM HEX HD BOLT {m[1]}",
        f"Bolt hex M{d} x {length} mm {m[2]}",
        f"برغي سداسي M{d}x{length} {m[3]}",
    ]


def nut_names(d: int, mat: str) -> list[str]:
    m = FASTENER_MATERIALS[mat]
    return [f"Hex nut M{d} {m[0]}", f"M{d} HEX NUT {m[1]}", f"Nut hex M{d} {m[2]}"]


def washer_names(d: int, mat: str) -> list[str]:
    m = FASTENER_MATERIALS[mat]
    return [f"Flat washer M{d} {m[0]}", f"M{d} FLAT WASHER {m[1]}", f"Washer flat M{d} {m[2]}"]


LUBRICANTS = [
    # (brand, arabic brand, line, grade, kind, arabic kind)
    ("Shell", "شل", "Tellus S2 M", "46", "hydraulic oil", "زيت هيدروليك"),
    ("Shell", "شل", "Tellus S2 M", "68", "hydraulic oil", "زيت هيدروليك"),
    ("Shell", "شل", "Omala S2 GX", "220", "gear oil", "زيت تروس"),
    ("Shell", "شل", "Omala S2 GX", "320", "gear oil", "زيت تروس"),
    ("Shell", "شل", "Gadus S2 V220", "2", "grease", "شحم"),
    ("Shell", "شل", "Gadus S2 V220", "3", "grease", "شحم"),
    ("Mobil", "موبيل", "DTE", "25", "hydraulic oil", "زيت هيدروليك"),
    ("Mobil", "موبيل", "DTE", "26", "hydraulic oil", "زيت هيدروليك"),
    ("Mobil", "موبيل", "Mobilux EP", "2", "grease", "شحم"),
    ("Mobil", "موبيل", "Mobilux EP", "3", "grease", "شحم"),
]
PACKS = {"oil": [("20L", "٢٠ لتر"), ("209 L drum", "٢٠٩ لتر"), ("4 litre", "٤ لتر")], "grease": [("18kg pail", "١٨ كجم"), ("400g cartridge", "٤٠٠ جم")]}


def lubricant_names(brand: str, ar_brand: str, line: str, grade: str, kind: str, ar_kind: str, rng: random.Random) -> list[str]:
    packs = PACKS["grease" if kind == "grease" else "oil"]
    p1, p2, p3 = (rng.choice(packs) for _ in range(3))
    return [
        f"{brand} {line} {grade} {kind} {p1[0]}",
        f"{brand.upper()} {line.upper()} {grade} {kind.upper()} {p2[0].upper()}",
        f"{kind.capitalize()} {brand} {line} {grade} {p3[0]}",
        f"{ar_kind} {ar_brand} {line} {ar(grade)} {p1[1]}",
    ]


def light_names(watts: int) -> list[str]:
    return [f"LED flood light {watts}W IP65", f"LED floodlight {watts} W 220V IP65", f"{watts}W LED flood lamp", f"كشاف ليد {ar(watts)} وات"]


def mcb_names(amps: int, poles: int) -> list[str]:
    word = {1: "single", 2: "double"}[poles]
    return [f"MCB {amps}A {word} pole", f"{poles}P MCB {amps} amp", f"Circuit breaker MCB {amps}A {poles}P"]


def helmet_names(colour: str, ar_colour: str) -> list[str]:
    return [f"3M Safety Helmet {colour.capitalize()} H-700", f"3M safety helmet {colour} H700 ratchet", f"خوذة سلامة ثري ام {ar_colour}"]


def glove_names(size: int) -> list[str]:
    return [f"Nitrile gloves size {size}", f"Gloves nitrile sz {size}", f"قفاز نيتريل مقاس {ar(size)}"]


def shoe_names(size: int) -> list[str]:
    return [f"Safety shoes size {size} S3", f"S3 safety boot {size}", f"Safety shoe S3 EU {size}"]


# ---------------------------------------------------------------- products

def products(rng: random.Random, families: set[str], scale: float) -> list[dict]:
    out: list[dict] = []

    def add(names: list[str], **attrs: object) -> None:
        out.append({"names": names, **attrs})

    if "bearings" in families:
        combos = {(rng.choice(list(BEARING_BRANDS)), rng.choice(SERIES), rng.choice(list(BEARING_VARIANTS))) for _ in range(int(40 * scale))}
        # Guarantee look-alikes: siblings with another variant or brand.
        for brand, series, variant in list(combos)[: int(12 * scale)]:
            combos.add((brand, series, rng.choice([v for v in BEARING_VARIANTS if v != variant])))
            combos.add((rng.choice([b for b in BEARING_BRANDS if b != brand]), series, variant))
        for brand, series, variant in sorted(combos):
            add(bearing_names(brand, series, variant), brand=brand, part=series, variant=variant, family="bearing")
    if "fasteners" in families:
        for _ in range(int(25 * scale)):
            d, length, mat = rng.choice([6, 8, 10, 12]), rng.choice([20, 25, 30, 40, 50]), rng.choice(list(FASTENER_MATERIALS))
            add(bolt_names(d, length, mat), family="bolt", key=("bolt", d, length, mat))
        for _ in range(int(8 * scale)):
            d, mat = rng.choice([6, 8, 10, 12]), rng.choice(list(FASTENER_MATERIALS))
            add(nut_names(d, mat), family="nut", key=("nut", d, mat))
            add(washer_names(d, mat), family="washer", key=("washer", d, mat))
    if "lubricants" in families:
        for lub in LUBRICANTS:
            add(lubricant_names(*lub, rng=rng), brand=lub[0], family="lubricant", key=lub[:4])
    if "electrical" in families:
        for watts in (30, 50, 100, 150, 200):
            add(light_names(watts), family="light", key=("light", watts))
        for amps in (10, 16, 20, 32):
            for poles in (1, 2):
                add(mcb_names(amps, poles), family="mcb", key=("mcb", amps, poles))
    if "safety" in families:
        for colour, ar_colour in (("white", "ابيض"), ("yellow", "اصفر"), ("red", "احمر"), ("blue", "ازرق")):
            add(helmet_names(colour, ar_colour), brand="3M", family="helmet", key=("helmet", colour))
        for size in (8, 9, 10):
            add(glove_names(size), family="glove", key=("glove", size))
        for size in (40, 41, 42, 43, 44):
            add(shoe_names(size), family="shoe", key=("shoe", size))

    # One product per key (random picks above can repeat).
    unique: dict[object, dict] = {}
    for p in out:
        unique.setdefault(p.get("key") or (p["family"], p.get("brand"), p.get("part"), p.get("variant")), p)
    return list(unique.values())


def rows_for(product: dict, pid: str, rng: random.Random, with_stock: bool) -> list[dict]:
    copies = rng.choices([1, 2, 3, 4], weights=[35, 35, 20, 10])[0]
    names = rng.sample(product["names"], k=min(copies, len(product["names"])))
    rows = []
    for name in names:
        row = {"name": name, "pid": pid}
        brand = product.get("brand")
        row["brand"] = rng.choice([brand, brand.lower() if brand else "", ""]) if brand and rng.random() < 0.75 else ""
        if product.get("part"):
            variant = product.get("variant") or ""
            row["part"] = rng.choice([product["part"], product["part"], f"{product['part']}-{variant}" if variant else product["part"], ""])
        else:
            row["part"] = ""
        if with_stock:
            row["stock"] = str(rng.choice([0, 2, 4, 6, 10, 12, 18, 24, 40, 100]))
            row["cost"] = f"{rng.uniform(0.2, 60):.2f}"
        rows.append(row)
    return rows


def write(filename: str, seed: int, families: set[str], scale: float, headers: dict[str, str], with_stock: bool) -> None:
    rng = random.Random(seed)
    rows: list[dict] = []
    for n, product in enumerate(products(rng, families, scale), start=1):
        rows.extend(rows_for(product, f"P{n:03d}", rng, with_stock))
    rng.shuffle(rows)
    code_prefix = filename[:3].upper()
    with (HERE / filename).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(list(headers.values()) + ["true_product_id"])
        for i, row in enumerate(rows, start=1):
            values = {"code": f"{code_prefix}-{i:04d}", **row}
            writer.writerow([values.get(k, "") for k in headers] + [row["pid"]])
    print(f"{filename}: {len(rows)} rows")


if __name__ == "__main__":
    write("bearings.csv", 11, {"bearings"}, 1.0, {"code": "Item Code", "name": "Description", "part": "Part Number", "brand": "Brand"}, False)
    write("fasteners.csv", 12, {"fasteners"}, 1.0, {"code": "SKU", "name": "Product Name", "stock": "Qty", "cost": "Unit Cost"}, True)
    write(
        "stores.csv", 13, {"bearings", "fasteners", "lubricants", "electrical", "safety"}, 0.6,
        {"code": "Stock Code", "name": "Item Description", "brand": "Manufacturer", "part": "MPN", "stock": "Qty On Hand", "cost": "Cost Price"}, True,
    )
    write(
        "blind.csv", 99, {"bearings", "fasteners", "lubricants", "electrical", "safety"}, 0.7,
        {"code": "Code", "name": "Name", "brand": "Make", "part": "Part No", "stock": "Stock", "cost": "Price"}, True,
    )
