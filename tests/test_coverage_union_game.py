import random
import unittest

from scripts.run_self_play_packing import play_game
from scripts.self_play_packing_game import GameRules


class UnionFakeEnv:
    def __init__(self, steps):
        self.remaining = steps
        self.violations = 0

    def step(self, _action):
        self.remaining -= 1
        return (
            {"pool": self.remaining}, 0.0, self.remaining <= 0, False,
            {"status": {
                "is_included": True, "is_valid": True, "is_placed_safe": True,
            }},
        )


def legacy_candidate(rank):
    return {
        "candidate_id": f"legacy-{rank}",
        "selection": {"rank": rank, "score": 1.0 - rank * 0.1},
        "command_action": {
            "item_idx": rank, "container_idx": 0,
            "place_pos": [0.0, 0.1 * rank, 0.5], "orientation": 0,
        },
    }


def coverage_candidate(number):
    return {
        "candidate_id": f"coverage-{number}",
        "selection": {
            "provider": "scrambled_halton_v1",
            "candidate_kind": "coverage_candidate",
        },
        "proposal_provenance": {
            "schema_version": 1,
            "source": "coverage",
            "coverage_seed": 9,
            "coverage_sequence_index": number,
        },
        "command_action": {
            "item_idx": number, "container_idx": 0,
            "place_pos": [0.3, 0.1 * number, 0.5], "orientation": 1,
        },
    }


def metrics(env):
    return {"soft_covered_by_other": env.violations}


class CoverageUnionGameTests(unittest.TestCase):
    def run_game(self, *, legacy_count, coverage_count, divisor=None,
                 steps=1, coverage_per_step=0):
        env = UnionFakeEnv(steps)
        return play_game(
            env, {"pool": steps},
            lambda _e, _o, _k: [
                legacy_candidate(r) for r in range(legacy_count)
            ],
            rules=GameRules(minimum_block=10),
            handoff_rng=random.Random(1), policy_rng=random.Random(2),
            metrics_fn=metrics, max_steps=steps,
            selection_mode="rank0",
            coverage_fn=(
                (lambda **_kwargs: [
                    coverage_candidate(n) for n in range(coverage_count)
                ]) if coverage_count else None
            ),
            coverage_per_step=coverage_per_step,
            paired_candidate_divisor=divisor,
        )

    def test_union_is_recorded_but_rank0_legacy_executes(self):
        result = self.run_game(
            legacy_count=3, coverage_count=2, coverage_per_step=3,
        )

        record = result["records"][0]
        sources = [
            row["proposal_provenance"]["source"]
            for row in record["candidate_set"]
        ]
        self.assertEqual(
            sources, ["legacy_provider"] * 3 + ["coverage"] * 2
        )
        self.assertEqual(record["selected_candidate_id"], "legacy-0")
        self.assertEqual(result["non_rank0_action_count"], 0)

    def test_divisor_trims_coverage_never_legacy(self):
        result = self.run_game(
            legacy_count=3, coverage_count=4, coverage_per_step=4,
            divisor=12,
        )

        record = result["records"][0]
        # 3 legacy + 4 coverage = 7 does not divide 12; trimmed to 6.
        self.assertEqual(record["candidate_count"], 6)
        sources = [
            row["proposal_provenance"]["source"]
            for row in record["candidate_set"]
        ]
        self.assertEqual(sources.count("legacy_provider"), 3)
        self.assertEqual(sources.count("coverage"), 3)

    def test_no_legacy_support_ends_game_despite_safe_coverage(self):
        result = self.run_game(
            legacy_count=0, coverage_count=3, coverage_per_step=3,
        )

        self.assertEqual(result["terminal_reason"], "no_retained_candidate")
        self.assertEqual(result["records"], [])


if __name__ == "__main__":
    unittest.main()
