import unittest
from unittest import mock

from viewer.params import fetch_names, parse_names

ROWS = [{"id": 167, "name": "2 metre temperature", "shortname": "2t"},
        {"id": 999, "name": "Other", "shortname": "oth"},
        {"id": 263000, "name": "Time-mean sea ice thickness", "shortname": None}]


class ParamTests(unittest.TestCase):
    def test_keeps_only_wanted_ids(self):
        self.assertEqual(parse_names(ROWS, {167, 263000}),
                         {167: {"short": "2t", "name": "2 metre temperature"},
                          263000: {"short": "", "name": "Time-mean sea ice thickness"}})

    def test_unreachable_api_gives_no_names_instead_of_failing(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertEqual(fetch_names({167}), {})

    def test_nothing_wanted_makes_no_request(self):
        with mock.patch("urllib.request.urlopen") as m:
            self.assertEqual(fetch_names(set()), {})
        m.assert_not_called()


if __name__ == "__main__":
    unittest.main()
