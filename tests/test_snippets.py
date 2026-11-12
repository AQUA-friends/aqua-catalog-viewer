import unittest

from viewer.snippets import fmt_date, leaf_tabs, plain_intake_ok

ENGINES = ["gsv", "polytope", "z3fdb"]


def leaf(driver, args=None, parameters=None, trail=("M", "e", "s")):
    return {"kind": "source", "name": trail[-1], "trail": list(trail), "driver": driver,
            "args": args or {}, "parameters": parameters or {}, "metadata": {}, "description": "d"}


class SnippetTests(unittest.TestCase):
    def tabs(self, l):
        return {t["id"]: t["code"] for t in leaf_tabs("Repo", "cat", l, ENGINES)}

    def test_gsv_has_one_aqua_tab_per_engine_and_yaml(self):
        t = self.tabs(leaf("gsv", {"request": {"a": 1}}))
        self.assertEqual(list(t), ["aqua-gsv", "aqua-polytope", "aqua-z3fdb", "yaml"])
        self.assertNotIn("engine", t["aqua-gsv"])
        self.assertIn('engine=\'polytope\'', t["aqua-polytope"])
        self.assertIn('catalog="cat"', t["aqua-gsv"])
        self.assertIn("aqua add cat -e /path/to/Repo/catalogs/cat", t["aqua-gsv"])

    def test_realization_default_is_passed_to_reader(self):
        t = self.tabs(leaf("gsv", {"request": {}}, {"realization": {"default": 2, "allowed": [1, 2]}}))
        self.assertIn("realization=2,", t["aqua-gsv"])
        self.assertIn("realization=2,", t["aqua-z3fdb"])

    def test_zarr_gets_intake_with_entries_form_for_parameters(self):
        plain = self.tabs(leaf("zarr", {"urlpath": "/x"}))
        self.assertEqual(list(plain), ["aqua", "intake", "yaml"])
        self.assertIn('cat["M"]["e"]["s"].to_dask()', plain["intake"])
        withp = self.tabs(leaf("zarr", {"urlpath": "/x/{{ realization }}"}, {"realization": {"default": 3}}))
        self.assertIn('._entries["s"]', withp["intake"])
        self.assertIn("entry(realization=3).to_dask()", withp["intake"])

    def test_no_intake_when_machine_variable_needed(self):
        l = leaf("netcdf", {"urlpath": "{{ LRA_PATH }}/x.nc"})
        self.assertFalse(plain_intake_ok(l))
        self.assertEqual(list(self.tabs(l)), ["aqua", "yaml"])

    def test_non_three_level_trail_only_yaml(self):
        self.assertEqual(list(self.tabs(leaf("zarr", {"urlpath": "/x"}, trail=("a", "b", "c", "d")))), ["yaml"])

    def test_yaml_has_no_anchors_for_shared_objects(self):
        shared = [1, 2]
        l = leaf("gsv", {"request": {"a": shared, "b": shared}})
        self.assertNotIn("&id", self.tabs(l)["yaml"])

    def test_yaml_scalar_lists_are_flow_style(self):
        l = leaf("gsv", {"request": {"levelist": [1, 5, 10]}})
        self.assertIn("levelist: [1, 5, 10]", self.tabs(l)["yaml"])

    def test_fmt_date(self):
        self.assertEqual(fmt_date("19900101T0000"), "1990-01-01")
        self.assertEqual(fmt_date("19900101T0600", time=True), "1990-01-01 06:00")
        self.assertEqual(fmt_date("complete"), "complete")


if __name__ == "__main__":
    unittest.main()
