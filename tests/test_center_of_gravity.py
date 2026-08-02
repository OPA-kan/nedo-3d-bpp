"""
cog_score has no published procedure, only a direction, so the local
quantity is raw and the handling instructions travel with it.

These tests pin the arithmetic and, more importantly, the contract: the
caveat must be in the payload, and nothing may pass for a score.
"""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# By path, not via sys.path: simulator/agent.py is the synced submission and
# shadows this repository's `agent` package for later test modules.
_SPEC = importlib.util.spec_from_file_location(
    "_ground_handling_diagnostics_cog",
    ROOT / "simulator" / "src" / "ground_handling" / "diagnostics.py",
)
_D = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_D)
calculate_center_of_gravity = _D.calculate_center_of_gravity


def item(mass, z):
    return {"mass": mass, "volume": 0.008, "pos": [0.0, 0.0, z]}


def container(items, height=1.0, thickness=0.05, buffer=0.0):
    return {
        "index": 0,
        "height": height,
        "thickness": thickness,
        "buffer": buffer,
        "volume": 10.0,
        "packed_items": items,
    }


class ArithmeticTests(unittest.TestCase):
    def test_the_centre_is_mass_weighted_not_a_plain_mean(self):
        result = calculate_center_of_gravity(
            [container([item(1.0, 0.0), item(3.0, 1.0)])]
        )

        self.assertAlmostEqual(result["com_z"], 0.75, places=9)

    def test_height_is_measured_from_the_floor_not_the_origin(self):
        """
        The container floor sits at thickness + buffer, so a box resting on
        it has a positive absolute z and zero useful height. Reporting the
        absolute value alone would make a thick-walled container look worse
        for free.
        """
        result = calculate_center_of_gravity(
            [container([item(1.0, 0.1)], thickness=0.05, buffer=0.05)]
        )

        self.assertAlmostEqual(result["com_z"], 0.1, places=9)
        self.assertAlmostEqual(result["com_z_above_floor"], 0.0, places=9)

    def test_the_ratio_normalises_by_interior_height(self):
        result = calculate_center_of_gravity(
            [container([item(1.0, 0.5)], height=1.0, thickness=0.0)]
        )

        self.assertAlmostEqual(result["com_height_ratio"], 0.5, places=9)

    def test_a_lower_load_gives_a_lower_ratio(self):
        low = calculate_center_of_gravity(
            [container([item(1.0, 0.1)], thickness=0.0)]
        )
        high = calculate_center_of_gravity(
            [container([item(1.0, 0.9)], thickness=0.0)]
        )

        self.assertLess(low["com_height_ratio"], high["com_height_ratio"])

    def test_items_across_containers_form_one_centre(self):
        """"荷物全体の重心" -- one centre for the whole load, not per box."""
        result = calculate_center_of_gravity(
            [
                container([item(1.0, 0.0)]),
                container([item(1.0, 1.0)]),
            ]
        )

        self.assertAlmostEqual(result["com_z"], 0.5, places=9)


class EmptyTests(unittest.TestCase):
    def test_an_empty_load_reports_nothing_rather_than_zero(self):
        """
        Zero is the best possible centre of gravity. An empty container
        must not score it.
        """
        result = calculate_center_of_gravity([container([])])

        self.assertIsNone(result["com_z"])
        self.assertIsNone(result["com_height_ratio"])

    def test_massless_items_do_not_divide_by_zero(self):
        result = calculate_center_of_gravity([container([item(0.0, 0.5)])])

        self.assertIsNone(result["com_z"])

    def test_a_zero_height_container_yields_no_ratio(self):
        result = calculate_center_of_gravity(
            [container([item(1.0, 0.0)], height=0.0)]
        )

        self.assertIsNone(result["com_height_ratio"])
        self.assertIsNotNone(result["com_z"])


class ContractTests(unittest.TestCase):
    def test_the_caveat_travels_with_the_number(self):
        """
        The point of storing this at all is that the next reader -- person
        or model -- gets the handling instructions at the point of use,
        without having to know a document exists.
        """
        result = calculate_center_of_gravity([container([item(1.0, 0.5)])])

        contract = result["com_contract"]
        self.assertIn("not a score", contract)
        self.assertIn("unpublished", contract)
        self.assertIn("SAME config", contract)

    def test_the_caveat_is_present_even_when_there_is_no_number(self):
        result = calculate_center_of_gravity([container([])])

        self.assertTrue(result["com_contract"])

    def test_no_field_is_named_score(self):
        result = calculate_center_of_gravity([container([item(1.0, 0.5)])])

        self.assertFalse([key for key in result if "score" in key])


if __name__ == "__main__":
    unittest.main()
