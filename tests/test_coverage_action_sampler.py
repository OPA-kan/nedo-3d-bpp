import unittest

from scripts.coverage_action_sampler import (
    container_domain,
    coverage_candidates,
    enumerate_strata,
    rotated_half_extents,
    sample_stratum,
    stratum_domain,
)


def container(points=None, center=(2.5, 0.0, 0.805)):
    return {
        "index": 1,
        "center": list(center),
        "points": points or [
            [center[0] - 0.96, -0.7, 0.04],
            [center[0] + 0.96, 0.7, 0.04],
            [center[0] + 0.96, -0.7, 1.57],
            [center[0] - 0.96, 0.7, 1.57],
        ],
    }


def item(length=0.4, width=0.3, height=0.2, index=7):
    return {"index": index, "length": length, "width": width, "height": height}


def observation():
    return {"pool_list": [item()], "container_list": [container()]}


class CoverageActionSamplerTests(unittest.TestCase):
    def test_domain_is_container_local_and_shrunk_by_half_extents(self):
        bounds = container_domain(container())
        self.assertAlmostEqual(bounds["x"][0], -0.96)
        self.assertAlmostEqual(bounds["x"][1], 0.96)

        domain = stratum_domain(container(), item(), orientation=0)
        self.assertAlmostEqual(domain["x"][0], -0.96 + 0.2)
        self.assertAlmostEqual(domain["y"][1], 0.7 - 0.15)
        self.assertAlmostEqual(domain["z"][0], 0.04 + 0.1)

    def test_oversized_orientation_is_excluded_not_clamped(self):
        tall = item(length=0.4, width=0.3, height=1.8)
        # upright, the 1.8 axis exceeds the 1.53 vertical span
        self.assertIsNone(stratum_domain(container(), tall, orientation=0))
        # rotated so the 1.8 axis lies along x (1.92 span), it fits
        self.assertIsNotNone(stratum_domain(container(), tall, orientation=2))
        half = rotated_half_extents(tall, 2)
        self.assertEqual(half, (0.9, 0.15, 0.2))

    def test_sampling_is_deterministic_and_seed_sensitive(self):
        stratum = enumerate_strata(observation())[0]
        first = sample_stratum(stratum, 3, coverage_seed=11)
        again = sample_stratum(stratum, 3, coverage_seed=11)
        other_seed = sample_stratum(stratum, 3, coverage_seed=12)
        other_index = sample_stratum(stratum, 4, coverage_seed=11)

        self.assertEqual(first, again)
        self.assertNotEqual(
            first["command_action"]["place_pos"],
            other_seed["command_action"]["place_pos"],
        )
        self.assertNotEqual(
            first["command_action"]["place_pos"],
            other_index["command_action"]["place_pos"],
        )
        for axis, value in zip(
            ("x", "y", "z"), first["command_action"]["place_pos"]
        ):
            low, high = stratum["domain"][axis]
            self.assertTrue(low <= value <= high)

    def test_provenance_declares_off_policy_coverage_contract(self):
        candidate = coverage_candidates(
            observation(), coverage_seed=5, budget=1
        )[0]

        provenance = candidate["proposal_provenance"]
        self.assertEqual(provenance["source"], "coverage")
        self.assertEqual(provenance["coverage_seed"], 5)
        self.assertEqual(provenance["coverage_sequence_index"], 0)
        self.assertIsNone(provenance["proposal_probability"])
        self.assertNotIn("score", candidate["selection"])
        self.assertNotIn("rank", candidate["selection"])
        self.assertEqual(
            candidate["command_action"]["container_idx"], 1
        )

    def test_round_robin_balances_strata_within_any_prefix(self):
        obs = {
            "pool_list": [item(index=1), item(index=2)],
            "container_list": [container()],
        }
        strata = enumerate_strata(obs)
        budget = len(strata) + 3
        candidates = coverage_candidates(obs, coverage_seed=1, budget=budget)

        self.assertEqual(len(candidates), budget)
        first_round = candidates[:len(strata)]
        self.assertEqual(
            sorted(
                c["selection"]["coverage_stratum_key"] for c in first_round
            ),
            sorted(s["stratum_key"] for s in strata),
        )
        self.assertTrue(all(
            c["proposal_provenance"]["coverage_sequence_index"] == 1
            for c in candidates[len(strata):]
        ))


if __name__ == "__main__":
    unittest.main()
