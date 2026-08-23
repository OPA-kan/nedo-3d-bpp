import json
import pathlib
import tempfile
import unittest

from scripts.build_paired_joint_outcome_dataset import (
    TARGET_HEADS,
    build_rows,
)


def fake_state(*_args):
    return {
        "container_values": [[1.0, 2.0]],
        "packed_item_values": [],
        "visible_item_values": [[0.5] * 3, [0.7] * 3],
        "visible_item_indices": [4, 9],
    }


def sample(candidate, replica, *, censored=False):
    return {
        "root_id": "root-1",
        "outcome_sample_id": f"sample-{candidate}-{replica}",
        "candidate_set_id": "set-1",
        "root_candidate_id": candidate,
        "exogenous_world_id": f"world-{replica}",
        "exogenous_world_sample_index": replica,
        "termination": "simulator_truncated" if censored else "horizon",
        "continuation_censored": censored,
        "root_candidate_provenance": {"source": "legacy_provider"},
        "raw_outcome_vector": {
            head: None if censored else 1.0 for head in TARGET_HEADS
        },
        "head_eligibility": {
            head: not censored for head in TARGET_HEADS
        },
    }


def manifest(samples):
    return {
        "selection": {"mcts": {"root_allocation_mode": "paired_round_robin"}},
        "games": [{
            "records": [{
                "step": 0,
                "state_snapshot_path": "step-000-state.json",
                "candidate_set": [
                    {
                        "candidate_id": "a",
                        "command_action": {
                            "item_idx": 0, "container_idx": 0,
                            "place_pos": [0.1, 0.2, 0.3], "orientation": 2,
                        },
                        "selection": {"rank": 0, "stable_item_index": 4},
                    },
                    {
                        "candidate_id": "b",
                        "command_action": {
                            "item_idx": 1, "container_idx": 0,
                            "place_pos": [0.4, 0.5, 0.6], "orientation": 1,
                        },
                        "selection": {"rank": 1, "stable_item_index": 9},
                    },
                ],
                "search": {"multi_head_branch_samples": samples},
            }],
        }],
    }


class BuildPairedJointOutcomeDatasetTests(unittest.TestCase):
    def write_run(self, payload):
        run_dir = pathlib.Path(tempfile.mkdtemp()) / "paired"
        run_dir.mkdir(parents=True)
        (run_dir / "manifest.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        return run_dir

    def test_rows_join_by_stable_item_index_and_keep_masks(self):
        run_dir = self.write_run(manifest([
            sample("a", 0), sample("b", 0), sample("a", 1, censored=True),
        ]))

        rows = build_rows(run_dir, cell_id="cell-x", state_loader=fake_state)

        self.assertEqual(len(rows), 3)
        by_candidate = {row["root_candidate_id"]: row for row in rows[:2]}
        self.assertEqual(
            by_candidate["a"]["features"]["acting_item"], [0.5] * 3
        )
        self.assertEqual(
            by_candidate["b"]["features"]["acting_item"], [0.7] * 3
        )
        self.assertEqual(
            by_candidate["b"]["features"]["action"][:2], [0.0, 1.0]
        )
        censored = rows[2]
        self.assertTrue(censored["continuation_censored"])
        self.assertTrue(
            all(value is None for value in censored["targets"].values())
        )
        self.assertFalse(any(censored["target_mask"].values()))

    def test_provenance_stays_out_of_features(self):
        run_dir = self.write_run(manifest([sample("a", 0)]))

        row = build_rows(
            run_dir, cell_id="cell-x", state_loader=fake_state
        )[0]

        self.assertEqual(
            sorted(row["features"]), ["acting_item", "action", "state"]
        )
        self.assertEqual(
            row["audit_only"]["provenance"]["source"], "legacy_provider"
        )
        self.assertEqual(row["audit_only"]["selection_rank"], 0)

    def test_non_paired_run_is_rejected(self):
        payload = manifest([sample("a", 0)])
        payload["selection"]["mcts"]["root_allocation_mode"] = "scalar_puct"
        run_dir = self.write_run(payload)

        with self.assertRaises(ValueError):
            build_rows(run_dir, cell_id="cell-x", state_loader=fake_state)


if __name__ == "__main__":
    unittest.main()
