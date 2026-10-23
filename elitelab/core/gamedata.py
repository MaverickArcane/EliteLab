"""Game facts shared by modules. Modules must not import each other, so anything two modules need lives here.

Keys are the game's internal commodity/material names as they appear in Cargo.json ("alieneggs") and in
journal events ("Type":"alieneggs"). Market.json wraps them as "$alieneggs_name;"; use norm() to compare.
Add keys only when observed in a real journal; do not guess them from display names.
"""

POWERS = ["Edmund Mahon", "Li Yong-Rui", "Aisling Duval", "Pranav Antal", "Denton Patreus", "Nakato Kaine",
          "Felicia Winters", "Jerome Archer", "Zemina Torval", "Yuri Grom", "A. Lavigny-Duval", "Archon Delaine"]

# Rare goods: internal key -> display name. Observed keys are marked; the rest are community-documented slugs and
# may be wrong, which is why cargo tagging also trusts Market.json's Rare flag and display-name matches.
RARES = {
    "leestianeviljuice": "Leestian Evil Juice",      # observed
    "bluemilk": "Azure Milk",                        # observed
    "lavianbrandy": "Lavian Brandy",                 # observed
    "disomacorn": "Diso Ma Corn",                    # observed
    "orrerianviciousbrew": "Orrerian Vicious Brew",  # observed
    "uszaiantreegrub": "Uszaian Tree Grub",          # observed
    "alieneggs": "Leathery Eggs",                    # observed (not 'leatheryeggs')
    "zeesszeantgrubglue": "Zeessze Ant Grub Glue",
    "momusbogspaniel": "Momus Bog Spaniel",
    "alyabodysoap": "Alya Body Soap",
    "fujintea": "Fujin Tea",
    "witchhaulkobebeef": "Witchhaul Kobe Beef",
    "taurichimes": "Tauri Chimes",
    "chateaudeaegaeon": "Chateau De Aegaeon",
    "cetirabbits": "Ceti Rabbits",
    "eraninpearlwhisky": "Eranin Pearl Whisky",
    "altairianskin": "Altairian Skin",
    "centaurimegagin": "Centauri Mega Gin",
    "lucanonionhead": "Lucan Onionhead",
    "wuthieloku": "Wuthielo Ku Froth",
    "onionheadbetastrain": "Onionhead Beta Strain",
    "indibourbon": "Indi Bourbon",
    "harmasilversearum": "Harma Silver Sea Rum",
    "kamitracigars": "Kamitra Cigars",
}
KNOWN_RARES = set(RARES)
RARE_NAMES = {v.lower(): k for k, v in RARES.items()}


def norm(name):
    """'$leestianeviljuice_name;' and 'Leestianeviljuice' both -> 'leestianeviljuice'."""
    n = (name or "").lower().strip()
    if n.startswith("$"):
        n = n[1:]
    if n.endswith("_name;"):
        n = n[:-6]
    return n


def is_rare(key_or_name):
    """True for a known rare by internal key or display name."""
    n = norm(key_or_name)
    return n in KNOWN_RARES or n in RARE_NAMES
