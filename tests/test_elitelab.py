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


class EngineeringTests(unittest.TestCase):
    """Recipes, the engineering wishlist and the trade planner against the fixture inventory
    (carbon 120, arsenic 4, chemical processors 29, datamined wake 8)."""
    @classmethod
    def setUpClass(cls):
        cls.core = make_core()
        cls.tools = cls.core.http.tools

    def call(self, tool, **q):
        return self.tools[tool].fn(q)

    def test_recipe_search_and_cost(self):
        hits = self.call("list_recipes", query="fsd boost")["results"]
        self.assertEqual(hits[0]["key"], "FSD_LongRange")                  # the Guardian FSD Booster unlock ranks below it
        self.assertEqual(self.call("list_recipes", query="guardian fsd booster", kind="unlock")["results"][0]["key"], "unlock_guardian_fsd_booster")
        u = self.call("get_recipe", key="unlock_guardian_fsd_booster")
        self.assertEqual(u["commodities"], {"HN Shock Mount": 8})
        self.assertEqual({m["key"]: m["count"] for m in u["materials"]}["guardian_moduleblueprint"], 1)
        r = self.call("get_recipe", key="fsd increased range", grade=5)
        g5 = {m["key"]: m["count"] for m in r["grades"]["5"]}
        self.assertEqual(g5, {"arsenic": 1, "chemicalmanipulators": 1, "dataminedwake": 1})
        total = {m["key"]: m["count"] for m in r["total"]["materials"]}
        self.assertEqual(total["dataminedwake"], 5)              # 5 rolls at G5
        self.assertEqual(total["chemicalprocessors"], 5)         # 2 rolls at G2 + 3 at G3
        self.assertEqual(r["engineers"]["Felicity Farseer"], 5)
        self.assertIn("candidates", self.call("get_recipe", key="shield"))   # ambiguous: no guess
        self.assertEqual(self.call("get_recipe", key="mass manager")["kind"], "experimental")
        by_eng = self.call("list_recipes", module="frame shift drive", engineer="farseer")["results"]
        self.assertEqual({h["key"]: h["engineer_grade"] for h in by_eng if h["key"] == "FSD_LongRange"}, {"FSD_LongRange": 5})
        self.assertTrue(all(h["kind"] == "blueprint" for h in by_eng))
        self.assertEqual({h["module"] for h in by_eng}, {"Frame shift drive"})       # exact module name excludes the interdictor
        self.assertIn("Frame shift drive interdictor", {h["module"] for h in self.call("list_recipes", module="frame shift")["results"]})

    def test_trade_ratios(self):
        from elitelab.core.gamedata import trade_ratio
        self.assertEqual(trade_ratio("vanadium", "carbon"), (1, 3))      # same family, one grade down
        self.assertEqual(trade_ratio("carbon", "vanadium"), (6, 1))      # same family, one grade up
        self.assertEqual(trade_ratio("iron", "vanadium"), (36, 1))       # other family: 6x more
        self.assertEqual(trade_ratio("tin", "vanadium"), (2, 1))         # other family, one grade down: 6 -> 3
        self.assertEqual(trade_ratio("carbon", "iron"), (6, 1))          # same grade, other family
        self.assertIsNone(trade_ratio("carbon", "gridresistors"))         # raw -> manufactured: no trader does that

    def test_wishlist_tracks_inventory_and_plans_trades(self):
        a = self.call("wishlist_add", item="2x g5 fsd boost")
        self.assertEqual(a["status"], "added")
        e = a["entry"]
        self.assertEqual((e["kind"], e["key"], e["grade"], e["qty"]), ("blueprint", "FSD_LongRange", 5, 2))
        needs = {n["key"]: n for n in a["needs"]}
        self.assertEqual((needs["dataminedwake"]["need"], needs["dataminedwake"]["have"], needs["dataminedwake"]["short"]), (10, 8, 2))
        self.assertEqual(needs["chemicalprocessors"]["short"], 0)
        self.assertEqual(self.call("wishlist_add", item="shield")["status"], "ambiguous")
        m = self.call("wishlist_add", item="50 vanadium")["entry"]
        self.assertEqual((m["kind"], m["key"], m["qty"]), ("material", "vanadium", 50))
        w = self.call("get_engineering_wishlist")
        self.assertEqual(w["summary"]["entries"], 2)
        trades = w["trades"]["trades"]
        van = next(t for t in trades if t["get"]["key"] == "vanadium")
        self.assertEqual((van["give"]["key"], van["give"]["qty"], van["get"]["qty"], van["ratio"]), ("carbon", 120, 20, "6:1"))
        self.assertFalse(any(t["get"]["key"] == "arsenic" for t in trades))   # the 6:1 trade used the carbon before the 36:1 one could
        self.assertIn("vanadium", [u["key"] for u in w["trades"]["unresolved"]])
        # live: collecting materials changes the shortfall without touching the list
        self.core.bus.emit("journal.MaterialCollected", {"event": "MaterialCollected", "Category": "Encoded", "Name": "dataminedwake", "Count": 2})
        row = next(r for r in self.core.store.get("wishlist", "needs") if r["key"] == "dataminedwake")
        self.assertEqual(row["short"], 0)
        # farm sites: by material, and only those covering a current shortfall (vanadium has no site, datamined wake does)
        tell = self.call("find_farm_sites", material="tellurium")["sites"]
        self.assertEqual([s["system"] for s in tell], ["HIP 36601"])
        self.assertEqual(tell[0]["body"], "C 3 b")
        self.assertIsNone(tell[0]["dist"])                                  # offline: no EDSM coordinates
        cover = self.call("find_farm_sites", for_wishlist=True)["sites"]
        self.assertTrue(cover and all(s["covers"] for s in cover))
        self.assertTrue(any("Atypical Disrupted Wake Echoes" in s["covers"] for s in cover))
        # grade ranges and tech broker unlocks
        rng = self.call("wishlist_add", item="dirty drives 2-5 x2")["entry"]
        self.assertEqual((rng["from_grade"], rng["grade"], rng["qty"]), (2, 5, 2))
        self.assertEqual(self.call("wishlist_add", item="unlock_guardian_fsd_booster")["entry"]["commodities"], {"HN Shock Mount": 8})
        self.assertNotIn("inventory", self.core.store.get("materials"))                 # not on SSE; modules use the tool
        self.assertEqual(self.call("get_material_inventory")["inventory"]["carbon"], 120)
        gp = self.call("wishlist_add", item="guardian_powercell", kind="material", qty=5)["entry"]     # exact key with an underscore
        self.assertEqual((gp["kind"], gp["key"], gp["qty"]), ("material", "guardian_powercell", 5))
        self.assertEqual(self.call("wishlist_add", item="FSD_LongRange", rolls="[1,2,3,4,6]")["entry"]["rolls"]["5"], 6)
        cs = self.call("wishlist_add", item="special_corrosive_shell", kind="experimental", module="Multi-cannon")["entry"]
        self.assertEqual((cs["module"], cs["name"]), ("Multi-cannon", "Corrosive shell"))     # the picked module, not the whole list
        self.assertIn("Fragment cannon", cs["fits"])
        self.call("wishlist_remove", id=cs["id"])
        self.call("wishlist_remove", id=gp["id"])
        self.call("wishlist_remove", id=self.core.store.get("wishlist", "entries")[-1]["id"])
        self.assertEqual(self.call("wishlist_remove", all=True)["removed"], 4)
        self.assertEqual(self.core.store.get("wishlist", "summary")["entries"], 0)

    def test_build_pinned_and_compared(self):
        url = ("https://edsy.org/#/L=JT00000H4C0S40,KLz29KLz29KLz29HNlI97H_W0HNlI97K_W0,DBwJ95L_W0DBwJ95L_W0DBwJ99L_W0DBwJ99L_W0,"
               "9p3H05I_W0A8cH93K_W0AOHG95I_W0AcJK95J_W0Ani19B76G93L_W0BIWG95G_W0Bb619,23u19,7T4H99L_W015OH95I_W013qH95I_W012GH95I_W0"
               "12GH95I_W012GH95I_W068qK92m_W0,Proper_0Bo_0I_0Tell_0Thee,ida_D07")
        r = self.call("pin_build", url=url)
        self.assertEqual((r["pinned"]["name"], r["pinned"]["ship"]), ("Proper Bo I Tell Thee", "Kestrel Mk II"))
        self.assertTrue(r["progress"]["same_ship"])                               # the fixture ends in a Kestrel with no modules
        self.assertEqual(r["progress"]["totals"]["to_buy"], 25)
        self.core.bus.emit("journal.Loadout", {"event": "Loadout", "Ship": "smallcombat01_nx", "ShipID": 50, "Modules": [
            {"Slot": "FrameShiftDrive", "Item": "Int_Hyperdrive_Overcharge_Size4_Class5", "On": True, "Engineering": {"BlueprintName": "FSD_LongRange", "Level": 3}},
            {"Slot": "TinyHardpoint1", "Item": "hpt_shieldbooster_size0_class5", "On": True, "Engineering": {"BlueprintName": "ShieldBooster_HeavyDuty", "Level": 5, "ExperimentalEffect": "special_shieldbooster_chunky"}}]})
        P = self.core.store.get("build", "progress")
        rows = {x["slot"]: x for x in P["slots"]}
        self.assertEqual(rows["FrameShiftDrive"]["status"], "engineer")
        self.assertEqual(rows["FrameShiftDrive"]["todo"], ["Increased Range G3 to G5", "apply Mass Manager"])
        self.assertEqual({m["key"]: m["count"] for m in rows["FrameShiftDrive"]["materials"]}["dataminedwake"], 5)   # only the G5 rolls
        self.assertEqual(rows["TinyHardpoint1"]["status"], "ok")                 # matched by item within the utility group
        self.assertEqual(P["totals"]["ok"], 1)
        w = self.call("build_to_wishlist")
        self.assertEqual((w["entry"]["kind"], w["entry"]["name"]), ("build", "Proper Bo I Tell Thee"))
        self.assertGreater(w["needs"], 10)
        self.call("build_to_wishlist")                                             # idempotent: still one build entry
        self.assertEqual(sum(1 for e in self.core.store.get("wishlist", "entries") if e["kind"] == "build"), 1)
        need_before = next(e for e in self.core.store.get("wishlist", "entries") if e["kind"] == "build")["units"]
        self.core.bus.emit("journal.Loadout", {"event": "Loadout", "Ship": "smallcombat01_nx", "ShipID": 50, "Modules": [
            {"Slot": "FrameShiftDrive", "Item": "Int_Hyperdrive_Overcharge_Size4_Class5", "On": True, "Engineering": {"BlueprintName": "FSD_LongRange", "Level": 5, "ExperimentalEffect": "special_fsd_heavy"}},
            {"Slot": "TinyHardpoint1", "Item": "hpt_shieldbooster_size0_class5", "On": True, "Engineering": {"BlueprintName": "ShieldBooster_HeavyDuty", "Level": 5, "ExperimentalEffect": "special_shieldbooster_chunky"}}]})
        need_after = next(e for e in self.core.store.get("wishlist", "entries") if e["kind"] == "build")["units"]
        self.assertLess(need_after, need_before)                                  # the entry follows the build's progress
        self.assertEqual(self.call("wishlist_remove", all=True)["removed"], 1)
        self.assertIsNone(self.call("unpin_build")["pinned"])

    def test_jump_range_laden_and_now(self):
        from elitelab.core.edsy import jump_range
        # a real Kestrel: 4A SCO FSD engineered to 943.02 optimal mass, 349.8 t unladen; the journal said MaxJumpRange 29.27
        self.assertAlmostEqual(jump_range("int_hyperdrive_overcharge_size4_class5", 943.019958, 349.8 + 3.2), 29.27, delta=0.02)
        self.assertEqual(jump_range("int_guardianfsdbooster_size5", 1, 1), None)                   # not an FSD
        self.assertAlmostEqual(jump_range("int_hyperdrive_size5_class5", 1050, 463, "int_guardianfsdbooster_size5") -
                               jump_range("int_hyperdrive_size5_class5", 1050, 463), 10.5, places=2)   # booster bonus
        self.core.bus.emit("journal.Loadout", {"event": "Loadout", "Ship": "smallcombat01_nx", "ShipID": 50, "UnladenMass": 349.8, "CargoCapacity": 8,
                                               "MaxJumpRange": 29.27, "FuelCapacity": {"Main": 16.0, "Reserve": 0.61}, "Modules": [
            {"Slot": "FrameShiftDrive", "Item": "int_hyperdrive_overcharge_size4_class5", "On": True,
             "Engineering": {"BlueprintName": "FSD_LongRange", "Level": 5, "Modifiers": [{"Label": "FSDOptimalMass", "Value": 943.019958, "OriginalValue": 585.0}]}}]})
        self.core.bus.emit("journal.file.Status", {"event": "Status", "Flags": 0, "Fuel": {"FuelMain": 14.72, "FuelReservoir": 0.45}, "Cargo": 0.0})
        j = self.call("get_commander_state")
        self.assertAlmostEqual(j["jump_range_laden"], jump_range("int_hyperdrive_overcharge_size4_class5", 943.019958, 349.8 + 16 + 8), places=2)
        self.assertAlmostEqual(j["jump_range_now"], jump_range("int_hyperdrive_overcharge_size4_class5", 943.019958, 349.8 + 14.72), places=2)
        self.assertGreater(j["jump_range_now"], j["jump_range_laden"])
        # with less than one jump of fuel in the tank the range shrinks (the FSD cannot burn 3.2 t it does not have)
        self.core.bus.emit("journal.file.Status", {"event": "Status", "Flags": 0, "Fuel": {"FuelMain": 1.0, "FuelReservoir": 0.45}, "Cargo": 0.0})
        low = self.call("get_commander_state")["jump_range_now"]
        self.assertLess(low, 20)
        self.assertAlmostEqual(low, jump_range("int_hyperdrive_overcharge_size4_class5", 943.019958, 349.8 + 1.0, fuel=1.0), places=2)

    def test_merit_rate_ignores_breaks(self):
        import time as _time
        now = int(_time.time())
        iso = lambda t: _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime(t))
        self.core.bus.emit("journal.LoadGame", {"event": "LoadGame", "timestamp": iso(now - 4 * 3600 - 600), "Commander": "Testpilot"})
        for t, n in ((now - 4 * 3600, 100), (now - 4 * 3600 + 300, 100), (now - 60, 100)):       # two gains 5 min apart, a 4 h break, one more
            self.core.bus.emit("journal.PowerplayMerits", {"event": "PowerplayMerits", "timestamp": iso(t), "Power": "Edmund Mahon", "MeritsGained": n, "TotalMerits": n})
        m = self.call("get_merits_summary")
        self.assertEqual(m["session_merits"], 300)
        self.assertEqual(m["breaks"], 1)
        self.assertLess(m["per_hour"], 100)                     # elapsed-time rate is dragged down by the break
        self.assertAlmostEqual(m["active_hours"], (300 + 900 + 60) / 3600, places=2)   # 5 min, a capped 15 min, 1 min since the last gain
        self.assertGreater(m["per_hour_active"], 800)

    def test_rares_table_is_the_fdev_list(self):
        from elitelab.core.gamedata import RARES, RARE_MARKETS, is_rare
        self.assertEqual(len(RARES), 142)
        self.assertEqual(RARES["alieneggs"], "Leathery Eggs")
        self.assertEqual(RARE_MARKETS["leestianeviljuice"], 128639992)
        self.assertTrue(is_rare("Lucan Onionhead") and not is_rare("lucanonionhead"))   # the old community slug was wrong

    def test_coriolis_link_and_slef_pin(self):
        import base64, gzip, struct
        from elitelab.core import coriolis
        # A Kestrel with only a 4A SCO FSD (standard slot 3 -> modification slot 3) engineered Increased Range G5 + Mass Manager
        fsd_id = next(i for i, m in coriolis.STANDARD["fsd"].items() if m["symbol"].lower() == "int_hyperdrive_overcharge_size4_class5")
        bp_id = next(int(i) for i, b in coriolis.BLUEPRINTS.items() if b["fdname"] == "FSD_LongRange")
        sp_id = next(int(i) for i, s in coriolis.SPECIALS.items() if s["edname"] == "special_fsd_heavy")
        ship = coriolis.SHIPS["kestrel"]
        code = "A0" + "--" + fsd_id + "----" + "-" * len(ship["slots"]["hardpoints"]) + "-" * len(ship["slots"]["internal"])
        blob = struct.pack("<bbibibi b b", 3, -2, bp_id, -3, 5, -4, sp_id, -1, -1)
        mods = base64.b64encode(gzip.compress(blob)).decode().replace("+", "-").replace("/", "_")
        url = f"https://coriolis.io/outfit/kestrel?code={code}..." + mods + "&bn=Test%20Kestrel"
        r = self.call("pin_build", url=url)
        self.assertEqual((r["pinned"]["source"], r["pinned"]["name"], r["pinned"]["ship"]), ("coriolis", "Test Kestrel", "Kestrel Mk II"))
        fsd = next(s for s in r["progress"]["slots"] if s["slot"] == "FrameShiftDrive")
        self.assertEqual((fsd["item"], fsd["blueprint"], fsd["grade"], fsd["experimental"]), ("int_hyperdrive_overcharge_size4_class5", "Increased range", 5, "Mass Manager"))
        self.assertEqual(r["progress"]["totals"]["slots"], 2)                       # bulkheads + the FSD
        # SLEF (what EDSY and Coriolis export): a Loadout event wrapped in [{header, data}]
        slef = json.dumps([{"header": {"appName": "EDSY"}, "data": {"Ship": "smallcombat01_nx", "ShipName": "Slef Kestrel", "Modules": [
            {"Slot": "PowerPlant", "Item": "Int_PowerPlant_Size5_Class5", "Engineering": {"BlueprintName": "PowerPlant_Armoured", "Level": 4, "ExperimentalEffect": "special_powerplant_cooled"}}]}}])
        r = self.call("pin_build", url=slef)
        self.assertEqual((r["pinned"]["source"], r["pinned"]["name"]), ("slef", "Slef Kestrel"))
        pp = r["progress"]["slots"][0]
        self.assertEqual((pp["target"], pp["blueprint"], pp["grade"], pp["experimental"]), ("5A Power Plant", "Armoured", 4, "Thermal Spread"))
        self.call("unpin_build")
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
