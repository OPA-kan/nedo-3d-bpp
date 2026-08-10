"""
Integration tests for the counterfactual replay contract.

These need the real simulator, so they exercise the parts the pure-function
tests cannot reach: that a candidate replay leaves the physics state exactly
as it found it, that it still does so when the replay raises, and that
replaying candidates does not change the episode the policy goes on to run.

Skipped below Python 3.12 or without PyBullet; CI runs 3.12.
"""
from __future__ import annotations

import copy
import importlib
import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"
CONFIG = SIMULATOR / "configs" / "sample_config.json"


def _simulator_available() -> tuple[bool, str]:
    if sys.version_info[:2] < (3, 12):
        return False, "simulator needs Python 3.12+ (PEP 701 f-strings)"
    if importlib.util.find_spec("pybullet") is None:
        return False, "pybullet is not installed"
    if str(SIMULATOR) not in sys.path:
        sys.path.insert(0, str(SIMULATOR))
    try:
        importlib.import_module("src.ground_handling.env")
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, f"simulator unavailable: {exc}"
    return True, ""


AVAILABLE, SKIP_REASON = _simulator_available()

# A job that is supposed to prove the physics contract must not be able to
# pass by skipping. Any environment that intends to run these sets
# NEDO_REQUIRE_INTEGRATION=1, and an unavailable simulator becomes an error
# instead of a green "OK (skipped=3)".
REQUIRE_INTEGRATION = os.environ.get(
    "NEDO_REQUIRE_INTEGRATION", ""
).strip().lower() in {"1", "true", "yes"}

if REQUIRE_INTEGRATION and not AVAILABLE:
    raise RuntimeError(
        "NEDO_REQUIRE_INTEGRATION is set but the replay integration tests "
        f"cannot run: {SKIP_REASON}. Install requirements-simulator.txt on "
        "Python 3.12+, or unset the variable to allow skipping."
    )


def body_states(env) -> list[tuple]:
    """Pose and velocity of every body, not just the packed items."""
    states = []
    for index in range(env.client.getNumBodies()):
        body_id = env.client.getBodyUniqueId(index)
        position, quaternion = env.client.getBasePositionAndOrientation(body_id)
        linear, angular = env.client.getBaseVelocity(body_id)
        states.append(
            (
                body_id,
                tuple(round(float(value), 9) for value in position),
                tuple(round(float(value), 9) for value in quaternion),
                tuple(round(float(value), 9) for value in linear),
                tuple(round(float(value), 9) for value in angular),
            )
        )
    return sorted(states)


@unittest.skipUnless(AVAILABLE, SKIP_REASON)
class ReplayStateEquivalenceTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        os.environ["NEDO_CANDIDATE_AUDIT"] = "1"
        os.environ.setdefault("LOOKAHEAD_SELECTION_MODE", "weighted")
        os.environ.setdefault("ITEM_COVERAGE_MODE", "class_aware")
        os.environ.setdefault("RELEASE_RISK_GATE_MODE", "shadow")
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))["000"]

    def build_env(self):
        from src.ground_handling.env import GroundHandlingEnv

        env = GroundHandlingEnv(
            config=copy.deepcopy(self.config),
            verbose=False,
            render_mode=None,
        )
        env.reset_settings()
        env.get_init_states()
        env.reset_item_stream()
        observation, _info = env.reset(seed=42)
        return env, observation

    def sample_candidates(self, agent_module, observation, limit=3):
        from scripts.measure_anchor_recall import (
            enumerate_oracle_candidates,
            policy_indexed_items,
        )
        from scripts.measure_anchor_recall import policy_observation

        policy_view = policy_observation(self.env, observation)
        records, _complete, _stats = enumerate_oracle_candidates(
            agent_module,
            policy_view,
            generator_mode="cartesian",
            attempt_kind="release",
            max_candidates=limit,
            indexed_items=policy_indexed_items(agent_module, policy_view),
        )
        return records[:limit]

    def test_replay_restores_every_body_exactly(self) -> None:
        from scripts.build_replay_dataset import replay_sample
        from scripts.measure_anchor_recall import load_agent_module

        agent_module = load_agent_module()
        self.env, observation = self.build_env()
        try:
            sample = self.sample_candidates(agent_module, observation)
            self.assertTrue(sample, "no candidates to replay")

            before = body_states(self.env)
            results, _seconds = replay_sample(self.env, sample)
            after = body_states(self.env)

            self.assertEqual(len(results), len(sample))
            # Replays must be invisible to the physics state: no leaked probe
            # body, no drift from the settle steps they ran.
            self.assertEqual(before, after)
        finally:
            self.env.close()

    def test_state_is_restored_even_when_a_replay_raises(self) -> None:
        from scripts import build_replay_dataset
        from scripts.measure_anchor_recall import load_agent_module

        agent_module = load_agent_module()
        self.env, observation = self.build_env()
        try:
            sample = self.sample_candidates(agent_module, observation)
            self.assertTrue(sample, "no candidates to replay")
            before = body_states(self.env)

            original = build_replay_dataset.CounterfactualReplay.run

            def exploding(self_, record, probe):
                raise RuntimeError("injected replay failure")

            build_replay_dataset.CounterfactualReplay.run = exploding
            try:
                with self.assertRaises(RuntimeError):
                    build_replay_dataset.replay_sample(self.env, sample)
            finally:
                build_replay_dataset.CounterfactualReplay.run = original

            self.assertEqual(before, body_states(self.env))
        finally:
            self.env.close()


@unittest.skipUnless(AVAILABLE, SKIP_REASON)
class ReplayTrajectoryTests(unittest.TestCase):
    """The sampled replays must not change the episode that actually runs."""

    STEPS = 3

    @classmethod
    def setUpClass(cls) -> None:
        os.environ["NEDO_CANDIDATE_AUDIT"] = "1"
        os.environ.setdefault("LOOKAHEAD_SELECTION_MODE", "weighted")
        os.environ.setdefault("ITEM_COVERAGE_MODE", "class_aware")
        os.environ.setdefault("RELEASE_RISK_GATE_MODE", "shadow")

    def run_episode(
        self,
        *,
        with_replay: bool,
        sampling_mode: str = "stratified_random",
    ):
        from scripts.build_replay_dataset import run_case
        from scripts.measure_anchor_recall import load_agent_module
        from src.ground_handling.env import GroundHandlingEnv

        agent_module = load_agent_module()
        config = json.loads(CONFIG.read_text(encoding="utf-8"))["000"]

        if with_replay:
            with tempfile.TemporaryDirectory() as directory:
                summary = run_case(
                    agent_module,
                    copy.deepcopy(config),
                    dataset_id="test",
                    case_id="000",
                    target_steps=set(range(self.STEPS)),
                    output_dir=pathlib.Path(directory),
                    per_stratum=1,
                    seed=1,
                    oracle_limit=8,
                    preview_limit=0,
                    skip_optimize=True,
                    sampling_mode=sampling_mode,
                )
                return [
                    entry["action"] for entry in summary["steps"]
                ]

        env = GroundHandlingEnv(
            config=copy.deepcopy(config), verbose=False, render_mode=None
        )
        solver = agent_module.Agent("")
        actions = []
        try:
            env.reset_settings()
            solver.get_init_states(env.get_init_states())
            env.reset_item_stream()
            observation, _info = env.reset(seed=42)
            from scripts.measure_anchor_recall import policy_observation

            terminated = truncated = False
            for _ in range(self.STEPS):
                if terminated or truncated:
                    break
                action = solver.policy(policy_observation(env, observation))
                actions.append(
                    {
                        "item_idx": int(action["item_idx"]),
                        "container_idx": int(action["container_idx"]),
                        "orientation": int(action["orientation"]),
                        "place_pos": [
                            round(float(value), 6)
                            for value in action["place_pos"]
                        ],
                    }
                )
                observation, _r, terminated, truncated, _i = env.step(action)
        finally:
            env.close()
        return actions

    def assert_actions_equivalent(self, control, replayed) -> None:
        self.assertTrue(control, "control episode produced no actions")
        self.assertEqual(len(control), len(replayed))
        for index, (expected, actual) in enumerate(zip(control, replayed)):
            for key in ("item_idx", "container_idx", "orientation"):
                self.assertEqual(
                    int(expected[key]),
                    int(actual[key]),
                    f"step {index} differs on {key}",
                )
            for axis, (left, right) in enumerate(
                zip(expected["place_pos"], actual["place_pos"])
            ):
                self.assertAlmostEqual(
                    float(left),
                    float(right),
                    places=5,
                    msg=f"step {index} place_pos[{axis}] differs",
                )

    def test_replaying_candidates_does_not_change_the_actions_taken(
        self,
    ) -> None:
        control = self.run_episode(with_replay=False)
        replayed = self.run_episode(with_replay=True)

        self.assert_actions_equivalent(control, replayed)

    def test_paired_constrained_diversity_replay_does_not_change_actions(self):
        control = self.run_episode(with_replay=False)
        replayed = self.run_episode(
            with_replay=True,
            sampling_mode="residual_diversity_constrained",
        )

        self.assert_actions_equivalent(control, replayed)


if __name__ == "__main__":
    unittest.main()
