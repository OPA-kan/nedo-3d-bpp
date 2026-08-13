from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from scripts.counterfactual_graph import (
    BoundedGraphExecutor,
    BranchCandidate,
    CounterfactualGraph,
    GraphBudget,
    board_difference,
    board_fingerprint,
    boards_equivalent,
    capture_replay_contract,
    replay_action_prefix,
    state_tensor_from_snapshot,
    write_graph,
)


def make_graph(**budget_overrides):
    return CounterfactualGraph.create(
        root_snapshot_id="snapshot-009",
        case_id="b000-k20",
        root_step=9,
        future_stream_id="case-order-sha256:abc",
        budget=GraphBudget(**budget_overrides),
        provenance={"commit": "deadbeef", "policy": "baseline"},
        board_fingerprint="board-root",
        state_ref="step-009-state.json",
        pool_item_indices=[17, 28, 31],
        cumulative_outcomes={"placed": 9, "volume": 0.71},
    )


class CounterfactualGraphTests(unittest.TestCase):
    def test_state_tensor_preserves_sets_in_container_frame_without_clock(self):
        snapshot = {
            "step": 15,
            "observation": {
                "container_list": [{
                    "index": 0, "length": 2.0, "width": 1.0,
                    "height": 1.5, "center": [2.5, 0.0, 0.75],
                    "shelf": True, "is_prioritized": False,
                    "packed_items": [{
                        "index": 7, "length": 0.4, "width": 0.3,
                        "height": 0.2, "mass": 5, "is_soft": True,
                    }],
                }],
                "pool_list": [{
                    "index": 9, "length": 0.5, "width": 0.2,
                    "height": 0.1, "mass": 3, "is_prioritized": True,
                }],
            },
            "physics": {"packed_items": [{
                "container_index": 0, "item_index": 7,
                "position": [2.6, 0.2, 0.9],
                "quaternion": [0.0, 0.0, 0.0, 1.0],
            }]},
        }

        tensor = state_tensor_from_snapshot(snapshot)

        self.assertNotIn("step", tensor)
        self.assertEqual(tensor["container_count"], 1)
        self.assertEqual(tensor["packed_item_indices"], [7])
        self.assertEqual(tensor["visible_item_indices"], [9])
        features = tensor["packed_item_features"]
        row = tensor["packed_item_values"][0]
        self.assertAlmostEqual(row[features.index("local_x")], 0.1)
        self.assertAlmostEqual(row[features.index("local_z")], 0.15)
        self.assertEqual(row[features.index("is_soft")], 1.0)

    def test_executor_builds_three_step_physical_dag_from_fresh_envs(self):
        created = []

        class Item:
            def __init__(self, index):
                self.index = index

        class Stream:
            def __init__(self):
                self.all_items = [Item(1), Item(2), Item(3)]
                self.visible_pool = list(self.all_items)
                self.current_index = 3

        class Env:
            def __init__(self):
                self.stream_manager = Stream()
                self.packed = []
                self.closed = False
                created.append(self)

            def reset_settings(self):
                self.packed = []

            def set_item_order(self, order):
                if set(order) != {1, 2, 3}:
                    return False
                by_index = {
                    item.index: item for item in self.stream_manager.all_items
                }
                self.stream_manager.all_items = [by_index[index] for index in order]
                return True

            def reset_item_stream(self):
                self.stream_manager.visible_pool = list(
                    self.stream_manager.all_items
                )

            def reset(self, seed):
                return self.observation(), {}

            def observation(self):
                return {
                    "pool_list": [
                        {"index": item.index}
                        for item in self.stream_manager.visible_pool
                    ]
                }

            def step(self, action):
                item = self.stream_manager.visible_pool.pop(action["item_idx"])
                self.packed.append(item.index)
                terminated = not self.stream_manager.visible_pool
                return (
                    self.observation(),
                    0,
                    terminated,
                    False,
                    {
                        "status": {
                            "is_included": True,
                            "is_valid": True,
                            "is_placed_safe": True,
                        }
                    },
                )

            def close(self):
                self.closed = True

        def snapshot(env, observation):
            return {
                "observation": observation,
                "physics": {
                    "packed_items": [
                        {
                            "container_index": 0,
                            "item_index": index,
                            "position": [index / 10, 0, 0.5],
                            "quaternion": [0, 0, 0, 1],
                        }
                        for index in env.packed
                    ]
                },
            }

        def candidates(_env, observation, limit):
            return [
                BranchCandidate(
                    candidate_id=f"item-{item['index']}",
                    command_action={
                        "item_idx": pool_index,
                        "container_idx": 0,
                        "place_pos": [item["index"] / 10, 0, 0.5],
                        "orientation": 0,
                    },
                    selection={
                        "rank": pool_index,
                        "stable_item_index": int(item["index"]),
                    },
                )
                for pool_index, item in enumerate(
                    observation["pool_list"][:limit]
                )
            ]

        def outcomes(env, info, _parent):
            placed = len(env.packed)
            return (
                {**info["status"], "placed_delta": 1, "volume_delta": 1.0},
                {"placed": placed, "volume": float(placed)},
            )

        root_snapshot = snapshot(Env(), {"pool_list": [
            {"index": 1}, {"index": 2}, {"index": 3}
        ]})
        graph = CounterfactualGraph.create(
            root_snapshot_id="root",
            case_id="fake",
            root_step=0,
            future_stream_id="stream-fake",
            budget=GraphBudget(horizon=3, branch_factor=2),
            provenance={"attempt_budget": 32},
            board_fingerprint=board_fingerprint(root_snapshot),
            state_ref=None,
            pool_item_indices=[1, 2, 3],
            cumulative_outcomes={"placed": 0, "volume": 0.0},
        )
        executor = BoundedGraphExecutor(
            env_factory=Env,
            snapshot_factory=snapshot,
            candidate_provider=candidates,
            outcome_provider=outcomes,
        )
        executor.expand(
            graph,
            {
                "seed": 42,
                "item_order": [1, 2, 3],
                "action_prefix": [],
            },
        )
        self.assertTrue(any(node.depth == 3 for node in graph.nodes.values()))
        self.assertTrue(all(env.closed for env in created[1:]))
        depth_two = [node for node in graph.nodes.values() if node.depth == 2]
        self.assertLess(len(depth_two), 4, "equivalent orderings should merge")
        graph.validate()

    def test_forced_candidates_preserve_path_and_pair(self):
        def candidate(index):
            return BranchCandidate(
                candidate_id=f"item-{index}", command_action={"item_idx": index},
                selection={"stable_item_index": index},
            )

        executor = BoundedGraphExecutor(
            env_factory=lambda: None,
            snapshot_factory=lambda _env, _observation: {},
            candidate_provider=lambda _env, _observation, _limit: [
                candidate(1), candidate(2), candidate(3), candidate(4),
            ],
            outcome_provider=lambda _env, _info, _parent: ({}, {}),
            forced_candidate_indices_by_path={(): [4], (4,): [3, 2]},
        )

        root = executor._candidates_for_path(None, {}, (), 3)
        child = executor._candidates_for_path(None, {}, (4,), 3)
        self.assertEqual(
            [row.selection["stable_item_index"] for row in root], [4, 1, 2]
        )
        self.assertEqual(
            [row.selection["stable_item_index"] for row in child], [3, 2, 1]
        )

    def test_forced_candidate_must_exist_in_provider_population(self):
        executor = BoundedGraphExecutor(
            env_factory=lambda: None,
            snapshot_factory=lambda _env, _observation: {},
            candidate_provider=lambda _env, _observation, _limit: [],
            outcome_provider=lambda _env, _info, _parent: ({}, {}),
            forced_candidate_indices_by_path={(): [9]},
        )
        with self.assertRaisesRegex(RuntimeError, "forced candidate item"):
            executor._candidates_for_path(None, {}, (), 3)

    def test_prefix_replay_rebuilds_an_independent_root(self):
        class Env:
            def __init__(self):
                self.item_order = None
                self.actions = []

            def reset_settings(self):
                self.actions = []

            def set_item_order(self, order):
                self.item_order = order
                return True

            def reset_item_stream(self):
                pass

            def reset(self, seed):
                return {"pool": [1, 2], "seed": seed}, {}

            def step(self, action):
                self.actions.append(action)
                return {"pool": [2]}, 0, False, False, {}

        contract = {
            "seed": 42,
            "item_order": [1, 2, 3],
            "action_prefix": [
                {
                    "item_idx": 0,
                    "container_idx": 0,
                    "place_pos": [0, 0, 0.5],
                    "orientation": 0,
                }
            ],
        }
        expected_snapshot = {
            "observation": {"pool_list": [{"index": 2}]},
            "physics": {"packed_items": []},
        }
        expected = board_fingerprint(expected_snapshot)
        result = replay_action_prefix(
            Env(),
            contract,
            expected_fingerprint=expected,
            snapshot_factory=lambda _env, _observation: expected_snapshot,
        )
        self.assertTrue(result.matched)
        self.assertEqual(result.actions_replayed, 1)
        self.assertIsNone(result.error)

    def test_prefix_replay_reports_mismatch_instead_of_labelling_it(self):
        class Env:
            def reset_settings(self):
                pass

            def set_item_order(self, _order):
                return True

            def reset_item_stream(self):
                pass

            def reset(self, seed):
                return {}, {}

        result = replay_action_prefix(
            Env(),
            {"seed": 42, "item_order": [], "action_prefix": []},
            expected_fingerprint="board-expected",
            snapshot_factory=lambda _env, _observation: {
                "observation": {"pool_list": []},
                "physics": {"packed_items": []},
            },
        )
        self.assertFalse(result.matched)
        self.assertEqual(result.error, "reconstruction_mismatch")

    def test_prefix_replay_accepts_submicron_solver_jitter(self):
        class Env:
            def reset_settings(self):
                pass

            def set_item_order(self, _order):
                return True

            def reset_item_stream(self):
                pass

            def reset(self, seed):
                return {}, {}

        expected_snapshot = {
            "observation": {"pool_list": []},
            "physics": {"packed_items": [{
                "container_index": 0,
                "item_index": 1,
                "position": [0.0, 0.0, 0.50000049],
                "quaternion": [0.0, 0.0, 0.0, 1.0],
            }]},
        }
        observed_snapshot = json.loads(json.dumps(expected_snapshot))
        observed_snapshot["physics"]["packed_items"][0]["position"][2] += (
            3e-7
        )

        result = replay_action_prefix(
            Env(),
            {"seed": 42, "item_order": [], "action_prefix": []},
            expected_fingerprint=board_fingerprint(expected_snapshot),
            expected_snapshot=expected_snapshot,
            snapshot_factory=lambda _env, _observation: observed_snapshot,
        )

        self.assertNotEqual(
            result.expected_fingerprint, result.observed_fingerprint
        )
        self.assertTrue(result.matched)
        self.assertIsNone(result.error)

    def test_replay_contract_captures_python_stream_and_action_prefix(self):
        class Item:
            def __init__(self, index):
                self.index = index

        class Stream:
            all_items = [Item(9), Item(2), Item(7), Item(5)]
            visible_pool = [all_items[1], all_items[3]]
            current_index = 4

        class Env:
            stream_manager = Stream()

        contract = capture_replay_contract(
            Env(),
            [
                {
                    "item_idx": 1,
                    "container_idx": 0,
                    "place_pos": [0, 0.1, 0.5],
                    "orientation": 2,
                    "ignored": "policy telemetry",
                }
            ],
            seed=42,
        )
        self.assertEqual(contract["item_order"], [9, 2, 7, 5])
        self.assertEqual(contract["visible_pool_item_indices"], [2, 5])
        self.assertEqual(contract["stream_current_index"], 4)
        self.assertNotIn("ignored", contract["action_prefix"][0])
        self.assertTrue(contract["future_stream_id"].startswith("stream-"))

    def test_board_fingerprint_uses_settled_pose_and_pool_order(self):
        snapshot = {
            "observation": {"pool_list": [{"index": 3}, {"index": 4}]},
            "physics": {
                "packed_items": [
                    {
                        "container_index": 0,
                        "item_index": 9,
                        "position": [0.1, 0.2, 0.30000001],
                        "quaternion": [0, 0, 0, 1],
                    }
                ]
            },
        }
        same = json.loads(json.dumps(snapshot))
        same["physics"]["packed_items"][0]["position"][2] = 0.30000002
        changed = json.loads(json.dumps(snapshot))
        changed["observation"]["pool_list"].reverse()
        self.assertEqual(board_fingerprint(snapshot), board_fingerprint(same))
        self.assertNotEqual(
            board_fingerprint(snapshot), board_fingerprint(changed)
        )

    def test_board_difference_reports_pose_and_pool_mismatch(self):
        expected = {
            "physics": {"packed_items": [{
                "container_index": 0,
                "item_index": 7,
                "position": [1.0, 2.0, 3.0],
                "quaternion": [0.0, 0.0, 0.0, 1.0],
            }]},
            "observation": {"pool_list": [{"index": 2}]},
        }
        observed = json.loads(json.dumps(expected))
        observed["physics"]["packed_items"][0]["position"][2] = 3.002
        observed["physics"]["packed_items"][0]["quaternion"] = [
            0.0, 0.0, 0.0, -1.0
        ]
        observed["observation"]["pool_list"] = [{"index": 3}]

        difference = board_difference(expected, observed)

        self.assertAlmostEqual(
            difference["max_position_abs_delta"], 0.002
        )
        self.assertEqual(
            difference["max_quaternion_abs_delta_sign_invariant"], 0.0
        )
        self.assertEqual(difference["expected_pool"], [2])
        self.assertEqual(difference["observed_pool"], [3])

    def test_board_equivalence_accepts_only_millimetre_bounded_pose_jitter(self):
        expected = {
            "physics": {"packed_items": [{
                "container_index": 0,
                "item_index": 7,
                "position": [1.0, 2.0, 3.0],
                "quaternion": [0.0, 0.0, 0.0, 1.0],
            }]},
            "observation": {"pool_list": [{"index": 2}]},
        }
        jittered = json.loads(json.dumps(expected))
        jittered["physics"]["packed_items"][0]["position"][0] += 8e-4
        jittered["physics"]["packed_items"][0]["quaternion"][0] += 8e-4
        changed_pool = json.loads(json.dumps(jittered))
        changed_pool["observation"]["pool_list"] = [{"index": 3}]
        moved = json.loads(json.dumps(expected))
        moved["physics"]["packed_items"][0]["position"][0] += 3e-3
        rotated = json.loads(json.dumps(expected))
        rotated["physics"]["packed_items"][0]["quaternion"][0] += 3e-3

        self.assertTrue(boards_equivalent(expected, jittered))
        self.assertFalse(boards_equivalent(expected, changed_pool))
        self.assertFalse(boards_equivalent(expected, moved))
        self.assertFalse(boards_equivalent(expected, rotated))

    def test_board_equivalence_accepts_measured_replay_rotation_drift(self):
        expected = {
            "physics": {"packed_items": [{
                "container_index": 0,
                "item_index": 7,
                "position": [1.0, 2.0, 3.0],
                "quaternion": [0.0, 0.0, 0.0, 1.0],
            }]},
            "observation": {"pool_list": [{"index": 2}]},
        }
        replayed = json.loads(json.dumps(expected))
        replayed["physics"]["packed_items"][0]["quaternion"][0] += (
            0.0016165637676563505
        )

        self.assertTrue(boards_equivalent(expected, replayed))

    def test_board_equivalence_accepts_measured_replay_position_drift(self):
        expected = {
            "physics": {"packed_items": [{
                "container_index": 0,
                "item_index": 7,
                "position": [1.0, 2.0, 3.0],
                "quaternion": [0.0, 0.0, 0.0, 1.0],
            }]},
            "observation": {"pool_list": [{"index": 2}]},
        }
        replayed = json.loads(json.dumps(expected))
        replayed["physics"]["packed_items"][0]["position"][0] += (
            0.0013103065951080572
        )

        self.assertTrue(boards_equivalent(expected, replayed))

    def test_horizon_is_explicitly_limited_to_three_through_five(self):
        for invalid in (0, 2, 6):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    GraphBudget(horizon=invalid)
        self.assertEqual(GraphBudget(horizon=3).horizon, 3)
        self.assertEqual(GraphBudget(horizon=5).horizon, 5)

    def test_ids_are_deterministic(self):
        first = make_graph()
        second = make_graph()
        self.assertEqual(first.graph_id, second.graph_id)
        self.assertEqual(first.root_id, second.root_id)

        kwargs = {
            "parent_id": first.root_id,
            "candidate_id": "candidate-17-a",
            "command_action": {"item_idx": 0, "place_pos": [0, 0, 0.5]},
            "child_board_fingerprint": "board-child",
            "child_state_ref": None,
            "child_pool_item_indices": [28, 31, 32],
            "immediate_outcomes": {"is_placed_safe": True},
            "cumulative_outcomes": {"placed": 10, "volume": 0.8},
            "selection": {"policy_selected": False, "rank": 2},
        }
        child, edge = first.add_transition(**kwargs)
        kwargs["parent_id"] = second.root_id
        other_child, other_edge = second.add_transition(**kwargs)
        self.assertEqual(child.node_id, other_child.node_id)
        self.assertEqual(edge.edge_id, other_edge.edge_id)

    def test_equivalent_state_is_a_dag_node_with_multiple_incoming_edges(self):
        graph = make_graph(branch_factor=3)
        common = {
            "parent_id": graph.root_id,
            "command_action": {"item_idx": 0},
            "child_board_fingerprint": "same-afterstate",
            "child_state_ref": None,
            "child_pool_item_indices": [28, 31],
            "immediate_outcomes": {"is_placed_safe": True},
            "cumulative_outcomes": {"placed": 10},
            "selection": {"policy_selected": False},
        }
        child_a, _ = graph.add_transition(candidate_id="a", **common)
        common["command_action"] = {"item_idx": 1}
        child_b, _ = graph.add_transition(candidate_id="b", **common)
        self.assertEqual(child_a.node_id, child_b.node_id)
        self.assertEqual(len(graph.nodes), 2)
        self.assertEqual(len(graph.edges), 2)

    def test_depth_budget_and_branch_budget_are_enforced(self):
        graph = make_graph(horizon=3, branch_factor=1)
        child, _ = graph.add_transition(
            parent_id=graph.root_id,
            candidate_id="a",
            command_action={"item_idx": 0},
            child_board_fingerprint="one",
            child_state_ref=None,
            child_pool_item_indices=[28],
            immediate_outcomes={},
            cumulative_outcomes={},
            selection={},
        )
        with self.assertRaises(RuntimeError):
            graph.add_transition(
                parent_id=graph.root_id,
                candidate_id="b",
                command_action={"item_idx": 1},
                child_board_fingerprint="two",
                child_state_ref=None,
                child_pool_item_indices=[17],
                immediate_outcomes={},
                cumulative_outcomes={},
                selection={},
            )
        parent = child
        for depth in (2, 3):
            parent, _ = graph.add_transition(
                parent_id=parent.node_id,
                candidate_id=f"depth-{depth}",
                command_action={"item_idx": 0},
                child_board_fingerprint=f"depth-{depth}",
                child_state_ref=None,
                child_pool_item_indices=[],
                immediate_outcomes={},
                cumulative_outcomes={},
                selection={},
            )
        with self.assertRaises(ValueError):
            graph.add_transition(
                parent_id=parent.node_id,
                candidate_id="too-deep",
                command_action={},
                child_board_fingerprint="depth-4",
                child_state_ref=None,
                child_pool_item_indices=[],
                immediate_outcomes={},
                cumulative_outcomes={},
                selection={},
            )

    def test_terminal_and_multi_axis_outcomes_survive_serialization(self):
        graph = make_graph()
        graph.add_transition(
            parent_id=graph.root_id,
            candidate_id="fall",
            command_action={"item_idx": 0},
            child_board_fingerprint="fallen-board",
            child_state_ref=None,
            child_pool_item_indices=[28, 31],
            immediate_outcomes={
                "placed_delta": 0,
                "volume_delta": 0.0,
                "cog_z": 0.73,
                "settle_angle_deg": 61.0,
                "priority_delta": 0,
                "soft_delta": 0,
                "is_placed_safe": False,
            },
            cumulative_outcomes={"placed": 9, "volume": 0.71},
            selection={"policy_selected": False, "rank": 7},
            terminal_reason="physical_failure",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "graph.json"
            write_graph(path, graph)
            payload = json.loads(path.read_text(encoding="utf-8"))
        child = next(node for node in payload["nodes"] if node["depth"] == 1)
        self.assertEqual(child["terminal_reason"], "physical_failure")
        outcomes = payload["edges"][0]["immediate_outcomes"]
        self.assertEqual(outcomes["settle_angle_deg"], 61.0)
        self.assertIn("cog_z", outcomes)


if __name__ == "__main__":
    unittest.main()
