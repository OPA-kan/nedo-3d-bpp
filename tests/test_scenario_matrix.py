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

RUNNER_SPEC = importlib.util.spec_from_file_location(
    "run_scenario_matrix", ROOT / "scripts" / "run_scenario_matrix.py"
)
runner = importlib.util.module_from_spec(RUNNER_SPEC)
sys.modules[RUNNER_SPEC.name] = runner
RUNNER_SPEC.loader.exec_module(runner)

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

    def test_preloaded_items_are_inside_the_container(self) -> None:
        """
        The check the builder did not have, and the reason it now does.

        The first version walked a single cursor along x from
        -length/2 + 0.25 and trusted the result. On the bundled geometry
        only TWO of these items fit in one row, so the third ran to
        x = 1.20 against an interior half-extent of 0.96 -- a box seeded
        24 cm inside the far wall, in a scene that was then executed and
        registered.

        Nothing caught it, and that is the part worth pinning. The configs
        carry no `points`/`n_vecs` (containers.py adds those at build
        time), so `Geometry.inside_container` takes its no-envelope early
        return and reports True for anything. Every assertion in this file
        that touches containment inherits that hole; this one uses the
        declared box extents directly instead.
        """
        for name, config in MATRIX.items():
            case = next(iter(config.values()))
            for container in case["containers"]["container_list"]:
                x_limit = (
                    float(container["length"]) / 2.0
                    - float(container["thickness"])
                )
                y_limit = (
                    float(container["width"]) / 2.0
                    - float(container["thickness"])
                )
                for seated in container["packed_items"]:
                    with self.subTest(scenario=name, item=seated["index"]):
                        x = abs(float(seated["pos"][0])) + \
                            float(seated["length"]) / 2.0
                        y = abs(float(seated["pos"][1])) + \
                            float(seated["width"]) / 2.0
                        self.assertLessEqual(x, x_limit + 1e-9)
                        self.assertLessEqual(y, y_limit + 1e-9)

    def test_an_impossible_preload_raises_rather_than_truncating(self) -> None:
        """
        Asking for more than fits must fail loudly. Returning a short list
        would put the scenario's `preloaded` count out of step with reality
        and change the denominator of num_placed_items without saying so.
        """
        case = SOURCE["000"]
        container = case["containers"]["container_list"][0]
        with self.assertRaises(builder.PreloadDoesNotFit):
            builder._preloaded_items(
                case["item_stream"]["item_list"], 40, container
            )

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


class DeathChannelReadingTests(unittest.TestCase):
    """
    Pins the reading of `place_states`, which was misread once already.

    app.py rebinds `place_states` inside the episode loop, so the result
    file carries the LAST step's status, not a summary of the episode. And
    env.py terminates on the first failure. Together that makes
    `is_valid: true` on an episode that placed 30 of 41 mean the opposite
    of healthy: the transport check passed and the item then failed to
    settle. HANDOFF reported that row as "`is_valid` true" as if it were a
    clean signal.
    """

    def test_each_status_triple_maps_to_its_own_channel(self) -> None:
        cases = {
            "inclusion": (False, False, False),
            "transport": (True, False, False),
            "settle": (True, True, False),
            "stream_exhausted": (True, True, True),
        }
        for expected, (included, valid, safe) in cases.items():
            with self.subTest(channel=expected):
                self.assertEqual(
                    runner.death_channel({
                        "is_included": included,
                        "is_valid": valid,
                        "is_placed_safe": safe,
                    }),
                    expected,
                )

    def test_is_valid_true_is_not_a_health_signal(self) -> None:
        """The specific misreading, pinned as its own case."""
        self.assertEqual(
            runner.death_channel(
                {"is_included": True, "is_valid": True,
                 "is_placed_safe": False}
            ),
            "settle",
        )

    def test_missing_status_is_unknown_not_success(self) -> None:
        self.assertEqual(runner.death_channel(None), "unknown")
        self.assertEqual(runner.death_channel({}), "unknown")

    def test_a_malformed_action_is_not_reported_as_inclusion(self) -> None:
        """
        check_action failing returns a different status dict entirely --
        none of is_included/is_valid/is_placed_safe is present. Reading it
        with .get() made every such ending report "inclusion", turning
        rules failure condition 1 into failure condition 2.
        """
        for status in (
            {"has_valid_action_keys": False},
            {"has_valid_action_pos (length must be 3)": False},
            {"has_valid_action_index (index in container_idx ...)": False},
        ):
            with self.subTest(status=next(iter(status))):
                self.assertEqual(
                    runner.death_channel(status), "malformed_action"
                )

    def test_a_short_trace_disqualifies_the_attribution(self) -> None:
        """
        app.py passes `fallback=env.action_space.sample()` with
        `time_out_sec=policy_timeout`. On an overrun the harness plays a
        RANDOM action and the agent writes no record, so the last trace
        entry belongs to an earlier step. One decision per step is the only
        evidence that did not happen.
        """
        row = {"steps": 20, "terminal_decision": {"decisions": 20}}
        runner.attach_trace_coverage(row)
        self.assertTrue(row["trace_covers_every_step"])
        self.assertNotIn("trace_coverage_warning", row)

        row = {"steps": 20, "terminal_decision": {"decisions": 18}}
        runner.attach_trace_coverage(row)
        self.assertFalse(row["trace_covers_every_step"])
        self.assertIn("trace_coverage_warning", row)

    def test_a_disqualified_attribution_is_not_printed_as_a_cause(
        self,
    ) -> None:
        row = {
            "scenario": "x", "containers": 1, "shelves": 0, "dedicated": 0,
            "preloaded": 0, "packed_items": 5, "total_items": 41,
            "placed_ratio": 0.12, "agent_placed": 5, "agent_of": 41,
            "fill_score": 1.0, "steps": 20, "death_channel": "settle",
            "trace_covers_every_step": False,
            "terminal_decision": {
                "decisions": 18,
                "final_action_source": "placement_core",
                "final_candidate_kind": "release_candidate",
            },
        }
        rendered = runner.format_row(row)
        self.assertIn("ATTRIBUTION UNSAFE", rendered)
        self.assertNotIn("release_candidate", rendered)

    def test_a_count_that_contradicts_the_run_is_an_error(self) -> None:
        """
        packed_items is reconstructed from a float ratio against a
        denominator taken from the CONFIG. If the config and the run do not
        belong together the row would be quietly wrong, so it raises.
        """
        shape = {
            "containers": 1, "shelves": 0, "dedicated": 0,
            "preloaded": 0, "stream_items": 41, "total_items": 41,
        }
        case = {
            "evaluation": {
                "num_placed_items": 24 / 41,
                "fill_score": 1.0,
                "step_metrics": [{"placed_count": 24}],
            },
            "place_states": {
                "is_included": True, "is_valid": True,
                "is_placed_safe": False,
            },
        }
        self.assertEqual(runner.summarize_case(case, shape)["packed_items"], 24)

        case["evaluation"]["step_metrics"] = [{"placed_count": 30}]
        with self.assertRaises(ValueError):
            runner.summarize_case(case, shape)

    def test_preloaded_items_are_removed_from_the_agents_credit(self) -> None:
        """
        num_placed_items counts pre-loaded items in BOTH numerator and
        denominator (env.py:121 sums stream total and already-packed items;
        evaluator.py:84 divides packed by it). A pre-loaded row therefore
        reads higher than the agent earned, so summarize_case reports
        agent_placed/agent_of next to it.
        """
        shape = {
            "containers": 1, "shelves": 0, "dedicated": 0,
            "preloaded": 3, "stream_items": 38, "total_items": 41,
        }
        row = runner.summarize_case(
            {
                "evaluation": {
                    "num_placed_items": 21 / 41,
                    "fill_score": 24.8,
                    "step_metrics": [{}] * 19,
                },
                "place_states": {
                    "is_included": True, "is_valid": False,
                    "is_placed_safe": False,
                },
            },
            shape,
        )
        self.assertEqual(row["packed_items"], 21)
        self.assertEqual(row["agent_placed"], 18)
        self.assertEqual(row["agent_of"], 38)
        self.assertEqual(row["death_channel"], "transport")


if __name__ == "__main__":
    unittest.main()
