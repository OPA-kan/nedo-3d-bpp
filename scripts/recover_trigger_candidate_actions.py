"""Replay a collection cell and recover root candidate command actions."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "simulator") not in sys.path:
    sys.path.insert(0, str(ROOT / "simulator"))

from scripts.build_counterfactual_graph import build_candidate_provider  # noqa: E402
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    load_agent_module,
    policy_observation,
    require_supported_python,
    state_snapshot,
)
from scripts.counterfactual_graph import board_fingerprint  # noqa: E402
from scripts.run_self_play_packing import (  # noqa: E402
    _candidate_record,
    _safe,
    _status,
)
from scripts.run_single_agent_packing import _fresh_env  # noqa: E402


def recover(
    manifest: dict[str, Any], dataset: dict[str, Any],
    task_config: dict[str, Any], *, cell: str, attempt_budget: int,
    top_k: int,
) -> dict[str, Any]:
    targets = {
        str(row["root_id"]): row for row in dataset.get("rows") or []
        if str(row.get("cell")) == cell
    }
    agent_module = load_agent_module()
    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget,
        scan_all_visible_items=True,
    )
    environment_seed = int(manifest["environment_seed"])
    case_id = str(manifest["case_id"])
    records = [
        record for episode in manifest.get("episodes") or []
        for record in episode.get("records") or []
    ]
    env = _fresh_env(task_config)
    recovered: dict[str, Any] = {}
    try:
        env.reset_settings()
        env.reset_item_stream()
        observation, _info = env.reset(seed=environment_seed)
        for record_index, record in enumerate(records):
            root_id = str(record["root_id"])
            if root_id in targets:
                observed = policy_observation(env, observation)
                snapshot = state_snapshot(
                    env, observed, case_id=case_id,
                    step=int(record["step"]),
                )
                if board_fingerprint(snapshot) != str(record["board_fingerprint"]):
                    raise RuntimeError(f"{root_id}: board fingerprint mismatch")
                candidates = list(provider(env, observation, int(top_k)))
                action_by_id = {
                    str(candidate_record["candidate_id"]):
                    candidate_record["command_action"]
                    for candidate in candidates
                    if (candidate_record := _candidate_record(candidate))[
                        "candidate_id"
                    ] is not None
                }
                expected = {
                    str(candidate["root_candidate_id"])
                    for candidate in targets[root_id].get("candidates") or []
                }
                missing = sorted(expected - set(action_by_id))
                if missing:
                    raise RuntimeError(
                        f"{root_id}: regenerated candidates missing {missing}"
                    )
                recovered[root_id] = {
                    candidate_id: action_by_id[candidate_id]
                    for candidate_id in sorted(expected)
                }
            observation, _reward, terminated, truncated, info = env.step(
                record["action"]
            )
            if not _safe(_status(info)) or terminated or truncated:
                if record_index != len(records) - 1:
                    raise RuntimeError("recorded prefix terminated early")
                break
    finally:
        env.close()
    missing_roots = sorted(set(targets) - set(recovered))
    if missing_roots:
        raise RuntimeError(f"dataset roots missing from manifest: {missing_roots}")
    return {
        "contract": "trigger_candidate_action_recovery_v1",
        "cell": cell,
        "case_id": case_id,
        "roots": len(recovered),
        "actions": recovered,
    }


def main() -> int:
    require_supported_python()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument("--task-config", type=pathlib.Path, required=True)
    parser.add_argument("--cell", required=True)
    parser.add_argument("--attempt-budget", type=int, default=128)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    config = json.loads(args.task_config.read_text(encoding="utf-8"))
    report = recover(
        manifest,
        json.loads(args.dataset.read_text(encoding="utf-8")),
        config[manifest["case_id"]],
        cell=args.cell,
        attempt_budget=args.attempt_budget,
        top_k=args.top_k,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"cell": report["cell"], "roots": report["roots"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
