import pathlib
import subprocess
import sys
import unittest

from scripts.evaluate_self_play_component_paired_continuation import (
    discovery_proposals,
    summarize,
)
from scripts.aggregate_self_play_component_paired_continuation import aggregate
from tests.test_evaluate_self_play_component_value_shadow import _estimate


def action(item):
    return {
        "item_idx": item,
        "container_idx": 0,
        "place_pos": [0.0, 0.0, 0.5],
        "orientation": 0,
    }


class ComponentPairedContinuationTests(unittest.TestCase):
    def test_script_can_be_invoked_by_path(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/evaluate_self_play_component_paired_continuation.py",
                "--help",
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_discovery_joins_selected_candidate_to_physical_actions(self):
        shadow = {
            "records": [{
                "eligible": True,
                "pair_id": "pair-1",
                "step": 4,
                "incumbent_candidate_id": "a",
                "candidate_estimates": {
                    "a": _estimate(5.0, 4.0, 1.0),
                    "b": _estimate(6.0, 4.0, 0.0),
                },
            }]
        }
        dataset = [{
            "pair_id": "pair-1",
            "case_id": "m-case",
            "step": 4,
            "trajectory_group": "trajectory-1",
            "future_stream_id": "stream-1",
            "policy_target": [
                {"candidate_id": "a", "command_action": action(1)},
                {"candidate_id": "b", "command_action": action(2)},
            ],
        }]

        proposals = discovery_proposals(shadow, dataset, beta=0.0)

        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["selected_candidate_id"], "b")
        self.assertEqual(proposals[0]["selected_action"], action(2))

    def test_summary_keeps_official_axes_and_stability_separate(self):
        result = summarize(
            [{
                "execution_valid": True,
                "comparison": {
                    "pareto_relation": "search_dominates",
                    "raw_deltas": {
                        "fill": 2.0,
                        "cog": -0.1,
                        "placement": 0.0,
                        "soft": 0.0,
                        "gate": 0.0,
                        "stability.max_shift": 0.2,
                        "stability.peak_kinetic_energy": 3.0,
                        "stability.items_shifted": 1.0,
                        "stability.items_toppled": 0.0,
                    },
                },
            }],
            beta=0.25,
            proposal_count=1,
        )

        self.assertFalse(result["official_score_claim"])
        self.assertEqual(
            result["mean_candidate_minus_incumbent"]["fill"], 2.0
        )
        self.assertEqual(
            result["mean_candidate_minus_incumbent"]["stability.max_shift"],
            0.2,
        )

    def test_aggregate_requires_every_frozen_proposal_exactly_once(self):
        comparison = {
            "pareto_relation": "incomparable",
            "raw_deltas": {
                name: 0.0 for name in (
                    "fill", "cog", "placement", "soft", "gate",
                    "stability.max_shift", "stability.peak_kinetic_energy",
                    "stability.items_shifted", "stability.items_toppled",
                )
            },
        }
        shards = [
            {
                "discovery_beta": 0.25,
                "proposal_count": 2,
                "records": [{
                    "pair_id": "p0", "step": 1,
                    "execution_valid": True, "comparison": comparison,
                }],
            },
            {
                "discovery_beta": 0.25,
                "proposal_count": 2,
                "records": [{
                    "pair_id": "p1", "step": 2,
                    "execution_valid": True, "comparison": comparison,
                }],
            },
        ]

        result = aggregate(shards, expected_proposals=2)

        self.assertEqual(result["executed_records"], 2)
        self.assertEqual(result["valid_records"], 2)

    def test_workflow_freezes_two_shard_beta_quarter_pilot(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        text = (
            root / ".github" / "workflows"
            / "self-play-puct-convergence.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("inputs.experiment == 'component-pair'", text)
        self.assertIn("--beta 0.25", text)
        self.assertIn("shard_index: [0, 1]", text)
        self.assertIn("--expected-proposals", text)


if __name__ == "__main__":
    unittest.main()
