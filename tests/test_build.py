import tempfile
import unittest
from pathlib import Path

from viewer.build import Builder


class HomeDescriptionTests(unittest.TestCase):
    def test_description_on_home_card(self):
        cat = {"name": "cat-a", "children": []}
        cat2 = {"name": "cat-b", "children": []}
        site = {"title": "T", "repos": [{"name": "r", "catalogs": [cat, cat2]}], "problems": []}
        cfg = {"repos": [{"name": "r", "path": ".", "descriptions": {"cat-a": "Sim <runs>.", "nope": "x"}}]}
        with tempfile.TemporaryDirectory() as out:
            Builder(cfg, site, out).build_home()
            html = (Path(out) / "index.html").read_text()
        self.assertIn('<p class="desc">Sim &lt;runs&gt;.</p>', html)
        self.assertEqual(html.count('class="desc"'), 1)


if __name__ == "__main__":
    unittest.main()
