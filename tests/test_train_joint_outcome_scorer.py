import importlib.util
import unittest

import numpy as np

from scripts.train_joint_outcome_scorer import (
    DOMINANCE_HEADS,
    TARGET_HEADS,
    _kendall_tau,
    _measured_dominance,
    build_arrays,
    compute_stats,
    evaluate_held_out,
    prepare_examples,
    split_by_cell,
)

TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


def dataset_row(cell, root, candidate, world, value):
    return {
        "cell_id": cell,
        "root_id": root,
        "root_candidate_id": candidate,
        "exogenous_world_id": f"world-{world}",
        "features": {
            "state": {
                "container_values": [[1.0, 2.0]],
                "packed_item_values": [],
                "visible_item_values": [[0.5, 0.5]],
                "visible_item_indices": [0],
            },
            "action": [0.0, 1.0, 0.1, 0.2, 0.3],
            "acting_item": [0.5, 0.5],
        },
        "targets": {head: value for head in TARGET_HEADS},
        "target_mask": {head: True for head in TARGET_HEADS},
    }


class PreparationTests(unittest.TestCase):
    def test_split_by_cell_holds_out_whole_cells(self):
        examples = prepare_examples([
            dataset_row("cell-a", "r1", "a", 0, 1.0),
            dataset_row("cell-b", "r2", "a", 0, 2.0),
        ])

        train, held = split_by_cell(examples, {"cell-b"})

        self.assertEqual([row["cell_id"] for row in train], ["cell-a"])
        self.assertEqual([row["cell_id"] for row in held], ["cell-b"])
        with self.assertRaises(ValueError):
            split_by_cell(examples, {"cell-a", "cell-b"})

    def test_arrays_are_padded_and_normalized(self):
        examples = prepare_examples([
            dataset_row("cell-a", "r1", "a", 0, 1.0),
            dataset_row("cell-a", "r1", "b", 0, 3.0),
        ])
        stats = compute_stats(examples)

        arrays = build_arrays(examples, stats)

        self.assertEqual(arrays["targets"].shape, (2, len(TARGET_HEADS)))
        self.assertTrue(np.isfinite(arrays["targets"]).all())
        self.assertFalse(arrays["packed_item_mask"][:, 0].any())

    def test_fully_censored_rows_are_dropped(self):
        censored = dataset_row("cell-a", "r1", "a", 0, 1.0)
        censored["target_mask"] = {head: False for head in TARGET_HEADS}
        censored["targets"] = {head: None for head in TARGET_HEADS}

        examples = prepare_examples([
            censored, dataset_row("cell-a", "r1", "b", 0, 2.0),
        ])

        self.assertEqual(len(examples), 1)


class MetricTests(unittest.TestCase):
    def test_kendall_tau_handles_perfect_and_reversed_order(self):
        self.assertEqual(_kendall_tau([1, 2, 3], [10, 20, 30]), 1.0)
        self.assertEqual(_kendall_tau([1, 2, 3], [30, 20, 10]), -1.0)
        self.assertIsNone(_kendall_tau([1, 1], [2, 3]))

    def test_measured_dominance_uses_shared_worlds_only(self):
        examples = prepare_examples([
            dataset_row("c", "r", "a", 0, 2.0),
            dataset_row("c", "r", "a", 1, 2.0),
            dataset_row("c", "r", "b", 0, 1.0),
        ])
        candidates = {"a": [0, 1], "b": [2]}
        head_indices = [TARGET_HEADS.index(head) for head in DOMINANCE_HEADS]
        signs = np.ones(len(DOMINANCE_HEADS))

        result = _measured_dominance(
            examples, candidates, "a", "b", head_indices, signs
        )

        self.assertEqual(result, 1.0)

    def test_evaluate_recovers_ordering_from_exact_predictions(self):
        examples = prepare_examples([
            dataset_row("c", "r", "a", world, 2.0) for world in range(2)
        ] + [
            dataset_row("c", "r", "b", world, 1.0) for world in range(2)
        ])
        means = np.asarray([row["targets"] for row in examples])
        members = means[None, :, :].repeat(2, axis=0)
        prediction = {
            "member_means": members,
            "mean": means,
            "epistemic_variance": np.zeros_like(means),
            "member_factors": np.stack([
                np.stack([np.eye(len(TARGET_HEADS)) * 1e-3] * len(examples))
            ] * 2),
        }

        report = evaluate_held_out(examples, prediction, draws=64)

        self.assertEqual(report["roots"], 1)
        tau = report["ordering_kendall_tau"]["game_reward"]
        self.assertEqual(tau["mean"], 1.0)
        self.assertEqual(report["dominance"]["direction_agreement"], 1.0)
        self.assertEqual(report["top_pick_regret"]["fill_gain"]["mean"], 0.0)


@unittest.skipUnless(TORCH_AVAILABLE, "torch not installed")
class ModelTests(unittest.TestCase):
    def test_fit_member_and_predict_shapes(self):
        import torch

        from scripts.train_joint_outcome_scorer import (
            build_model,
            fit_member,
            joint_nll,
            predict,
        )

        examples = prepare_examples([
            dataset_row("c", f"r{i}", name, world, float(i + world))
            for i in range(3)
            for name in ("a", "b")
            for world in range(2)
        ])
        stats = compute_stats(examples)
        arrays = build_arrays(examples, stats)
        widths = {
            "container": 2, "packed_item": 22, "visible_item": 2,
            "action": len(examples[0]["action"]),
        }
        widths["packed_item"] = len(np.asarray(stats["packed_item"][0]))

        model = fit_member(
            torch, arrays, widths,
            groups=[row["root_id"] for row in examples],
            seed=7, epochs=1, dim=16,
        )
        prediction = predict(torch, [model, model], arrays, stats)

        self.assertEqual(
            prediction["mean"].shape, (len(examples), len(TARGET_HEADS))
        )
        self.assertEqual(
            prediction["member_factors"].shape,
            (2, len(examples), len(TARGET_HEADS), len(TARGET_HEADS)),
        )
        batch_mean, batch_factor = model({
            key: (
                torch.from_numpy(value).bool()
                if value.dtype == bool else torch.from_numpy(value).float()
            )
            for key, value in arrays.items()
        })
        loss = joint_nll(
            torch, batch_mean, batch_factor,
            torch.from_numpy(arrays["targets"]).float(),
            torch.from_numpy(arrays["target_mask"]).bool(),
        )
        self.assertTrue(torch.isfinite(loss))


if __name__ == "__main__":
    unittest.main()
