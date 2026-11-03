"""Real CLI with a deterministic community-provider boundary for browser tests.

Set ELITELAB_MINING_LIVE=1 for explicitly requested live Spansh smoke checks.
Only the two mining search endpoints can make external requests in that mode.
"""
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
fixture = json.loads((ROOT / "tests/fixtures/mining/spansh.json").read_text())
original_fetch = Services.fetch_json


def fetch(self, url, body=None, **kwargs):
    if url == "https://www.spansh.co.uk/api/systems/search":
        if os.environ.get("ELITELAB_MINING_LIVE") == "1":
            return original_fetch(self, url, body, **kwargs)
        origin = fixture["bodies"]["results"][0]
        return {"results":[{"name":(body or {})["filters"]["name"]["value"],
                "controlling_power":"Edmund Mahon", "power_state":"Stronghold",
                **{axis:origin.get("system_"+axis) for axis in "xyz"}}]}
    if url == "https://www.spansh.co.uk/api/stations/field_values/market":
        if os.environ.get("ELITELAB_MINING_LIVE") == "1":
            return original_fetch(self, url, body, **kwargs)
        return {"min_max":{"Platinum":{}, "Painite":{}, "Low Temperature Diamonds":{}}}
    kind = next((k for k in fixture if url == f"https://www.spansh.co.uk/api/{k}/search"), None)
    if kind is None:
        raise RuntimeError("Browser fixture blocks unrelated community requests")
    if (body or {}).get("reference_system") == "Unavailable test":
        raise RuntimeError("Synthetic provider failure")
    if os.environ.get("ELITELAB_MINING_LIVE") == "1":
        return original_fetch(self, url, body, **kwargs)
    data = copy.deepcopy(fixture[kind])
    stamp = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
    for row in data["results"]:
        row["updated_at"] = row["market_updated_at"] = stamp
        for ring in row.get("rings", []):
            ring["signals_updated_at"] = stamp
    return data


Services.fetch_json = fetch
raise SystemExit(main(["serve", "--no-browser"]))
