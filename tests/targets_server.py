"""Real CLI with a synthetic Spansh boundary, or explicitly enabled live queries."""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from elitelab.core import config
from elitelab.core.services import Services
from elitelab.__main__ import main

config.OFFLINE = False
fixture = json.loads((ROOT / "tests/fixtures/targets/stations.json").read_text())
original = Services.fetch_json


def fetch(self, url, body=None, **kwargs):
    if url != "https://www.spansh.co.uk/api/stations/search":
        raise RuntimeError("Target fixture blocks unrelated community requests")
    ref = (body or {}).get("reference_system")
    if ref == "Unavailable test":
        raise RuntimeError("Synthetic private provider error")
    if ref == "Empty test":
        return {"count":0, "results":[]}
    if os.environ.get("ELITELAB_TARGETS_LIVE") == "1":
        return original(self, url, body, **kwargs)
    data = copy.deepcopy(fixture)
    for row in data["results"]:
        row["market_updated_at"] = (dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=2)).isoformat()
    return data


Services.fetch_json = fetch
raise SystemExit(main(["serve", "--no-browser"]))
