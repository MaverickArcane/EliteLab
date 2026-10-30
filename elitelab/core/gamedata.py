"""Game facts shared by modules. Modules must not import each other, so anything two modules need lives here.

Keys are the game's internal commodity/material names as they appear in Cargo.json ("alieneggs") and in
journal events ("Type":"alieneggs"). Market.json wraps them as "$alieneggs_name;"; use norm() to compare.
Add keys only when observed in a real journal; do not guess them from display names.
"""

POWERS = ["Edmund Mahon", "Li Yong-Rui", "Aisling Duval", "Pranav Antal", "Denton Patreus", "Nakato Kaine",
          "Felicia Winters", "Jerome Archer", "Zemina Torval", "Yuri Grom", "A. Lavigny-Duval", "Archon Delaine"]

# Rare goods: journal key -> display name, from EDCD FDevIDs rare_commodity.csv (142 entries, 2026-10-24). Keys are the
# game's symbols lower-cased, exactly as Cargo.json and MarketSell write them (Leathery Eggs is 'alieneggs').
RARES = {
    "azcancriformula42": "AZ Cancri Formula 42",
    "cetiaepyornisegg": "Aepyornis Egg",
    "aganipperush": "Aganippe Rush",
    "alacarakmoskinart": "Alacarakmo Skin Art",
    "albinoquechuamammoth": "Albino Quechua Mammoth Meat",
    "altairianskin": "Altairian Skin",
    "alyabodilysoap": "Alya Body Soap",
    "anduligafireworks": "Anduliga Fire Works",
    "anynacoffee": "Any Na Coffee",
    "apavietii": "Apa Vietii",
    "aroucaconventualsweets": "Arouca Conventual Sweets",
    "bluemilk": "Azure Milk",
    "bakedgreebles": "Baked Greebles",
    "baltahsinevacuumkrill": "Baltah'sine Vacuum Krill",
    "bankiamphibiousleather": "Banki Amphibious Leather",
    "bastsnakegin": "Bast Snake Gin",
    "belalansrayleather": "Belalans Ray Leather",
    "borasetanipathogenetics": "Borasetani Pathogenetics",
    "buckyballbeermats": "Buckyball Beer Mats",
    "burnhambiledistillate": "Burnham Bile Distillate",
    "cd75catcoffee": "CD-75 Kitten Brand Coffee",
    "centaurimegagin": "Centauri Mega Gin",
    "ceremonialheiketea": "Ceremonial Heike Tea",
    "cetirabbits": "Ceti Rabbits",
    "chameleoncloth": "Chameleon Cloth",
    "chateaudeaegaeon": "Chateau De Aegaeon",
    "cherbonesbloodcrystals": "Cherbones Blood Crystals",
    "chieridanimarinepaste": "Chi Eridani Marine Paste",
    "classifiedexperimentalequipment": "Classified Experimental Equipment",
    "coquimspongiformvictuals": "Coquim Spongiform Victuals",
    "animaleffigies": "Crom Silver Fesh",
    "crystallinespheres": "Crystalline Spheres",
    "damnacarapaces": "Damna Carapaces",
    "deltaphoenicispalms": "Delta Phoenicis Palms",
    "deuringastruffles": "Deuringas Truffles",
    "disomacorn": "Diso Ma Corn",
    "duradrives": "Duradrives",
    "aerialedenapple": "Eden Apples of Aerial",
    "eleuthermals": "Eleu Thermals",
    "eraninpearlwhisky": "Eranin Pearl Whisky",
    "eshuumbrellas": "Eshu Umbrellas",
    "esusekucaviar": "Esuseku Caviar",
    "ethgrezeteabuds": "Ethgreze Tea Buds",
    "personalgifts": "Festive Gifts",
    "fujintea": "Fujin Tea",
    "galactictravelguide": "Galactic Travel Guide",
    "geawendancedust": "Geawen Dance Dust",
    "gerasiangueuzebeer": "Gerasian Gueuze Beer",
    "giantirukamasnails": "Giant Irukama Snails",
    "giantverrix": "Giant Verrix",
    "gilyasignatureweapons": "Gilya Signature Weapons",
    "gomanyauponcoffee": "Goman Yaupon Coffee",
    "hip10175bushmeat": "HIP 10175 Bush Meat",
    "hip118311swarm": "HIP 118311 Swarm",
    "hiporganophosphates": "HIP Organophosphates",
    "hip41181squid": "HIP Proto-Squid",
    "hr7221wheat": "HR 7221 Wheat",
    "haidneblackbrew": "Haiden Black Brew",
    "harmasilversearum": "Harma Silver Sea Rum",
    "havasupaidreamcatcher": "Havasupai Dream Catcher",
    "helvetitjpearls": "Helvetitj Pearls",
    "holvaduellingblades": "Holva Duelling Blades",
    "honestypills": "Honesty Pills",
    "indibourbon": "Indi Bourbon",
    "jaquesquinentianstill": "Jaques Quinentian Still",
    "jaradharrepuzzlebox": "Jaradharre Puzzle Box",
    "jarouarice": "Jaroua Rice",
    "jotunmookah": "Jotun Mookah",
    "kachiriginleaches": "Kachirigin Filter Leeches",
    "kamitracigars": "Kamitra Cigars",
    "kamorinhistoricweapons": "Kamorin Historic Weapons",
    "karetiicouture": "Karetii Couture",
    "karsukilocusts": "Karsuki Locusts",
    "kinagoinstruments": "Kinago Violins",
    "konggaale": "Kongga Ale",
    "korrokungpellets": "Koro Kung Pellets",
    "ltthypersweet": "LTT Hyper Sweet",
    "lavianbrandy": "Lavian Brandy",
    "alieneggs": "Leathery Eggs",
    "leestianeviljuice": "Leestian Evil Juice",
    "livehecateseaworms": "Live Hecate Sea Worms",
    "transgeniconionhead": "Lucan Onionhead",
    "lyraeweed": "Lyrae Weed",
    "masterchefs": "Master Chefs",
    "mechucoshightea": "Mechucos High Tea",
    "medbstarlube": "Medb Starlube",
    "mokojingbeastfeast": "Mokojing Beast Feast",
    "momusbogspaniel": "Momus Bog Spaniel",
    "motronaexperiencejelly": "Motrona Experience Jelly",
    "mukusubiichitinos": "Mukusubii Chitin-os",
    "mulachigiantfungus": "Mulachi Giant Fungus",
    "nanomedicines": "Nanomedicines",
    "neritusberries": "Neritus Berries",
    "ngadandarifireopals": "Ngadandari Fire Opals",
    "ngunamodernantiques": "Nguna Modern Antiques",
    "njangarisaddles": "Njangari Saddles",
    "noneuclidianexotanks": "Non Euclidian Exotanks",
    "ochoengchillies": "Ochoeng Chillies",
    "onionhead": "Onionhead",
    "onionheada": "Onionhead Alpha Strain",
    "onionheadb": "Onionhead Beta Strain",
    "ophiuchiexinoartefacts": "Ophiuch Exino Artefacts",
    "orrerianviciousbrew": "Orrerian Vicious Brew",
    "pantaaprayersticks": "Pantaa Prayer Sticks",
    "pavoniseargrubs": "Pavonis Ear Grubs",
    "platinumaloy": "Platinum Alloy",
    "rajukrustoves": "Rajukru Multi-Stoves",
    "rapabaosnakeskins": "Rapa Bao Snake Skins",
    "rusanioldsmokey": "Rusani Old Smokey",
    "sanumameat": "Sanuma Decorative Meat",
    "saxonwine": "Saxon Wine",
    "shanscharisorchid": "Shan's Charis Orchid",
    "soontillrelics": "Soontill Relics",
    "sothiscrystallinegold": "Sothis Crystalline Gold",
    "tanmarktranquiltea": "Tanmark Tranquil Tea",
    "tarachtorspice": "Tarach Spice",
    "taurichimes": "Tauri Chimes",
    "terramaterbloodbores": "Terra Mater Blood Bores",
    "thehuttonmug": "The Hutton Mug",
    "watersofshintara": "The Waters of Shintara",
    "thrutiscream": "Thrutis Cream",
    "tiegfriessynthsilk": "Tiegfries Synth Silk",
    "tiolcewaste2pasteunits": "Tiolce Waste2Paste Units",
    "toxandjivirocide": "Toxandji Virocide",
    "advert1": "Ultra-Compact Processor Prototypes",
    "uszaiantreegrub": "Uszaian Tree Grub",
    "utgaroarmillenialeggs": "Utgaroar Millennial Eggs",
    "uzumokulowgwings": "Uzumoku Low-G Wings",
    "vherculisbodyrub": "V Herculis Body Rub",
    "vanayequirhinofur": "Vanayequi Ceratomorpha Fur",
    "vegaslimweed": "Vega Slimweed",
    "vidavantianlace": "Vidavantian Lace",
    "lftvoidextractcoffee": "Void Extract Coffee",
    "volkhabbeedrones": "Volkhab Bee Drones",
    "wheemetewheatcakes": "Wheemete Wheat Cakes",
    "witchhaulkobebeef": "Witchhaul Kobe Beef",
    "wolf1301fesh": "Wolf Fesh",
    "wulpahyperboresystems": "Wulpa Hyperbore Systems",
    "wuthielokufroth": "Wuthielo Ku Froth",
    "xihecompanions": "Xihe Biomorphic Companions",
    "yasokondileaf": "Yaso Kondi Leaf",
    "zeesszeantglue": "Zeessze Ant Grub Glue",
}
# Origin station market id per rare (FDevIDs), for loops and price-by-distance work.
RARE_MARKETS = {
    "azcancriformula42": 3228400128,
    "cetiaepyornisegg": 3222560256,
    "aganipperush": 128012800,
    "alacarakmoskinart": 3231373824,
    "albinoquechuamammoth": 3222822912,
    "altairianskin": 128151032,
    "alyabodilysoap": 3221638400,
    "anduligafireworks": 3230243584,
    "anynacoffee": 3229880064,
    "apavietii": 128958681,
    "aroucaconventualsweets": 128098040,
    "bluemilk": 128639992,
    "bakedgreebles": 3229378560,
    "baltahsinevacuumkrill": 128088056,
    "bankiamphibiousleather": 3228346112,
    "bastsnakegin": 128086776,
    "belalansrayleather": 3223537152,
    "borasetanipathogenetics": 3229638400,
    "buckyballbeermats": 128745551,
    "burnhambiledistillate": 3230224384,
    "cd75catcoffee": 3228566016,
    "centaurimegagin": 3228728832,
    "ceremonialheiketea": 3227417856,
    "cetirabbits": 3222560000,
    "chameleoncloth": 3223418880,
    "chateaudeaegaeon": 3228416768,
    "cherbonesbloodcrystals": 3229594624,
    "chieridanimarinepaste": 128128760,
    "classifiedexperimentalequipment": 128986325,
    "coquimspongiformvictuals": 3223832576,
    "animaleffigies": 3228463360,
    "crystallinespheres": 128059402,
    "damnacarapaces": 3227751936,
    "deltaphoenicispalms": 128045312,
    "deuringastruffles": 3229713408,
    "disomacorn": 128161016,
    "duradrives": 3223453184,
    "aerialedenapple": 128083448,
    "eleuthermals": 3230624768,
    "eraninpearlwhisky": 128001536,
    "eshuumbrellas": 3222295552,
    "esusekucaviar": 3226919680,
    "ethgrezeteabuds": 3229524992,
    "personalgifts": 3223105792,
    "fujintea": 128134392,
    "galactictravelguide": 128673074,
    "geawendancedust": 3230954752,
    "gerasiangueuzebeer": 3228047360,
    "giantirukamasnails": 3225345792,
    "giantverrix": 128121336,
    "gilyasignatureweapons": 3226857216,
    "gomanyauponcoffee": 3224449792,
    "hip10175bushmeat": 3223234816,
    "hip118311swarm": 3223177472,
    "hiporganophosphates": 3227036160,
    "hip41181squid": 3227995392,
    "hr7221wheat": 3226170880,
    "haidneblackbrew": 3226557696,
    "harmasilversearum": 3221575424,
    "havasupaidreamcatcher": 3221438976,
    "helvetitjpearls": 3231094528,
    "holvaduellingblades": 3222713088,
    "honestypills": 3229561344,
    "indibourbon": 128118520,
    "jaquesquinentianstill": 128667761,
    "jaradharrepuzzlebox": 3230754816,
    "jarouarice": 3224698112,
    "jotunmookah": 128078840,
    "kachiriginleaches": 3221595648,
    "kamitracigars": 3225450752,
    "kamorinhistoricweapons": 3221669632,
    "karetiicouture": 3227333120,
    "karsukilocusts": 3225028096,
    "kinagoinstruments": 3227394304,
    "konggaale": 3226978048,
    "korrokungpellets": 3228726272,
    "ltthypersweet": 3224166400,
    "lavianbrandy": 128106744,
    "alieneggs": 128164088,
    "leestianeviljuice": 128639992,
    "livehecateseaworms": 128042496,
    "transgeniconionhead": 128057866,
    "lyraeweed": 3226417152,
    "masterchefs": 128123640,
    "mechucoshightea": 3228398848,
    "medbstarlube": 3228762368,
    "mokojingbeastfeast": 3229612800,
    "momusbogspaniel": 128075256,
    "motronaexperiencejelly": 3229750528,
    "mukusubiichitinos": 3221719296,
    "mulachigiantfungus": 3228892672,
    "nanomedicines": 3226651904,
    "neritusberries": 3228206080,
    "ngadandarifireopals": 3226127872,
    "ngunamodernantiques": 3221538304,
    "njangarisaddles": 3222416896,
    "noneuclidianexotanks": 3224135424,
    "ochoengchillies": 3226719232,
    "onionhead": 128129272,
    "onionheada": 3226977024,
    "onionheadb": 3223027200,
    "ophiuchiexinoartefacts": 3228939264,
    "orrerianviciousbrew": 128166392,
    "pantaaprayersticks": 3228824064,
    "pavoniseargrubs": 128117240,
    "platinumaloy": 3223779840,
    "rajukrustoves": 3227512320,
    "rapabaosnakeskins": 3222875648,
    "rusanioldsmokey": 3229255680,
    "sanumameat": 3230331136,
    "saxonwine": 3227986432,
    "shanscharisorchid": 128107768,
    "soontillrelics": 3225348096,
    "sothiscrystallinegold": 128668557,
    "tanmarktranquiltea": 128057866,
    "tarachtorspice": 128041984,
    "taurichimes": 128134648,
    "terramaterbloodbores": 128051466,
    "thehuttonmug": 3228728832,
    "watersofshintara": 128666762,
    "thrutiscream": 3226522368,
    "tiegfriessynthsilk": 3227726848,
    "tiolcewaste2pasteunits": 3224141312,
    "toxandjivirocide": 3230258688,
    "advert1": 3227172352,
    "uszaiantreegrub": 128164856,
    "utgaroarmillenialeggs": 128037120,
    "uzumokulowgwings": 3226474496,
    "vherculisbodyrub": 3228959232,
    "vanayequirhinofur": 3227289856,
    "vegaslimweed": 128149240,
    "vidavantianlace": 3231082240,
    "lftvoidextractcoffee": 3229028864,
    "volkhabbeedrones": 3227831808,
    "wheemetewheatcakes": 3225032704,
    "witchhaulkobebeef": 3223358720,
    "wolf1301fesh": 128084984,
    "wulpahyperboresystems": 3221388032,
    "wuthielokufroth": 3222155776,
    "xihecompanions": 3224133120,
    "yasokondileaf": 3223088640,
    "zeesszeantglue": 128125432,
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


# -- Engineering -------------------------------------------------------------------------------------------------
# Materials (with trader families), blueprints and experimental effects live in engineering.json next to this file.
# Where the numbers come from and what is assumed (rolls per grade, trader ratios) is in docs/DECISIONS.md.
import json as _json       # noqa: E402
import math as _math       # noqa: E402
import os as _os           # noqa: E402
import re as _re           # noqa: E402

with open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "engineering.json"), "r", encoding="utf-8") as _f:
    _ENG = _json.load(_f)

MATERIALS = _ENG["materials"]                              # [{key, name, category, grade, family}]
MATERIAL_BY_KEY = {m["key"]: m for m in MATERIALS}
MATERIAL_BY_NAME = {m["name"].lower(): m["key"] for m in MATERIALS}
MATERIAL_CAPS = {int(k): v for k, v in _ENG["caps"].items()}       # grade -> max you can carry
BLUEPRINTS = _ENG["blueprints"]                            # [{key, name, module, aliases, max_grade, grades{g: {key: n}}, engineers{name: max grade}}]
BLUEPRINT_BY_KEY = {b["key"]: b for b in BLUEPRINTS}
EXPERIMENTALS = _ENG["experimentals"]                      # [{key, name, modules[], ingredients{key: n}}]
EXPERIMENTAL_BY_KEY = {e["key"]: e for e in EXPERIMENTALS}
UNLOCKS = _ENG.get("unlocks", [])                          # technology broker: [{key, name, module, broker, ingredients{key: n}, commodities{name: n}}]
UNLOCK_BY_KEY = {u["key"]: u for u in UNLOCKS}
BLUEPRINT_BY_LOWER = {b["key"].lower(): b["key"] for b in BLUEPRINTS}      # journal BlueprintName / EDSY fdname -> key
EXPERIMENTAL_BY_LOWER = {e["key"].lower(): e["key"] for e in EXPERIMENTALS}
ROLLS_PER_GRADE = {int(k): v for k, v in _ENG["rolls_per_grade"].items()}   # planning hint: rolls to complete each grade
TRADE = _ENG["trade"]                                      # same_family_down, same_family_up, cross_family_factor

_WORDS = _re.compile(r"[a-z0-9]+")
_STOP = {"a", "an", "the", "for", "to", "of", "and", "my", "engineered", "engineering", "blueprint", "recipe", "mod",
         "modification", "roll", "rolls", "effect", "experimental"}


def tokens(text):
    """Lower-case words of a query, minus filler ('engineered', 'blueprint', 'for'...)."""
    return [t for t in _WORDS.findall((text or "").lower()) if t not in _STOP]


def material_name(key):
    m = MATERIAL_BY_KEY.get(key)
    return m["name"] if m else key


def resolve_material(name):
    """Journal key, display name, or a loose all-words match that hits exactly one material. Returns key or None."""
    if not name:
        return None
    k = norm(name)
    if k in MATERIAL_BY_KEY:
        return k
    n = name.strip().lower()
    if n in MATERIAL_BY_NAME:
        return MATERIAL_BY_NAME[n]
    words = _WORDS.findall(n)
    hits = [m["key"] for m in MATERIALS if words and all(w in m["name"].lower() for w in words)]
    return hits[0] if len(hits) == 1 else None


def _key_words(key):
    """'FSD_LongRange' -> ['fsd', 'long', 'range']; 'special_fsd_heavy' -> ['fsd', 'heavy']."""
    spaced = _re.sub(r"(?<=[a-z])(?=[A-Z])", " ", key.replace("_", " ").replace("special ", ""))
    return _WORDS.findall(spaced.lower())


def blueprint_modules(blueprint):
    """Explicit supported modules; aliases remain search terms, not applicability."""
    return blueprint.get("modules") or [blueprint["module"]]


def _build_index():
    out = []
    for b in BLUEPRINTS:
        words = set(_WORDS.findall(b["module"].lower()) + _WORDS.findall(b["name"].lower()) + _key_words(b["key"]))
        for a in b["aliases"]:
            words |= set(_WORDS.findall(a.lower()))
        for m in blueprint_modules(b):
            words |= set(_WORDS.findall(m.lower()))
        out.append(("blueprint", b, words))
    for e in EXPERIMENTALS:
        words = set(_WORDS.findall(e["name"].lower()) + _key_words(e["key"]))
        for m in e["modules"]:
            words |= set(_WORDS.findall(m.lower()))
        out.append(("experimental", e, words))
    for u in UNLOCKS:
        words = set(_WORDS.findall(u["name"].lower()) + _WORDS.findall(u["module"].lower()) + ["unlock", "tech", "broker", u["broker"].lower()])
        out.append(("unlock", u, words))
    return out


RECIPE_INDEX = _build_index()


RECIPE_MODULES = sorted({m for b in BLUEPRINTS for m in blueprint_modules(b)} | {m for e in EXPERIMENTALS for m in e["modules"]} | {u["module"] for u in UNLOCKS})
ENGINEERS = sorted({e for b in BLUEPRINTS for e in b["engineers"]})
_MODULE_NAMES = {m.lower() for m in RECIPE_MODULES}


def find_recipes(query, kind=None, module=None, engineer=None, limit=20):
    """Blueprints and experimental effects whose module, name, key or aliases contain every word of ``query``
    (prefix match, so 'boost' finds 'boosted'). Exact words score higher. Empty query lists everything.
    ``module`` restricts by module words, ``engineer`` to blueprints that engineer offers (adds engineer_grade).
    Returns [{kind, key, name, module, max_grade, score}] best first."""
    q = tokens(query)
    mod = tokens(module) if module else []
    exact_mod = (module or "").strip().lower() if (module or "").strip().lower() in _MODULE_NAMES else None
    eng = tokens(engineer) if engineer else []
    out = []
    for kind_, r, words in RECIPE_INDEX:
        if kind and kind_ != kind:
            continue
        mod_name = r.get("module") or ", ".join(r.get("modules") or [])
        fits = blueprint_modules(r) if kind_ == "blueprint" else ([r["module"]] if r.get("module") else r.get("modules") or [])
        matching = fits
        if exact_mod:                       # a known module name (the UI select) matches that module only
            matching = [m for m in fits if m.lower() == exact_mod]
            if not matching:
                continue
        elif mod:
            matching = [m for m in fits if all(any(w.startswith(t) for w in tokens(m)) for t in mod)]
            if not matching:
                continue
        if kind_ == "blueprint":
            mod_name = next((m for m in matching if all(t in q for t in tokens(m))), matching[0])
        eng_grade = None
        if eng:
            if kind_ != "blueprint":
                continue
            for name, g in r["engineers"].items():
                nwords = _WORDS.findall(name.lower())
                if all(any(w.startswith(t) for w in nwords) for t in eng):
                    eng_grade = max(eng_grade or 0, g)
            if not eng_grade:
                continue
        score, ok = 0, True
        for t in q:
            if t in words:
                score += 2
            elif any(w.startswith(t) for w in words):
                score += 1
            else:
                ok = False
                break
        if not ok:
            continue
        hit = {"kind": kind_, "key": r["key"], "name": r["name"], "module": mod_name, "max_grade": r.get("max_grade"),
               "score": score, "_n": len(words)}
        if eng_grade:
            hit["engineer_grade"] = eng_grade
        if kind_ == "unlock":
            hit["broker"] = r["broker"]
        out.append(hit)
    out.sort(key=lambda x: (-x["score"], x["kind"] != "blueprint", x["kind"] == "unlock", x["_n"], x["module"], x["name"]))
    for x in out:
        x.pop("_n")
    return out[:limit] if limit else out


def resolve_recipe(query, kind=None, module=None):
    """One recipe for a free-text query or an exact key. Returns {"match": hit} when there is a clear winner,
    else {"candidates": [hits...]} (empty when nothing matched)."""
    query = (query or "").strip()
    if query in BLUEPRINT_BY_KEY or query in EXPERIMENTAL_BY_KEY or query in UNLOCK_BY_KEY:
        hits = [h for h in find_recipes("", kind=kind, module=module, limit=0) if h["key"] == query]
        return {"match": hits[0]} if hits else {"candidates": []}
    hits = find_recipes(query, kind=kind, module=module, limit=0)
    if len(hits) == 1 or (len(hits) > 1 and hits[0]["score"] > hits[1]["score"]):
        return {"match": hits[0]}
    return {"candidates": hits[:12]}


def recipe_cost(key, grade=None, from_grade=0, rolls=None, qty=1):
    """Materials {key: count} to take a blueprint from ``from_grade`` (0 = unengineered) to ``grade``, applying
    ROLLS_PER_GRADE rolls at each grade unless ``rolls`` ({grade: n}) overrides it; or ``qty`` applications of an
    experimental effect or technology broker unlock (commodities not included). Raises KeyError for an unknown key."""
    qty = int(qty or 1)
    b = BLUEPRINT_BY_KEY.get(key)
    need = {}
    if b:
        grade = int(grade or b["max_grade"])
        for g in range(int(from_grade or 0) + 1, grade + 1):
            n = (rolls or {}).get(g, (rolls or {}).get(str(g)))
            n = ROLLS_PER_GRADE.get(g, 1) if n is None else int(n)
            for k, c in (b["grades"].get(str(g)) or {}).items():
                need[k] = need.get(k, 0) + c * n * qty
        return need
    e = EXPERIMENTAL_BY_KEY.get(key) or UNLOCK_BY_KEY.get(key)
    if e:
        return {k: c * qty for k, c in e["ingredients"].items()}
    raise KeyError(key)


def trade_ratio(give_key, get_key):
    """(give, get) units at a material trader for one trade of ``give_key`` into ``get_key``, reduced to lowest terms,
    or None when the pair cannot be traded (different type, no trader family, or the same material).
    Same family: 1 -> 3 per grade down, 6 -> 1 per grade up. A different family costs a further factor of 6."""
    a, b = MATERIAL_BY_KEY.get(give_key), MATERIAL_BY_KEY.get(get_key)
    if not a or not b or give_key == get_key or a["category"] != b["category"] or not a.get("family") or not b.get("family"):
        return None
    d = a["grade"] - b["grade"]
    if d > 0:
        give, get = 1, TRADE["same_family_down"] ** d
    elif d < 0:
        give, get = TRADE["same_family_up"] ** (-d), 1
    else:
        give, get = 1, 1
    if a["family"] != b["family"]:
        give *= TRADE["cross_family_factor"]
    g = _math.gcd(give, get)
    return give // g, get // g
