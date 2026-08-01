"""
Post-mortem of episode-ending placements: did the model know?

Every risk-on episode still ends with an unsafe placement. Two very
different diagnoses share that symptom:

- STARVATION: the frozen rotation model scored the fatal action as
  dangerous, but the policy had nothing safer to pick (or the linear
  penalty was too small to matter) -- fix lies in candidate generation
  or lambda, not the model.
- FALSE NEGATIVE: the model scored the fatal action as safe -- fix
  lies in the model (features or fit).

This tool reconstructs each episode's container state offline from the
step_metrics settle results (settled AABBs are ground truth), computes
the frozen mech P_rot for the fatal commanded placement, and buckets
episodes by the model's verdict. No physics, no simulator.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.evaluate_mechanics_features as emf  # noqa: E402
from scripts.measure_residual_capacity import rebuild_case_items  # noqa: E402

DEFAULT_ABLATION_DIR = ROOT / "reports" / "risk-ablation"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "replay-analysis"
HIGH_RISK = 0.5
LOW_RISK = 0.2


def container_template(config: dict[str, Any]) -> dict[str, Any]:
    container = dict(config["containers"]["container_list"][0])
    container.setdefault("packed_items", [])
    container.setdefault(
        "center", [0.0, 0.0, float(container["height"]) / 2.0]
    )
    return container


def rebuild_final_state(
    agent,
    steps: list[dict[str, Any]],
    items_by_index: dict[int, dict[str, Any]],
    container: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """
    Pack all settled steps before the fatal one into the container as
    AABBs at their observed settle poses; return (container, fatal_step).
    """
    packed = []
    for step in steps[:-1]:
        pos = step.get("settle_final_position")
        dims = step.get("settle_aabb_dimensions")
        if pos is None or dims is None:
            continue
        item = items_by_index.get(int(step.get("selected_item_index", -1)))
        packed.append(
            {
                "index": int(step.get("selected_item_index", -1)),
                "length": float(dims[0]),
                "width": float(dims[1]),
                "height": float(dims[2]),
                "orientation": 0,
                "is_soft": bool(item.get("is_soft")) if item else False,
                "is_prioritized": (
                    bool(item.get("is_prioritized")) if item else False
                ),
                "pos": [float(v) for v in pos],
                "orn": [0.0, 0.0, 0.0, 1.0],
            }
        )
    container = dict(container)
    container["packed_items"] = packed
    return container, (steps[-1] if steps else None)


def fatal_risk(
    agent,
    container: dict[str, Any],
    fatal: dict[str, Any],
    items_by_index: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    place_pos = fatal.get("place_pos")
    item = items_by_index.get(int(fatal.get("selected_item_index", -1)))
    if place_pos is None or item is None:
        return None
    dims = agent.get_rotated_dimensions(
        float(item["length"]),
        float(item["width"]),
        float(item["height"]),
        int(fatal.get("orientation", 0)),
    )
    x, y, z = (float(v) for v in place_pos)
    probability = agent.release_rotation_risk_probability_mech(
        x, y, z, tuple(float(v) for v in dims), container
    )
    status = fatal.get("status") or {}
    angle = float(fatal.get("settle_angle_deg") or 0.0)
    displacement = float(fatal.get("settle_displacement_norm") or 0.0)
    if not status.get("is_valid", True):
        channel = "transport_invalid"
    elif angle > 30.0:
        channel = "topple"
    elif displacement > 0.3:
        channel = "slide"
    elif not status.get("is_placed_safe", True):
        channel = "unsafe_other"
    else:
        channel = "safe_end"
    return {
        "p_rot": float(probability),
        "channel": channel,
        "settle_angle_deg": angle,
        "settle_displacement_norm": displacement,
        "item_index": int(fatal.get("selected_item_index", -1)),
    }


def analyze(ablation_dir: pathlib.Path, configs_dir: pathlib.Path):
    agent = emf.load_agent_module()
    rows_path = ablation_dir / "rows.jsonl"
    episodes = []
    with rows_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                episodes.append(json.loads(line))

    item_cache: dict[str, dict[int, dict[str, Any]]] = {}
    config_cache: dict[str, dict[str, Any]] = {}
    results = []
    for episode in episodes:
        if episode.get("process_returncode") != 0:
            continue
        for case_id in episode["cases"]:
            run_dir = ablation_dir / "runs" / episode["label"]
            evaluation_path = run_dir / "evaluation_results.json"
            if not evaluation_path.exists():
                continue
            evaluation = json.loads(
                evaluation_path.read_text(encoding="utf-8")
            )
            case = evaluation.get(case_id)
            if not isinstance(case, dict):
                continue
            steps = (case.get("evaluation") or {}).get("step_metrics") or []
            if not steps:
                continue
            if case_id not in item_cache:
                config_path = configs_dir / f"{case_id}.json"
                config = json.loads(
                    config_path.read_text(encoding="utf-8")
                )[case_id]
                config_cache[case_id] = config
                item_cache[case_id] = {
                    int(item["index"]): item
                    for item in rebuild_case_items(case_id)[0]
                }
            container, fatal = rebuild_final_state(
                agent,
                steps,
                item_cache[case_id],
                container_template(config_cache[case_id]),
            )
            if fatal is None:
                continue
            verdict = fatal_risk(
                agent, container, fatal, item_cache[case_id]
            )
            if verdict is None:
                continue
            verdict["label"] = episode["label"]
            verdict["arm"] = episode["arm"]
            verdict["case_id"] = case_id
            results.append(verdict)
    return results


def render(results: list[dict[str, Any]]) -> str:
    by_channel: dict[str, list[dict[str, Any]]] = {}
    for entry in results:
        by_channel.setdefault(entry["channel"], []).append(entry)
    topples = by_channel.get("topple", [])
    known = [r for r in topples if r["p_rot"] >= HIGH_RISK]
    missed = [r for r in topples if r["p_rot"] < LOW_RISK]
    middle = [
        r for r in topples if LOW_RISK <= r["p_rot"] < HIGH_RISK
    ]
    lines = [
        "# Terminal-failure post-mortem: channels, then model verdicts",
        "",
        f"- fatal placements analysed: {len(results)} (container "
        "rebuilt from observed settle AABBs; P_rot from the frozen "
        "mech model on the commanded pose)",
        "",
        "## Death channels",
        "",
        "| channel | episodes |",
        "|---|---:|",
    ]
    for channel, entries in sorted(
        by_channel.items(), key=lambda kv: -len(kv[1])
    ):
        lines.append(f"| {channel} | {len(entries)} |")
    lines += [
        "",
        "The rotation model can only answer for the topple channel:",
        "",
        f"- KNOWN (P_rot >= {HIGH_RISK}): {len(known)} -- flagged; "
        "failure is starvation or an insufficient penalty.",
        f"- AMBIGUOUS ({LOW_RISK}-{HIGH_RISK}): {len(middle)}",
        f"- MISSED (P_rot < {LOW_RISK}): {len(missed)} -- rotation-"
        "model false negatives, the model-improvement targets.",
        "",
        "transport_invalid deaths never reach physics -- they are a "
        "candidate-generation / transport-validation problem and no "
        "release-risk lambda can fix them.",
        "",
        "| episode | arm | channel | P_rot | settle angle | "
        "displacement |",
        "|---|---|---|---:|---:|---:|",
    ]
    for entry in sorted(
        results, key=lambda r: (r["channel"], r["p_rot"])
    ):
        lines.append(
            f"| {entry['label']} | {entry['arm']} "
            f"| {entry['channel']} "
            f"| {entry['p_rot']:.3f} "
            f"| {entry['settle_angle_deg']:.1f} "
            f"| {entry['settle_displacement_norm']:.3f} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ablation-dir", type=pathlib.Path, default=DEFAULT_ABLATION_DIR
    )
    parser.add_argument(
        "--configs-dir",
        type=pathlib.Path,
        required=True,
        help="Directory holding <case_id>.json task-b configs.",
    )
    parser.add_argument(
        "--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT_DIR
    )
    args = parser.parse_args()
    results = analyze(args.ablation_dir, args.configs_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "terminal-failures.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    markdown_path = args.output_dir / "terminal-failures.md"
    markdown_path.write_text(render(results), encoding="utf-8")
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
