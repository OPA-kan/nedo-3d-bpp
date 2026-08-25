import unittest

from scripts.league_season_status import status


class LeagueSeasonStatusTests(unittest.TestCase):
    def test_checked_in_season_contract_is_in_sync(self):
        result = status()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["wave"], 7)
        self.assertEqual(result["round"], 3)
        self.assertEqual(result["champion"], "pi2-pref-w6")
        self.assertEqual(result["expected_cells"], 154)


if __name__ == "__main__":
    unittest.main()
