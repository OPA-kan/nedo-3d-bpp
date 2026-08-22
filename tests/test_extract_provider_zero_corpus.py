import unittest

from scripts.extract_provider_zero_corpus import build_corpus, resample_corpus


def _audit(node, board, depth, *, wider=0, top=0):
    prefix = [{"item_idx": index} for index in range(6 + depth)]
    return {
        "node_key": node,
        "depth": depth,
        "absolute_action_prefix": prefix,
        "board_fingerprint": board,
        "model_visible_state_signature": f"model-{board}",
        "replay_contract": {
            "seed": 42,
            "item_order": [1, 2, 3],
            "action_prefix": prefix,
        },
        "top_k_proposal_count": top,
        "wider_proposal_count": wider,
    }


class ProviderZeroCorpusTests(unittest.TestCase):
    def test_deduplicates_boards_but_retains_node_prevalence(self):
        aggregate = {"experiment": "search", "roots": [
            {"root_id": "r1", "reference_condition": "h5-s48"},
        ]}
        root = {
            "root_id": "r1",
            "case_id": "m-single-empty-shelf",
            "source_manifest": "case/mcts/manifest.json",
            "step": 6,
            "conditions": {"h5-s48": {"candidate_exhaustion_audits": [
                _audit("n1", "b1", 3),
                _audit("n2", "b1", 3),
                _audit("recovered", "b2", 2, wider=4),
            ]}},
        }

        corpus = build_corpus(
            aggregate,
            [{"complete": True, "roots": [root]}],
        )

        self.assertEqual(corpus["summary"]["provider_zero_nodes"], 2)
        self.assertEqual(corpus["summary"]["provider_zero_unique_boards"], 1)
        self.assertEqual(len(corpus["states"]), 1)
        self.assertEqual(corpus["states"][0]["occurrence_count"], 2)
        self.assertEqual(corpus["states"][0]["effective_step"], 9)
        self.assertEqual(
            corpus["states"][0]["stratum"],
            "m-single-empty-shelf|mid_9_10",
        )

    def test_sampling_is_deterministic_and_stratified(self):
        aggregate = {"roots": [
            {"root_id": "r1", "reference_condition": "h5-s48"},
        ]}
        audits = [
            _audit(f"n{index}", f"b{index}", 3)
            for index in range(6)
        ] + [
            _audit(f"late{index}", f"late-b{index}", 5)
            for index in range(6)
        ]
        payload = {"complete": True, "roots": [{
            "root_id": "r1",
            "case_id": "m-single-empty-shelf",
            "source_manifest": "case/mcts/manifest.json",
            "step": 6,
            "conditions": {"h5-s48": {
                "candidate_exhaustion_audits": audits,
            }},
        }]}

        first = build_corpus(
            aggregate, [payload], max_per_stratum=2, seed=7
        )
        second = build_corpus(
            aggregate, [payload], max_per_stratum=2, seed=7
        )

        self.assertEqual(first, second)
        self.assertEqual(first["summary"]["selected_unique_boards"], 4)
        self.assertEqual(
            sorted(first["summary"]["selected_counts_by_stratum"].values()),
            [2, 2],
        )

    def test_rejects_inconsistent_replay_depth(self):
        aggregate = {"roots": [
            {"root_id": "r1", "reference_condition": "h5-s48"},
        ]}
        bad = _audit("n1", "b1", 3)
        bad["absolute_action_prefix"].pop()
        payload = {"complete": True, "roots": [{
            "root_id": "r1",
            "case_id": "m-single-empty-shelf",
            "source_manifest": "case/mcts/manifest.json",
            "step": 6,
            "conditions": {"h5-s48": {
                "candidate_exhaustion_audits": [bad],
            }},
        }]}
        with self.assertRaisesRegex(ValueError, "inconsistent replay depth"):
            build_corpus(aggregate, [payload])

    def test_resamples_a_durable_full_corpus_without_raw_shards(self):
        states = [
            {
                "board_fingerprint": f"b{index}",
                "stratum": "case|mid_9_10",
            }
            for index in range(5)
        ]
        source = {
            "experiment": "provider_zero_rescue_corpus",
            "summary": {"provider_zero_unique_boards": 521},
            "states": states,
        }

        sampled = resample_corpus(source, max_per_stratum=2, seed=9)

        self.assertEqual(len(sampled["states"]), 2)
        self.assertEqual(
            sampled["summary"]["provider_zero_unique_boards"], 521
        )
        self.assertEqual(sampled["summary"]["selected_unique_boards"], 2)


if __name__ == "__main__":
    unittest.main()
