"""Crew quotas conserve tonnes and remove owner transfers from market orders."""
import copy
import random
import unittest

from elitelab.core.hauling import build, divide, view
from modules.party.loads import recommend
from modules.party.desk import project
from modules.trade.operations import operation_view
from modules.trade.profit import split_profit


class WorkloadTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"commodity":"gold", "planned_quantity":12000, "source":"Buy / Sol", "destination":"Sell / Lave",
                     "source_price":100, "destination_price":300, "crew_enabled":True,
                     "crew_split":split_profit(100,300,12000)}
        self.members = [{"id":"a", "cmdr":"Owner", "leader":True, "capacity":752,"cargo_count":0,"cargo":[]},
                        {"id":"b", "cmdr":"Friend", "capacity":400,"cargo_count":0,"cargo":[]},
                        {"id":"c", "cmdr":"Small ship", "capacity":100,"cargo_count":0,"cargo":[]}]

    def test_equal_tonnes_not_equal_runs_and_owner_order_exclusion(self):
        saved = build(self.plan,None,self.members,{"mode":"equal","owner_hauls":True})
        w = view(saved,None,self.members,self.plan)
        self.assertEqual([r["loading_target"] for r in w["members"]],[4000,4000,4000])
        self.assertEqual([r["loading_runs"] for r in w["members"]],[6,10,40])
        self.assertEqual(w["loading"]["order_remaining"],8000)
        self.assertEqual(w["buy_budget"],8000*150)
        self.assertEqual(w["economics"]["owner_profit"],1600000)
        self.assertEqual(w["economics"]["crew_profit"],800000)

    def test_owner_sitting_out_and_custom_weights(self):
        saved = build(self.plan,None,self.members,{"mode":"equal","owner_hauls":False})
        w = view(saved,None,self.members,self.plan)
        self.assertEqual([r["loading_target"] for r in w["members"]],[0,6000,6000])
        self.assertEqual(w["loading"]["order_remaining"],12000)
        custom = build(self.plan,None,self.members,{"mode":"custom","owner_hauls":True,"shares":{"a":2,"b":1,"c":1}})
        self.assertEqual([r["loading_target"] for r in custom["members"]],[6000,3000,3000])
        custom = build(self.plan,None,self.members,{"mode":"custom","owner_hauls":True,"shares":{"a":0,"b":2,"c":1}})
        self.assertEqual([r["loading_target"] for r in custom["members"]],[0,8000,4000])

    def test_rounding_conserves_whole_tonnes(self):
        for quantity in (1,2,4,1001,19876):
            self.plan["planned_quantity"]=quantity
            s=build(self.plan,None,self.members,{})
            assigned=[r["loading_target"] for r in s["members"]]
            self.assertEqual(sum(assigned),quantity)
            self.assertLessEqual(max(assigned)-min(assigned),1)

    def test_committed_loads_conserve_tonnes_across_weighted_remainders(self):
        self.assertEqual(divide(12,{"a":2,"b":1,"c":1},{"a":0,"b":0,"c":7}),{"a":3,"b":2,"c":7})
        rng = random.Random(71)
        for _ in range(200):
            total = rng.randrange(1,1001)
            weights = {mid:rng.randrange(5) for mid in "abcde"}
            weights["a"] += 1
            left, minimums = total, {}
            for mid in weights:
                minimums[mid] = rng.randrange(left+1)
                left -= minimums[mid]
            amounts = divide(total,weights,minimums)
            self.assertEqual(sum(amounts.values()),total)
            for mid in weights:
                self.assertGreaterEqual(amounts[mid],minimums[mid])
                if not weights[mid]:
                    self.assertEqual(amounts[mid],minimums[mid])

    def test_ship_changes_and_disconnects_do_not_shift_saved_targets(self):
        s=build(self.plan,None,self.members,{})
        before=copy.deepcopy(s)
        self.members[1]["capacity"]=752
        self.members[2]["stale"]=True
        w=view(s,None,self.members,self.plan)
        self.assertEqual([r["loading_target"] for r in w["members"]],[4000]*3)
        self.assertEqual(w["members"][1]["loading_runs"],6)
        self.assertFalse(w["members"][2]["connected"])
        self.assertEqual(s,before)

    def test_order_counts_crew_delivery_but_never_owner_transfer_twice(self):
        s=build(self.plan,None,self.members,{})
        op={"quantity":12000,"reports":{"a":{"loading":1000},"b":{"loading":500}}}
        w=view(s,op,self.members,self.plan)
        self.assertEqual(w["loading"],{"remaining":10500,"owner_remaining":3000,"order_remaining":7500,"owner_target":4000})
        op["reports"]["a"]["loading"]=4000
        self.assertEqual(view(s,op,self.members,self.plan)["loading"]["order_remaining"],7500)

    def test_rebalance_preserves_deliveries_and_divides_only_unfinished_work(self):
        s=build(self.plan,None,self.members,{})
        op={"quantity":12000,"stage":"loading","reports":{"a":{"loading":1000,"unloading":0},"b":{"loading":500,"unloading":0}}}
        revised=build(self.plan,op,self.members,{"owner_hauls":False},s)
        self.assertEqual([r["loading_target"] for r in revised["members"]],[1000,5750,5250])
        self.assertEqual([r["unloading_target"] for r in revised["members"]],[0,6000,6000])
        self.assertEqual(view(revised,op,self.members,self.plan)["loading"]["order_remaining"],10500)

    def test_join_preserves_absent_shares_and_in_flight_loads(self):
        saved = build(self.plan, None, self.members, {})
        self.members[0].update(cargo_count=3500, cargo=[{"key":"gold", "count":3500}])
        self.members[1]["stale"] = True
        self.members.append({"id":"d", "cmdr":"New crew", "capacity":500, "cargo_count":0, "cargo":[]})
        op = {"quantity":12000, "stage":"loading", "reports":{"b":{"loading":1000}}}
        revised = build(self.plan, op, self.members, saved, saved, joining=True)
        rows = {r["id"]:r for r in view(revised, op, self.members, self.plan)["members"]}
        self.assertEqual(rows["b"]["loading_target"],4000)
        self.assertEqual(rows["a"]["loading_remaining"],3500)
        self.assertEqual(rows["c"]["loading_remaining"],2250)
        self.assertEqual(rows["d"]["loading_remaining"],2250)
        self.assertEqual(rows["d"]["loading_runs_left"],5)
        self.assertEqual(sum(r["loading_target"] for r in revised["members"]),12000)
        self.members[1]["stale"] = False
        suggestion = recommend(self.plan, operation_view(op), self.members, workload=view(revised,op,self.members,self.plan))
        self.assertGreater(next(r["next_buy"] for r in suggestion["members"] if r["id"]=="b"),0)

    def test_join_after_departure_keeps_loading_targets(self):
        saved = build(self.plan, None, self.members, {})
        self.members.append({"id":"d", "cmdr":"New crew", "capacity":500})
        for stage in ("transit", "unloading"):
            op = {"quantity":12000,"stage":stage,"reports":{"a":{"loading":3500},"b":{"loading":4500},"c":{"loading":4000}}}
            revised = build(self.plan, op, self.members, saved, saved, joining=True)
            self.assertEqual([r["loading_target"] for r in revised["members"]],[4000,4000,4000,0])
            self.assertEqual([r["unloading_target"] for r in revised["members"]],[3000]*4)

    def test_final_partial_load_top_up_and_progress_need_no_arithmetic(self):
        self.members[1]["capacity"]=752
        saved=build(self.plan,None,self.members,{})
        op=operation_view({"id":"job","stage":"loading","quantity":12000,"reports":{
            "a":{"loading":4000},"b":{"loading":3650},"c":{"loading":4000}}})
        self.members[1].update(cargo_count=100,cargo=[{"key":"gold","count":100}])
        w=view(saved,op,self.members,self.plan)
        suggestion=recommend(self.plan,op,self.members,workload=w)
        self.assertEqual([r["next_buy"] for r in suggestion["members"]],[0,250,0])
        shared={"members":self.members,"plan":self.plan,"operation":op,"workload":w,"load_suggestion":suggestion}
        d=project(shared,"b",self.members[1])
        self.assertEqual((d["action"],d["quantity"]),("buy",250))
        self.assertIn("deliver 350 t",d["reason"])
        self.assertEqual(d["load_earnings"],350*50)
        self.assertEqual(d["assignment"]["loading_runs_left"],1)
        self.assertEqual(d["assignment"]["loading_partial_load"],350)
        self.members[1].update(cargo_count=350,cargo=[{"key":"gold","count":350}])
        shared["load_suggestion"]=recommend(self.plan,op,self.members,workload=w)
        d=project(shared,"b",self.members[1])
        self.assertEqual((d["action"],d["quantity"]),("deliver",350))
        op["reports"]["b"]["loading"]=4000
        op=operation_view(op)
        shared["operation"]=op
        shared["workload"]=view(saved,op,self.members,self.plan)
        shared["load_suggestion"]=recommend(self.plan,op,self.members,workload=shared["workload"])
        d=project(shared,"b",self.members[1])
        self.assertEqual(d["assignment"]["loading_runs_left"],0)
        self.assertEqual(d["action"],"wait")

    def test_final_pickups_never_exceed_quotas_or_global_remaining(self):
        self.plan["planned_quantity"]=1000
        saved=build(self.plan,None,self.members,{})
        op=operation_view({"id":"job","stage":"loading","quantity":1000,"reports":{"a":{"loading":350},"b":{"loading":200},"c":{"loading":100}}})
        w=view(saved,op,self.members,self.plan)
        s=recommend(self.plan,op,self.members,workload=w)
        self.assertLessEqual(sum(r["next_buy"] for r in s["members"]),350)
        for r in s["members"]:
            self.assertLessEqual(r["next_buy"],r["remaining"])
        self.assertEqual(s["members"][0]["next_buy"],0)

    def test_unknown_capacity_gets_equal_tonnes_but_unknown_runs(self):
        self.members[1]["capacity"]=None
        w=view(build(self.plan,None,self.members,{}),None,self.members,self.plan)
        self.assertEqual(w["members"][1]["loading_target"],4000)
        self.assertIsNone(w["members"][1]["loading_runs_left"])

    def test_local_pickup_consumes_old_shared_allowance_on_both_legs(self):
        self.plan["planned_quantity"] = 350
        self.members[1]["capacity"] = 500
        saved = build(self.plan, None, self.members, {"mode":"custom", "shares":{"b":1}})
        for phase in ("loading", "unloading"):
            op = operation_view({"id":"job", "stage":phase, "quantity":350, "reports":{}})
            w = view(saved, op, self.members, self.plan)
            shared = {"plan":self.plan, "operation":op, "members":self.members, "workload":w,
                      "load_suggestion":recommend(self.plan, op, self.members, workload=w)}
            for aboard, expected in ((100, ("buy",250)), (350, ("deliver",350)), (400, ("deliver",350))):
                with self.subTest(phase=phase, aboard=aboard):
                    local = {**self.members[1], "cargo_count":aboard, "cargo":[{"key":"gold", "count":aboard}]}
                    d = project(shared, "b", local)
                    self.assertEqual((d["action"],d["quantity"]), expected)

    def test_rebalance_keeps_assigned_cargo_when_owner_stops_new_runs(self):
        self.plan["planned_quantity"] = 400
        saved = build(self.plan, None, self.members, {"mode":"custom", "shares":{"a":1}})
        self.members[0].update(cargo_count=400, cargo=[{"key":"gold", "count":400}])
        for phase in ("loading", "unloading"):
            op = operation_view({"id":"job", "stage":phase, "quantity":400, "reports":{}})
            revised = build(self.plan, op, self.members, {"owner_hauls":False}, saved)
            w = view(revised, op, self.members, self.plan)
            self.assertEqual(w["members"][0][phase+"_remaining"],400)
            self.assertEqual(w[phase]["order_remaining"],0)
            shared = {"plan":self.plan, "operation":op, "members":self.members, "workload":w,
                      "load_suggestion":recommend(self.plan, op, self.members, workload=w)}
            d = project(shared,"a",self.members[0])
            self.assertEqual((d["action"],d["quantity"]),("transfer_in" if phase=="loading" else "deliver",400))
            self.assertEqual(sum(r[phase+"_target"] for r in revised["members"]),400)
            # Opting out keeps only this in-flight load, not future purchases.
            empty = [{**m,"cargo_count":0,"cargo":[]} if m["id"]=="a" else m for m in self.members]
            suggestion = recommend(self.plan,op,empty,workload=view(revised,op,empty,self.plan))
            self.assertEqual(next(r["next_buy"] for r in suggestion["members"] if r["id"]=="a"),0)

    def test_rebalance_keeps_equal_shares_when_current_loads_fit(self):
        saved = build(self.plan,None,self.members,{})
        self.members[0].update(cargo_count=200,cargo=[{"key":"gold","count":200}])
        op = {"id":"job","stage":"loading","quantity":12000,"reports":{}}
        revised = build(self.plan,op,self.members,{},saved)
        self.assertEqual([r["loading_target"] for r in revised["members"]],[4000]*3)
        self.assertNotEqual(revised["basis"], saved["basis"])

    def test_unassigned_cargo_does_not_block_assigned_pickups(self):
        self.plan["planned_quantity"] = 100
        saved = build(self.plan,None,self.members,{"mode":"custom","shares":{"b":1}})
        self.members[0].update(cargo_count=100,cargo=[{"key":"gold","count":100}])
        op = operation_view({"id":"job","stage":"loading","quantity":100,"reports":{}})
        w = view(saved,op,self.members,self.plan)
        suggestion = recommend(self.plan,op,self.members,workload=w)
        self.assertEqual(next(r["next_buy"] for r in suggestion["members"] if r["id"]=="b"),100)

    def test_invalid_inputs_do_not_produce_work(self):
        for settings in ({"mode":"capacity"},{"owner_hauls":"yes"},{"mode":"custom","shares":{"a":-1}},
                         {"mode":"custom","shares":{"a":1.5}},{"mode":"custom","shares":{}},
                         {"mode":"custom","shares":{"unknown":1}}):
            with self.assertRaises(ValueError): build(self.plan,None,self.members,settings)
