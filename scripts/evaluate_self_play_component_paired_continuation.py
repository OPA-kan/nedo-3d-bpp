"""Physically validate component-V proposals with paired continuations.

The shadow value model only nominates roots.  This script reconstructs each
root twice, forces either the MCTS incumbent or the nominated action, and then
returns both arms to the same unchanged hand-coded policy until termination.
Final fill, CoG, priority, soft, placed gate, and local shake proxies remain a
vector; no unpublished official weights are invented.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"
for path in (ROOT, SIMULATOR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.build_paired_search_follow import (  # noqa: E402
    compare_arms,
    run_arm,
)
from scripts.build_replay_dataset import load_agent_module, require_supported_python  # noqa: E402
from scripts.counterfactual_graph import canonical_action  # noqa: E402
from scripts.evaluate_self_play_component_value_shadow import select_candidate  # noqa: E402


def _read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def discovery_proposals(
    shadow: dict[str, Any], dataset: list[dict[str, Any]], *, beta: float,
) -> list[dict[str, Any]]:
    """Join stored estimates to replay actions and reapply a declared beta."""
    source = {
        (str(row["pair_id"]), int(row["step"])): row for row in dataset
    }
    proposals = []
    for record in shadow.get("records", []):
        if not record.get("eligible"):
            continue
        incumbent_id = str(record["incumbent_candidate_id"])
        decision = select_candidate(
            record["candidate_estimates"],
            incumbent_id=incumbent_id,
            beta=beta,
        )
        if not decision["changed"]:
            continue
        key = (str(record["pair_id"]), int(record["step"]))
        row = source.get(key)
        if row is None:
            raise ValueError(f"shadow root is absent from dataset: {key}")
        actions = {
            str(candidate["candidate_id"]): canonical_action(
                candidate["command_action"]
            )
            for candidate in row.get("policy_target", [])
        }
        selected_id = str(decision["selected_candidate_id"])
        missing = [
            identifier for identifier in (incumbent_id, selected_id)
            if identifier not in actions
        ]
        if missing:
            raise ValueError(f"candidate actions missing at {key}: {missing}")
        proposals.append({
            "pair_id": key[0],
            "case_id": str(row["case_id"]),
            "step": key[1],
            "trajectory_group": str(row["trajectory_group"]),
            "future_stream_id": str(row["future_stream_id"]),
            "incumbent_candidate_id": incumbent_id,
            "selected_candidate_id": selected_id,
            "incumbent_action": actions[incumbent_id],
            "selected_action": actions[selected_id],
            "shadow_comparison": decision["comparisons_to_incumbent"][selected_id],
        })
    return sorted(
        proposals, key=lambda row: (row["pair_id"], row["step"])
    )


def _source_paths(
    source_root: pathlib.Path, proposal: dict[str, Any],
) -> tuple[pathlib.Path, pathlib.Path]:
    pair_root = source_root / proposal["pair_id"]
    snapshot = (
        pair_root / "mcts" / "game-000"
        / f"step-{int(proposal['step']):03d}-state.json"
    )
    scenario = proposal["case_id"]
    if scenario.startswith("m-"):
        scenario = scenario[2:]
    config = pair_root / "configs" / f"{scenario}.json"
    for path in (snapshot, config):
        if not path.is_file():
            raise FileNotFoundError(path)
    return snapshot, config


def run_proposal(
    proposal: dict[str, Any], *, source_root: pathlib.Path,
    output_dir: pathlib.Path, policy_generation: str,
) -> dict[str, Any]:
    snapshot_path, config_path = _source_paths(source_root, proposal)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    task_config = config[proposal["case_id"]]
    agent_module = load_agent_module()
    root_dir = output_dir / f"{proposal['pair_id']}-step-{proposal['step']:03d}"
    common = {
        "agent_module": agent_module,
        "task_config": task_config,
        "snapshot": snapshot,
        # The compared incumbent came from MCTS visits, so it need not equal
        # the hand-coded policy action.  We still call that policy at the
        # root to keep its internal state synchronized before continuation.
        "incumbent_action": proposal["incumbent_action"],
        "require_live_incumbent": False,
        "capture_offsets": {3, 6},
        "policy_generation": policy_generation,
    }
    incumbent = run_arm(
        **common, arm="incumbent",
        root_action=proposal["incumbent_action"],
        output_dir=root_dir / "incumbent",
    )
    candidate = run_arm(
        **common, arm="candidate",
        root_action=proposal["selected_action"],
        output_dir=root_dir / "candidate",
    )
    execution_valid = bool(
        incumbent["root_action_accepted"] and candidate["root_action_accepted"]
        and incumbent["root_fingerprint_matches"]
        and candidate["root_fingerprint_matches"]
    )
    return {
        **proposal,
        "snapshot_path": snapshot_path.as_posix(),
        "execution_valid": execution_valid,
        "arms": {"incumbent": incumbent, "candidate": candidate},
        "comparison": compare_arms(incumbent, candidate),
    }


def summarize(
    records: list[dict[str, Any]], *, beta: float, proposal_count: int,
) -> dict[str, Any]:
    valid = [row for row in records if row.get("execution_valid")]
    relations = collections.Counter(
        row["comparison"]["pareto_relation"] for row in valid
    )
    deltas = [row["comparison"]["raw_deltas"] for row in valid]

    def mean(name: str) -> float | None:
        values = [float(row[name]) for row in deltas if row.get(name) is not None]
        return sum(values) / len(values) if values else None

    return {
        "schema_version": 1,
        "experiment": "paired_component_value_continuation",
        "scalarization": False,
        "discovery_beta": float(beta),
        "proposal_count": int(proposal_count),
        "executed_records": len(records),
        "valid_records": len(valid),
        "pareto_relations": dict(sorted(relations.items())),
        "mean_candidate_minus_incumbent": {
            name: mean(name) for name in (
                "fill", "cog", "placement", "soft", "gate",
                "stability.max_shift", "stability.peak_kinetic_energy",
                "stability.items_shifted", "stability.items_toppled",
            )
        },
        "official_score_claim": False,
        "reason": (
            "official component normalization and weights are unpublished; "
            "local stability is a deterministic proxy"
        ),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow", type=pathlib.Path, required=True)
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument("--source-root", type=pathlib.Path, required=True)
    parser.add_argument("--beta", type=float, default=0.25)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--policy-generation", default="pi0-component-pilot")
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    if args.beta < 0.0:
        raise SystemExit("beta must be non-negative")
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("invalid shard")
    shadow = json.loads(args.shadow.read_text(encoding="utf-8"))
    proposals = discovery_proposals(
        shadow, _read_jsonl(args.dataset), beta=args.beta
    )
    selected = [
        row for index, row in enumerate(proposals)
        if index % args.shard_count == args.shard_index
    ]
    records = [
        run_proposal(
            row, source_root=args.source_root,
            output_dir=args.output_dir,
            policy_generation=args.policy_generation,
        )
        for row in selected
    ]
    result = summarize(records, beta=args.beta, proposal_count=len(proposals))
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.json_output)
    return 0 if len(records) == len(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
