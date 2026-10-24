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


def _build_index():
    out = []
    for b in BLUEPRINTS:
        words = set(_WORDS.findall(b["module"].lower()) + _WORDS.findall(b["name"].lower()) + _key_words(b["key"]))
        for a in b["aliases"]:
            words |= set(_WORDS.findall(a.lower()))
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


RECIPE_MODULES = sorted({b["module"] for b in BLUEPRINTS} | {m for e in EXPERIMENTALS for m in e["modules"]} | {u["module"] for u in UNLOCKS})
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
        if exact_mod:                       # a known module name (the UI select) matches that module only
            if exact_mod not in [m.lower() for m in ([r["module"]] if r.get("module") else r.get("modules") or [])]:
                continue
        elif mod:
            mwords = set(_WORDS.findall(mod_name.lower()))
            if not all(any(w.startswith(t) for w in mwords) for t in mod):
                continue
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
        hits = [h for h in find_recipes("", limit=0) if h["key"] == query]
        return {"match": hits[0]}
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
