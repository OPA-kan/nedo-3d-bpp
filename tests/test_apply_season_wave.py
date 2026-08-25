import pathlib
import tempfile
import unittest
from unittest import mock

from scripts import apply_season_wave


class ApplySeasonWaveTests(unittest.TestCase):
    def test_reapplying_current_wave_is_an_idempotent_noop(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            temp = pathlib.Path(temporary)
            plan = temp / "waves.json"
            collection = temp / "collection.yml"
            learning = temp / "learning.yml"
            plan.write_bytes((root / "reports/league/season/waves.json").read_bytes())
            collection.write_bytes((root / ".github/workflows/terminal-rollout-hard-state.yml").read_bytes())
            learning.write_bytes((root / ".github/workflows/rollout-geometry-policy-learning.yml").read_bytes())
            before = collection.read_text(encoding="utf-8")
            with (
                mock.patch.object(apply_season_wave, "PLAN", plan),
                mock.patch.object(apply_season_wave, "COLLECTION", collection),
                mock.patch.object(apply_season_wave, "LEARNING", learning),
            ):
                result = apply_season_wave.apply("6")
            self.assertTrue(result["already_applied"])
            self.assertEqual(result["new_cells"], 0)
            self.assertEqual(collection.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
