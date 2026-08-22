import json
import pathlib
import tempfile
import unittest

from scripts.evaluate_self_play_puct_convergence import (
    aggregate_convergence,
    policy_signature,
)
from scripts.rerun_self_play_puct_roots import (
    discover_roots,
    load_task_config,
    needs_promotion,
)


def _policy(qs, visits=(4, 4, 4)):
    return [
        {
            "candidate_id": f"c{index}",
            "rank": index,
            "q": q,
            "visits": visits[index],
            "probability": visits[index] / sum(visits),
        }
        for index, q in enumerate(qs)
    ]


class SelfPlayPuctConvergenceTests(unittest.TestCase):
    def test_loads_named_task_from_scenario_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "scenario.json"
            path.write_text(json.dumps({"m-case": {"agent": {"optimize": True}}}))

            self.assertEqual(
                load_task_config(path, "m-case"),
                {"agent": {"optimize": True}},
            )

    def test_discovers_only_q_discriminating_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            pair = root / "pair"
            (pair / "mcts" / "game-000").mkdir(parents=True)
            (pair / "configs").mkdir()
            (pair / "configs" / "scenario.json").write_text("{}")
            for step in range(2):
                (pair / "mcts" / "game-000" / f"step-{step:03d}-state.json").write_text(
                    json.dumps({
                        "board_fingerprint": f"board-{step}",
                        "model_visible_state_signature": f"model-{step}",
                        "game_state_signature": f"game-{step}",
                        "replay_contract": {"seed": 42, "action_prefix": []},
                        "self_play_game": {
                            "player_to_move": 0, "block_length": 0,
                            "handoff_count": 0,
                        },
                    })
                )
            manifest = {
                "case_id": "m-scenario",
                "rules": {},
                "candidate_contract": {"attempt_budget": 128, "top_k": 3},
                "games": [{
                    "trajectory_id": "trajectory-a",
                    "records": [
                        {"step": 0, "candidate_set": [], "search": {
                            "policy_target": _policy((0.0, 0.0, 0.0))}},
                        {"step": 1, "candidate_set": [], "search": {
                            "policy_target": _policy((0.0, 0.1, 0.0))}},
                    ],
                    "captures": [
                        {"step": 0, "snapshot_path": "step-000-state.json"},
                        {"step": 1, "snapshot_path": "step-001-state.json"},
                    ],
                }],
            }
            (pair / "mcts" / "manifest.json").write_text(json.dumps(manifest))

            roots = discover_roots(root)

            self.assertEqual(len(roots), 1)
            self.assertEqual(roots[0]["step"], 1)
            self.assertEqual(roots[0]["model_visible_state_signature"], "model-1")
            self.assertEqual(roots[0]["config_path"], pair / "configs" / "scenario.json")

    def test_promotion_detects_q_or_visit_instability(self):
        stable = {
            label: {"policy_target": _policy((0.2, 0.1, 0.0), (8, 3, 1))}
            for label in ("h2-s24", "h2-s48", "h3-s48", "h5-s48")
        }
        self.assertFalse(needs_promotion(stable))
        unstable = dict(stable)
        unstable["h5-s48"] = {
            "policy_target": _policy((0.1, 0.2, 0.0), (3, 8, 1))
        }
        self.assertTrue(needs_promotion(unstable))

    def test_policy_signature_tracks_q_order_and_visit_top(self):
        signature = policy_signature(_policy((0.0, 0.2, 0.1), (2, 7, 3)))
        self.assertEqual(signature["q_top"], "c1")
        self.assertEqual(signature["visit_top"], "c1")
        self.assertEqual(signature["q_relations"]["c0|c1"], -1)
        self.assertEqual(signature["q_relations"]["c1|c2"], 1)

    def test_aggregate_requires_determinism_and_reports_promoted_stability(self):
        base = {
            "h2-s12-a": {"policy_target": _policy((0.2, 0.1, 0.0))},
            "h2-s12-b": {"policy_target": _policy((0.2, 0.1, 0.0))},
            "h2-s24": {"policy_target": _policy((0.2, 0.1, 0.0))},
            "h2-s48": {"policy_target": _policy((0.2, 0.1, 0.0))},
            "h3-s48": {"policy_target": _policy((0.1, 0.2, 0.0))},
            "h5-s48": {"policy_target": _policy((0.1, 0.2, 0.0))},
            "h2-s96": {"policy_target": _policy((0.1, 0.2, 0.0))},
            "h3-s96": {"policy_target": _policy((0.1, 0.2, 0.0))},
            "h5-s96": {"policy_target": _policy((0.1, 0.2, 0.0))},
        }
        payload = {"complete": True, "roots": [{
            "root_id": "root-a", "game_state_signature": "state-a",
            "promoted": True,
            "original_search": {"policy_target": _policy((0.2, 0.1, 0.0))},
            "conditions": base,
        }]}

        result = aggregate_convergence([payload], expected_roots=1)

        self.assertTrue(result["instrument_deterministic"])
        self.assertEqual(result["promoted_roots"], 1)
        self.assertEqual(result["bounded_search_stable_roots"], 1)
        self.assertEqual(result["bounded_search_stable_game_state_groups"], 1)
        self.assertEqual(result["bounded_q_top_stable_roots"], 1)
        self.assertEqual(result["bounded_visit_top_stable_roots"], 1)
        self.assertEqual(result["bounded_q_order_stable_roots"], 1)


if __name__ == "__main__":
    unittest.main()
