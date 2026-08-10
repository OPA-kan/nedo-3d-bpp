import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check_placement_pipeline_parity.py"
SPEC = importlib.util.spec_from_file_location(
    "check_placement_pipeline_parity", SCRIPT_PATH
)
parity = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = parity
SPEC.loader.exec_module(parity)


class PlacementPipelineParityTests(unittest.TestCase):
    def test_comparable_ignores_only_wall_clock_measurements(self):
        record = {
            "budget": 128,
            "top": ["candidate"],
            "chosen": "candidate",
            "top_attempts": 128,
            "choose_attempts": 128,
            "top_seconds": 1.0,
            "choose_seconds": 2.0,
        }

        self.assertEqual(
            parity.comparable(record),
            {
                "budget": 128,
                "top": ["candidate"],
                "chosen": "candidate",
                "top_attempts": 128,
                "choose_attempts": 128,
            },
        )

    def test_synthetic_observation_has_stable_item_classes(self):
        observation = parity.synthetic_observation()
        items = observation["pool_list"]

        self.assertEqual([item["index"] for item in items], list(range(6)))
        self.assertEqual(
            [item["index"] for item in items if item["is_soft"]], [4]
        )
        self.assertEqual(
            [item["index"] for item in items if item["is_prioritized"]],
            [3],
        )


if __name__ == "__main__":
    unittest.main()
