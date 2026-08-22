"""Extract replayable provider-zero states from a convergence run.

The convergence shards repeat some physical boards through different search
paths.  Provider recall is therefore reported both per exhausted node and per
unique board.  One deterministic representative replay contract is retained
for every unique board so rescue proposals can be tested without treating
transpositions as independent examples.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
from typing import Any


def _step_band(step: int) -> str:
    if step <= 8:
        return "early_le8"
    if step <= 10:
        return "mid_9_10"
    return "late_ge11"


def _stratum(record: dict[str, Any]) -> str:
    return f"{record['case_id']}|{_step_band(int(record['effective_step']))}"


def collect_provider_zero_states(
    aggregate: dict[str, Any], shards: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    references = {
        str(root["root_id"]): str(root["reference_condition"])
        for root in aggregate.get("roots", [])
    }
    by_node: dict[str, dict[str, Any]] = {}
    for payload in shards:
        if payload.get("complete") is not True:
            raise ValueError(
                f"incomplete convergence shard: {payload.get('shard_index')}"
            )
        for root in payload.get("roots", []):
            root_id = str(root["root_id"])
            if root_id not in references:
                raise ValueError(f"aggregate has no reference for {root_id}")
            label = references[root_id]
            condition = root.get("conditions", {}).get(label)
            if condition is None:
                raise ValueError(f"root {root_id} missing reference {label}")
            for audit in condition.get("candidate_exhaustion_audits", []):
                if int(audit.get("wider_proposal_count", 0)) != 0:
                    continue
                if int(audit.get("top_k_proposal_count", 0)) != 0:
                    raise ValueError(
                        "wider provider empty despite a nonempty Top-K prefix"
                    )
                node_key = str(audit["node_key"])
                contract = audit["replay_contract"]
                record = {
                    "node_key": node_key,
                    "root_id": root_id,
                    "case_id": str(root["case_id"]),
                    "source_manifest": str(root["source_manifest"]),
                    "root_step": int(root["step"]),
                    "depth": int(audit["depth"]),
                    "effective_step": len(audit["absolute_action_prefix"]),
                    "board_fingerprint": str(audit["board_fingerprint"]),
                    "model_visible_state_signature": str(
                        audit["model_visible_state_signature"]
                    ),
                    # Prefix replay consumes only these three fields.  Avoid
                    # copying stream-manager telemetry and a second copy of
                    # the same absolute prefix into the durable corpus.
                    "replay_contract": {
                        "seed": int(contract["seed"]),
                        "item_order": list(contract["item_order"]),
                        "action_prefix": list(
                            audit["absolute_action_prefix"]
                        ),
                    },
                }
                if record["effective_step"] != (
                    record["root_step"] + record["depth"]
                ):
                    raise ValueError(
                        f"inconsistent replay depth at {node_key}"
                    )
                previous = by_node.get(node_key)
                if previous is not None and previous != record:
                    raise ValueError(f"node audit changed for {node_key}")
                by_node[node_key] = record

    by_board: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in by_node.values():
        by_board[record["board_fingerprint"]].append(record)

    states = []
    for board, occurrences in sorted(by_board.items()):
        ordered = sorted(occurrences, key=lambda row: row["node_key"])
        representative = dict(ordered[0])
        representative["occurrence_count"] = len(ordered)
        representative["occurrence_node_keys"] = [
            row["node_key"] for row in ordered
        ]
        representative["stratum"] = _stratum(representative)
        states.append(representative)

    node_case_counts = collections.Counter(
        row["case_id"] for row in by_node.values()
    )
    board_case_counts = collections.Counter(row["case_id"] for row in states)
    board_stratum_counts = collections.Counter(row["stratum"] for row in states)
    summary = {
        "provider_zero_nodes": len(by_node),
        "provider_zero_unique_boards": len(states),
        "node_counts_by_case": dict(sorted(node_case_counts.items())),
        "board_counts_by_case": dict(sorted(board_case_counts.items())),
        "board_counts_by_stratum": dict(sorted(board_stratum_counts.items())),
    }
    return states, summary


def sample_states(
    states: list[dict[str, Any]], *, max_per_stratum: int, seed: int,
) -> list[dict[str, Any]]:
    if max_per_stratum < 0:
        raise ValueError("max_per_stratum must be non-negative")
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for state in states:
        grouped[str(state["stratum"])].append(state)
    selected = []
    for stratum, rows in sorted(grouped.items()):
        ordered = sorted(
            rows,
            key=lambda row: hashlib.sha256(
                f"{seed}:{stratum}:{row['board_fingerprint']}".encode("utf-8")
            ).hexdigest(),
        )
        selected.extend(
            ordered if max_per_stratum == 0 else ordered[:max_per_stratum]
        )
    return sorted(selected, key=lambda row: row["board_fingerprint"])


def build_corpus(
    aggregate: dict[str, Any], shards: list[dict[str, Any]], *,
    max_per_stratum: int = 0, seed: int = 20260823,
) -> dict[str, Any]:
    states, summary = collect_provider_zero_states(aggregate, shards)
    selected = sample_states(
        states, max_per_stratum=max_per_stratum, seed=seed
    )
    selected_counts = collections.Counter(row["stratum"] for row in selected)
    return {
        "schema_version": 1,
        "experiment": "provider_zero_rescue_corpus",
        "source_experiment": aggregate.get("experiment"),
        "sampling": {
            "unit": "unique_board_fingerprint",
            "seed": int(seed),
            "max_per_stratum": int(max_per_stratum),
            "stratum": "case_id_x_effective_step_band",
        },
        "summary": {
            **summary,
            "selected_unique_boards": len(selected),
            "selected_counts_by_stratum": dict(sorted(selected_counts.items())),
        },
        "states": selected,
    }


def resample_corpus(
    corpus: dict[str, Any], *, max_per_stratum: int, seed: int,
) -> dict[str, Any]:
    states = sample_states(
        list(corpus.get("states", [])),
        max_per_stratum=max_per_stratum,
        seed=seed,
    )
    selected_counts = collections.Counter(row["stratum"] for row in states)
    result = dict(corpus)
    result["sampling"] = {
        "unit": "unique_board_fingerprint",
        "seed": int(seed),
        "max_per_stratum": int(max_per_stratum),
        "stratum": "case_id_x_effective_step_band",
        "parent_corpus": corpus.get("experiment"),
    }
    result["summary"] = {
        **corpus.get("summary", {}),
        "selected_unique_boards": len(states),
        "selected_counts_by_stratum": dict(sorted(selected_counts.items())),
    }
    result["states"] = states
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--root", type=pathlib.Path)
    source.add_argument("--corpus", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--max-per-stratum", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260823)
    args = parser.parse_args()

    if args.corpus is not None:
        corpus = resample_corpus(
            json.loads(args.corpus.read_text(encoding="utf-8")),
            max_per_stratum=args.max_per_stratum,
            seed=args.seed,
        )
    else:
        aggregate = json.loads(
            (args.root / "aggregate.json").read_text(encoding="utf-8")
        )
        shard_paths = sorted(args.root.glob("convergence-shard-*.json"))
        if not shard_paths:
            raise SystemExit(f"no convergence shards below {args.root}")
        shards = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in shard_paths
        ]
        corpus = build_corpus(
            aggregate,
            shards,
            max_per_stratum=args.max_per_stratum,
            seed=args.seed,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
