"""Product knowledge used by normalisation. Data only: add a product family by
extending these tables, not the code in normalize.py.

Variant suffixes are what separate real duplicates from look-alikes. Each maps
to one or more classes, "<property>:<value>". Two rows with the same base part
number but a different value for the same property are different products
(for example seal:rubber_both vs seal:metal_both). Suffixes with the same
classes but different spellings (SKF 2RSH, NSK DDU) are brand equivalents.
"""

from __future__ import annotations

# Bearings, first version. Upper case, as printed in part numbers.
VARIANT_SUFFIXES: dict[str, tuple[str, ...]] = {
    # Rubber seals, both sides
    "2RS": ("seal:rubber_both",),
    "2RS1": ("seal:rubber_both",),
    "2RSH": ("seal:rubber_both",),
    "2RSR": ("seal:rubber_both",),
    "LLU": ("seal:rubber_both",),
    "DDU": ("seal:rubber_both",),
    "2RSL": ("seal:low_friction_both",),
    # Rubber seal, one side
    "RS": ("seal:rubber_one",),
    "RS1": ("seal:rubber_one",),
    "RSH": ("seal:rubber_one",),
    "LU": ("seal:rubber_one",),
    "DU": ("seal:rubber_one",),
    # Metal shields
    "ZZ": ("seal:metal_both",),
    "2Z": ("seal:metal_both",),
    "Z": ("seal:metal_one",),
    # Internal clearance
    "C2": ("clearance:c2",),
    "C3": ("clearance:c3",),
    "C4": ("clearance:c4",),
    "C5": ("clearance:c5",),
    # Snap ring
    "N": ("ring:groove",),
    "NR": ("ring:groove_with_ring",),
}

# Longest first, so "2RSH" is peeled before "RS" and "H".
SUFFIXES_LONGEST_FIRST: tuple[str, ...] = tuple(sorted(VARIANT_SUFFIXES, key=len, reverse=True))

# Brand spellings to one canonical key. Keys are lower case with punctuation
# and spaces removed. Anything not listed is kept as written (normalised).
BRAND_ALIASES: dict[str, str] = {
    "skf": "skf",
    "fag": "fag",
    "schaeffler": "schaeffler",
    "ina": "ina",
    "nsk": "nsk",
    "ntn": "ntn",
    "koyo": "koyo",
    "jtekt": "koyo",
    "timken": "timken",
    "nachi": "nachi",
    "rhp": "rhp",
    "loctite": "loctite",
    "henkel": "loctite",
    "3m": "3m",
    "bosch": "bosch",
    "makita": "makita",
    "dewalt": "dewalt",
    "stanley": "stanley",
    "wurth": "wurth",
    "würth": "wurth",
    "gates": "gates",
    "optibelt": "optibelt",
    "parker": "parker",
    "festo": "festo",
    "smc": "smc",
    "siemens": "siemens",
    "schneider": "schneider",
    "schneiderelectric": "schneider",
    "abb": "abb",
    "omron": "omron",
    "rs": "rs",
    "rspro": "rs",
    "shell": "shell",
    "mobil": "mobil",
    "exxonmobil": "mobil",
    "castrol": "castrol",
    "total": "total",
    "totalenergies": "total",
    "fuchs": "fuchs",
}

# Brands recognised inside item names when there is no brand column. Only
# distinctive names: short common words ("rs", "ina") would cause false hits.
BRANDS_IN_TEXT: tuple[str, ...] = (
    "skf", "fag", "schaeffler", "nsk", "ntn", "koyo", "timken", "nachi", "rhp",
    "loctite", "3m", "bosch", "makita", "dewalt", "stanley", "wurth", "gates",
    "optibelt", "parker", "festo", "smc", "siemens", "schneider", "abb", "omron",
    "shell", "mobil", "castrol", "fuchs",
)

# Whole-word abbreviations expanded in normalised text.
ABBREVIATIONS: dict[str, str] = {
    "brg": "bearing",
    "brgs": "bearings",
    "ss": "stainless steel",
    "s/s": "stainless steel",
    "stl": "steel",
    "galv": "galvanised",
    "galvanized": "galvanised",
    "blk": "black",
    "wht": "white",
    "hd": "head",
    "hex hd": "hex head",
    "skt": "socket",
    "csk": "countersunk",
    "assy": "assembly",
    "qty": "quantity",
}

# Length units to millimetres, mass to grams, volume to millilitres.
# Arabic unit words are included (after letter unification).
LENGTH_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "مم": 1.0, "سم": 10.0, "متر": 1000.0}
MASS_TO_G = {"g": 1.0, "gm": 1.0, "gms": 1.0, "gram": 1.0, "grams": 1.0, "kg": 1000.0, "kgs": 1000.0, "جم": 1.0, "جرام": 1.0, "غرام": 1.0, "كجم": 1000.0, "كغ": 1000.0, "كيلو": 1000.0}
VOLUME_TO_ML = {"ml": 1.0, "l": 1000.0, "lt": 1000.0, "ltr": 1000.0, "litre": 1000.0, "liter": 1000.0, "litres": 1000.0, "liters": 1000.0, "مل": 1.0, "لتر": 1000.0}

# ---------------------------------------------------------------- languages
# Many catalogues mix English and Arabic, and Arabic names often spell Latin
# brands and suffixes out in Arabic letters ("اس كي اف" = SKF, "زد زد" = ZZ).

# Arabic-Indic and Persian digits to ASCII (NFKC leaves them alone).
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# Tatweel and short-vowel marks are decoration; letter variants are unified.
ARABIC_DROP = dict.fromkeys([0x0640, *range(0x064B, 0x0660), 0x0670])
ARABIC_UNIFY = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})

# Whole phrases rewritten to Latin after the steps above. Keys are matched as
# whole words; longest first.
PHRASES: dict[str, str] = {
    "2 ار اس": "2rs",
    "2ار اس": "2rs",
    "ار اس": "rs",
    "زد زد": "zz",
    "2 زد": "2z",
    "سي 3": "c3",
    "اس كي اف": "skf",
    "ان اس كيه": "nsk",
    "ان اس كي": "nsk",
    "ان تي ان": "ntn",
    "فاج": "fag",
    "تيمكن": "timken",
    "كويو": "koyo",
    "شل": "shell",
    "موبيل": "mobil",
    "لوكتايت": "loctite",
    "ثري ام": "3m",
    "3 ام": "3m",
    "بوش": "bosch",
}
# "في" before digits is the letter V ("في220" = V220); elsewhere it means "in".
ARABIC_V_BEFORE_DIGIT = "في"

# Latin letters spelled out ("ess kay eff" = SKF), used only to find brands.
LETTER_NAMES: dict[str, str] = {
    "ay": "a", "bee": "b", "see": "c", "cee": "c", "dee": "d", "ee": "e", "eff": "f", "ef": "f", "gee": "g",
    "aitch": "h", "eye": "i", "jay": "j", "kay": "k", "el": "l", "em": "m", "en": "n", "oh": "o", "pee": "p",
    "cue": "q", "ar": "r", "ess": "s", "es": "s", "tee": "t", "you": "u", "vee": "v", "ex": "x", "why": "y",
    "zed": "z", "zee": "z",
}

# ---------------------------------------------------------------- product words
# Coarse product types. Two items whose types don't overlap are different
# products (grease is not gear oil), whatever else matches.
PRODUCT_TYPES: dict[str, str] = {
    # English
    "bearing": "bearing", "bearings": "bearing",
    "grease": "grease",
    "oil": "oil", "lubricant": "oil",
    "adhesive": "adhesive", "threadlocker": "adhesive", "threadlock": "adhesive", "glue": "adhesive", "sealant": "adhesive",
    "helmet": "helmet", "hardhat": "helmet",
    "light": "light", "floodlight": "light", "lamp": "light", "bulb": "light", "spotlight": "light",
    "bolt": "bolt", "bolts": "bolt",
    "screw": "screw", "screws": "screw",
    "nut": "nut", "nuts": "nut",
    "washer": "washer", "washers": "washer",
    "belt": "belt", "belts": "belt",
    "filter": "filter", "filters": "filter",
    "hose": "hose", "hoses": "hose",
    "valve": "valve", "valves": "valve",
    "cable": "cable", "cables": "cable",
    "glove": "glove", "gloves": "glove",
    "motor": "motor", "motors": "motor",
    "pump": "pump", "pumps": "pump",
    "برغي": "bolt", "بولت": "bolt",
    "mcb": "breaker", "rcbo": "breaker", "rcd": "breaker", "breaker": "breaker", "contactor": "contactor",
    "socket": "socket", "switch": "switch", "fuse": "fuse", "fuses": "fuse",
    "shoe": "shoe", "shoes": "shoe", "boot": "shoe", "boots": "shoe",
    "tape": "tape", "spray": "spray", "brush": "brush", "disc": "disc", "blade": "blade", "drill": "drill",
    # Arabic (after letter unification) and Arabizi
    "بلي": "bearing", "رولمان": "bearing", "رمان": "bearing", "rolman": "bearing", "rulman": "bearing", "belly": "bearing", "bely": "bearing",
    "شحم": "grease", "sha7m": "grease", "shahm": "grease",
    "زيت": "oil", "zet": "oil", "zeit": "oil", "zayt": "oil",
    "لاصق": "adhesive", "غراء": "adhesive",
    "خوذه": "helmet",
    "كشاف": "light", "لمبه": "light",
    "مسمار": "screw", "مسامير": "screw",
    "صامولة": "nut", "صاموله": "nut",
    "ورده": "washer",
    "سير": "belt",
    "فلتر": "filter",
    "خرطوم": "hose",
    "صمام": "valve", "محبس": "valve",
    "كابل": "cable",
    "قفاز": "glove", "جوانتي": "glove",
    "موتور": "motor",
    "مضخه": "pump", "طلمبه": "pump",
}

COLOURS: dict[str, str] = {
    "white": "white", "black": "black", "red": "red", "blue": "blue", "yellow": "yellow", "green": "green",
    "orange": "orange", "grey": "grey", "gray": "grey", "silver": "silver", "brown": "brown", "clear": "clear",
    "ابيض": "white", "اسود": "black", "احمر": "red", "ازرق": "blue", "اصفر": "yellow", "اخضر": "green",
    "برتقالي": "orange", "رمادي": "grey", "فضي": "silver", "بني": "brown", "شفاف": "clear",
}

# ---------------------------------------------------------------- explanations
# Plain words for variant classes, used in reasons shown to customers.
CLASS_NAMES: dict[str, str] = {
    "seal:rubber_both": "rubber seals on both sides",
    "seal:rubber_one": "a rubber seal on one side",
    "seal:low_friction_both": "low-friction seals on both sides",
    "seal:metal_both": "metal shields on both sides",
    "seal:metal_one": "a metal shield on one side",
    "clearance:c2": "C2 (smaller) internal clearance",
    "clearance:c3": "C3 (larger) internal clearance",
    "clearance:c4": "C4 internal clearance",
    "clearance:c5": "C5 internal clearance",
    "ring:groove": "a snap-ring groove",
    "ring:groove_with_ring": "a snap ring",
}
PROPERTY_NAMES = {"seal": "seal type", "clearance": "internal clearance", "ring": "snap ring"}
# Properties where "not written" means standard, so it differs from written.
ABSENT_MEANS_STANDARD = {"clearance", "ring"}

# Materials and strength grades, as "<property>:<value>". Rows naming
# different values for the same property are different products (an A2 bolt
# is not an A4 bolt; a zinc-plated one is not stainless).
MATERIALS: dict[str, str] = {
    "a2": "stainless_grade:a2", "a4": "stainless_grade:a4",
    "stainless": "material:stainless", "inox": "material:stainless",
    "zinc": "material:zinc", "zp": "material:zinc", "galvanised": "material:galvanised", "hdg": "material:galvanised",
    "brass": "material:brass", "nylon": "material:nylon", "copper": "material:copper",
    "aluminium": "material:aluminium", "aluminum": "material:aluminium",
    "8.8": "strength:8.8", "10.9": "strength:10.9", "12.9": "strength:12.9",
    "زنك": "material:zinc", "ستانلس": "material:stainless", "استانلس": "material:stainless", "مجلفن": "material:galvanised", "نحاس": "material:brass",
}
# A2 and A4 are stainless steel grades.
MATERIAL_IMPLIES = {"stainless_grade:a2": "material:stainless", "stainless_grade:a4": "material:stainless"}

# Container and pack words. Ignored when comparing names: "Tellus 46 20L" and
# "Tellus 46 209 L drum" are the same oil in different packs.
CONTAINER_WORDS = frozenset({
    "drum", "pail", "cartridge", "tub", "barrel", "can", "bottle", "tube", "box", "pack", "bag", "jar", "carton",
    "of", "pcs", "pc", "pieces", "pk",
    "برميل", "عبوه", "جردل", "علبه", "كرتونه", "كيس",
})
