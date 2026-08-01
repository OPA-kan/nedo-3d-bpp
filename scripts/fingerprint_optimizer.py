"""
Fingerprint the *semantics* of the Task A offline optimizer.

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
"""
from __future__ import annotations

import argparse
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


def component_versions(agent) -> dict[str, Any]:
    """The declared knobs of theta. Absent names are recorded as null."""
    names = (
        # candidate generation / enumeration order
        "ANCHOR_GENERATOR_MODE",
        "SHALLOW_ANCHOR_ATTEMPTS",
        "DEEP_ANCHOR_ATTEMPTS",
        # feasibility / geometry
        "BOUNDARY_MARGIN",
        "TRANSPORT_CLEARANCE",
        "MIN_SUPPORT_RATIO",
        "FLOOR_ACTION_LIFT",
        "EPS",
        # ranking / risk
        "RELEASE_RISK_GATE_MODE",
        "RELEASE_RISK_LIVE_RERANK",
        "RELEASE_RISK_P_MODEL",
        "RELEASE_RISK_RERANK_LAMBDA",
        "RELEASE_RISK_SLIDE_LAMBDA",
        # selection / rescue
        "RESCUE_SCAN_ENABLED",
        "RESCUE_SCAN_ATTEMPT_BUDGET",
        "CROSS_STEP_INCUMBENT_MODE",
        "VISIBLE_POOL_ROLLOUT_MODE",
        "ITEM_COVERAGE_MODE",
        "LOOKAHEAD_SELECTION_MODE",
        # offline search budget
        "OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM",
        "OFFLINE_PAIR_MACRO_BUDGET_SECONDS",
        "OFFLINE_SEARCH_BUDGET_SECONDS",
        "OFFLINE_MAX_EVALUATIONS",
        "OFFLINE_RANDOM_SEED",
        "OFFLINE_FILL_WEIGHT",
        "OFFLINE_STABILITY_WEIGHT",
    )
    out: dict[str, Any] = {}
    for name in names:
        value = getattr(agent, name, None)
        out[name] = value if isinstance(
            value, (int, float, str, bool, type(None))
        ) else repr(value)
    return out


def _container(agent, center_x: float = 0.0, cut_x: float = 0.0) -> dict:
    return {
        "length": 2.0,
        "width": 1.45,
        "height": 1.61,
        "thickness": 0.04,
        "buffer": 0.0,
        "cut_x": cut_x,
        "require_shelf": False,
        "is_prioritized": False,
        "center": [center_x, 0.0, 0.0],
        "packed_items": [],
    }


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
            "Semantic identity of the Task A offline optimizer, defined as "
            "the whole dependency graph DryRunEvaluator reaches, not as "
            "Agent.optimize. If behaviour_sha256 changes, E_theta changed "
            "and every Task A measurement predates it -- re-run the Task A "
            "sweep and stamp the affected ledger entries with the new "
            "core_ref, even when no offline file was edited."
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
