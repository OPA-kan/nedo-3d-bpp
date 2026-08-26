"""Integration test: shared_prefix_env=True vs. the default fresh-replay
path in scripts/run_vector_mcts.py::vector_search_root.

Needs the real simulator (same gate as test_replay_integration.py and
test_env_checkpoint.py). scripts/env_checkpoint.py is proven correct in
isolation by test_env_checkpoint.py; this proves the wiring into the
actual search -- vector_search_root(shared_prefix_env=True) restoring a
scripts.env_checkpoint snapshot on a single persistent env instead of
every try_action_path() call rebuilding a fresh env and replaying the
prefix from scratch -- reproduces byte-identical search results (nodes,
root rows, edge statistics, frontier) to the unmodified default path,
across a search that expands multiple tree levels deep (so many
restore() calls at different depths reuse the one shared env).
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

# A job that is supposed to prove this wiring must not be able to pass by
# skipping. Any environment that intends to run these sets
# NEDO_REQUIRE_INTEGRATION=1, and an unavailable simulator becomes an error
# instead of a green "OK (skipped=1)".
REQUIRE_INTEGRATION = os.environ.get(
    "NEDO_REQUIRE_INTEGRATION", ""
).strip().lower() in {"1", "true", "yes"}

if REQUIRE_INTEGRATION and not AVAILABLE:
    raise RuntimeError(
        "NEDO_REQUIRE_INTEGRATION is set but the shared_prefix_env "
        f"integration test cannot run: {SKIP_REASON}. Install "
        "requirements-simulator.txt on Python 3.12+, or unset the "
        "variable to allow skipping."
    )


@unittest.skipUnless(AVAILABLE, SKIP_REASON)
class SharedPrefixEnvEquivalenceTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))["000"]

    def test_shared_prefix_env_matches_default_fresh_replay(self) -> None:
        from scripts.build_counterfactual_graph import build_candidate_provider
        from scripts.measure_anchor_recall import load_agent_module
        from scripts.run_self_play_packing import _candidate_action
        from scripts.run_single_agent_packing import _fresh_env
        from scripts.run_vector_mcts import vector_search_root

        agent_module = load_agent_module()
        provider = build_candidate_provider(
            agent_module, attempt_budget=64, scan_all_visible_items=True,
        )

        env = _fresh_env(copy.deepcopy(self.config))
        prefix_actions: list = []
        try:
            env.reset_settings()
            env.reset_item_stream()
            observation, _info = env.reset(seed=42)
            for _ in range(2):
                candidates = provider(env, observation, 1)
                self.assertTrue(candidates, "no safe candidate for the prefix")
                action = _candidate_action(candidates[0])
                prefix_actions.append(action)
                observation, _r, terminated, truncated, _info = env.step(action)
                self.assertFalse(terminated or truncated)
            root_candidates = provider(env, observation, 4)
            self.assertTrue(root_candidates, "no safe root candidates")
        finally:
            env.close()

        def run(shared_prefix_env: bool):
            return vector_search_root(
                agent_module, copy.deepcopy(self.config), case_id="case",
                environment_seed=42, prefix_actions=list(prefix_actions),
                root_candidates=root_candidates, attempt_budget=64,
                deep_top_k=4, expansions=6, max_depth=4, step=2,
                shared_prefix_env=shared_prefix_env,
            )

        baseline = run(shared_prefix_env=False)
        candidate_result = run(shared_prefix_env=True)

        self.assertFalse(baseline["shared_prefix_env"])
        self.assertTrue(candidate_result["shared_prefix_env"])
        self.assertGreater(baseline["explored_nodes"], 1, "test too shallow")

        def normalized(result: dict) -> dict:
            result = copy.deepcopy(result)
            result.pop("timing", None)
            result.pop("shared_prefix_env", None)
            return result

        self.assertEqual(normalized(baseline), normalized(candidate_result))


if __name__ == "__main__":
    unittest.main()
