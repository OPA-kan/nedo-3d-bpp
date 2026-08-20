"""Record the official shake's own post-shake state. No clone.

Preregistered in `reports/hazard/post-shake-direct-protocol.md`.

## What this is for

The local soft/priority proxy reads the settled state BEFORE the
bundled shake. The official soft_item_score procedure is unpublished
and may read after it, which left `soft` as the one score axis whose
local instrument has never agreed with official feedback. Two earlier
instruments tried to rebuild the terminal state in a second DIRECT
world and shake the copy; both failed their fidelity gates
(`reports/hazard/post-shake/verdict.md`,
`reports/hazard/post-shake/revalidation-verdict.md`), the second one on
peak kinetic energy, which a rebuilt world cannot reproduce in
principle.

The rebuild was never necessary. `Evaluator.shake_test` computes, in
the live world:

    before = self._live_poses(containers)
    ... official gravity schedule ...
    after  = self._live_poses(containers)
    finally: restoreState(...)

`after` is the exact post-shake state, produced by the official code on
every run and then discarded. This module records it instead.

## How the interception is safe

`_live_poses` is called from nowhere in `evaluator.py` except
`shake_test` (`settled_snapshot` reads poses directly), so wrapping it
for the duration of one `shake_test` call is unambiguous. On the
post-shake call the wrapper delegates to the original and then calls
the evaluator's OWN `settled_snapshot(containers)` while the world
still holds the post-shake state. That call only reads (`get_pose`,
`getAABB`); it steps nothing. `shake_test`'s `finally` restores the
state regardless, so the episode is left exactly as `shake_test` left
it before.

The post-shake attribute counts come from
`calculate_attribute_placement` via `settled_snapshot` -- the same
function the pre-shake proxy uses. The soft/priority contract is not
reimplemented here; that is gate G3.

Nothing under `simulator/` is modified, no agent knob is added, and the
agent's behaviour is untouched.

## Use

Set `NEDO_POSTSHAKE_CAPTURE` to an output path and run the episode
through `scripts/run_test_capture.py` (a wrapper around the bundled
`run_test.py` that calls `install()` first). With the variable unset,
`install()` is a no-op and the run is the stock run -- gate G1 checks
that claim empirically.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any

_INSTALLED = False


def capture_shake_labels(evaluator, containers) -> dict[str, Any]:
    """Run one bundled shake and retain its exact pre/post state metrics.

    ``Evaluator.shake_test`` restores the PyBullet state before returning, so
    callers cannot read the shaken board afterwards.  This helper shadows
    ``_live_poses`` on this evaluator instance only and takes the evaluator's
    own read-only ``settled_snapshot`` at the two points the bundled shake
    already exposes.  It neither reimplements the attribute rule nor changes
    the state that ``shake_test`` restores.

    Unlike :func:`install`, this is an in-process measurement seam for offline
    branch builders.  It deliberately does not run the second control shake;
    the recorder's no-op property was already established by the frozen v3
    fidelity campaign, and doubling every graph-edge shake would only add
    measurement cost.
    """
    original_live_poses = evaluator._live_poses
    instance_dict = getattr(evaluator, "__dict__", {})
    had_instance_override = "_live_poses" in instance_dict
    previous_instance_value = instance_dict.get("_live_poses")
    calls: list[list[dict]] = []
    captured: dict[str, Any] = {}

    def recording_live_poses(inner_containers):
        poses = original_live_poses(inner_containers)
        calls.append(poses)
        which = "pre_shake" if len(calls) == 1 else "post_shake"
        if which not in captured:
            captured[which] = evaluator.settled_snapshot(inner_containers)
        return poses

    evaluator._live_poses = recording_live_poses
    try:
        response = evaluator.shake_test(containers)
    finally:
        if had_instance_override:
            evaluator._live_poses = previous_instance_value
        else:
            delattr(evaluator, "_live_poses")

    return {
        "shake_response": response,
        "live_poses_calls": len(calls),
        "pre_shake": captured.get("pre_shake"),
        "post_shake": captured.get("post_shake"),
    }


def _capture_path() -> pathlib.Path | None:
    raw = os.environ.get("NEDO_POSTSHAKE_CAPTURE", "").strip()
    if not raw:
        return None
    return pathlib.Path(raw)


def install() -> bool:
    """Wrap Evaluator.shake_test to record pre/post-shake metrics.

    Returns True if the recorder was installed. Idempotent; a no-op
    when NEDO_POSTSHAKE_CAPTURE is unset, so the same wrapper script
    serves both arms of the no-op gate.
    """
    global _INSTALLED
    if _INSTALLED:
        return True
    if _capture_path() is None:
        return False

    from src.ground_handling.evaluator import Evaluator

    original_shake_test = Evaluator.shake_test
    original_live_poses = Evaluator._live_poses

    records: list[dict[str, Any]] = []

    def shake_test(self, containers):  # type: ignore[no-untyped-def]
        calls: list[list[dict]] = []
        captured: dict[str, Any] = {}

        def recording_live_poses(inner_self, inner_containers):
            poses = original_live_poses(inner_self, inner_containers)
            calls.append(poses)
            # Call 1 is `before` (pre-shake), call 2 is `after`
            # (post-shake, still live -- restoreState has not run).
            # settled_snapshot only reads; it cannot perturb either.
            which = "pre_shake" if len(calls) == 1 else "post_shake"
            if which not in captured:
                captured[which] = original_settled_snapshot(
                    inner_self, inner_containers
                )
            return poses

        original_settled_snapshot = Evaluator.settled_snapshot
        Evaluator._live_poses = recording_live_poses
        try:
            response = original_shake_test(self, containers)
        finally:
            Evaluator._live_poses = original_live_poses

        # G1a (protocol post-shake-direct-protocol.md): the official
        # method saves and restores state, so calling it again -- this
        # time entirely unwrapped -- must return the same answer on the
        # same terminal state. A recorder that perturbed the world, or a
        # settled_snapshot read that was not read-only, shows up here as
        # a divergence. Compared on the same state, so run-to-run timing
        # nondeterminism cannot confound it.
        control = original_shake_test(self, containers)
        noop_check = {
            "control_matches": control == response,
            "live_poses_calls": len(calls),
            "expected_live_poses_calls": 2,
            "wrapped": response,
            "control": control,
        }

        records.append(
            {
                "shake_response": response,
                "live_poses_calls": len(calls),
                "noop_check": noop_check,
                "pre_shake": captured.get("pre_shake"),
                "post_shake": captured.get("post_shake"),
            }
        )
        _write(records)
        return response

    Evaluator.shake_test = shake_test
    _INSTALLED = True
    return True


def _write(records: list[dict[str, Any]]) -> None:
    path = _capture_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"episodes": records}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


ATTRIBUTE_KEYS = (
    "soft_items",
    "soft_covered_by_other",
    "soft_clean_ratio",
    "priority_items",
    "priority_covered_by_other",
    "priority_misrouted",
    "priority_clean_ratio",
    "has_priority_container",
)


def attribute_counts(metrics: dict | None) -> dict[str, Any]:
    """Project a settled_snapshot metrics dict onto the attribute axes.

    Keys absent from a given simulator build are omitted rather than
    defaulted, so a contract change surfaces as a missing key in the
    gate report instead of a silent zero.
    """
    if not metrics:
        return {}
    return {k: metrics[k] for k in ATTRIBUTE_KEYS if k in metrics}
