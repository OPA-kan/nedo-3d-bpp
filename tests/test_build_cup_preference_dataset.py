import json
import pathlib
import tempfile
import unittest

from scripts.build_cup_preference_dataset import build_dataset


class CupPreferenceDatasetTests(unittest.TestCase):
    def test_strict_pair_joins_snapshot_actions_and_terminal_truth(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            rollout = root / "cup-cell-course" / "rule-grid" / "rollout"
            episode = rollout / "episode-000"
            episode.mkdir(parents=True)
            (episode / "step-000-state.json").write_text("{}")
            candidates = [
                {
                    "root_candidate_id": candidate_id,
                    "safe": True,
                    "stable_item_index": index,
                    "command_action": {
                        "item_idx": index, "container_idx": 0,
                        "place_pos": [float(index), 0, 0],
                        "orientation": 0,
                    },
                    "one_step_vector": {"fill_gain": float(index)},
                }
                for index, candidate_id in ((1, "champ"), (2, "actor"))
            ]
            vectors = [
                {
                    "root_candidate_id": candidate_id,
                    "terminal_genuine": True,
                    "terminal_termination": "no_retained_candidate",
                    "terminal_vector": {
                        "fill_gain": fill, "soft_violation_gain": 0,
                        "priority_covered_gain": 0,
                        "priority_misrouted_gain": 0,
                    },
                }
                for candidate_id, fill in (("champ", 1.0), ("actor", 2.0))
            ]
            manifest = {
                "episodes": [{"records": [{
                    "step": 0, "root_id": "root", "snapshot_path":
                    "step-000-state.json", "board_fingerprint": "board",
                    "timing": {"decision_total_seconds": 9.0},
                    "search": {"root_candidates": candidates},
                    "mining": {
                        "actor_candidate_id": "actor",
                        "champion_candidate_id": "champ",
                        "winner_candidate_id": "actor",
                        "pair_rows": vectors, "fork_seconds": 7.0,
                    },
                }]}],
            }
            (rollout / "manifest.json").write_text(json.dumps(manifest))
            # A second course is required by the leakage-safe group contract.
            second = root / "cup-cell-course2" / "rule-grid" / "rollout"
            (second / "episode-000").mkdir(parents=True)
            (second / "episode-000" / "step-000-state.json").write_text("{}")
            (second / "manifest.json").write_text(json.dumps(manifest))

            dataset = build_dataset(root)

        self.assertEqual(dataset["root_count"], 2)
        self.assertEqual(dataset["group_count"], 2)
        row = dataset["rows"][0]
        self.assertEqual(row["incumbent_candidate_id"], "champ")
        self.assertEqual(row["selected_candidate_id"], "actor")
        self.assertEqual(row["estimated_no_terminal_decision_seconds"], 2.0)
        self.assertEqual(
            [candidate["terminal_vector"]["fill_gain"]
             for candidate in row["candidates"]],
            [1.0, 2.0],
        )

    def test_one_sided_verdict_is_skipped_not_imported_or_fatal(self):
        """A legacy fork whose loser never reached a terminal.

        Cup 006's rule-alpha produced one: the actor's action turned out
        physically unsafe inside the fork, so it left the terminal audit
        entirely and the champion stood alone on a one-candidate frontier
        with terminal_truth_complete still True. That is not strict
        dominance -- it must not become a training pair, and it must not
        abort the whole Cup either.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)

            def write(cell: str, records: list) -> None:
                rollout = root / cell / "rule-grid" / "rollout"
                (rollout / "episode-000").mkdir(parents=True)
                (rollout / "episode-000" / "step-000-state.json").write_text(
                    "{}"
                )
                (rollout / "manifest.json").write_text(
                    json.dumps({"episodes": [{"records": records}]})
                )

            candidates = [
                {
                    "root_candidate_id": candidate_id,
                    "safe": True,
                    "stable_item_index": index,
                    "command_action": {
                        "item_idx": index, "container_idx": 0,
                        "place_pos": [float(index), 0, 0],
                        "orientation": 0,
                    },
                    "one_step_vector": {"fill_gain": float(index)},
                }
                for index, candidate_id in ((1, "champ"), (2, "actor"))
            ]

            def record(root_id: str, actor_terminal: bool) -> dict:
                rows = [{
                    "root_candidate_id": "champ",
                    "terminal_genuine": True,
                    "terminal_termination": "no_retained_candidate",
                    "terminal_vector": {
                        "fill_gain": 1.0, "soft_violation_gain": 0,
                        "priority_covered_gain": 0,
                        "priority_misrouted_gain": 0,
                    },
                }, {
                    "root_candidate_id": "actor",
                    # The unsafe side carries no terminal truth at all.
                    "terminal_genuine": True if actor_terminal else None,
                    "terminal_termination": (
                        "no_retained_candidate" if actor_terminal else None
                    ),
                    "terminal_vector": {
                        "fill_gain": 2.0, "soft_violation_gain": 0,
                        "priority_covered_gain": 0,
                        "priority_misrouted_gain": 0,
                    } if actor_terminal else None,
                }]
                return {
                    "step": 0, "root_id": root_id,
                    "snapshot_path": "step-000-state.json",
                    "board_fingerprint": "board",
                    "timing": {"decision_total_seconds": 9.0},
                    "search": {"root_candidates": candidates},
                    "mining": {
                        "actor_candidate_id": "actor",
                        "champion_candidate_id": "champ",
                        # The champion "won" a one-horse race.
                        "winner_candidate_id": (
                            "actor" if actor_terminal else "champ"
                        ),
                        "terminal_truth_complete": True,
                        "pair_rows": rows, "fork_seconds": 7.0,
                    },
                }

            write("cup-cell-course", [
                record("good", True), record("one-sided", False),
            ])
            write("cup-cell-course2", [record("good2", True)])

            dataset = build_dataset(root)

        self.assertEqual(dataset["root_count"], 2)
        self.assertEqual(dataset["one_sided_verdicts_skipped"], 1)
        self.assertNotIn(
            "one-sided",
            [row["source_root_id"] for row in dataset["rows"]],
        )

    def test_ties_are_not_imported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            rollout = root / "cup-cell-course" / "rule-grid" / "rollout"
            (rollout / "episode-000").mkdir(parents=True)
            (rollout / "manifest.json").write_text(json.dumps({
                "episodes": [{"records": [{"mining": {
                    "actor_candidate_id": "a",
                    "champion_candidate_id": "b",
                    "winner_candidate_id": None,
                }}]}]
            }))
            with self.assertRaisesRegex(ValueError, "no strict Cup"):
                build_dataset(root)


if __name__ == "__main__":
    unittest.main()
