"""Build a single-case Task A config from a bundled sample case."""
from __future__ import annotations

import argparse
import copy
import json
import pathlib


def build_task_a_config(
    source_config: dict,
    source_case: str,
    *,
    optimization_timeout: float,
    policy_timeout: float = 8.0,
) -> dict:
    if source_case not in source_config:
        raise KeyError(f"unknown source case: {source_case}")
    case = copy.deepcopy(source_config[source_case])
    case["agent"]["optimize"] = True
    case["agent"]["optimization_timeout"] = float(
        optimization_timeout
    )
    case["agent"]["policy_timeout"] = float(policy_timeout)
    case["item_stream"]["look_ahead"] = 1
    case["item_stream"]["max_space"] = 1
    case["item_stream"]["visible_pool"] = []
    return {f"a{source_case}": case}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--source-case", required=True)
    parser.add_argument("--optimization-timeout", type=float, required=True)
    parser.add_argument("--policy-timeout", type=float, default=8.0)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.source.read_text(encoding="utf-8"))
    result = build_task_a_config(
        source,
        args.source_case,
        optimization_timeout=args.optimization_timeout,
        policy_timeout=args.policy_timeout,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
