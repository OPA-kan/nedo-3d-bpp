import importlib.util
import json
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from scripts.train_self_play_set_value import (
    BehaviorValueEnsemble,
    PlayerZeroLeafValue,
    build_model,
    example_from_state,
    prepare_examples,
    run_grouped_audit,
    select_ensemble_members,
    train_final_ensemble,
    validate_ensemble_size,
)

TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


def row(group, *, fill=None, stability=None, eligible=True):
    heads = {}
    if fill is not None:
        heads["fill_return"] = {
            "value": fill, "target_eligible": True, "censor_reason": None,
        }
    if stability is not None:
        heads["terminal_stability_peak_kinetic_energy"] = {
            "value": stability,
            "target_eligible": True,
            "censor_reason": None,
        }
    return {
        "schema_version": 3,
        "split_group": group,
        "trajectory_group": group,
        "value_target_semantics": "V^pi_behavior_observed_suffix_not_V_star",
        "value_target_eligible": eligible,
        "return_to_go": 5.0,
        "value_heads": heads,
        "value_head_eligibility": {
            name: bool(head["target_eligible"]) for name, head in heads.items()
        },
        "game_features": {
            "player_to_move": 0, "block_length": 2, "handoff_count": 1,
        },
        "state": {
            "container_features": ["length"],
            "container_values": [[2.0]],
            "packed_item_features": ["local_z", "mass"],
            "packed_item_values": [[0.8, 4.0]],
            "visible_item_features": ["mass"],
            "visible_item_values": [[2.0]],
        },
    }


class SelfPlaySetValueTests(unittest.TestCase):
    def test_builds_masked_multi_head_behavior_value_examples(self):
        examples, contract = prepare_examples([
            row("g1", fill=3.0),
            row("g2", stability=8.0),
        ])

        self.assertEqual(contract["semantics"], "V^pi_behavior_not_V_star")
        self.assertEqual(
            contract["head_names"],
            [
                "return_to_go",
                "fill_return",
                "terminal_stability_peak_kinetic_energy",
            ],
        )
        self.assertEqual(examples[0]["target_mask"], [True, True, False])
        self.assertEqual(examples[1]["target_mask"], [True, False, True])
        self.assertEqual(examples[0]["group"], "g1")
        self.assertNotIn("step", examples[0])

    def test_rejects_non_behavior_value_semantics(self):
        bad = row("g1", fill=1.0)
        bad["value_target_semantics"] = "V_star"

        with self.assertRaisesRegex(ValueError, "behavior-policy value"):
            prepare_examples([bad])

    def test_requires_three_to_five_ensemble_members(self):
        for size in (3, 4, 5):
            validate_ensemble_size(size)
        for size in (1, 2, 6):
            with self.assertRaises(ValueError):
                validate_ensemble_size(size)

    def test_shadow_selects_only_the_fold_that_excluded_its_trajectory(self):
        manifest = {
            "members": [{"path": "final.pt"}],
            "group_excluded_ensembles": [
                {
                    "excluded_groups": ["g1", "g3"],
                    "members": [{"path": "fold-0.pt"}],
                },
                {
                    "excluded_groups": ["g2"],
                    "members": [{"path": "fold-1.pt"}],
                },
            ],
        }

        members, excluded = select_ensemble_members(manifest, "g2")

        self.assertEqual(members, [{"path": "fold-1.pt"}])
        self.assertEqual(excluded, ["g2"])
        with self.assertRaisesRegex(ValueError, "found 0"):
            select_ensemble_members(manifest, "unknown")

    def test_inference_example_matches_training_feature_order(self):
        source = row("g1")["state"]
        example = example_from_state(
            source,
            SimpleNamespace(
                current_player=1, block_length=4, handoff_count=2,
            ),
        )

        self.assertEqual(example["game"], [1.0, 4.0, 2.0, 1.0, 1.0, 1.0])
        self.assertEqual(example["packed_item"], [[0.8, 4.0]])

    @mock.patch(
        "scripts.counterfactual_graph.state_tensor_from_snapshot",
        return_value={"tensor": True},
    )
    @mock.patch(
        "scripts.build_replay_dataset.state_snapshot", return_value={}
    )
    @mock.patch(
        "scripts.build_replay_dataset.policy_observation", return_value={}
    )
    def test_leaf_adapter_converts_player_to_move_value_to_player_zero(
        self, _policy, _snapshot, _tensor,
    ):
        class Ensemble:
            def predict(self, state, game_state):
                self.seen = (state, game_state)
                return {
                    "return_to_go": {
                        "mean": 25.0, "variance": 9.0,
                        "members": [22.0, 25.0, 28.0],
                    },
                    "fill_return": {
                        "mean": 3.0, "variance": 1.0,
                        "members": [2.0, 3.0, 4.0],
                    },
                }

        adapter = PlayerZeroLeafValue(Ensemble(), value_scale=50.0)
        state = SimpleNamespace(
            current_player=1, block_length=0, handoff_count=0, placements=2,
        )

        value = adapter(env=object(), observation={}, state=state)

        self.assertEqual(value, -0.5)
        self.assertEqual(adapter.calls[0]["return_to_go_player0_mean"], -25.0)
        self.assertEqual(adapter.calls[0]["heads"]["fill_return"]["mean"], 3.0)

    @unittest.skipUnless(TORCH_AVAILABLE, "torch not installed")
    def test_set_transformer_emits_one_value_per_head(self):
        import torch

        examples, contract = prepare_examples([
            row("g1", fill=3.0), row("g2", stability=8.0),
        ])
        model = build_model(torch, contract, dim=16)
        batch = {
            "game": torch.zeros((2, 6)),
            "container": torch.zeros((2, 1, 1)),
            "container_mask": torch.zeros((2, 1), dtype=torch.bool),
            "packed_item": torch.zeros((2, 1, 2)),
            "packed_item_mask": torch.zeros((2, 1), dtype=torch.bool),
            "visible_item": torch.zeros((2, 1, 1)),
            "visible_item_mask": torch.zeros((2, 1), dtype=torch.bool),
        }

        self.assertEqual(
            tuple(model(batch).shape), (2, len(contract["head_names"]))
        )

    @unittest.skipUnless(TORCH_AVAILABLE, "torch not installed")
    def test_saved_oof_ensemble_excludes_group_and_runs_inference(self):
        examples, contract = prepare_examples([
            row("g1", fill=1.0), row("g2", fill=2.0), row("g3", fill=3.0),
        ])
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory)
            audit = run_grouped_audit(
                examples, contract, ensemble_size=3, epochs=1, folds=3,
                seed=7, oof_output_dir=output,
            )
            final_members = train_final_ensemble(
                examples, contract, ensemble_size=3, epochs=1, seed=11,
                output_dir=output,
            )
            (output / "manifest.json").write_text(json.dumps({
                "semantics": "V^pi_behavior_not_V_star",
                "members": final_members,
                "group_excluded_ensembles": audit[
                    "group_excluded_ensembles"
                ],
            }), encoding="utf-8")

            ensemble = BehaviorValueEnsemble(output, excluded_group="g1")
            prediction = ensemble.predict(
                row("g1")["state"],
                SimpleNamespace(
                    current_player=0, block_length=2, handoff_count=1,
                ),
            )

        self.assertIn("g1", ensemble.excluded_groups)
        self.assertEqual(len(prediction["return_to_go"]["members"]), 3)


if __name__ == "__main__":
    unittest.main()
