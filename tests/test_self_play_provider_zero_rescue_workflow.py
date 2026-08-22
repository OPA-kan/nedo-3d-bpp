import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ProviderZeroRescueWorkflowTests(unittest.TestCase):
    def test_workflow_freezes_sample_then_runs_physical_shards(self):
        text = (
            ROOT / ".github" / "workflows"
            / "self-play-provider-zero-rescue.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch", text)
        self.assertIn("[skip provider rescue]", text)
        self.assertIn("max_per_stratum", text)
        self.assertIn("provider-zero-corpus-32572648489.json", text)
        self.assertIn("extract_provider_zero_corpus.py", text)
        self.assertIn("source_run_id", text)
        self.assertIn("self-play-puct-matrix-aggregate-", text)
        self.assertIn("run_provider_zero_rescue.py", text)
        self.assertIn("tests.test_run_provider_zero_rescue", text)
        self.assertIn("shard_index: [0, 1, 2, 3, 4, 5, 6, 7]", text)
        self.assertIn("NEDO_REQUIRE_INTEGRATION", text)
        self.assertIn("evaluate_provider_zero_rescue.py", text)
        self.assertIn("provider-zero-rescue-aggregate-", text)


if __name__ == "__main__":
    unittest.main()
