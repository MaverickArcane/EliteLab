"""EliteLab test suite. Standard-library unittest only.

Runs the real core against a fixture journal folder, offline (no Spansh/EDSM calls).

    python -m unittest discover -s tests -v
"""
import json
import logging
import os
import sys
import tempfile
import unittest

logging.disable(logging.CRITICAL)   # the bus-isolation test deliberately makes a handler fail

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "journals")
sys.path.insert(0, ROOT)
os.environ["ELITELAB_JOURNAL_DIR"] = FIXTURES
os.environ["ELITELAB_OFFLINE"] = "1"
os.environ["ELITELAB_DATA_DIR"] = tempfile.mkdtemp(prefix="elitelab-test-")

from elitelab.core import Core, config, loader  # noqa: E402


def make_core():
    core = Core()
    loader.load_all(core)
    core.watcher.replay()
    return core


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = make_core()
        cls.tools = {name: r for name, r in cls.core.http.tools.items()}

    def call(self, tool, **q):
        return self.tools[tool].fn(q)

    # -- loader ---------------------------------------------------------------
    def test_modules_load_in_dependency_order(self):
        names = list(self.core.modules)
        self.assertIn("journal", names)
        self.assertLess(names.index("journal"), names.index("powerplay"))
        self.assertLess(names.index("powerplay"), names.index("targets"))
        self.assertLess(names.index("history"), names.index("map"))

    def test_missing_dependency_is_an_error(self):
        mods = loader.discover()
        mods["broken"] = loader.ModuleInfo("broken", "/nowhere", {"requires": ["does-not-exist"]})
        with self.assertRaises(RuntimeError):
            loader.resolve_order(mods)

    def test_schema_lists_every_tool_with_input_schema(self):
        schema = self.call("list_tools")
        names = {t["tool"] for t in schema["tools"]}
        for expected in ("get_commander_state", "get_powerplay_status", "get_rares_loop", "find_sell_targets",
                         "get_materials", "set_wishlist", "get_travel_history", "get_merits_summary", "find_combat_systems"):
            self.assertIn(expected, names)
        for t in schema["tools"]:
            self.assertEqual(t["input_schema"]["type"], "object")

    # -- journal --------------------------------------------------------------
    def test_commander_state_from_fixture(self):
        j = self.call("get_commander_state")
        self.assertEqual(j["cmdr"], "Testpilot")
        self.assertEqual(j["system"], "Zaonce")
        self.assertTrue(j["docked"])
        self.assertEqual(j["station"], "Ridley Scott")
        self.assertEqual(j["system_power"], "Edmund Mahon")
        self.assertEqual(j["credits"], 1000266000)          # Status.json balance wins over LoadGame
        self.assertEqual(j["game_version"], "4.4.1.1")

    def test_ship_name_learned_from_shipyard_events(self):
        j = self.call("get_commander_state")
        self.assertEqual(j["ship"], "Kestrel Mk II")         # loadout only says smallcombat01_nx
        self.assertEqual(j["ship_ident"], "TS-02K")
        self.assertAlmostEqual(j["jump_range"], 29.2)
        self.assertEqual(j["ship_info"]["rebuy"], 200000)

    def test_cargo_rares_tagged_including_market_prefixed_names(self):
        items = {i["key"]: i for i in self.call("get_commander_state")["cargo"]["items"]}
        self.assertTrue(items["leestianeviljuice"]["rare"])
        self.assertTrue(items["alieneggs"]["rare"])         # from Market.json "$alieneggs_name;"

    def test_market_rares_in_stock(self):
        m = self.call("get_commander_state")["market"]
        self.assertEqual(m["station"], "Ridley Scott")
        self.assertEqual([r["name"] for r in m["rares_in_stock"]], ["Leathery Eggs"])

    def test_carrier_summary(self):
        c = self.call("get_commander_state")["carrier"]
        self.assertEqual(c["callsign"], "TST-001")
        self.assertEqual(c["system"], "Leesti")
        self.assertEqual(c["free_space"], 19985)
        self.assertEqual(c["services"], ["Refuel"])          # BlackMarket not activated

    def test_feed_newest_first(self):
        feed = self.call("get_commander_state")["feed"]
        self.assertTrue(feed)
        texts = " | ".join(f["text"] for f in feed)
        self.assertIn("Jumped to Zaonce", texts)
        self.assertIn("Sold 28 t Leestian Evil Juice", texts)
        self.assertGreaterEqual(feed[0]["ts"], feed[-1]["ts"])

    def test_rare_tagging_does_not_depend_on_the_last_market(self):
        """Leathery Eggs must be rare even when the last-opened market did not list them (key is 'alieneggs')."""
        from elitelab.core.gamedata import is_rare
        self.assertTrue(is_rare("alieneggs")); self.assertTrue(is_rare("Leathery Eggs")); self.assertTrue(is_rare("$bluemilk_name;"))
        self.assertFalse(is_rare("leatheryeggs")); self.assertFalse(is_rare("gold"))

    def test_journal_no_longer_carries_materials(self):
        j = self.call("get_commander_state")
        self.assertNotIn("materials", j)
        self.assertEqual(self.call("get_materials")["totals"]["Encoded"], 8)

    def test_history_ignores_supercruise_startjump(self):
        hist = self.core.modules["history"].instance
        h = [m for m in self.core.modules.values() if m.name == "history"][0]
        before = self.core.store.get("history", "version")
        self.core.bus.emit("journal.StartJump", {"event": "StartJump", "JumpType": "Supercruise", "StarSystem": "Zaonce"})
        self.assertEqual(self.core.store.get("history", "version"), before)
        self.core.bus.emit("journal.StartJump", {"event": "StartJump", "JumpType": "Hyperspace", "StarSystem": "Lave", "StarClass": "G"})
        self.assertEqual(self.core.store.get("history", "version"), before + 1)

    def test_loop_survives_a_stale_selection(self):
        self.core.write_data({"selected": "does-not-exist"}, "loop.json")
        from elitelab.core import loader
        spec = [m for m in loader.discover().values() if m.name == "loop"][0]
        import importlib.util
        s = importlib.util.spec_from_file_location("elitelab_modules.loop_again", os.path.join(spec.path, "module.py"))
        mod = importlib.util.module_from_spec(s); s.loader.exec_module(mod)
        lp = mod.Loop(self.core)
        self.assertEqual(lp.selected, "lave")
        self.core.write_data({"selected": "lave"}, "loop.json")

    def test_recent_events_limit_is_clamped(self):
        self.assertEqual(len(self.call("get_recent_events", limit=-5)), 1)
        self.assertLessEqual(len(self.call("get_recent_events", limit=9999)), 200)

    def test_merits_zone_cleared_on_death(self):
        total = self.call("get_powerplay_status")["merits"]
        self.core.bus.emit("journal.SupercruiseDestinationDrop", {"event": "SupercruiseDestinationDrop", "Type": "$Warzone_Powerplay_Med:#index=4;", "Type_Localised": "Power Conflict Zone [Medium Intensity]"})
        self.core.bus.emit("journal.Died", {"event": "Died", "timestamp": "2026-10-22T11:00:00Z"})
        # a gain with no cause after dying must not be blamed on the zone; TotalMerits unchanged so other tests are unaffected
        self.core.bus.emit("journal.PowerplayMerits", {"event": "PowerplayMerits", "timestamp": "2026-10-22T11:00:05Z", "Power": "Edmund Mahon", "MeritsGained": 0, "TotalMerits": total})
        last = self.call("get_merits_summary")["recent"][0]
        self.assertEqual(last["activity"], "unattributed")

    # -- powerplay / merits -----------------------------------------------------
    def test_powerplay_status(self):
        p = self.call("get_powerplay_status")
        self.assertEqual(p["power"], "Edmund Mahon")
        self.assertEqual(p["merits"], 10192)
        self.assertEqual(p["rank"], 2)
        self.assertIn("cycle_end", p)

    def test_merit_attribution(self):
        m = self.call("get_merits_summary")
        by = m["by_activity"]
        self.assertEqual(by["rares"]["merits"], 420)
        self.assertEqual(by["objective bonus"]["merits"], 3600)
        self.assertEqual(by["combat zone"]["merits"], 172)
        self.assertEqual(m["unattributed"], 0)
        zone = next(g for g in m["recent"] if g["activity"] == "combat zone")
        self.assertIn("Krait Phantom", zone["detail"])

    # -- loop -------------------------------------------------------------------
    def test_loop_ticks_from_hold_and_sorts_done_last(self):
        lp = self.call("get_rares_loop")
        by = {s["system"]: s for s in lp["stations"]}
        self.assertTrue(by["Leesti"]["done"]); self.assertEqual(by["Leesti"]["tons"], 28)
        self.assertTrue(by["Zaonce"]["done"]); self.assertEqual(by["Zaonce"]["tons"], 3)   # alieneggs key
        self.assertFalse(by["Lave"]["done"])
        self.assertEqual(lp["done_count"], 2)
        self.assertEqual(lp["tons_total"], 31)
        self.assertFalse(lp["stations"][0]["done"])
        self.assertTrue(lp["stations"][-1]["done"])

    # -- materials ---------------------------------------------------------------
    def test_materials_inventory_and_wishlist(self):
        mats = {m["key"]: m for m in self.call("get_materials")["materials"]}
        self.assertEqual(mats["dataminedwake"]["count"], 8)   # 5 + 3 collected
        self.assertEqual(mats["dataminedwake"]["grade"], 5)
        self.assertEqual(mats["dataminedwake"]["cap"], 100)
        r = self.call("set_wishlist", items={"Datamined Wake Exceptions": 15, "arsenic": 10, "not a thing": 1}, mode="replace", label="test")
        self.assertEqual(r["unknown"], ["not a thing"])
        short = {w["key"]: w["short"] for w in r["wishlist"]}
        self.assertEqual(short["dataminedwake"], 7)
        self.assertEqual(short["arsenic"], 6)
        self.call("set_wishlist", items={}, mode="clear")
        self.assertEqual(self.call("get_wishlist")["wishlist"], [])

    def test_material_sources_resolve_fuzzy_names(self):
        s = self.call("material_sources", name="datamined wake")
        self.assertEqual(s["key"], "dataminedwake")
        self.assertIn("hint", s)

    # -- history -----------------------------------------------------------------
    def test_history_route_and_star_class(self):
        h = self.call("get_travel_history", days=0)
        names = [r["name"] for r in h["route"]]
        self.assertEqual(names, ["Leesti", "Zaonce"])
        by = {s["name"]: s for s in h["systems"]}
        self.assertEqual(by["Zaonce"]["star_class"], "K")    # from StartJump, not FSDJump
        self.assertEqual(h["jumps"], 1)

    # -- http helpers ---------------------------------------------------------------
    def test_recent_events_filter(self):
        evs = self.call("get_recent_events", limit=5, event="PowerplayMerits")
        self.assertTrue(evs)
        self.assertTrue(all(e["event"] == "PowerplayMerits" for e in evs))
        self.assertNotIn("_replay", evs[0])


class JournalDockingTests(unittest.TestCase):
    def test_location_undocked_clears_previous_station(self):
        core = make_core()
        core.bus.emit("journal.Docked", {
            "event": "Docked", "StarSystem": "Old system",
            "StationName": "Old station", "StationType": "Coriolis",
        })
        core.bus.emit("journal.Location", {
            "event": "Location", "StarSystem": "New system",
            "StarPos": [0, 0, 0], "Docked": False,
        })
        j = core.http.tools["get_commander_state"].fn({})
        self.assertEqual(j["system"], "New system")
        self.assertEqual((j["docked"], j["station"], j["station_type"]), (False, None, None))

    def test_location_docked_sets_station(self):
        core = make_core()
        core.bus.emit("journal.Undocked", {"event": "Undocked"})
        core.bus.emit("journal.Location", {
            "event": "Location", "StarSystem": "New system",
            "StarPos": [0, 0, 0], "Docked": True,
            "StationName": "New station", "StationType": "Orbis",
        })
        j = core.http.tools["get_commander_state"].fn({})
        self.assertEqual(j["system"], "New system")
        self.assertEqual((j["docked"], j["station"], j["station_type"]), (True, "New station", "Orbis"))

    def test_jumps_clear_previous_station(self):
        for event in ("FSDJump", "CarrierJump"):
            with self.subTest(event=event):
                core = make_core()
                core.bus.emit("journal.Docked", {
                    "event": "Docked", "StarSystem": "Old system",
                    "StationName": "Old station", "StationType": "Coriolis",
                })
                core.bus.emit("journal." + event, {
                    "event": event, "StarSystem": "New system", "StarPos": [0, 0, 0],
                })
                j = core.http.tools["get_commander_state"].fn({})
                self.assertEqual(j["system"], "New system")
                self.assertEqual((j["docked"], j["station"], j["station_type"]), (False, None, None))


class StoreTests(unittest.TestCase):
    def test_store_change_detection_and_subscribers(self):
        from elitelab.core.bus import EventBus
        from elitelab.core.store import Store
        bus = EventBus(); store = Store(bus); seen = []
        store.subscribe(lambda ns, key, value, ver: seen.append((ns, key)))
        bus.on("state.x.*", lambda name, payload: seen.append(("bus", name)))
        self.assertTrue(store.set("x", "a", 1))
        self.assertFalse(store.set("x", "a", 1))        # unchanged: no notification
        self.assertTrue(store.set("x", "a", 2))
        self.assertEqual(seen.count(("x", "a")), 2)
        self.assertEqual(seen.count(("bus", "state.x.a")), 2)
        self.assertEqual(store.get("x", "a"), 2)
        self.assertEqual(store.snapshot()["x"], {"a": 2})


class BusTests(unittest.TestCase):
    def test_wildcards_and_isolation(self):
        from elitelab.core.bus import EventBus
        bus = EventBus(); hits = []
        bus.on("journal.*", lambda n, p: hits.append(n))
        bus.on("journal.FSDJump", lambda n, p: (_ for _ in ()).throw(RuntimeError("boom")))
        bus.on("*", lambda n, p: hits.append("all"))
        bus.emit("journal.FSDJump", {})
        bus.emit("other", {})
        self.assertEqual(hits, ["journal.FSDJump", "all", "all"])   # the failing handler did not stop the others


if __name__ == "__main__":
    unittest.main()
