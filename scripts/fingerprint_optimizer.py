"""
Behavioural regression fingerprint over declared probes, for the Task A
offline optimizer.

`Agent.optimize` has been touched by 2 of the 33 commits that changed
`agent/agent.py`, yet the optimizer it defines has changed roughly a dozen
times. ADR-001 section 2 requires the offline dry run to replay the online
placement core, so

    E_theta(pi) = DryRun(pi ; PlacementCore_theta)

and every change to candidate generation, anchor order, release candidates,
support/geometry validation, rescue, ranking or risk rerank moves
`PlacementCore_theta` and therefore moves `E_theta` -- silently, with no
offline file in the diff. `git log -- agent/agent.py` cannot see this, and
the evidence ledger's `status` cannot either: an entry goes stale because
the substrate moved, not because anyone re-measured.

This computes an identity for the whole dependency graph reachable from the
dry run, in two layers:

- **components**: the declared constants that parameterise theta.
- **behaviour**: what the core actually *does* on a fixed, tiny state set --
  the enumerated candidate stream, the chosen action, the rescue action, and
  a complete dry-run result. This catches changes that no constant records,
  which is most of them.

Every probe runs with an infinite deadline and a fixed attempt budget, so
the fingerprint is a property of the code, never of the machine it ran on.
That matters: the deadline-driven arm of the dry run is measurably
machine-speed dependent (see docs/MEASUREMENT_AUDIT.md F6), and a
fingerprint that inherited that would be useless.

LIMITS -- this is not the mathematical identity of the optimizer.

- **Probe-bounded.** A semantic change the probes do not exercise is
  invisible. Two real examples already: the probe's winner is a settled
  candidate, so it does not expose the offline/online risk-ranking gap
  (ADR-003); and MIN_SUPPORT_RATIO 0.55 -> 0.50 leaves `behaviour`
  untouched because the probe placements sit well above both thresholds.
  Widening the probe set strictly increases what it can catch.
- **API-generation bound.** Cores predating `PlacementCore.rescue_choose`
  (before a893922) cannot be probed at all, so this cannot fingerprint the
  whole history -- only cores sharing today's call surface.
- **Equality, not distance.** A changed hash says "different", never "how
  different" or "worse".

Read the two hashes together:

    component changed, behaviour same -> a default or an unfired condition
    component same, behaviour changed -> internal semantics moved
    both changed                      -> configuration and behaviour both
    neither changed                   -> unchanged *within probe coverage*
"""
from __future__ import annotations

import argparse
import os
import hashlib
import importlib.util
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / "agent" / "agent.py"
FINGERPRINT_PATH = ROOT / "context" / "optimizer_fingerprint.json"

# Probe budgets are fixed here, not read from the agent: the fingerprint must
# change when the agent's shipped budget changes, so it cannot use it.
PROBE_ATTEMPT_BUDGET = 96
PROBE_CANDIDATE_LIMIT = 12
INF = float("inf")


def load_agent(path: pathlib.Path = AGENT_PATH):
    spec = importlib.util.spec_from_file_location("fingerprint_agent", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


KNOBS_PATH = ROOT / "context" / "knobs.json"

# Not environment knobs, so context/knobs.json cannot carry them, but they
# still parameterise theta. Keep the list short and explicit: anything
# settable belongs in knobs.json instead.
UNSETTABLE_COMPONENTS = (
    "MIN_SUPPORT_RATIO",
    "TRANSPORT_CLEARANCE",
    "EPS",
    "OFFLINE_RANDOM_SEED",
)


def component_names(path: pathlib.Path = KNOBS_PATH) -> list[str]:
    """
    Read the semantic knobs from the canonical registry rather than from a
    list maintained here.

    The hand-written list this replaces covered 26 of the 47 environment
    knobs agent.py actually reads, and four of its names did not exist at
    all. A merge that introduced three new knobs therefore left
    component_sha256 unchanged -- the fingerprint was measuring the
    registered projection P(theta), not theta, and nothing flagged the
    difference. tests/test_knob_registry.py now fails when agent.py reads a
    knob this registry does not list.
    """
    with path.open(encoding="utf-8") as handle:
        registry = json.load(handle)
    names = [
        name for name, spec in registry["knobs"].items()
        if spec.get("semantic")
    ]
    return sorted(set(names) | set(UNSETTABLE_COMPONENTS))


def component_versions(agent) -> dict[str, Any]:
    """The declared knobs of theta. Absent names are recorded as null."""
    out: dict[str, Any] = {}
    for name in component_names():
        value = getattr(agent, name, None)
        out[name] = value if isinstance(
            value, (int, float, str, bool, type(None))
        ) else repr(value)
    return out


def _half_space_model(dims: dict, center_x: float) -> dict:
    """
    The probe container's own half-spaces, built by the SIMULATOR's builder.

    Without these the probe is a bare dimension dict, and
    rectangular_container_anchor_bounds falls back to its box formula. That
    made the fingerprint blind to ANCHOR_TRUE_ENVELOPE: the flag changed
    shipped search geometry and behaviour_sha256 did not move, a false
    negative from the drift catcher whose whole job is to catch exactly
    that. The real containers are not boxes -- seven planes, y asymmetric
    at [-W/2, +W/2 - thickness] -- and a probe that cannot represent the
    asymmetry cannot see a defect that lives in it.

    Generated rather than hand-written, through the same call chain
    ContainerManager uses (write_open_cut_corner_cup_obj, then the fixed
    rotation and offset), so this cannot drift into invented geometry.
    utils.py imports only math and numpy, so no PyBullet is required and
    the fingerprint stays runnable anywhere.
    """
    import math
    import tempfile

    sys.path.insert(0, str(ROOT / "simulator"))
    from src.ground_handling.utils import (  # noqa: E402
        aff, write_open_cut_corner_cup_obj,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        points, n_vecs = write_open_cut_corner_cup_obj(
            os.path.join(tmp_dir, "probe.obj"),
            width=dims["length"],
            height=dims["height"],
            cut_x=dims["cut_x"],
            cut_y=dims.get("cut_y", 0.0),
            depth=dims["width"],
            wall=dims["thickness"],
            bottom=dims["thickness"],
        )
    rot = [
        [1, 0, 0],
        [0, math.cos(math.pi / 2), -math.sin(math.pi / 2)],
        [0, math.sin(math.pi / 2), math.cos(math.pi / 2)],
    ]
    pos = (0.0, 0.0, dims["height"] / 2 + dims["buffer"])
    aff_points = aff(points, rot, pos)
    return {
        "center": [pos[0] + center_x, pos[1], pos[2]],
        "points": [
            (point[0] + center_x, point[1], point[2])
            for point in aff_points
        ],
        "n_vecs": aff(n_vecs, rot, intercept=(0, 0, 0)),
    }


def _container(
    agent, center_x: float = 0.0, cut_x: float = 0.44, cut_y: float = 0.4
) -> dict:
    # Dimensions and cut match the bundled case-000 container exactly. The
    # cut used to default to 0.0, which the simulator's own builder rejects
    # (`cut_x, cut_y must be > 0`) -- the probe was not a shape the
    # simulator can construct, which is the same root as the missing
    # half-spaces.
    dims = {
        "length": 2.0,
        "width": 1.45,
        "height": 1.61,
        "thickness": 0.04,
        "buffer": 0.0,
        "cut_x": cut_x,
        "cut_y": cut_y,
        "require_shelf": False,
        "is_prioritized": False,
        "packed_items": [],
    }
    return {**dims, **_half_space_model(dims, center_x)}


def _item(index: int, length: float, width: float, height: float,
          mass: float, soft: bool = False, priority: bool = False) -> dict:
    return {
        "index": index,
        "length": length,
        "width": width,
        "height": height,
        "mass": mass,
        "is_soft": soft,
        "is_prioritized": priority,
    }


def _probe_items() -> list[dict]:
    """Deliberately mixed: sizes, a soft item and a priority item, so a
    change to soft/priority support handling or to class ordering shows up."""
    return [
        _item(0, 0.55, 0.40, 0.24, 8),
        _item(1, 0.50, 0.40, 0.40, 10, soft=True),
        _item(2, 0.45, 0.30, 0.20, 5),
        _item(3, 0.35, 0.28, 0.20, 6, priority=True),
        _item(4, 0.30, 0.25, 0.20, 5),
    ]


def _round(value: Any, places: int = 6) -> Any:
    if isinstance(value, float):
        return round(value, places)
    if isinstance(value, (list, tuple)):
        return [_round(v, places) for v in value]
    return value


def _decision_digest(agent, decision) -> Any:
    if decision is None:
        return None
    action = decision.action
    return {
        "item_idx": int(action["item_idx"]),
        "container_idx": int(action["container_idx"]),
        "place_pos": _round([float(v) for v in action["place_pos"]]),
        "orientation": int(action["orientation"]),
        "score": _round(float(decision.score)),
        "kind": getattr(decision.candidate, "kind", None),
        "candidate_center": _round(
            [float(v) for v in decision.candidate.center]
        ),
    }


def behavioural_probe(agent) -> dict[str, Any]:
    """
    What the core does, not what it declares. Infinite deadlines and fixed
    attempt budgets throughout, so this is reproducible on any machine.
    """
    probe: dict[str, Any] = {}
    items = _probe_items()

    # 1. Selection on an empty container, both the anytime and the
    #    work-budgeted paths. Diverges if enumeration order, geometry,
    #    support or ranking move.
    observation = {
        "pool_list": items,
        "container_list": [_container(agent)],
    }
    indexed = list(enumerate(items))
    probe["choose"] = _decision_digest(
        agent, agent.PlacementCore.choose(observation, indexed, deadline=INF)
    )
    probe["rescue_choose"] = _decision_digest(
        agent,
        agent.PlacementCore.rescue_choose(
            observation, indexed, deadline=INF,
            attempt_budget=PROBE_ATTEMPT_BUDGET,
        ),
    )

    # 2. Per-item selection, which is exactly what the dry run does. A change
    #    that only affects multi-item pools would otherwise hide here.
    per_item = []
    for index, item in indexed:
        single = {
            "pool_list": [item],
            "container_list": [_container(agent)],
        }
        per_item.append(
            _decision_digest(
                agent,
                agent.PlacementCore.rescue_choose(
                    single, [(0, item)], deadline=INF,
                    attempt_budget=PROBE_ATTEMPT_BUDGET,
                ),
            )
        )
    probe["per_item_rescue"] = per_item

    # 3. A complete dry run: the evaluation function E_theta itself.
    evaluator = agent.DryRunEvaluator(
        [_container(agent)], attempts_per_item=PROBE_ATTEMPT_BUDGET
    )
    result = evaluator.evaluate(items, deadline=None)
    probe["dry_run"] = {
        key: _round(value)
        for key, value in agent.dataclass_to_dict(result).items()
        # runtime is wall-clock; everything else is semantics
        if key != "runtime_seconds"
    }
    probe["dry_run_rank_key"] = _round(list(result.rank_key()))

    # 4. Constructive seed order: the search's starting point.
    probe["constructive_order"] = [
        int(entry["index"]) for entry in agent.constructive_order(items)
    ]
    return probe


def live_ranking_probe(agent) -> dict[str, Any]:
    """
    The ONLINE selector, which is deliberately fingerprinted apart from
    E_theta.

    ADR-001 section 2 lists ranking among what the dry run must share with
    `policy()`. It currently does not: `Agent.policy` passes
    `risk_lambda=RELEASE_RISK_RERANK_LAMBDA`, while
    `DryRunEvaluator.evaluate` calls the core with no `risk_lambda` at all,
    so `apply_release_risk` returns release scores unchanged offline. The
    shipped executor is risk-on and the offline evaluator simulates the
    pre-risk greedy policy.

    Keeping this as a separate hash makes that gap visible instead of
    hidden: if `live_ranking_sha256` moves while `behaviour_sha256` does
    not, an online ranking change did not reach the offline evaluator, and
    the two have drifted further apart.
    """
    items = _probe_items()
    observation = {
        "pool_list": items,
        "container_list": [_container(agent)],
    }
    indexed = list(enumerate(items))
    lam = getattr(agent, "RELEASE_RISK_RERANK_LAMBDA", None)
    live_lambda = lam if getattr(
        agent, "RELEASE_RISK_LIVE_RERANK", False
    ) else None
    return {
        "live_lambda": live_lambda,
        "slide_lambda": getattr(agent, "RELEASE_RISK_SLIDE_LAMBDA", None),
        "risk_model": getattr(agent, "RELEASE_RISK_P_MODEL", None),
        "choose_risk_adjusted": _decision_digest(
            agent,
            agent.PlacementCore.choose(
                observation, indexed, deadline=INF, risk_lambda=live_lambda
            ),
        ),
        "rescue_risk_adjusted": _decision_digest(
            agent,
            agent.PlacementCore.rescue_choose(
                observation, indexed, deadline=INF,
                attempt_budget=PROBE_ATTEMPT_BUDGET,
                risk_lambda=live_lambda,
            ),
        ),
    }


def _sha(payload: Any) -> str:
    blob = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def fingerprint(agent) -> dict[str, Any]:
    components = component_versions(agent)
    behaviour = behavioural_probe(agent)
    live_ranking = live_ranking_probe(agent)
    behaviour_sha = _sha(behaviour)
    component_sha = _sha(components)
    live_sha = _sha(live_ranking)
    return {
        "version": 1,
        "contract": (
            "Behavioural regression fingerprint over declared probes for "
            "the Task A offline optimizer, scoped to the dependency graph "
            "DryRunEvaluator reaches rather than to Agent.optimize. If "
            "behaviour_sha256 changes, E_theta changed and every Task A "
            "measurement predates it -- re-run the Task A sweep and stamp "
            "the affected ledger entries with the new core_ref, even when "
            "no offline file was edited. It is NOT the optimizer's "
            "mathematical identity: changes the probes do not exercise are "
            "invisible, cores predating PlacementCore.rescue_choose cannot "
            "be probed, and a changed hash reports difference, not "
            "distance. Unchanged means unchanged WITHIN PROBE COVERAGE."
        ),
        "probe": {
            "attempt_budget": PROBE_ATTEMPT_BUDGET,
            "deadline": "infinite (fingerprint must not depend on machine speed)",
        },
        "component_sha256": component_sha,
        "behaviour_sha256": behaviour_sha,
        "live_ranking_sha256": live_sha,
        # Whether the probe *happens* to expose the offline/online ranking
        # gap. True here only means the probe's winner was a settled
        # candidate, which apply_release_risk leaves alone -- it is NOT
        # evidence that the two rankings agree in general. The structural
        # fact is established by code and by an ablation at lambda=50
        # leaving the dry run bit-identical, not by this flag.
        "probe_selection_identical": (
            live_ranking["choose_risk_adjusted"] == behaviour["choose"]
        ),
        "adr001_section2_ranking_shared": _adr001_note(live_ranking),
        "components": components,
        "behaviour": behaviour,
        "live_ranking": live_ranking,
    }


def _adr001_note(live_ranking: dict[str, Any]) -> str:
    if live_ranking["live_lambda"] is None:
        return (
            "vacuous: live rerank is off, so there is no ranking difference "
            "to share"
        )
    return (
        "VIOLATED: policy() ranks with risk_lambda="
        f"{live_ranking['live_lambda']} but DryRunEvaluator calls the core "
        "with none, so the offline evaluator simulates the pre-risk greedy "
        "policy while the shipped executor is risk-on. Undocumented "
        "simulation gap, not a recorded decision -- see "
        "docs/MEASUREMENT_AUDIT.md F8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write", action="store_true",
        help="Overwrite the stored fingerprint after a reviewed change.",
    )
    parser.add_argument(
        "--output", type=pathlib.Path, default=FINGERPRINT_PATH
    )
    args = parser.parse_args()

    current = fingerprint(load_agent())
    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(current, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.output}")
        print(f"  behaviour_sha256 {current['behaviour_sha256']}")
        return 0

    print(json.dumps(
        {
            "component_sha256": current["component_sha256"],
            "behaviour_sha256": current["behaviour_sha256"],
        },
        ensure_ascii=False, indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
