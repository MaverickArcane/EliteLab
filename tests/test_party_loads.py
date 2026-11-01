import copy
import unittest

from modules.party.loads import recommend


class LoadSuggestionsTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"commodity":"gold", "planned_quantity":19876}
        self.members = [{"id":"a", "cmdr":"Owner", "leader":True, "capacity":700, "cargo_count":0, "cargo":[]},
                        {"id":"b", "cmdr":"Crew", "capacity":400, "cargo_count":0, "cargo":[]}]

    def test_full_rounds_fit_different_ships_and_change_live(self):
        before = copy.deepcopy(self.plan)
        s = recommend(self.plan, None, self.members)
        self.assertEqual((s["round_capacity"], s["suggested_quantity"], s["full_rounds"], s["tail"]), (1100,19800,18,76))
        self.assertEqual([m["next_buy"] for m in s["members"]], [700,400])
        self.members[1]["capacity"] = 500
        s = recommend(self.plan, None, self.members)
        self.assertEqual((s["round_capacity"],s["suggested_quantity"]), (1200,19200))
        self.assertEqual(self.plan, before)

    def test_cargo_in_transit_and_other_goods_reduce_purchases(self):
        self.members[0].update(cargo_count=300,cargo=[{"key":"gold","count":200},{"key":"silver","count":100}])
        op={"stage":"loading", "remaining_load":1000}
        s=recommend(self.plan,op,self.members)
        self.assertEqual((s["round_capacity"],s["aboard"],s["next_buy"]), (1000,200,800))
        self.assertEqual([m["next_buy"] for m in s["members"]], [400,400])
        op["remaining_load"]=250
        s=recommend(self.plan,op,self.members)
        self.assertEqual([m["next_buy"] for m in s["members"]], [25,25])
        op["remaining_load"]=100
        self.assertEqual(recommend(self.plan,op,self.members)["next_buy"],0)

    def test_partial_round_has_no_overallocation(self):
        for remaining in (0,1,23,500,1099,1100,1101):
            s=recommend(self.plan,{"stage":"loading","remaining_load":remaining},self.members)
            self.assertEqual(sum(m["next_buy"] for m in s["members"]),min(remaining,1100))
            self.assertTrue(all(0<=m["next_buy"]<=m["free"] for m in s["members"]))

    def test_away_stale_unknown_or_offline_members_do_not_inflate_space(self):
        for change in ({"stale":True},{"activity":"away"},{"capacity":None},{"cargo_count":None},{"telemetry":{"game_running":False}},{"telemetry":{"vehicle":"srv"}}):
            members=copy.deepcopy(self.members);members[1].update(change)
            s=recommend(self.plan,None,members)
            self.assertEqual(s["round_capacity"],700)
            self.assertEqual(len(s["excluded"]),1)

    def test_unloading_pickups_use_remaining_sales_and_pause_disables_them(self):
        op={"stage":"unloading","remaining_unload":500,"remaining_load":0}
        s=recommend(self.plan,op,self.members)
        self.assertEqual(s["next_buy"],500)
        op["paused"]=True
        self.assertEqual(recommend(self.plan,op,self.members)["next_buy"],0)
        for stage in ("transit","complete","cancelled"):
            op.update(stage=stage,paused=False)
            self.assertFalse(recommend(self.plan,op,self.members)["enabled"])
