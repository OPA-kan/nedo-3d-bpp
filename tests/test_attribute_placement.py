"""
The published half of placement_score and soft_item_score.

These are rule transcriptions, so the tests are written as the rule text
reads: what is penalised, what is explicitly NOT penalised, and what is
only penalised under a precondition. A test that merely pinned the current
output would not catch a misreading of the rule, which is the only failure
mode that matters here.
"""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Loaded by path rather than by putting simulator/ on sys.path: the
# submission is synced there as simulator/agent.py, which shadows this
# repository's `agent` package for every test module that runs afterwards.
_SPEC = importlib.util.spec_from_file_location(
    "_ground_handling_diagnostics",
    ROOT / "simulator" / "src" / "ground_handling" / "diagnostics.py",
)
_DIAGNOSTICS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_DIAGNOSTICS)
calculate_attribute_placement = _DIAGNOSTICS.calculate_attribute_placement


def item(index, x=0.0, y=0.0, z=0.0, size=0.2, **flags):
    half = size / 2.0
    return {
        "index": index,
        "mass": 1.0,
        "volume": size ** 3,
        "pos": [x, y, z],
        "aabb_min": [x - half, y - half, z - half],
        "aabb_max": [x + half, y + half, z + half],
        "is_soft": bool(flags.get("soft", False)),
        "is_prioritized": bool(flags.get("priority", False)),
    }


def container(items, *, prioritized=False, index=0):
    return {
        "index": index,
        "volume": 10.0,
        "is_prioritized": prioritized,
        "packed_items": items,
    }


def stacked(lower_flags, upper_flags):
    """Two boxes, the second resting exactly on the first."""
    return [item(0, z=0.0, **lower_flags), item(1, z=0.2, **upper_flags)]


class CoverageRuleTests(unittest.TestCase):
    def test_a_rigid_item_on_a_soft_one_is_a_violation(self):
        result = calculate_attribute_placement(
            [container(stacked({"soft": True}, {}))]
        )

        self.assertEqual(result["soft_covered_by_other"], 1)

    def test_soft_on_soft_is_explicitly_free(self):
        """README:379 -- same-attribute stacking carries no penalty."""
        result = calculate_attribute_placement(
            [container(stacked({"soft": True}, {"soft": True}))]
        )

        self.assertEqual(result["soft_covered_by_other"], 0)
        self.assertEqual(result["soft_clean_ratio"], 1.0)

    def test_priority_on_priority_is_explicitly_free(self):
        result = calculate_attribute_placement(
            [container(stacked({"priority": True}, {"priority": True}))]
        )

        self.assertEqual(result["priority_covered_by_other"], 0)

    def test_the_two_attributes_are_judged_independently(self):
        """
        A soft cover over a priority item satisfies neither rule for the
        item beneath: it is priority covered by non-priority. Pinned because
        reading the rules as one combined class is the obvious misreading.
        """
        result = calculate_attribute_placement(
            [container(stacked({"priority": True}, {"soft": True}))]
        )

        self.assertEqual(result["priority_covered_by_other"], 1)
        self.assertEqual(result["soft_covered_by_other"], 0)

    def test_an_item_that_is_both_needs_a_cover_that_is_both(self):
        result = calculate_attribute_placement(
            [container(stacked({"soft": True, "priority": True}, {"soft": True}))]
        )

        self.assertEqual(result["priority_covered_by_other"], 1)
        self.assertEqual(result["soft_covered_by_other"], 0)

    def test_an_item_alongside_rather_than_above_is_not_a_cover(self):
        result = calculate_attribute_placement(
            [container([item(0, soft=True), item(1, x=0.25)])]
        )

        self.assertEqual(result["soft_covered_by_other"], 0)

    def test_an_item_floating_well_clear_is_not_a_cover(self):
        result = calculate_attribute_placement(
            [container([item(0, soft=True), item(1, z=1.0)])]
        )

        self.assertEqual(result["soft_covered_by_other"], 0)

    def test_one_item_is_counted_once_however_many_things_cover_it(self):
        """The rule is about the buried item, not the number of burials."""
        items = [
            item(0, soft=True),
            item(1, x=-0.05, z=0.2),
            item(2, x=0.05, z=0.2),
        ]

        result = calculate_attribute_placement([container(items)])

        self.assertEqual(result["soft_covered_by_other"], 1)


class RoutingRuleTests(unittest.TestCase):
    def test_a_priority_item_in_a_plain_container_is_misrouted(self):
        result = calculate_attribute_placement(
            [
                container([item(0, priority=True)], index=0),
                container([], prioritized=True, index=1),
            ]
        )

        self.assertEqual(result["priority_misrouted"], 1)

    def test_misrouting_needs_a_priority_container_to_exist(self):
        """
        "優先手荷物用のコンテナがあるのに" is a precondition, not decoration.
        Every stream without one would otherwise score a fabricated penalty.
        """
        result = calculate_attribute_placement(
            [container([item(0, priority=True)])]
        )

        self.assertEqual(result["priority_misrouted"], 0)
        self.assertFalse(result["has_priority_container"])

    def test_a_priority_item_in_its_own_container_is_clean(self):
        result = calculate_attribute_placement(
            [container([item(0, priority=True)], prioritized=True)]
        )

        self.assertEqual(result["priority_misrouted"], 0)
        self.assertEqual(result["priority_clean_ratio"], 1.0)


class RatioTests(unittest.TestCase):
    def test_an_absent_attribute_yields_no_opinion_rather_than_a_perfect_score(
        self,
    ):
        """
        None, not 1.0. A stream with no soft cargo has nothing to say, and
        averaging a fabricated 1.0 across arms would dilute the episodes
        that do carry soft items.
        """
        result = calculate_attribute_placement([container([item(0)])])

        self.assertIsNone(result["soft_clean_ratio"])
        self.assertIsNone(result["priority_clean_ratio"])

    def test_the_ratio_falls_as_violations_accumulate(self):
        clean = calculate_attribute_placement(
            [container([item(0, soft=True), item(1, soft=True, x=0.5)])]
        )
        half = calculate_attribute_placement(
            [
                container(
                    [
                        item(0, soft=True),
                        item(1, z=0.2),
                        item(2, soft=True, x=0.5),
                    ]
                )
            ]
        )

        self.assertEqual(clean["soft_clean_ratio"], 1.0)
        self.assertEqual(half["soft_clean_ratio"], 0.5)

    def test_the_priority_ratio_cannot_go_negative_when_both_rules_fire(self):
        """
        One item can be both covered and misrouted. The counts are reported
        separately and honestly; the ratio must not run past zero.
        """
        result = calculate_attribute_placement(
            [
                container(
                    [item(0, priority=True), item(1, z=0.2)], index=0
                ),
                container([], prioritized=True, index=1),
            ]
        )

        self.assertEqual(result["priority_covered_by_other"], 1)
        self.assertEqual(result["priority_misrouted"], 1)
        self.assertEqual(result["priority_clean_ratio"], 0.0)


class ContractTests(unittest.TestCase):
    def test_no_field_is_named_score(self):
        """
        The violations-to-0-100 mapping is unpublished, so nothing here may
        pass for the official number. The naming is the guardrail.
        """
        result = calculate_attribute_placement([container([item(0)])])

        self.assertFalse([key for key in result if "score" in key])


if __name__ == "__main__":
    unittest.main()
