import importlib.util
import json
import pathlib
import sys
import unittest

import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / "agent" / "agent.py"
SPEC = importlib.util.spec_from_file_location("matrix_agent", AGENT_PATH)
agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent
SPEC.loader.exec_module(agent)

BUILDER_SPEC = importlib.util.spec_from_file_location(
    "build_scenario_matrix", ROOT / "scripts" / "build_scenario_matrix.py"
)
builder = importlib.util.module_from_spec(BUILDER_SPEC)
sys.modules[BUILDER_SPEC.name] = builder
BUILDER_SPEC.loader.exec_module(builder)

SOURCE = json.loads(
    (ROOT / "simulator" / "configs" / "sample_config.json")
    .read_text(encoding="utf-8")
)
MATRIX = builder.build_all(SOURCE, look_ahead=10, policy_timeout=8.0)


def observation_from(case: dict, visible: int = 10) -> dict:
    """The observation shape the harness hands policy() on the first step."""
    return {
        "pool_list": case["item_stream"]["item_list"][:visible],
        "container_list": builder.observation_containers(case),
    }


class ScenarioMatrixContractTests(unittest.TestCase):
    """
    Coverage probe for the container combinations COMPETITION_RULES section
    2 says will be posed.

    The bundled sample covers exactly one axis: both cases are
    single-container, empty, with no dedicated container, differing only in
    the shelf. The whole development suite derives from those two cases, so
    two containers, a pre-loaded initial state and a priority-dedicated
    container have never been executed. The rules also require one agent to
    self-detect the setup and handle every task, so these branches WILL be
    taken in evaluation.

    These are contract tests, not benchmarks: they assert the agent returns
    a well-formed, in-bounds action for every combination, not that it
    scores well. The physical counterpart is
    scripts/run_scenario_matrix.py.
    """

    def test_matrix_covers_every_declared_axis(self) -> None:
        containers = {
            len(c["containers"]["container_list"])
            for case in MATRIX.values() for c in case.values()
        }
        flags = [
            (
                any(k["require_shelf"] for k in c["containers"]["container_list"]),
                any(k["is_prioritized"] for k in c["containers"]["container_list"]),
                sum(len(k["packed_items"]) for k in c["containers"]["container_list"]) > 0,
            )
            for case in MATRIX.values() for c in case.values()
        ]
        self.assertEqual(containers, {1, 2}, "both container counts required")
        self.assertTrue(any(shelf for shelf, _, _ in flags))
        self.assertTrue(any(ded for _, ded, _ in flags))
        self.assertTrue(any(pre for _, _, pre in flags))

    def test_matrix_keeps_task_b_single_slot_replenishment(self) -> None:
        for name, config in MATRIX.items():
            case = next(iter(config.values()))
            with self.subTest(scenario=name):
                self.assertEqual(case["item_stream"]["max_space"], 1)

    def test_default_stream_variant_preserves_original_order(self) -> None:
        case = next(iter(MATRIX["dual-empty"].values()))
        expected = SOURCE["000"]["item_stream"]["item_list"]
        self.assertEqual(case["item_stream"]["item_list"], expected)
        self.assertEqual(
            case["item_stream"]["development_stream_variant"], "original"
        )

    def test_declared_stream_variants_change_model_input_and_keep_ids_unique(self) -> None:
        variants = {
            name: builder.build_all(
                SOURCE, look_ahead=10, policy_timeout=8.0,
                stream_variant=name,
            )["dual-empty"]["m-dual-empty"]["item_stream"]["item_list"]
            for name in (
                "source-001", "reverse-000", "interleave", "rotate-000-7",
            )
        }
        original = SOURCE["000"]["item_stream"]["item_list"]
        for name, items in variants.items():
            with self.subTest(variant=name):
                self.assertNotEqual(items, original)
                indices = [int(item["index"]) for item in items]
                self.assertEqual(len(indices), len(set(indices)))
        self.assertEqual(
            variants["reverse-000"][0]["index"], original[-1]["index"]
        )
        self.assertEqual(variants["rotate-000-7"][0]["index"], original[7]["index"])
        self.assertEqual(
            len(variants["interleave"]),
            len(SOURCE["000"]["item_stream"]["item_list"])
            + len(SOURCE["001"]["item_stream"]["item_list"]),
        )

    def test_every_scenario_yields_a_wellformed_action(self) -> None:
        for name, config in MATRIX.items():
            case = next(iter(config.values()))
            with self.subTest(scenario=name):
                solver = agent.Agent("")
                solver.get_init_states({
                    "optimize": case["agent"]["optimize"],
                    "container_list": case["containers"]["container_list"],
                })
                action = solver.policy(observation_from(case))

                self.assertIsNotNone(action, "policy returned nothing")
                for key in ("item_idx", "container_idx", "place_pos",
                            "orientation"):
                    self.assertIn(key, action)
                self.assertIn(
                    int(action["container_idx"]),
                    range(len(case["containers"]["container_list"])),
                )
                self.assertEqual(len(action["place_pos"]), 3)
                self.assertTrue(
                    np.all(np.isfinite(np.asarray(action["place_pos"],
                                                  dtype=np.float64))),
                    "place_pos must be finite",
                )
                self.assertIn(int(action["orientation"]), range(6))

    def test_preloaded_state_blocks_the_space_it_occupies(self) -> None:
        """
        A pre-loaded container must constrain the agent.

        The first version of this test only checked that the action was
        not within 1e-6 of a seated item's CENTRE, which a placement 1 cm
        inside the same box would pass. It asserted almost nothing while
        reading as a real occupancy check. This uses the agent's own
        geometry instead: the chosen placement's AABB must not intersect
        any pre-loaded item's AABB.
        """
        config = MATRIX["single-preloaded"]
        case = next(iter(config.values()))
        container = case["containers"]["container_list"][0]
        self.assertTrue(container["packed_items"])

        observation = observation_from(case)
        observation["container_list"][0]["packed_items"] = [
            dict(item) for item in container["packed_items"]
        ]
        solver = agent.Agent("")
        solver.get_init_states({
            "optimize": False,
            "container_list": builder.observation_containers(case),
        })
        action = solver.policy(observation)
        self.assertIsNotNone(action)

        # item_idx is the POOL index, not the item's own `index` field
        # (env.py:62,210 -- spaces.Discrete(lookahead_k)). Resolving it as
        # an item id raised StopIteration here, which is worth recording:
        # a test that had silently used the wrong one would have compared
        # the wrong box's dimensions and still passed most of the time.
        chosen = observation["pool_list"][int(action["item_idx"])]
        size = agent.get_rotated_dimensions(
            chosen["length"], chosen["width"], chosen["height"],
            int(action["orientation"]),
        )
        target = np.asarray(action["place_pos"], dtype=np.float64)
        lo = target - np.asarray(size, dtype=np.float64) / 2.0
        hi = target + np.asarray(size, dtype=np.float64) / 2.0

        for seated in container["packed_items"]:
            centre = np.asarray(seated["pos"], dtype=np.float64)
            half = np.asarray(
                [seated["length"], seated["width"], seated["height"]],
                dtype=np.float64,
            ) / 2.0
            overlap = np.all(lo < centre + half) and np.all(hi > centre - half)
            self.assertFalse(
                bool(overlap),
                f"placement overlaps pre-loaded item {seated['index']}",
            )

    def test_dedicated_container_is_offered_to_priority_items(self) -> None:
        """
        With a dedicated container present the agent must be able to route
        a priority item into it. Asserts reachability, not that every
        priority item goes there -- routing policy is a separate question
        from the branch being wired at all.
        """
        config = MATRIX["dual-dedicated-priority"]
        case = next(iter(config.values()))
        containers = builder.observation_containers(case)
        dedicated = [
            index for index, c in enumerate(containers) if c["is_prioritized"]
        ]
        self.assertTrue(dedicated, "scenario must declare a dedicated container")

        priority_items = [
            item for item in case["item_stream"]["item_list"]
            if item.get("is_prioritized")
        ]
        self.assertTrue(priority_items, "sample has priority items")

        solver = agent.Agent("")
        solver.get_init_states(
            {"optimize": False, "container_list": containers}
        )
        action = solver.policy({
            "pool_list": priority_items[:1],
            "container_list": [dict(c) for c in containers],
        })

        self.assertIsNotNone(action)
        self.assertIn(
            int(action["container_idx"]),
            dedicated,
            "a lone priority item was not routed to the dedicated container",
        )

    def test_two_containers_receive_distinct_geometry(self) -> None:
        """
        Renamed after audit. The previous version was called
        `test_two_containers_are_both_reachable` and its docstring claimed
        to catch a world/local conversion that ignored the container
        offset -- but its assertion was `reached <= {0, 1} and reached`,
        which passes when every action goes to container 0. It tested
        nothing the well-formedness test did not already cover, under a
        name that promised the opposite.

        What this checks is the precondition it can check without physics:
        the two containers are laid out at different offsets and the agent
        derives different geometry for them. Whether the agent ever CHOOSES
        the second container is a policy property, verified physically
        instead -- the dual-dedicated-priority episode used containers 0
        and 1 for 22 and 9 placements. `test_dedicated_container_is_
        offered_to_priority_items` is the unit-level proof that index 1 is
        addressable at all, because routing there is forced.
        """
        config = MATRIX["dual-empty"]
        case = next(iter(config.values()))
        containers = builder.observation_containers(case)

        self.assertEqual(len(containers), 2)
        self.assertNotEqual(
            containers[0]["center"][0], containers[1]["center"][0],
            "the two containers must not sit at the same offset",
        )

        solver = agent.Agent("")
        solver.get_init_states(
            {"optimize": False, "container_list": containers}
        )
        templates = solver._container_templates
        self.assertEqual(len(templates), 2)
        self.assertNotEqual(
            tuple(templates[0]["center"]), tuple(templates[1]["center"]),
            "the agent collapsed both containers onto one offset",
        )


if __name__ == "__main__":
    unittest.main()
