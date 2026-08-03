"""
Execute the container-configuration matrix against the physics.

`scripts/build_scenario_matrix.py` writes the configs and
`tests/test_scenario_matrix.py` checks the first decision without physics.
This is the third piece: it runs a whole episode per configuration and
reports, per row, how far the agent got and WHICH CHANNEL ended the
episode.

The death channel is the reason this script exists. `place_states` in the
simulator result is NOT an episode summary -- app.py rebinds it on every
step (`place_states = {k: v for k, v in info['status'].items()}` inside the
while loop), so what lands in the result file is the status of the LAST
step only. env.step terminates on the first failure, so that last step is
either the killing action or, for a completed run, the successful one that
emptied the stream. Reading `is_valid: true` off a row that placed 30 of 41
as "the episode was clean" is exactly backwards: it means the transport
check PASSED and the item then failed to settle.

    is_included false                     -> inclusion  (outside the box)
    is_included true,  is_valid false     -> transport  (corridor blocked)
    is_valid true,     is_placed_safe false -> settle    (toppled/slid)
    all three true                        -> stream_exhausted (survived)

A second reading trap this script defuses: `num_placed_items` is
`sum(len(c.packed_items)) / num_total_items`, and `num_total_items` counts
pre-loaded items on both sides (env.py:121, evaluator.py:81-89). On a
pre-loaded row the headline ratio therefore includes items the agent was
handed for free, so `agent_placed / agent_of` is reported alongside it.

    python3 scripts/build_scenario_matrix.py --output-dir reports/scenario-matrix
    python3 scripts/run_scenario_matrix.py --matrix-dir reports/scenario-matrix \
        --output-dir reports/scenario-matrix/runs

`rows.jsonl` is an append-only LOG across invocations -- re-running one
scenario adds a row rather than replacing one, so it can hold several
entries per scenario. `summary.json` is the authority: `--summarize`
rebuilds it from the run directories on disk, each of which holds only its
latest execution.

This is a coverage probe, not a benchmark. The scenes are synthetic
combinations of the bundled geometry, so the scores are not comparable to
the development suite or to any official number; what they establish is
that a configuration runs and how it dies.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_checks import load_json, run  # noqa: E402

SIMULATOR = ROOT / "simulator"
AGENT = ROOT / "agent" / "agent.py"
DEFAULT_MATRIX_DIR = ROOT / "reports" / "scenario-matrix"

DEATH_CHANNELS = ("inclusion", "transport", "settle", "stream_exhausted")


def sync_agent_into_simulator() -> None:
    """
    The simulator imports SIMULATOR/agent.py, which is a COPY of the
    submission source. Skipping this step measures whatever copy was left
    behind by the last run, which is how the first risk ablation silently
    compared an arm against itself. Content-compare first so concurrent
    invocations skip the racy rewrite.
    """
    target = SIMULATOR / "agent.py"
    source_bytes = AGENT.read_bytes()
    if target.exists() and target.read_bytes() == source_bytes:
        return
    target.write_bytes(source_bytes)


STATUS_KEYS = ("is_included", "is_valid", "is_placed_safe")


def death_channel(place_states: dict[str, Any] | None) -> str:
    """
    Classify the terminal step. See the module docstring: place_states is
    the last step's status, not the episode's.

    The membership check is not defensive padding. `check_action` failing
    (rules failure condition 1: malformed action, out-of-range index or
    coordinate) makes env.step return early with a COMPLETELY DIFFERENT
    status dict -- `{'has_valid_action_keys': False}`,
    `{'has_valid_action_pos ...': False}`, `{'has_valid_action_index
    ...': False}` -- which contains none of these three keys. The first
    version of this function used .get() straight through, so every such
    ending read `is_included` as None and was reported as "inclusion", a
    containment failure. That is failure condition 1 silently relabelled as
    failure condition 2.
    """
    if not place_states:
        return "unknown"
    if not all(key in place_states for key in STATUS_KEYS):
        return "malformed_action"
    if not place_states["is_included"]:
        return "inclusion"
    if not place_states["is_valid"]:
        return "transport"
    if not place_states["is_placed_safe"]:
        return "settle"
    return "stream_exhausted"


def terminal_decision(trace_path: pathlib.Path) -> dict[str, Any] | None:
    """
    Attribute the death to an action, which the channel alone cannot do.

    `transport` says the corridor was blocked; it does not say whether the
    agent chose a placement it believed in or emitted the hard-coded
    `[0, 0, 0.25]` of the unsafe_protocol_fallback (agent.py:7008-7078).
    Those call for opposite fixes, and the distinction is only in the
    trace: action_source `placement_core` means the agent picked and was
    wrong, `unsafe_protocol_fallback` means it had nothing to pick.

    candidate_kind separates the two acceptance paths.
    `release_candidate` goes through release_rejection_reason, which checks
    containment, static geometry and corridor and -- unlike the settled
    path's rejection_reason -- does NOT check support.
    """
    if not trace_path.exists():
        return None
    decisions = []
    truncated = False
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            truncated = True
            break
        if record.get("event") == "decision":
            decisions.append(record)
    if not decisions:
        return None
    if truncated:
        # The dropped line IS the final decision, so the attribution below
        # would be off by one. An earlier comment here claimed the earlier
        # decisions were "still the answer"; they are not.
        return {"decisions": len(decisions), "trace_truncated": True}
    final = decisions[-1]
    kinds: dict[str, int] = {}
    for decision in decisions:
        kind = decision.get("candidate_kind") or "none"
        kinds[kind] = kinds.get(kind, 0) + 1
    return {
        # "final", not "fatal": on a stream_exhausted row this describes
        # the placement that finished the stream, not a cause of death.
        # Read it together with death_channel.
        "decisions": len(decisions),
        "candidate_kind_counts": kinds,
        "final_action_source": final.get("action_source"),
        "final_candidate_kind": final.get("candidate_kind"),
        "final_internal_outcome": final.get("internal_outcome"),
        "final_no_safe_action": bool(final.get("no_safe_action")),
        "final_action_command": final.get("action_command"),
    }


def scenario_shape(config: dict[str, Any]) -> dict[str, Any]:
    case = next(iter(config.values()))
    containers = case["containers"]["container_list"]
    preloaded = sum(len(c["packed_items"]) for c in containers)
    stream = len(case["item_stream"]["item_list"])
    return {
        "containers": len(containers),
        "shelves": sum(1 for c in containers if c["require_shelf"]),
        "dedicated": sum(1 for c in containers if c["is_prioritized"]),
        "preloaded": preloaded,
        "stream_items": stream,
        # env.py:121 -- the denominator of num_placed_items
        "total_items": preloaded + stream,
    }


def summarize_case(
    result: dict[str, Any], shape: dict[str, Any]
) -> dict[str, Any]:
    evaluation = result.get("evaluation") or {}
    steps = evaluation.get("step_metrics") or []
    ratio = float(evaluation.get("num_placed_items", 0.0))
    packed = round(ratio * shape["total_items"])
    final = steps[-1] if steps else {}
    # The count is reconstructed from a float ratio, and the denominator
    # comes from the CONFIG rather than the run. Both assumptions are
    # cheap to check against the simulator's own per-step counter, and a
    # mismatch means the config and the result do not belong together --
    # e.g. --summarize pointed at a matrix rebuilt with other parameters.
    reported = final.get("placed_count")
    if reported is not None and int(reported) != packed:
        raise ValueError(
            f"placed count disagrees: reconstructed {packed} from ratio "
            f"{ratio} x {shape['total_items']} total, but the run reports "
            f"{int(reported)}. The config and the result do not match."
        )
    row = {
        **shape,
        "placed_ratio": round(ratio, 4),
        "packed_items": packed,
        # What the AGENT achieved: pre-loaded items are free on both sides
        # of the official ratio, so they are removed here.
        "agent_placed": packed - shape["preloaded"],
        "agent_of": shape["stream_items"],
        "fill_score": round(float(evaluation.get("fill_score", 0.0)), 3),
        "steps": len(steps),
        "place_states": result.get("place_states"),
        "death_channel": death_channel(result.get("place_states")),
        "status": result.get("status"),
    }
    for key in (
        "priority_items",
        "priority_misrouted",
        "priority_covered_by_other",
        "priority_clean_ratio",
        "soft_items",
        "soft_covered_by_other",
        "soft_clean_ratio",
    ):
        if key in final:
            row[key] = final[key]
    return row


def run_scenario(
    name: str,
    config_path: pathlib.Path,
    output_dir: pathlib.Path,
    *,
    trace: bool,
) -> dict[str, Any]:
    run_dir = output_dir / name
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "evaluation_results.json"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SIMULATOR)
    trace_path = run_dir / "policy-trace.jsonl"
    if trace:
        trace_path.unlink(missing_ok=True)
        env["NEDO_POLICY_TRACE_PATH"] = str(trace_path.resolve())
    else:
        env.pop("NEDO_POLICY_TRACE_PATH", None)

    outcome = run(
        [
            sys.executable,
            "scripts/run_test.py",
            "--config-path",
            str(config_path.resolve()),
            "--module-path",
            "",
            "--result-dir",
            str(run_dir.resolve()),
            "--result-fname",
            result_path.name,
        ],
        SIMULATOR,
        env,
    )
    (run_dir / "simulator.log").write_text(
        outcome["stdout"] + outcome["stderr"], encoding="utf-8"
    )

    config = load_json(config_path)
    evaluation = load_json(result_path)
    shape = scenario_shape(config)
    row: dict[str, Any] = {
        "scenario": name,
        "config": config_path.name,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "process_returncode": outcome["returncode"],
        "process_seconds": outcome["seconds"],
    }
    if not isinstance(evaluation, dict) or not evaluation:
        # A configuration that never ran is the headline finding, not an
        # error to swallow: camera.num_containers raised IndexError here.
        row["error"] = (outcome["stderr"] or outcome["stdout"])[-2000:]
        row.update(shape)
        row["death_channel"] = "did_not_run"
        return row
    row.update(summarize_case(next(iter(evaluation.values())), shape))
    if trace:
        row["policy_trace"] = str(trace_path)
        row["terminal_decision"] = terminal_decision(trace_path)
        attach_trace_coverage(row)
    return row


def attach_trace_coverage(row: dict[str, Any]) -> None:
    """
    Decide whether the trace is entitled to attribute anything.

    app.py calls the agent as
    `runner.call('policy', time_out_sec=policy_timeout,
    fallback=env.action_space.sample())`. If the agent overruns, the
    HARNESS substitutes a RANDOM action and the agent never returns, so it
    writes no trace record for that step. The margin is thin --
    POLICY_BUDGET_SECONDS is 6.5 against a policy_timeout of 8.0 -- and
    when it happens the last trace record belongs to an EARLIER step, so
    terminal_decision names the wrong action with no outward sign.

    One decision per step is the only evidence that no substitution
    occurred. Without this the attribution is unfalsifiable, which is worse
    than absent.
    """
    terminal = row.get("terminal_decision") or {}
    decisions = terminal.get("decisions")
    steps = row.get("steps")
    if decisions is None or steps is None:
        row["trace_covers_every_step"] = None
        return
    covers = decisions == steps
    row["trace_covers_every_step"] = covers
    if not covers:
        row["trace_coverage_warning"] = (
            f"{decisions} decisions for {steps} steps: the harness "
            "substituted a random action on at least one step "
            "(policy timeout), so terminal_decision does NOT describe the "
            "final action"
        )


def resummarize(
    name: str, config_path: pathlib.Path, output_dir: pathlib.Path
) -> dict[str, Any] | None:
    """
    Rebuild a row from a completed run WITHOUT re-executing the episode.

    Episodes are minutes long and machine-speed dependent, so re-running
    them to add a derived field would produce a different table, not the
    same one annotated. This reads the artefacts already on disk.
    """
    run_dir = output_dir / name
    evaluation = load_json(run_dir / "evaluation_results.json")
    if not isinstance(evaluation, dict) or not evaluation:
        return None
    shape = scenario_shape(load_json(config_path))
    row: dict[str, Any] = {"scenario": name, "config": config_path.name}
    row.update(summarize_case(next(iter(evaluation.values())), shape))
    trace_path = run_dir / "policy-trace.jsonl"
    if trace_path.exists():
        row["policy_trace"] = str(trace_path)
        row["terminal_decision"] = terminal_decision(trace_path)
        attach_trace_coverage(row)
    return row


def format_row(row: dict[str, Any]) -> str:
    terminal = row.get("terminal_decision") or {}
    attribution = ""
    # Only a death has a cause. On a stream_exhausted row the final
    # decision is the placement that finished the stream, and printing it
    # under the same label would read as an attribution for a death that
    # did not happen.
    if terminal and row.get("death_channel") not in (
        "stream_exhausted", "did_not_run", None
    ):
        if row.get("trace_covers_every_step") is False:
            attribution = " | ATTRIBUTION UNSAFE (harness fallback fired)"
        elif terminal.get("trace_truncated"):
            attribution = " | ATTRIBUTION UNSAFE (trace truncated)"
        else:
            attribution = (
                f" | killed by {terminal.get('final_action_source')}"
                f"/{terminal.get('final_candidate_kind')}"
            )
    return (
        f"{row['scenario']:26s} "
        f"c={row.get('containers')} shelf={row.get('shelves')} "
        f"ded={row.get('dedicated')} pre={row.get('preloaded')} | "
        f"placed {row.get('packed_items')}/{row.get('total_items')} "
        f"({row.get('placed_ratio')}) | "
        f"agent {row.get('agent_placed')}/{row.get('agent_of')} | "
        f"fill {row.get('fill_score')} | "
        f"steps {row.get('steps')} | death {row.get('death_channel')}"
        f"{attribution}"
    )


def write_summary(
    output_dir: pathlib.Path, matrix_dir: pathlib.Path,
    rows: list[dict[str, Any]],
) -> None:
    (output_dir / "summary.json").write_text(
        json.dumps({
            "schema_version": 2,
            "purpose": (
                "Physical execution of the container-configuration matrix. "
                "Coverage probe, not a benchmark: reports whether a "
                "configuration runs and which channel ends the episode. "
                "death_channel is derived from place_states, which app.py "
                "overwrites every step and which therefore describes the "
                "LAST step only. terminal_decision comes from the policy "
                "trace and says whether the agent chose the killing action "
                "or fell back, and through which acceptance path."
            ),
            "matrix_dir": str(matrix_dir),
            "rows": rows,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix-dir", type=pathlib.Path,
                        default=DEFAULT_MATRIX_DIR)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--scenario", action="append", default=None,
                        help="run only these scenarios (repeatable)")
    parser.add_argument("--trace", action="store_true",
                        help="write a policy trace per episode; needed to "
                             "attribute a death to a candidate kind")
    parser.add_argument("--summarize", action="store_true",
                        help="rebuild summary.json from an existing run "
                             "without executing any episode")
    args = parser.parse_args()
    # Resolve before anything derives a path from these: run() executes in
    # SIMULATOR, so a relative --output-dir would land in the wrong place.
    args.matrix_dir = args.matrix_dir.resolve()
    args.output_dir = args.output_dir.resolve()

    manifest = load_json(args.matrix_dir / "manifest.json")
    if not manifest:
        parser.error(
            f"no manifest in {args.matrix_dir}; run "
            "scripts/build_scenario_matrix.py first"
        )
    names = [row["scenario"] for row in manifest["scenarios"]]
    if args.scenario:
        unknown = set(args.scenario) - set(names)
        if unknown:
            parser.error(f"unknown scenario(s): {sorted(unknown)}")
        names = [name for name in names if name in set(args.scenario)]

    if args.summarize:
        rows = []
        for name in names:
            row = resummarize(
                name, args.matrix_dir / f"{name}.json", args.output_dir
            )
            if row is None:
                print(f"{name:26s} no completed run on disk", flush=True)
                continue
            rows.append(row)
            print(format_row(row), flush=True)
        if not rows:
            parser.error(f"nothing to summarize under {args.output_dir}")
        write_summary(args.output_dir, args.matrix_dir, rows)
        return 0

    sync_agent_into_simulator()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = args.output_dir / "rows.jsonl"

    rows = []
    for name in names:
        row = run_scenario(
            name, args.matrix_dir / f"{name}.json", args.output_dir,
            trace=args.trace,
        )
        rows.append(row)
        with rows_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(format_row(row), flush=True)

    write_summary(args.output_dir, args.matrix_dir, rows)
    return 0 if all(r.get("process_returncode") == 0 for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
