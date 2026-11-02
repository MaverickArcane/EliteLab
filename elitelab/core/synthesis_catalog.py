"""Shared synthesis data; costs remain sourced in synthesis.json."""
import json
from pathlib import Path

CATALOG = json.loads(Path(__file__).with_name("synthesis.json").read_text(encoding="utf8"))
RECIPES = CATALOG["recipes"]
BY_KEY = {r["key"]: r for r in RECIPES}
