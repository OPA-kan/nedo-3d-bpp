import pathlib
import subprocess
import sys
import unittest

from scripts.select_critical_self_play_replays import rank_games, select_diverse


ROOT = pathlib.Path(__file__).resolve().parents[1]


def game(
    reason="max_steps", violations=0, ranks=(0,), fingerprints=("a",),
    prefilter_rejections=0,
):
    return {
        "terminal_reason": reason,
        "new_attribute_violations": violations,
        "non_rank0_action_count": sum(rank > 0 for rank in ranks),
        "handoff_count": 2,
        "prefilter_rejections": prefilter_rejections,
        "records": [{"selected_rank": rank} for rank in ranks],
        "captures": [
            {"board_fingerprint": fingerprint} for fingerprint in fingerprints
        ],
    }


class CriticalReplaySelectionTests(unittest.TestCase):
    def test_cli_imports_renderer_when_run_as_an_isolated_script(self):
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(ROOT / "scripts" / "select_critical_self_play_replays.py"),
                "--help",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_attribute_and_terminal_events_outrank_plain_exploration(self):
        rows = rank_games([
            ("plain", {"case_id": "a", "games": [game(ranks=(0, 1))]}),
            ("attribute", {"case_id": "b", "games": [game(violations=1)]}),
            ("terminal", {"case_id": "c", "games": [
                game(reason="selected_action_failure")
            ]}),
        ])

        self.assertEqual([row["label"] for row in rows], [
            "terminal", "attribute", "plain",
        ])
        self.assertIn("physical rejection", rows[0]["reasons"])
        self.assertIn("attribute violation +1", rows[1]["reasons"])

    def test_prefiltered_negative_proposals_make_a_game_replay_worthy(self):
        rows = rank_games([
            ("plain", {"games": [game(ranks=(0, 1))]}),
            ("filtered", {"games": [game(prefilter_rejections=2)]}),
        ])

        self.assertEqual(rows[0]["label"], "filtered")
        self.assertIn("PyBullet filtered 2 proposal(s)", rows[0]["reasons"])

    def test_selection_keeps_scenario_coverage_before_global_fill(self):
        rows = rank_games([
            ("a", {"case_id": "a", "games": [
                game(violations=2), game(violations=1),
            ]}),
            ("b", {"case_id": "b", "games": [game(ranks=(2, 2))]}),
        ])

        selected = select_diverse(rows, top_k=2)

        self.assertEqual({row["label"] for row in selected}, {"a", "b"})
        self.assertGreaterEqual(
            selected[0]["critical_score"], selected[1]["critical_score"]
        )


if __name__ == "__main__":
    unittest.main()
