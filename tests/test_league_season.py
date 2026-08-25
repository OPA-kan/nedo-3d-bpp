import copy
import unittest

from scripts.league_season import (
    challenger_identity,
    finish_round,
    render_season_log,
    render_season_summary,
)


PLAN = {
    "waves": {
        "5": {"round": 1, "expected_cells": 118},
        "6": {"round": 2, "expected_cells": 136},
        "7": {"round": 3, "expected_cells": 154},
        "14": {"round": 10, "expected_cells": 280},
    }
}
NAMES = {
    "names": {
        "w6": {"name": "プリフヒバリ"},
        "w7": {"name": "プリフスバル"},
        "w14": {"name": "プリフユメミシ"},
    }
}


def registry(generation=1, champion="pi1-pref-g1"):
    return {
        "contract": "policy_league_registry_v1",
        "generation_counter": generation,
        "members": [{
            "name": champion,
            "role": "champion",
            "generation": generation,
            "source": "run-champion",
            "outcomes": {},
        }],
    }


def report(champion="pi1-pref-g1", promoted=False):
    return {
        "champion": champion,
        "challenger": "pi2-pref-w6",
        "promoted": promoted,
        "matches": {
            champion: {
                "counts": {
                    "challenger_wins": 1 if promoted else 0,
                    "member_wins": 0 if promoted else 1,
                    "equal": 7,
                    "incomparable": 2,
                }
            }
        },
        "benchmarks": {
            "pi0-search": {"standing": "below_benchmark"}
        },
    }


class LeagueSeasonTests(unittest.TestCase):
    def test_challenger_uses_next_champion_generation_and_wave_name(self):
        identity = challenger_identity(registry(), "6", NAMES)
        self.assertEqual(identity["id"], "pi2-pref-w6")
        self.assertEqual(identity["display_name"], "プリフヒバリ")

    def test_finish_round_advances_to_next_preregistered_wave(self):
        state = {
            "contract": "league_season_state_v1",
            "active": True,
            "wave": 6,
            "round": 2,
            "history": [],
        }
        updated = finish_round(
            state=state,
            plan=PLAN,
            names=NAMES,
            report=report(),
            registry_before=registry(),
            registry_after=registry(),
            runs={"collection": "c6", "learning": "l6", "match": "m6"},
            completed_at="2026-08-26T00:00:00Z",
        )
        self.assertTrue(updated["active"])
        self.assertEqual(updated["wave"], 7)
        self.assertEqual(updated["round"], 3)
        self.assertEqual(updated["stage"], "collecting")
        self.assertEqual(updated["challenger"], "pi2-pref-w7")
        self.assertEqual(len(updated["history"]), 1)
        self.assertEqual(updated["history"][0]["counts"]["losses"], 1)

    def test_wave_14_stops_and_summary_is_final(self):
        state = {
            "contract": "league_season_state_v1",
            "active": True,
            "wave": 14,
            "round": 10,
            "history": [],
        }
        final_report = report()
        final_report["challenger"] = "pi2-pref-w14"
        updated = finish_round(
            state=state,
            plan=PLAN,
            names=NAMES,
            report=final_report,
            registry_before=registry(),
            registry_after=registry(),
            runs={"collection": "c14", "learning": "l14", "match": "m14"},
            completed_at="2026-08-26T01:00:00Z",
        )
        self.assertFalse(updated["active"])
        self.assertEqual(updated["stage"], "complete")
        self.assertIsNone(updated["next_wave"])
        self.assertIn("Season complete", render_season_summary(updated))

    def test_finish_is_idempotent_for_same_match_run(self):
        state = {
            "contract": "league_season_state_v1",
            "active": True,
            "wave": 6,
            "round": 2,
            "history": [],
        }
        kwargs = dict(
            plan=PLAN,
            names=NAMES,
            report=report(),
            registry_before=registry(),
            registry_after=registry(),
            runs={"collection": "c6", "learning": "l6", "match": "m6"},
            completed_at="2026-08-26T00:00:00Z",
        )
        once = finish_round(state=state, **kwargs)
        twice = finish_round(state=copy.deepcopy(once), **kwargs)
        self.assertEqual(twice, once)

    def test_log_is_rebuilt_from_history(self):
        state = {
            "history": [{
                "round": 2, "wave": 6,
                "runs": {"collection": "c", "learning": "l", "match": "m"},
                "challenger": "pi2-pref-w6",
                "display_name": "プリフヒバリ",
                "promoted": False,
                "counts": {"wins": 0, "losses": 1, "equal": 7,
                           "incomparable": 2},
                "benchmark": "below_benchmark",
            }]
        }
        text = render_season_log(state)
        self.assertIn("プリフヒバリ", text)
        self.assertIn("0-1-7-2", text)


if __name__ == "__main__":
    unittest.main()
