"""
The release acceptance path has no support check; the settled one does.

`Geometry.rejection_reason` (settled candidates) runs containment ->
headroom -> static geometry -> **support** -> corridor. Its release
counterpart `Geometry.release_rejection_reason` runs containment ->
static geometry -> corridor and stops. The support step is simply absent.

That asymmetry is not neutral, because the two paths disagree about what
counts as a surface. `support_surfaces()` deliberately EXCLUDES soft and
prioritised items -- the rules score both "priority items buried" and
"normal items on soft items" (COMPETITION_RULES section 4) -- while
`release_rest_height()` destructures the same list as
`for box, _is_soft, _is_priority in packed_aabbs_local(container)` and
throws both flags away, so every packed item raises the rest height. A
release candidate is then centred at `rest_height + dz/2 + lift`
(agent.py:2930-2940), i.e. planned to come to rest exactly ON the item
whose flag was discarded, and nothing downstream rejects it: the risk gate
ships off (`RELEASE_RISK_GATE_MODE` default "off").

These tests demonstrate that end to end on the bundled geometry rather
than asserting it from reading. What they do NOT show is that this is what
kills any particular episode -- see reports/scenario-matrix, where the
priority-dedicated scene ends with priority_covered_by_other 2 of 3 placed
priority items. Linking the two needs per-item attribution that no
instrument here produces yet.
"""
import copy
import importlib.util
import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / "agent" / "agent.py"
SPEC = importlib.util.spec_from_file_location("release_gap_agent", AGENT_PATH)
agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent
SPEC.loader.exec_module(agent)

SOURCE = json.loads(
    (ROOT / "simulator" / "configs" / "sample_config.json")
    .read_text(encoding="utf-8")
)


def container_with(seated_flags: dict) -> tuple[dict, dict]:
    """
    A bundled container carrying one packed item on the floor.

    Geometry comes from the real sample so the containment and corridor
    checks are exercised against a genuine envelope; only the flag on the
    seated item varies between subtests.
    """
    case = copy.deepcopy(SOURCE["000"])
    container = copy.deepcopy(case["containers"]["container_list"][0])
    container["center"] = [0.0, 0.0, 0.0]
    item = copy.deepcopy(case["item_stream"]["item_list"][0])
    thickness = float(container["thickness"])
    buffer = float(container.get("buffer", 0.0))
    seated = dict(
        item,
        pos=[0.0, 0.0, thickness + buffer + float(item["height"]) / 2.0],
        orn=[0.0, 0.0, 0.0, 1.0],
        **seated_flags,
    )
    container["packed_items"] = [seated]
    # packed_aabbs_local memoises on the list object; a fresh list per call
    # keeps subtests from reading each other's cache.
    return container, seated


class ReleaseSupportGapTests(unittest.TestCase):
    def setUp(self) -> None:
        agent._PACKED_AABBS_CACHE.clear()

    def _candidates_over(self, container, dims):
        """
        The two candidates that describe the same intended stack.

        A release candidate is aimed RELEASE_TARGET_LIFT (5.2 cm) above the
        surface it will come to rest on -- the item is dropped, not seated
        -- so comparing it directly against the settled path would compare
        a floating box, and "support" would mean "in mid-air" rather than
        "the surface below is not a legal one". The settled twin is
        therefore built at the resting height itself.
        """
        rest = agent.release_rest_height(0.0, 0.0, dims, container)
        released = agent.AABB(
            (0.0, 0.0, rest + dims[2] / 2.0 + agent.RELEASE_TARGET_LIFT),
            dims, "release_candidate",
        )
        seated = agent.AABB(
            (0.0, 0.0, rest + dims[2] / 2.0), dims, "candidate"
        )
        return rest, released, seated

    def test_rest_height_rises_onto_a_priority_item(self) -> None:
        """
        The plan itself, before any acceptance check: a prioritised item
        raises the release rest height exactly as an ordinary one would.
        """
        dims = (0.3, 0.3, 0.3)
        heights = {}
        for label, flags in (
            ("normal", {"is_prioritized": False, "is_soft": False}),
            ("priority", {"is_prioritized": True, "is_soft": False}),
            ("soft", {"is_prioritized": False, "is_soft": True}),
        ):
            agent._PACKED_AABBS_CACHE.clear()
            container, seated = container_with(flags)
            heights[label] = agent.release_rest_height(
                0.0, 0.0, dims, container
            )
            expected_top = (
                float(seated["pos"][2]) + float(seated["height"]) / 2.0
            )
            with self.subTest(seated=label):
                self.assertAlmostEqual(heights[label], expected_top, places=6)

        floor = (
            float(container["thickness"])
            + float(container.get("buffer", 0.0))
        )
        self.assertGreater(heights["priority"], floor)
        self.assertEqual(heights["priority"], heights["normal"])
        self.assertEqual(heights["soft"], heights["normal"])

    def test_release_accepts_what_the_settled_path_rejects(self) -> None:
        """
        The asymmetry: the release path accepts a drop onto a flagged item
        while the settled path refuses the resulting stack, and refuses it
        for exactly the missing reason.

        The two AABBs are not identical -- they differ by the 5.2 cm
        release lift, because that is what the generator actually emits.
        The control below is what makes "support" mean the flag rather
        than the height.
        """
        dims = (0.3, 0.3, 0.3)
        for label, flags in (
            ("priority", {"is_prioritized": True, "is_soft": False}),
            ("soft", {"is_prioritized": False, "is_soft": True}),
        ):
            with self.subTest(seated=label):
                agent._PACKED_AABBS_CACHE.clear()
                container, _ = container_with(flags)
                _, released, seated = self._candidates_over(container, dims)

                self.assertIsNone(
                    agent.Geometry.release_rejection_reason(
                        released, container
                    ),
                    f"release path accepted a landing on a {label} item",
                )
                self.assertEqual(
                    agent.Geometry.rejection_reason(seated, container),
                    "support",
                    f"settled path should refuse to rest on a {label} item",
                )

    def test_the_settled_path_allows_the_same_stack_on_a_normal_item(
        self,
    ) -> None:
        """
        Control. Without this the previous test proves only that something
        about the position is unacceptable to the settled path -- it must
        accept the identical geometry when the item below carries no flag,
        or "support" would just mean "too high".
        """
        agent._PACKED_AABBS_CACHE.clear()
        dims = (0.3, 0.3, 0.3)
        container, _ = container_with(
            {"is_prioritized": False, "is_soft": False}
        )
        _, released, seated = self._candidates_over(container, dims)
        self.assertIsNone(
            agent.Geometry.rejection_reason(seated, container),
            "the settled path rejects a normal stack, so 'support' in the "
            "previous test is not evidence about the flags",
        )
        self.assertIsNone(
            agent.Geometry.release_rejection_reason(released, container),
            "both paths must accept the unflagged control",
        )

    def test_the_release_path_has_no_support_step_at_all(self) -> None:
        """
        Pins the structural claim, so a future reader does not have to
        re-derive it from two call sites. REJECTION_REASONS lists support;
        the release path can never return it.
        """
        self.assertIn("support", agent.REJECTION_REASONS)
        source = AGENT_PATH.read_text(encoding="utf-8")
        start = source.index("def release_rejection_reason")
        end = source.index("def valid", start)
        body = source[start:end]
        self.assertNotIn("has_stable_support", body)
        for expected in ("inside_container", "clears_static_geometry",
                         "transport_path_clear"):
            self.assertIn(expected, body)


if __name__ == "__main__":
    unittest.main()
