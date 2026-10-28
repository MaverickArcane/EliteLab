"""Live work follows available holds and physical cargo, not initial quotas."""
import copy
import unittest
from elitelab.core.hauling import build, view
from modules.party.loads import recommend
from modules.party.desk import project
from modules.trade.operations import operation_view


class LiveHaulingTests(unittest.TestCase):
    def setUp(self):
        self.plan={"commodity":"gold","source":"Buy / Sol","destination":"Sell / Lave","planned_quantity":1160}
        self.members=[{"id":"a","cmdr":"Owner","leader":True,"capacity":1136,"cargo_count":0,"cargo":[]},
                      {"id":"b","cmdr":"Skibothy","capacity":1200,"cargo_count":0,"cargo":[]}]
        self.op={"id":"job","stage":"loading","quantity":1160,"reports":{}}
        self.settings={"mode":"live","owner_hauls":True}

    def state(self, previous=None):
        op=operation_view(self.op)
        saved=build(self.plan,op,self.members,self.settings,previous)
        workload=view(saved,op,self.members,self.plan)
        return saved, {"plan":self.plan,"operation":op,"members":self.members,"workload":workload,
                       "load_suggestion":recommend(self.plan,op,self.members,workload=workload)}

    def test_final_1160_goes_to_the_1200_ship(self):
        saved, state=self.state()
        self.assertEqual([r["next_buy"] for r in state["load_suggestion"]["members"]],[0,1160])
        self.assertEqual(project(state,"b",self.members[1])["quantity"],1160)
        self.assertEqual(project(state,"a",self.members[0])["action"],"wait")
        self.assertEqual(state["workload"]["loading"]["order_remaining"],1160)

    def test_preview_can_use_observed_remaining_when_plan_quantity_is_automatic(self):
        self.plan["planned_quantity"]=0
        saved=build(self.plan,None,self.members,self.settings,fallback_quantity=1160)
        projected=view(saved,None,self.members,self.plan)
        self.assertEqual(projected["quantity"],1160)
        self.assertEqual(projected["loading"]["order_remaining"],1160)

    def test_split_only_when_remainder_needs_multiple_ships(self):
        self.op["quantity"]=1700
        _,state=self.state()
        self.assertEqual([r["next_buy"] for r in state["load_suggestion"]["members"]],[500,1200])
        self.assertEqual(state["load_suggestion"]["next_buy"],1700)

    def test_real_52_tonne_tail_is_identical_for_owner_and_member(self):
        self.op.update(quantity=19876,reports={"a":{"loading":10224},"b":{"loading":8464}})
        self.members[0].update(cargo_count=1136,cargo=[{"key":"gold","count":1136}])
        _,state=self.state()
        pickup=next(r for r in state["load_suggestion"]["members"] if r["id"]=="b")
        self.assertEqual((state["load_suggestion"]["remaining"],pickup["next_buy"]),(1188,52))
        self.assertEqual(project(state,"b",self.members[1])["quantity"],52)
        owner=project(state,"a",self.members[0])
        self.assertEqual((owner["action"],owner["quantity"]),("transfer_in",1136))
        self.assertEqual(state["workload"]["loading"]["order_remaining"],52)

    def test_delivery_before_cargo_snapshot_does_not_reserve_the_same_load_twice(self):
        self.op["quantity"]=1188
        self.members[0].update(cargo_count=1136,cargo=[{"key":"gold","count":1136}],cargo_at="old")
        saved,_=self.state()
        self.op["reports"]={"a":{"loading":1136}}
        saved,state=self.state(saved)
        self.assertEqual([r["next_buy"] for r in state["load_suggestion"]["members"]],[0,52])
        self.assertEqual(project(state,"b",self.members[1])["quantity"],52)
        # Repeated polls of the old cargo snapshot do not change that allocation.
        _,state=self.state(saved)
        self.assertEqual(project(state,"b",self.members[1])["quantity"],52)

    def test_faster_ship_keeps_working_beyond_initial_estimate(self):
        self.op["quantity"]=10000
        saved,state=self.state()
        initial=next(r for r in saved["members"] if r["id"]=="a")["loading_target"]
        self.op["reports"]={"a":{"loading":initial+100}}
        self.members[1].update(cargo_count=1200,cargo=[{"key":"gold","count":1200}])
        _,state=self.state(saved)
        self.assertGreater(project(state,"a",self.members[0])["quantity"],0)
        self.assertEqual(state["operation"]["loaded"],initial+100)

    def test_historical_corrections_do_not_release_physical_cargo(self):
        for phase in ("loading", "unloading"):
            with self.subTest(phase=phase):
                self.op.update(stage=phase, quantity=2200, reports={})
                self.members[0].update(capacity=1000,cargo_count=1000,cargo=[{"key":"gold","count":1000}])
                saved,_=self.state()
                self.op["reports"]={"a":{phase:1000,"reported":{phase:0},"adjustments":{phase:1000}}}
                saved,state=self.state(saved)
                self.assertEqual(project(state,"b",self.members[1])["quantity"],200)
                self.assertEqual(project(state,"a",self.members[0])["quantity"],1000)
                # Reducing the same accounting correction must not invent cargo.
                self.op["reports"]["a"].update({phase:500,"adjustments":{phase:500}})
                _,state=self.state(saved)
                self.assertEqual(project(state,"b",self.members[1])["quantity"],700)

    def test_legacy_snapshot_preserves_hold_until_new_physical_evidence(self):
        self.op["quantity"]=2200
        self.members[0].update(capacity=1000,cargo_count=1000,cargo=[{"key":"gold","count":1000}])
        saved,_=self.state()
        for row in saved["members"]:
            snapshot=row["cargo_snapshot"]
            snapshot["delivered"]=snapshot.pop("reported")
        self.op["reports"]={"a":{"loading":1000,"reported":{"loading":0},"adjustments":{"loading":1000}}}
        saved,state=self.state(saved)
        self.assertEqual(project(state,"b",self.members[1])["quantity"],200)
        self.members.pop(0)  # cargo is still reserved when the owner disconnects
        _,state=self.state(saved)
        self.assertEqual(state["workload"]["reserved"]["loading"],1000)

    def test_late_journal_or_manual_report_does_not_consume_a_newer_hold(self):
        self.op["quantity"]=2200
        self.members[0].update(capacity=1000,cargo_count=1000,cargo=[{"key":"gold","count":1000}],cargo_at="2026-10-20T12:00:00Z")
        saved,_=self.state()
        for kind,at in (("MarketSell","2026-10-20T11:00:00Z"),("manual","2026-10-20T13:00:00Z")):
            self.op["reports"]={"a":{"loading":1000,"reported":{"loading":1000},
                "delivery_evidence":{"loading":{"kind":kind,"at":at}}}}
            _,state=self.state(saved)
            self.assertEqual(project(state,"b",self.members[1])["quantity"],200)

    def test_heartbeat_combining_historical_and_new_delivery_consumes_only_proven_cargo(self):
        self.op["quantity"]=2200
        self.members[0].update(capacity=1000,cargo_count=1000,cargo=[{"key":"gold","count":1000}],cargo_at="2026-10-20T12:00:00Z")
        saved,_=self.state()
        self.op["reports"]={"a":{"loading":1200,"reported":{"loading":1200},
            "delivery_evidence":{"loading":{"kind":"MarketSell","at":"2026-10-20T13:00:00Z","tonnes":200}}}}
        _,state=self.state(saved)
        self.assertEqual(project(state,"b",self.members[1])["quantity"],200)
        self.assertEqual(project(state,"a",self.members[0])["quantity"],800)

    def test_leaving_releases_unpicked_work_but_preserves_cargo(self):
        self.op["quantity"]=3000
        self.members[1].update(cargo_count=500,cargo=[{"key":"gold","count":500}])
        saved,_=self.state()
        self.members.pop()
        saved,state=self.state(saved)
        absent=next(r for r in state["workload"]["members"] if r["id"]=="b")
        self.assertEqual(absent["loading_remaining"],500)
        self.assertEqual(state["workload"]["reserved"]["loading"],500)
        self.assertEqual(project(state,"a",self.members[0])["quantity"],1136)
        self.assertEqual(next(r for r in state["workload"]["members"] if r["id"]=="a")["loading_remaining"],2500)
        # A delayed report consumes held cargo without inventing a new pickup.
        self.op["reports"]={"b":{"loading":500}}
        _,state=self.state(saved)
        self.assertEqual(state["workload"]["reserved"]["loading"],0)

    def test_switching_to_live_keeps_cargo_from_a_stale_existing_report(self):
        self.op["quantity"]=3000
        previous=build(self.plan,self.op,self.members,{"mode":"equal"})
        self.members[1].update(stale=True,cargo_count=500,cargo=[{"key":"gold","count":500}])
        _,state=self.state(previous)
        self.assertEqual(state["workload"]["reserved"]["loading"],500)
        self.assertEqual(next(r["loading_remaining"] for r in state["workload"]["members"] if r["id"]=="a"),2500)

    def test_no_available_ship_preserves_unassigned_work(self):
        for m in self.members:m["activity"]="away"
        _,state=self.state()
        self.assertEqual(state["load_suggestion"]["next_buy"],0)
        self.assertEqual(state["workload"]["unassigned"]["loading"],1160)

    def test_full_ships_keep_future_estimates_without_requesting_more_cargo(self):
        self.op["quantity"]=10000
        for m in self.members:m.update(cargo_count=m["capacity"],cargo=[{"key":"gold","count":m["capacity"]}])
        _,state=self.state()
        self.assertEqual(state["load_suggestion"]["next_buy"],0)
        self.assertEqual(state["workload"]["unassigned"]["loading"],0)
        for r in state["workload"]["members"]:self.assertGreater(r["loading_remaining"],r["capacity"])

    def test_owner_opt_out_and_other_cargo_reduce_available_space(self):
        self.settings["owner_hauls"]=False
        self.members[1].update(cargo_count=100,cargo=[{"key":"silver","count":100}])
        _,state=self.state()
        self.assertEqual([r["next_buy"] for r in state["load_suggestion"]["members"]],[0,1100])

    def test_live_allocations_conserve_remaining_work_across_ship_changes(self):
        for quantity in (1,52,1160,1700,2336,5000,19876):
            for cargo in (0,500,1136):
                self.op["quantity"]=quantity
                self.members[0].update(cargo_count=cargo,cargo=[{"key":"gold","count":cargo}])
                _,state=self.state()
                w=state["workload"]
                self.assertEqual(sum(r["loading_remaining"] for r in w["members"])+w["unassigned"]["loading"],quantity)
                self.assertLessEqual(state["load_suggestion"]["next_buy"],max(0,quantity-cargo))

    def test_local_cargo_after_leader_snapshot_consumes_pickup_allowance(self):
        _,state=self.state()
        local={**self.members[1],"cargo_count":1100,"cargo":[{"key":"gold","count":1100}]}
        self.assertEqual(project(state,"b",local)["quantity"],60)

    def test_unloading_pause_and_finished_phases(self):
        for stage in ("unloading","transit","complete","cancelled"):
            self.op["stage"]=stage
            self.op["reports"]={"a":{"loading":1160}}
            _,state=self.state()
            d=project(state,"b",self.members[1])
            if stage=="unloading":self.assertEqual((d["action"],d["quantity"]),("buy",1160))
            else:self.assertEqual(d["action"],"wait")
        self.op.update(stage="unloading",paused=True)
        _,state=self.state()
        self.assertEqual(project(state,"b",self.members[1])["action"],"wait")
