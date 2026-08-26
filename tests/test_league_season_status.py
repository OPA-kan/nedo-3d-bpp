import unittest

from scripts.league_season_status import status


class LeagueSeasonStatusTests(unittest.TestCase):
    def test_checked_in_season_contract_is_in_sync(self):
        # pins CONSISTENCY, not the current round: the season advances
        # between commits, so hardcoding wave/round breaks every round
        import json, pathlib
        state = json.loads(pathlib.Path(
            "reports/league/season/state.json"
        ).read_text(encoding="utf-8"))
        result = status()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["wave"], state["wave"])
        self.assertEqual(result["round"], state["round"])
        self.assertEqual(result["champion"], state["champion"])
        self.assertEqual(result["expected_cells"], state["expected_cells"])
        self.assertEqual(
            result["matrix_counts"]["collection"], state["expected_cells"]
        )


if __name__ == "__main__":
    unittest.main()
