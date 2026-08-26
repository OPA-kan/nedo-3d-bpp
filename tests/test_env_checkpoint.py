"""Integration tests: checkpoint+restore vs. fresh-reconstruction replay.

Needs the real simulator (same gate as test_replay_integration.py).
Proves scripts/env_checkpoint.py's capture/restore reproduces exactly
what full replay-from-scratch would have produced, on both physics
state (every body's pose/velocity) and the Python-side bookkeeping
that PyBullet's own saveState/restoreState does not touch (stream
manager, container packed-item lists, step metrics).
"""
from __future__ import annotations

import copy
import importlib
import json
import os
import pathlib
import sys
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

# A job that is supposed to prove the checkpoint contract must not be able
# to pass by skipping. Any environment that intends to run these sets
# NEDO_REQUIRE_INTEGRATION=1, and an unavailable simulator becomes an error
# instead of a green "OK (skipped=3)".
REQUIRE_INTEGRATION = os.environ.get(
    "NEDO_REQUIRE_INTEGRATION", ""
).strip().lower() in {"1", "true", "yes"}

if REQUIRE_INTEGRATION and not AVAILABLE:
    raise RuntimeError(
        "NEDO_REQUIRE_INTEGRATION is set but the env_checkpoint integration "
        f"tests cannot run: {SKIP_REASON}. Install requirements-simulator.txt "
        "on Python 3.12+, or unset the variable to allow skipping."
    )


def body_states(env) -> list[tuple]:
    """Pose and velocity of every body, not just the packed items."""
    states = []
    for index in range(env.client.getNumBodies()):
        body_id = env.client.getBodyUniqueId(index)
        position, quaternion = env.client.getBasePositionAndOrientation(body_id)
        linear, angular = env.client.getBaseVelocity(body_id)
        states.append((
            body_id,
            tuple(round(float(value), 9) for value in position),
            tuple(round(float(value), 9) for value in quaternion),
            tuple(round(float(value), 9) for value in linear),
            tuple(round(float(value), 9) for value in angular),
        ))
    return sorted(states)


def bookkeeping_state(env) -> dict:
    """Everything env_checkpoint captures that saveState does not."""
    return {
        "current_index": env.stream_manager.current_index,
        "visible_pool": [
            item.index for item in env.stream_manager.visible_pool
        ],
        "num_step": env.num_step,
        "step_metrics": copy.deepcopy(env.step_metrics),
        "packed_items": {
            container.index: [
                item.index for item in container.packed_items
            ]
            for container in env.container_manager.containers
        },
        "last_settle_metrics": copy.deepcopy(
            env.validator.last_settle_metrics
        ),
    }


@unittest.skipUnless(AVAILABLE, SKIP_REASON)
class EnvCheckpointEquivalenceTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))["000"]

    def build_env(self, *, seed=42):
        from scripts.run_single_agent_packing import _fresh_env

        env = _fresh_env(copy.deepcopy(self.config))
        env.reset_settings()
        env.reset_item_stream()
        observation, _info = env.reset(seed=seed)
        return env, observation

    def next_action(self, env, observation, agent_module):
        from scripts.build_counterfactual_graph import build_candidate_provider
        from scripts.run_self_play_packing import _candidate_action

        provider = build_candidate_provider(
            agent_module, attempt_budget=64, scan_all_visible_items=True,
        )
        candidates = provider(env, observation, 1)
        self.assertTrue(candidates, "no safe candidate to step with")
        return _candidate_action(candidates[0])

    def test_checkpoint_restore_reproduces_a_direct_continuation(self) -> None:
        """Same env, same client: branch A (direct) vs branch B (via a
        restored checkpoint) from the identical point must agree exactly."""
        from scripts import env_checkpoint
        from scripts.measure_anchor_recall import load_agent_module

        agent_module = load_agent_module()
        env, observation = self.build_env()
        try:
            # Advance two real steps so the checkpoint sits mid-episode,
            # not at the raw reset state.
            for _ in range(2):
                action = self.next_action(env, observation, agent_module)
                observation, _r, terminated, truncated, _info = env.step(action)
                self.assertFalse(terminated or truncated)

            checkpoint = env_checkpoint.capture(env)
            next_action = self.next_action(env, observation, agent_module)

            # Branch A: step directly from here.
            obs_a, r_a, term_a, trunc_a, info_a = env.step(next_action)
            bodies_a = body_states(env)
            bookkeeping_a = bookkeeping_state(env)

            # Rewind to the checkpoint and take the SAME action again.
            env_checkpoint.restore(checkpoint, env)
            self.assertEqual(
                bookkeeping_state(env),
                {
                    "current_index": checkpoint.stream_manager.current_index,
                    "visible_pool": [
                        item.index
                        for item in checkpoint.stream_manager.visible_pool
                    ],
                    "num_step": checkpoint.num_step,
                    "step_metrics": checkpoint.step_metrics,
                    "packed_items": {
                        container.index: [
                            item.index for item in container.packed_items
                        ]
                        for container in checkpoint.containers
                    },
                    "last_settle_metrics": checkpoint.last_settle_metrics,
                },
                "restore() did not reproduce the captured bookkeeping",
            )
            obs_b, r_b, term_b, trunc_b, info_b = env.step(next_action)
            bodies_b = body_states(env)
            bookkeeping_b = bookkeeping_state(env)

            self.assertEqual(bodies_a, bodies_b)
            self.assertEqual(bookkeeping_a, bookkeeping_b)
            self.assertEqual((r_a, term_a, trunc_a), (r_b, term_b, trunc_b))
            self.assertEqual(info_a, info_b)
            self.assertEqual(
                {k: v for k, v in obs_a.items() if k != "depth_map"},
                {k: v for k, v in obs_b.items() if k != "depth_map"},
            )

            env_checkpoint.release(checkpoint, env)
        finally:
            env.close()

    def test_checkpoint_restore_matches_fresh_reconstruction(self) -> None:
        """The whole point: a checkpoint-based branch on one persistent
        env must land in the same place a totally fresh env would reach
        replaying the identical action sequence from scratch (the
        pattern _rollout/_terminal_rollout use today)."""
        from scripts import env_checkpoint
        from scripts.measure_anchor_recall import load_agent_module

        agent_module = load_agent_module()

        # Reference: fresh env, plain replay of a 3-action prefix.
        ref_env, ref_obs = self.build_env()
        prefix_actions = []
        try:
            for _ in range(3):
                action = self.next_action(ref_env, ref_obs, agent_module)
                prefix_actions.append(action)
                ref_obs, _r, terminated, truncated, _info = ref_env.step(action)
                self.assertFalse(terminated or truncated)
            reference_bodies = body_states(ref_env)
            reference_bookkeeping = bookkeeping_state(ref_env)
        finally:
            ref_env.close()

        # Candidate: fresh env, checkpoint after action 1, restore, then
        # replay actions 2 and 3 from the checkpoint instead of stepping
        # through action 1 again.
        env, observation = self.build_env()
        try:
            observation, _r, terminated, truncated, _info = env.step(
                prefix_actions[0]
            )
            self.assertFalse(terminated or truncated)
            checkpoint = env_checkpoint.capture(env)

            # Perturb the live env with a throwaway action so restore()
            # is doing real work, not a no-op.
            distractor = self.next_action(env, observation, agent_module)
            env.step(distractor)

            env_checkpoint.restore(checkpoint, env)
            for action in prefix_actions[1:]:
                observation, _r, terminated, truncated, _info = env.step(action)
                self.assertFalse(terminated or truncated)

            self.assertEqual(body_states(env), reference_bodies)
            self.assertEqual(bookkeeping_state(env), reference_bookkeeping)
            env_checkpoint.release(checkpoint, env)
        finally:
            env.close()

    def test_release_forbids_a_later_restore(self) -> None:
        from scripts import env_checkpoint

        env, _observation = self.build_env()
        try:
            checkpoint = env_checkpoint.capture(env)
            env_checkpoint.release(checkpoint, env)
            with self.assertRaises(ValueError):
                env_checkpoint.restore(checkpoint, env)
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
