import os
import tempfile
import unittest
from pathlib import Path

from viewer.load import load_repo, walk

CATALOG = """
sources:
  M1:
    description: model one
    driver: yaml_file_cat
    args:
      path: '{{CATALOG_DIR}}/catalog/M1/main.yaml'
"""
MAIN = """
sources:
  exp-a:
    description: experiment a
    metadata: {expid: '0001'}
    driver: yaml_file_cat
    args:
      path: '{{ CATALOG_DIR }}/exp-a.yaml'
"""
EXP = """
sources:
  base: &base
    description: base source
    driver: gsv
    metadata: {fixer_name: fx, source_grid_name: hpz7, variables: [78, 79]}
    args: &args
      request: &req {levtype: pl, levelist: [500, 850]}
      data_start_date: 19900101T0000
      data_end_date: 20141231T2300
  merged:
    <<: *base
    description: inherits driver and args through a merge key
  z:
    driver: zarr
    args: {urlpath: /some/path}
    parameters:
      realization: {default: 1, allowed: [1, 2]}
  empty:
    driver: null
"""


def make_repo(root, files):
    for rel, text in files.items():
        p = Path(root) / "catalogs" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def load(files, **cfg):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp, files)
        return load_repo({"name": "t", "path": tmp, **cfg})


BASE = {"c1/catalog.yaml": CATALOG, "c1/catalog/M1/main.yaml": MAIN, "c1/catalog/M1/exp-a.yaml": EXP}


class LoadTests(unittest.TestCase):
    def test_tree_and_merge_keys(self):
        repo, problems = load(BASE)
        self.assertEqual(problems, [])
        [cat] = repo["catalogs"]
        entries = {e["name"]: e for _, e in walk(cat["children"])}
        self.assertEqual(entries["exp-a"]["kind"], "node")
        self.assertEqual(entries["merged"]["driver"], "gsv")  # inherited via <<
        self.assertEqual(entries["empty"]["kind"], "placeholder")
        info = entries["base"]["info"]
        self.assertEqual((info["start"], info["end"]), ("19900101T0000", "20141231T2300"))
        self.assertEqual((info["fixer"], info["grid"], info["levtype"]), ("fx", "hpz7", "pl"))
        self.assertEqual(info["levels"], [500, 850])

    def test_relative_repo_path(self):
        """CI passes `--repos-dir repos`, a relative path."""
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(Path(tmp) / "repos" / "t", BASE)
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                repo, problems = load_repo({"name": "t", "path": "unused", "strict": True}, repos_dir="repos")
            finally:
                os.chdir(cwd)
        self.assertEqual(problems, [])
        self.assertEqual(len(list(walk(repo["catalogs"][0]["children"]))), 6)

    def test_include_and_exclude(self):
        files = {**BASE, "c2/catalog.yaml": "sources: {}"}
        repo, _ = load(files, include=["c1", "c2"], exclude=["c2"])
        self.assertEqual([c["name"] for c in repo["catalogs"]], ["c1"])

    def test_unknown_include_is_hard_error_even_if_not_strict(self):
        _, problems = load(BASE, include=["nope"], strict=False)
        self.assertEqual([p["level"] for p in problems], ["error"])

    def test_validation_levels_follow_strict(self):
        files = {**BASE, "c1/catalog/M1/exp-a.yaml": """
sources:
  bad_gsv: {driver: gsv}
  bad_zarr: {driver: zarr}
  bad_param:
    driver: zarr
    args: {urlpath: x}
    parameters: {realization: {default: 9, allowed: [1, 2]}}
  no_driver: {description: oops}
"""}
        _, lenient = load(files, strict=False)
        _, strict = load(files, strict=True)
        self.assertEqual(len(lenient), 4)
        self.assertEqual({p["level"] for p in lenient}, {"warning"})
        self.assertEqual({p["level"] for p in strict}, {"error"})

    def test_missing_referenced_file_is_hard_error(self):
        files = {**BASE}
        del files["c1/catalog/M1/exp-a.yaml"]
        _, problems = load(files, strict=False)
        self.assertEqual(problems[0]["level"], "error")
        self.assertIn("not found", problems[0]["msg"])

    def test_cycle_is_reported(self):
        files = {**BASE, "c1/catalog/M1/exp-a.yaml": """
sources:
  loop: {driver: yaml_file_cat, args: {path: '{{CATALOG_DIR}}/exp-a.yaml'}}
"""}
        _, problems = load(files)
        self.assertTrue(any("cycle" in p["msg"] for p in problems))


if __name__ == "__main__":
    unittest.main()
