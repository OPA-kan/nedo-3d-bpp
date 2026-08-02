import random
import unittest

from scripts import build_stream_variants as variants


def item(index, *, length=0.5, soft=False, priority=False, mass=8):
    return {
        "index": index,
        "length": length,
        "width": 0.4,
        "height": 0.24,
        "mass": mass,
        "is_soft": soft,
        "is_prioritized": priority,
        "lateralFriction": 0.4,
    }


class PermuteTests(unittest.TestCase):
    """
    Permute is the noise probe, so it must vary arrival order and nothing
    else. If content drifts, a null comparison stops being null.
    """

    def _source(self):
        return [
            item(0),
            item(1, length=0.3, soft=True),
            item(2, length=0.7, priority=True),
            item(3, mass=12),
        ]

    def test_the_multiset_is_preserved_exactly(self):
        source = self._source()

        drawn = variants.build_variant(
            source, mode="permute", rng=random.Random(1)
        )

        self.assertEqual(
            variants.stream_profile(drawn),
            variants.stream_profile(source),
        )

    def test_index_is_reassigned_positionally(self):
        drawn = variants.build_variant(
            self._source(), mode="permute", rng=random.Random(7)
        )

        self.assertEqual([i["index"] for i in drawn], [0, 1, 2, 3])

    def test_non_dimensional_attributes_travel_with_the_item(self):
        drawn = variants.build_variant(
            self._source(), mode="permute", rng=random.Random(3)
        )

        heavy = [i for i in drawn if i["mass"] == 12]
        self.assertEqual(len(heavy), 1)
        self.assertEqual(heavy[0]["lateralFriction"], 0.4)

    def test_the_same_seed_reproduces_the_same_stream(self):
        source = self._source()

        first = variants.build_variant(
            source, mode="permute", rng=random.Random(11)
        )
        second = variants.build_variant(
            source, mode="permute", rng=random.Random(11)
        )

        self.assertEqual(first, second)

    def test_the_source_list_is_not_mutated(self):
        source = self._source()
        before = [dict(i) for i in source]

        variants.build_variant(source, mode="permute", rng=random.Random(5))

        self.assertEqual(source, before)


class ResampleTests(unittest.TestCase):
    def test_length_is_preserved_but_content_may_drift(self):
        source = [item(i, length=0.1 * (i + 1)) for i in range(6)]

        drawn = variants.build_variant(
            source, mode="resample", rng=random.Random(2)
        )

        self.assertEqual(len(drawn), len(source))

    def test_only_whole_source_items_appear(self):
        source = [item(0), item(1, length=0.3, soft=True)]
        signatures = {variants.class_signature(i) for i in source}

        drawn = variants.build_variant(
            source, mode="resample", rng=random.Random(4)
        )

        for entry in drawn:
            self.assertIn(variants.class_signature(entry), signatures)


class ModeTests(unittest.TestCase):
    def test_an_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            variants.build_variant(
                [item(0)], mode="jitter", rng=random.Random(0)
            )


if __name__ == "__main__":
    unittest.main()
