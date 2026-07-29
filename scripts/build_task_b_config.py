from __future__ import annotations

import argparse
import copy
import json
import pathlib
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "simulator" / "configs" / "sample_config.json"


def build_task_b_config(
    source: dict[str, Any],
    *,
    source_case: str,
    task_id: str,
    look_ahead: int,
    policy_timeout: float,
) -> dict[str, Any]:
    if source_case not in source:
        raise KeyError(f"source case not found: {source_case}")
    if look_ahead <= 0:
        raise ValueError("look_ahead must be positive")
    if policy_timeout <= 0:
        raise ValueError("policy_timeout must be positive")

    task = copy.deepcopy(source[source_case])
    item_stream = task["item_stream"]
    item_count = len(item_stream["item_list"])
    if look_ahead > item_count:
        raise ValueError(
            f"look_ahead {look_ahead} cannot exceed item count {item_count}"
        )

    task["agent"]["optimize"] = False
    task["agent"]["policy_timeout"] = float(policy_timeout)
    item_stream["look_ahead"] = int(look_ahead)
    item_stream["max_space"] = 1
    item_stream["visible_pool"] = []
    return {task_id: task}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, default=DEFAULT_SOURCE)
    parser.add_argument("--source-case", default="001")
    parser.add_argument("--task-id")
    parser.add_argument("--look-ahead", type=int, required=True)
    parser.add_argument("--policy-timeout", type=float, default=8.0)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.source.read_text(encoding="utf-8"))
    task_id = args.task_id or f"task-b-k{args.look_ahead}"
    generated = build_task_b_config(
        source,
        source_case=args.source_case,
        task_id=task_id,
        look_ahead=args.look_ahead,
        policy_timeout=args.policy_timeout,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(generated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
