import random
import unittest

from scripts.self_play_packing_search import PuctTree, build_return_targets


def candidate(name, rank):
    return {
        "candidate_id": name,
        "selection": {"rank": rank},
        "command_action": {"item_idx": rank},
    }


class PuctTreeTests(unittest.TestCase):
    def test_seeded_root_dirichlet_noise_changes_prior_and_preserves_mass(self):
        rows = [candidate("a", 0), candidate("b", 1), candidate("c", 2)]
        left = PuctTree(cpuct=2.0, prior_mode="uniform")
        right = PuctTree(cpuct=2.0, prior_mode="uniform")

        left_noise = left.add_dirichlet_noise(
            "root", rows, alpha=0.3, epsilon=0.25,
            rng=random.Random(19),
        )
        right_noise = right.add_dirichlet_noise(
            "root", rows, alpha=0.3, epsilon=0.25,
            rng=random.Random(19),
        )

        self.assertEqual(left_noise, right_noise)
        policy = left.policy("root")
        self.assertAlmostEqual(sum(row["prior"] for row in policy), 1.0)
        self.assertTrue(any(
            abs(row["prior"] - row["base_prior"]) > 1e-6
            for row in policy
        ))

    def test_uniform_cold_start_probes_each_root_action(self):
        rows = [candidate("a", 0), candidate("b", 1), candidate("c", 2)]
        tree = PuctTree(cpuct=2.0, prior_mode="uniform")

        chosen = []
        for _ in range(3):
            row = tree.select("root", player=0, candidates=rows)
            chosen.append(row["candidate_id"])
            tree.backup([("root", row["candidate_id"], 0)], [0.0, 0.0])

        self.assertEqual(chosen, ["a", "b", "c"])
        self.assertEqual(
            [row["visits"] for row in tree.policy("root")], [1, 1, 1]
        )
        self.assertEqual(
            [row["probability"] for row in tree.policy("root")],
            [1 / 3, 1 / 3, 1 / 3],
        )

    def test_backup_uses_player_at_each_node(self):
        rows = [candidate("a", 0)]
        tree = PuctTree(cpuct=1.0, prior_mode="uniform")
        root = tree.select("root", player=0, candidates=rows)
        child = tree.select("child", player=1, candidates=rows)

        tree.backup([
            ("root", root["candidate_id"], 0),
            ("child", child["candidate_id"], 1),
        ], [0.75, -0.75])

        self.assertEqual(tree.policy("root")[0]["q"], 0.75)
        self.assertEqual(tree.policy("child")[0]["q"], -0.75)

    def test_visit_action_sampling_is_seeded_and_shared(self):
        rows = [candidate("a", 0), candidate("b", 1)]
        tree = PuctTree(cpuct=1.0, prior_mode="uniform")
        for name in ("a", "a", "a", "b"):
            tree.backup([("root", name, 0)], [0.0, 0.0], candidates=rows)

        left = tree.choose(
            "root", rows, temperature=1.0, rng=random.Random(19)
        )
        right = tree.choose(
            "root", rows, temperature=1.0, rng=random.Random(19)
        )

        self.assertEqual(left["candidate_id"], right["candidate_id"])


class ReturnTargetTests(unittest.TestCase):
    def test_targets_are_suffix_returns_from_each_players_perspective(self):
        captures = [
            {
                "step": 0, "snapshot_path": "s0.json", "player_to_move": 0,
                "rewards_before": [0.0, 0.0],
            },
            {
                "step": 1, "snapshot_path": "s1.json", "player_to_move": 1,
                "rewards_before": [-5.0, 5.0],
            },
            {
                "step": 2, "snapshot_path": "s2.json", "player_to_move": 0,
                "rewards_before": [-5.0, 5.0],
            },
        ]
        records = [
            {
                "step": 0, "selected_candidate_id": "a",
                "search": {"policy_target": [
                    {"candidate_id": "a", "probability": 0.75, "visits": 3},
                    {"candidate_id": "b", "probability": 0.25, "visits": 1},
                ]},
            },
            {"step": 1, "selected_candidate_id": "b"},
        ]

        targets = build_return_targets(
            captures, records, final_rewards=[45.0, -45.0],
            value_target_eligible=True,
        )

        self.assertEqual(targets[0]["return_to_go"], 45.0)
        self.assertEqual(targets[1]["return_to_go"], -50.0)
        self.assertEqual(targets[2]["return_to_go"], 50.0)
        self.assertEqual(targets[0]["policy_target"][0]["visits"], 3)
        self.assertEqual(targets[1]["policy_target"], [
            {"candidate_id": "b", "probability": 1.0, "visits": None}
        ])
        self.assertEqual(targets[2]["policy_target"], [])
        self.assertFalse(targets[2]["policy_target_eligible"])
        self.assertTrue(all(row["value_target_eligible"] for row in targets))

    def test_censored_episode_keeps_return_but_marks_value_ineligible(self):
        targets = build_return_targets(
            [{
                "step": 0, "player_to_move": 0,
                "rewards_before": [0.0, 0.0],
            }], [], final_rewards=[0.0, 0.0], value_target_eligible=False,
        )

        self.assertEqual(targets[0]["return_to_go"], 0.0)
        self.assertFalse(targets[0]["value_target_eligible"])

    def test_non_zero_sum_reward_accounting_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "zero-sum"):
            build_return_targets(
                [{
                    "step": 0, "player_to_move": 0,
                    "rewards_before": [0.0, 0.0],
                }], [], final_rewards=[1.0, 0.0],
                value_target_eligible=True,
            )


if __name__ == "__main__":
    unittest.main()
