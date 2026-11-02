"""Execute planner output against a copy of inventory, checking every exchange."""
import copy
import random
import unittest
from unittest.mock import patch

from elitelab.core import gamedata as gd
from modules.wishlist.module import Wishlist
from modules.wishlist import trading


COMPOSITES = "fedproprietarycomposites"
ALLOYS = "protoradiolicalloys"
MANIPULATORS = "chemicalmanipulators"
ISOLATORS = "pharmaceuticalisolators"


class MaterialTradeTests(unittest.TestCase):
    def plan(self, inv, needs, reserve=0):
        rows = [Wishlist.material_row(k, n, inv.get(k, 0)) for k, n in needs.items()]
        before = copy.deepcopy((rows, inv))
        result = Wishlist.plan_trades(rows, inv, reserve)
        self.assertEqual((rows, inv), before, "Planning mutated live inventory or needs")
        stock, edges = dict(inv), {}
        for step in result["trades"]:
            donor, target = step["give"]["key"], step["get"]["key"]
            give, get = gd.trade_ratio(donor, target)
            paid, received = step["give"]["qty"], step["get"]["qty"]
            self.assertGreater(paid, 0)
            self.assertEqual(paid % give, 0)
            self.assertEqual(received, paid // give * get)
            self.assertEqual(step["ratio"], f"{give}:{get}")
            stock[donor] = stock.get(donor, 0) - paid
            stock[target] = stock.get(target, 0) + received
            self.assertGreaterEqual(stock[donor], needs.get(donor, 0) + max(0, reserve), step)
            self.assertLessEqual(stock[target], gd.MATERIAL_CAPS[gd.MATERIAL_BY_KEY[target]["grade"]], step)
            self.assertEqual(gd.MATERIAL_BY_KEY[donor]["category"], gd.MATERIAL_BY_KEY[target]["category"])
            edges.setdefault(donor, set()).add(target)
        for origin in edges:
            pending, visited = list(edges[origin]), set()
            while pending:
                key = pending.pop()
                self.assertNotEqual(key, origin, "Exchange graph contains a cycle")
                if key not in visited:
                    visited.add(key)
                    pending.extend(edges.get(key, ()))
        unresolved = {k: max(0, n - stock.get(k, 0)) for k, n in needs.items() if n > stock.get(k, 0)}
        self.assertEqual({r["key"]: r["short"] for r in result["unresolved"]}, unresolved)
        original_short = sum(max(0, n - inv.get(k, 0)) for k, n in needs.items())
        self.assertEqual(result["covered"], original_short - sum(unresolved.values()))
        return result, stock

    def example(self, reserve=0, manipulator_need=14):
        return ({COMPOSITES: 66 + reserve, ALLOYS: 4 + reserve, MANIPULATORS: manipulator_need + reserve},
                {COMPOSITES: 38, MANIPULATORS: manipulator_need, ISOLATORS: 5})

    def test_issue_57_combines_donors_before_spending_the_intermediate(self):
        inv, needs = self.example()
        plan, stock = self.plan(inv, needs)
        self.assertEqual(plan["covered"], 1)
        self.assertEqual(stock, {COMPOSITES: 42, ALLOYS: 0, MANIPULATORS: 14, ISOLATORS: 1})
        self.assertEqual(len(plan["trades"]), 3)
        self.assertEqual([t["get"]["key"] for t in plan["trades"]], [MANIPULATORS, MANIPULATORS, ISOLATORS])
        self.assertEqual(plan["unresolved"][0]["short"], 4)
        self.assertFalse(plan["search_limited"])

    def test_nonzero_reserve_protects_donors_and_intermediate(self):
        inv, needs = self.example(reserve=2)
        plan, stock = self.plan(inv, needs, reserve=2)
        self.assertEqual(plan["covered"], 1)
        self.assertEqual(stock[ALLOYS], 2)
        self.assertEqual(stock[MANIPULATORS], 16)

    def test_intermediate_needs_room_for_a_whole_exchange(self):
        # Isolate this route so an alternative intermediate cannot hide a cap violation.
        catalog = {k: gd.MATERIAL_BY_KEY[k] for k in (COMPOSITES, ALLOYS, MANIPULATORS, ISOLATORS)}
        with patch.dict(gd.MATERIAL_BY_KEY, catalog, clear=True):
            for need, covered in ((144, 1), (148, 0)):
                with self.subTest(need=need):
                    inv, needs = self.example(manipulator_need=need)
                    plan, _ = self.plan(inv, needs)
                    self.assertEqual(plan["covered"], covered)
                    if not covered:
                        self.assertEqual(plan["trades"], [])

    def test_insufficient_combined_surplus_does_not_commit_partial_funding(self):
        inv, needs = self.example()
        inv[COMPOSITES] = 61
        plan, stock = self.plan(inv, needs)
        self.assertEqual(plan["trades"], [])
        self.assertEqual(stock, inv)

    def test_untradeable_and_other_categories_cannot_fund_a_chain(self):
        plan, _ = self.plan({"guardian_powercell": 100, "carbon": 300, "dataminedwake": 100},
                            {ISOLATORS: 5, "guardian_powercell": 105})
        self.assertEqual(plan["trades"], [])
        self.assertEqual(next(r for r in plan["unresolved"] if r["key"] == "guardian_powercell")["note"], "not tradeable")

    def test_coverage_excludes_overfill_and_intermediate_receipts(self):
        plan, stock = self.plan({"vanadium": 1}, {"carbon": 1})
        self.assertEqual(stock["carbon"], 3)
        self.assertEqual(plan["covered"], 1)
        self.assertEqual(plan["by_trader"]["Raw"]["get"], 3)

    def test_final_target_cap_leaves_unresolved_need(self):
        plan, stock = self.plan({MANIPULATORS: 150, ISOLATORS: 99}, {ISOLATORS: 101})
        self.assertEqual(stock[ISOLATORS], 100)
        self.assertEqual(plan["covered"], 1)
        self.assertEqual(plan["unresolved"][0]["short"], 1)

    def test_plan_is_independent_of_input_iteration_order(self):
        inv, needs = self.example()
        forward, _ = self.plan(inv, needs)
        backward, _ = self.plan(dict(reversed(list(inv.items()))), dict(reversed(list(needs.items()))))
        self.assertEqual(forward, backward)

    def test_exhausted_search_reports_limit_without_spending_speculatively(self):
        inv, needs = self.example()
        with patch.object(trading, "CHAIN_SEARCH_BUDGET", 1):
            plan, stock = self.plan(inv, needs)
        self.assertTrue(plan["search_limited"])
        self.assertIn("Search limit reached", plan["note"])
        self.assertEqual(stock, inv)

    def test_seeded_inventories_produce_executable_acyclic_plans(self):
        rng = random.Random(57)
        catalog = [m for m in gd.MATERIAL_BY_KEY.values() if m.get("family")]
        for case in range(35):
            with self.subTest(case=case):
                chosen = rng.sample(catalog, 20)
                inv = {m["key"]: rng.randrange(gd.MATERIAL_CAPS[m["grade"]] + 1) for m in chosen}
                needs = {m["key"]: rng.randrange(gd.MATERIAL_CAPS[m["grade"]] + 20) for m in rng.sample(catalog, 10)}
                self.plan(inv, needs, reserve=case % 4)
