import unittest

from viewer.snippets import availability, fmt_date, install_blocks, leaf_tabs, plain_intake_ok

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

    def test_intake_per_machine_for_catalog_variables(self):
        l = leaf("netcdf", {"urlpath": "{{ LRA_PATH }}/{{ realization }}.nc"}, {"realization": {"default": 2}})
        machines = {"levante": {"LRA_PATH": "/work/lra"}, "wilma": {"LRA_PATH": None}, "mn5": {"OTHER": "/x"}}
        tabs = leaf_tabs("Repo", "cat", l, ENGINES, {"LRA_PATH": "/pfs/lra"}, machines)
        intake = next(t for t in tabs if t["id"] == "intake")
        # wilma sets it to null, mn5 does not list it, the default is a local path: only levante
        self.assertEqual([c["name"] for c in intake["choices"]], ["levante"])
        code = intake["choices"][0]["code"]
        self.assertIn("    realization=2,\n    LRA_PATH='/work/lra',\n).to_dask()", code)
        self.assertIn('._entries["s"]', code)
        self.assertIn("synced", intake["note"])

    def test_online_when_every_default_is_remote(self):
        l = leaf("zarr", {"urlpath": "{{ ZARR_PATH }}/x.zarr"})
        variables = {"ZARR_PATH": "s3://bucket/zarr"}
        machines = {"levante": {"ZARR_PATH": "/work/zarr"}, "mn5": {}}
        intake = next(t for t in leaf_tabs("Repo", "cat", l, ENGINES, variables, machines) if t["id"] == "intake")
        self.assertEqual([c["name"] for c in intake["choices"]], ["levante", "online"])
        self.assertIn("ZARR_PATH='s3://bucket/zarr'", intake["choices"][1]["code"])

    def test_no_online_when_one_default_is_local(self):
        l = leaf("zarr", {"urlpath": "{{ A }}/{{ B }}.zarr"})
        tabs = leaf_tabs("Repo", "cat", l, ENGINES, {"A": "s3://a", "B": "/local"}, {})
        self.assertEqual([t["id"] for t in tabs], ["aqua", "yaml"])

    def test_undeclared_variable_has_no_intake_even_with_machines(self):
        l = leaf("netcdf", {"urlpath": "{{ LRA_PATH }}/x.nc"})
        tabs = leaf_tabs("Repo", "cat", l, ENGINES, {}, {"levante": {"LRA_PATH": "/work"}})
        self.assertEqual([t["id"] for t in tabs], ["aqua", "yaml"])

    def test_merge_key_patch_only_when_needed(self):
        patch = "intake.utils.no_duplicates_constructor = yaml.SafeLoader.construct_yaml_map"
        merged = self.tabs({**leaf("zarr", {"urlpath": "/x"}), "merge_keys": True})
        self.assertIn(patch, merged["intake"])
        self.assertLess(merged["intake"].index(patch), merged["intake"].index("intake.open_catalog"))
        self.assertNotIn(patch, self.tabs(leaf("zarr", {"urlpath": "/x"}))["intake"])

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


class InstallTests(unittest.TestCase):
    def test_open_repo_has_online_and_editable(self):
        b = dict(install_blocks("Repo", "https://x/Repo.git", "cat", True))
        self.assertEqual(b["Online"], "aqua add cat")
        self.assertIn("-e path/to/Repo/catalogs/cat", b["Editable"])

    def test_private_repo_is_editable_only(self):
        self.assertEqual([l for l, _ in install_blocks("Repo", "u", "cat", False)], ["Editable"])


class MachineMetadataTests(unittest.TestCase):
    VARS = {"LRA_PATH": "/pfs/lra"}
    MACHINES = {"MN5": {"LRA_PATH": "/gpfs/lra"}, "levante": {"LRA_PATH": "/work/lra"}}

    def netcdf(self, declared=None, path="{{ LRA_PATH }}/x.nc"):
        l = leaf("netcdf", {"urlpath": path})
        l["machines_declared"] = declared
        return l

    def intake(self, l, variables=None, machines=None):
        tabs = leaf_tabs("Repo", "cat", l, ENGINES, variables or self.VARS, machines or self.MACHINES)
        return {t["id"]: t for t in tabs}

    def test_no_metadata_keeps_automatic_list_and_warning(self):
        t = self.intake(self.netcdf())
        self.assertEqual([c["name"] for c in t["intake"]["choices"]], ["MN5", "levante"])
        self.assertIn("synced", t["intake"]["note"])

    def test_declared_subset_replaces_list_case_insensitively(self):
        t = self.intake(self.netcdf(["mn5"]))
        self.assertEqual([c["name"] for c in t["intake"]["choices"]], ["MN5"])
        self.assertNotIn("synced", t["intake"]["note"])
        self.assertEqual([b["name"] for b in t["aqua"]["badges"]], ["MN5"])

    def test_declared_extra_machine_uses_defaults(self):
        t = self.intake(self.netcdf(["levante", "lumi"]))
        names = [c["name"] for c in t["intake"]["choices"]]
        self.assertEqual(names, ["levante", "lumi"])
        lumi = t["intake"]["choices"][1]["code"]
        self.assertIn("LRA_PATH='/pfs/lra'", lumi)
        self.assertIn("catalog defaults", lumi)

    def test_declared_machine_without_any_value_has_badge_but_no_snippet(self):
        t = self.intake(self.netcdf(["lumi"]), variables={"LRA_PATH": None})
        self.assertNotIn("intake", t)
        self.assertEqual([b["name"] for b in t["aqua"]["badges"]], ["lumi"])

    def test_gsv_machines_local_polytope_online(self):
        l = leaf("gsv", {"request": {}})
        l["machines_declared"] = ["MN5", "online"]
        t = {x["id"]: x for x in leaf_tabs("Repo", "cat", l, ENGINES, {}, {"MN5": {}})}
        self.assertEqual([b["name"] for b in t["aqua-gsv"]["badges"]], ["MN5"])
        self.assertEqual([b["name"] for b in t["aqua-z3fdb"]["badges"]], ["MN5"])
        self.assertEqual([(b["name"], b["kind"]) for b in t["aqua-polytope"]["badges"]], [("online", "online")])

    def test_gsv_without_metadata_has_no_machine_badges(self):
        t = {x["id"]: x for x in leaf_tabs("Repo", "cat", leaf("gsv", {"request": {}}), ENGINES)}
        self.assertEqual(t["aqua-gsv"]["badges"], [])

    def test_online_badge_for_remote_path_without_variables(self):
        l = leaf("zarr", {"urlpath": "s3://b/{{ realization }}.zarr"}, {"realization": {"default": 1}})
        l["machines_declared"] = None
        t = {x["id"]: x for x in leaf_tabs("Repo", "cat", l, ENGINES)}
        self.assertEqual([b["name"] for b in t["aqua"]["badges"]], ["online"])
        self.assertEqual(availability(l, ENGINES), [{"name": "online", "kind": "online"}])

    def test_online_chip_with_declared_machines(self):
        l = self.netcdf(["levante"])
        t = self.intake(l, variables={"LRA_PATH": "s3://b/lra"})
        self.assertEqual([c["name"] for c in t["intake"]["choices"]], ["levante", "online"])


if __name__ == "__main__":
    unittest.main()
