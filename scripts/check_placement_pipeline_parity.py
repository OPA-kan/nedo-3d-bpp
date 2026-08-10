import argparse
import copy
import importlib.util
import json
import pathlib
import sys
import time


def load_agent(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def synthetic_observation():
    items = []
    for index in range(6):
        items.append(
            {
                "index": index,
                "length": 0.18 + 0.02 * (index % 4),
                "width": 0.16 + 0.02 * (index % 3),
                "height": 0.14 + 0.02 * (index % 2),
                "mass": 2.0 + index % 5,
                "is_soft": index == 4,
                "is_prioritized": index == 3,
            }
        )
    container = {
        "length": 2.0,
        "width": 1.45,
        "height": 1.61,
        "thickness": 0.04,
        "buffer": 0.0,
        "cut_x": 0.44,
        "require_shelf": True,
        "is_prioritized": False,
        "center": [0.0, 0.0, 0.0],
        "packed_items": [
            {
                "index": 100,
                "length": 0.42,
                "width": 0.36,
                "height": 0.22,
                "mass": 5.0,
                "orientation": 0,
                "is_soft": False,
                "is_prioritized": False,
                "position": [-0.45, 0.25, 0.11],
            },
            {
                "index": 101,
                "length": 0.34,
                "width": 0.30,
                "height": 0.18,
                "mass": 4.0,
                "orientation": 0,
                "is_soft": False,
                "is_prioritized": False,
                "position": [0.15, 0.45, 0.09],
            },
        ],
    }
    return {"pool_list": items, "container_list": [container]}


def decision_record(decision):
    if decision is None:
        return None
    return {
        "item_idx": int(decision.action["item_idx"]),
        "container_idx": int(decision.action["container_idx"]),
        "orientation": int(decision.action["orientation"]),
        "place_pos": [
            float(value).hex() for value in decision.action["place_pos"]
        ],
        "candidate_center": [
            float(value).hex() for value in decision.candidate.center
        ],
        "candidate_size": [
            float(value).hex() for value in decision.candidate.size
        ],
        "candidate_kind": decision.candidate.name,
        "score": float(decision.score).hex(),
    }


def run_case(module, budget):
    observation = synthetic_observation()
    indexed_items = list(enumerate(observation["pool_list"]))
    diagnostics_top = {}
    started = time.perf_counter()
    top = module.PlacementCore.top_candidates(
        copy.deepcopy(observation),
        copy.deepcopy(indexed_items),
        3,
        diagnostics=diagnostics_top,
        risk_lambda=1.0,
        attempt_budget=budget,
    )
    top_seconds = time.perf_counter() - started
    diagnostics_choose = {}
    started = time.perf_counter()
    chosen = module.PlacementCore.choose(
        copy.deepcopy(observation),
        copy.deepcopy(indexed_items),
        diagnostics=diagnostics_choose,
        risk_lambda=1.0,
        attempt_budget=budget,
    )
    choose_seconds = time.perf_counter() - started
    return {
        "budget": int(budget),
        "top": [decision_record(decision) for decision in top],
        "chosen": decision_record(chosen),
        "top_attempts": int(
            diagnostics_top.get("search", {}).get("attempts_consumed", 0)
        ),
        "choose_attempts": int(
            diagnostics_choose.get("search", {}).get(
                "attempts_consumed", 0
            )
        ),
        "top_seconds": top_seconds,
        "choose_seconds": choose_seconds,
    }


def comparable(record):
    return {
        key: value
        for key, value in record.items()
        if key not in {"top_seconds", "choose_seconds"}
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-agent", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-agent", type=pathlib.Path, required=True)
    parser.add_argument(
        "--budgets", type=int, nargs="+", default=[128, 512, 2048]
    )
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    baseline = load_agent(args.baseline_agent, "pipeline_baseline_agent")
    candidate = load_agent(args.candidate_agent, "pipeline_candidate_agent")
    rows = []
    all_match = True
    for budget in args.budgets:
        baseline_record = run_case(baseline, budget)
        candidate_record = run_case(candidate, budget)
        matches = comparable(baseline_record) == comparable(candidate_record)
        all_match = all_match and matches
        rows.append(
            {
                "budget": int(budget),
                "matches": matches,
                "baseline": baseline_record,
                "candidate": candidate_record,
            }
        )
    report = {
        "schema_version": 1,
        "all_match": all_match,
        "baseline_agent": str(args.baseline_agent),
        "candidate_agent": str(args.candidate_agent),
        "rows": rows,
    }
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    raise SystemExit(0 if all_match else 1)


if __name__ == "__main__":
    main()
