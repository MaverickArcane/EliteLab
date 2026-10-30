"""Issue 50: shared utility blueprints must be selectable for heat sinks."""
import tempfile
import unittest
from unittest.mock import patch

from test_elitelab import Core, config, loader


class HeatSinkRecipeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        data = patch.object(config, "DATA_DIR", temporary.name)
        data.start()
        self.addCleanup(data.stop)
        self.core = Core()
        loader.load_all(self.core)
        self.addCleanup(self.core.close)

    def call(self, tool, **params):
        return self.core.http.tools[tool].fn(params)

    def test_heat_sink_filter_and_picker_offer_all_four_blueprints(self):
        expected = {"Misc_HeatSinkCapacity", "Misc_LightWeight", "Misc_Reinforced", "Misc_Shielded"}
        results = self.call("list_recipes", module="Heat sink launcher", kind="blueprint")["results"]
        self.assertEqual({row["key"] for row in results}, expected)
        self.assertTrue(all(row["module"] == "Heat sink launcher" for row in results))
        modules = self.call("wishlist_options")["modules"]
        heat_sink = next(row for row in modules if row["module"] == "Heat sink launcher")
        self.assertEqual({row["key"] for row in heat_sink["blueprints"]}, expected)
        chaff = next(row for row in modules if row["module"] == "Chaff launcher")
        self.assertTrue(expected - {"Misc_HeatSinkCapacity"} <= {row["key"] for row in chaff["blueprints"]})

    def test_recipe_detail_and_wishlist_keep_selected_module_and_grade_costs(self):
        for key, material in (("Misc_LightWeight", "phosphorus"),
                              ("Misc_Reinforced", "nickel"),
                              ("Misc_Shielded", "wornshieldemitters")):
            with self.subTest(key=key):
                detail = self.call("get_recipe", key=key, module="Heat sink launcher", grade=1)
                self.assertEqual(detail["module"], "Heat sink launcher")
                self.assertEqual(detail["max_grade"], 5)
                self.assertEqual(set(detail["grades"]), {"1", "2", "3", "4", "5"})
                self.assertEqual(detail["engineers"], {"Petra Olmanova": 5, "Ram Tah": 5})
                added = self.call("wishlist_add", item=key, module="Heat sink launcher", grade=1, qty=2)
                self.assertEqual(added["entry"]["module"], "Heat sink launcher")
                self.assertEqual({row["key"]: row["need"] for row in added["needs"]}, {material: 2})
        restarted = Core()
        loader.load_all(restarted)
        self.addCleanup(restarted.close)
        entries = restarted.http.tools["get_engineering_wishlist"].fn({})["entries"]
        self.assertEqual(len(entries), 3)
        self.assertTrue(all(row["module"] == "Heat sink launcher" for row in entries))

    def test_free_text_and_engineer_filters_find_shared_recipes(self):
        result = self.call("list_recipes", query="lightweight", module="heat sink", engineer="Ram Tah")
        self.assertEqual([row["key"] for row in result["results"]], ["Misc_LightWeight"])
        self.assertEqual(result["results"][0]["engineer_grade"], 5)
        added = self.call("wishlist_add", item="heat sink launcher lightweight", grade=1)
        self.assertEqual(added["entry"]["module"], "Heat sink launcher")
        # An unrelated exact module must not gain utility recipes.
        result = self.call("list_recipes", module="Frame shift drive", kind="blueprint")
        self.assertFalse(any(row["key"].startswith("Misc_") for row in result["results"]))

    def test_legacy_key_defaults_to_chaff_and_wrong_module_is_rejected(self):
        added = self.call("wishlist_add", item="Misc_LightWeight", grade=1)
        self.assertEqual(added["entry"]["module"], "Chaff launcher")
        with self.assertRaisesRegex(ValueError, "not available"):
            self.call("wishlist_add", item="Misc_LightWeight", module="Frame shift drive", grade=1)
        detail = self.call("get_recipe", key="Misc_LightWeight", module="Frame shift drive")
        self.assertEqual(detail["candidates"], [])


if __name__ == "__main__":
    unittest.main()
