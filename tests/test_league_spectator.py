import json
import pathlib
import tempfile
import unittest

from scripts.build_spectator_data import (
    load_config_items,
    violation_delta,
)
from scripts.render_league_spectator import render_html


class LeagueSpectatorTests(unittest.TestCase):
    def test_violation_event_keeps_each_official_counter_separate(self):
        before = {
            "soft_covered_by_other": 1,
            "priority_covered_by_other": 2,
            "priority_misrouted": 0,
        }
        after = {
            "soft_covered_by_other": 3,
            "priority_covered_by_other": 2,
            "priority_misrouted": 1,
        }
        self.assertEqual(violation_delta(before, after), [2, 0, 1])

    def test_config_fallback_uses_real_scenario_geometry(self):
        with tempfile.TemporaryDirectory() as temporary:
            items = load_config_items(
                pathlib.Path(temporary),
                "permute-000-191",
                "dual-preloaded-dedicated",
            )
        self.assertGreater(len(items), 0)
        self.assertTrue(all(len(dims) == 3 for dims in items.values()))

    def test_rendered_room_embeds_match_and_live_status(self):
        template = (
            '<script id="match-data">__MATCH_DATA__</script>'
            '<script id="live-data">__LIVE_STATUS__</script>'
        )
        match = {"challenger": "pi2", "cells": {}}
        live = {"stage": "league", "revision": "m6"}
        html = render_html(template, match, live)
        self.assertNotIn("__MATCH_DATA__", html)
        self.assertNotIn("__LIVE_STATUS__", html)
        self.assertEqual(
            json.loads(html.split('<script id="match-data">', 1)[1]
                       .split("</script>", 1)[0]),
            match,
        )

    def test_real_shell_has_live_polling_and_attribute_effects(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        template = (root / "reports/league/spectator/shell.html").read_text(
            encoding="utf-8"
        )
        match = json.loads((
            root / "tests/fixtures/league-spectator-match.json"
        ).read_text(encoding="utf-8"))
        live = {"active": True, "round": 2, "wave": 6,
                "stage": "league", "revision": "demo"}
        html = render_html(template, match, live)
        self.assertIn("pollRaceControl", html)
        self.assertIn("SOFT CRUSH!", html)
        self.assertIn("PRIORITY FOUL!", html)
        self.assertIn("viol_delta", html)
        self.assertIn("refreshSeasonView", html)
        self.assertIn('id="match-history"', html)
        self.assertNotIn("__LIVE_STATUS__", html)


if __name__ == "__main__":
    unittest.main()
