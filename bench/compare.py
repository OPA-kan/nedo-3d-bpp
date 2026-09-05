"""Paired comparison of two runs over the same scenes.

Both runs must have been produced on the same suite.  For every metric the
report gives the per-scene paired difference (B minus A), its mean, a
bootstrap 95 % interval of the mean, and how many scenes moved each way.
A difference whose interval contains zero is reported as "no evidence",
never as a win.

When both runs are the same arm, the report also states whether the two
are identical step for step -- the negative control every change to the
bench or the planner has to pass before a comparison is believed.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np

from .metrics import COMPARED


def load_run(run_dir: pathlib.Path) -> dict[str, dict]:
    records = {}
    for path in sorted(pathlib.Path(run_dir).glob("*.json")):
        if path.name in ("summary.json", "agreement.json"):
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if "scene" in record and "metrics" in record:
            records[record["scene"]] = record
    return records


def bootstrap_mean_ci(values: np.ndarray, resamples: int = 10000, seed: int = 0,
                      alpha: float = 0.05) -> tuple[float, float]:
    if values.size == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, values.size, size=(resamples, values.size))
    means = values[idx].mean(axis=1)
    return (float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2)))


def _steps_identical(a: dict, b: dict) -> bool:
    keys = ("event", "item_index", "pool_index", "container_idx", "orientation",
            "place_pos", "is_included", "is_valid", "is_placed_safe")
    sa, sb = a.get("steps", []), b.get("steps", [])
    if len(sa) != len(sb):
        return False
    return all(all(x.get(k) == y.get(k) for k in keys) for x, y in zip(sa, sb))


def compare_runs(run_a: dict[str, dict], run_b: dict[str, dict],
                 label_a: str = "A", label_b: str = "B") -> dict:
    scenes = sorted(set(run_a) & set(run_b))
    missing = sorted((set(run_a) | set(run_b)) - set(scenes))
    rows = {}
    for metric, direction in COMPARED.items():
        a = np.array([float(run_a[s]["metrics"].get(metric, np.nan)) for s in scenes])
        b = np.array([float(run_b[s]["metrics"].get(metric, np.nan)) for s in scenes])
        diff = b - a
        ok = ~np.isnan(diff)
        diff = diff[ok]
        if diff.size == 0:
            continue
        lo, hi = bootstrap_mean_ci(diff)
        if direction == "timing":
            better = np.zeros_like(diff, dtype=bool)
            worse = np.zeros_like(diff, dtype=bool)
            evidence = "timing-only"
        else:
            better = diff > 0 if direction == "up" else diff < 0
            worse = diff < 0 if direction == "up" else diff > 0
            if (lo > 0 and direction == "up") or (hi < 0 and direction == "down"):
                evidence = "b-better"
            elif (hi < 0 and direction == "up") or (lo > 0 and direction == "down"):
                evidence = "b-worse"
            else:
                evidence = "none"
        rows[metric] = {
            "direction": direction,
            "n": int(diff.size),
            "mean_a": float(a[ok].mean()), "mean_b": float(b[ok].mean()),
            "mean_diff": float(diff.mean()),
            "ci95": [lo, hi],
            "better": int(better.sum()), "worse": int(worse.sum()),
            "equal": int((diff == 0).sum()),
            "evidence": evidence,
        }
    identical = all(_steps_identical(run_a[s], run_b[s]) for s in scenes) if scenes else False
    end_reasons = {
        label_a: _count(run_a[s]["metrics"]["end_reason"] for s in scenes),
        label_b: _count(run_b[s]["metrics"]["end_reason"] for s in scenes),
    }
    same_arm = all(
        run_a[s].get("arm", {}).get("arm") == run_b[s].get("arm", {}).get("arm") for s in scenes
    )
    return {
        "labels": [label_a, label_b], "scenes": scenes, "missing": missing,
        "same_arm": same_arm, "identical_steps": identical,
        "end_reasons": end_reasons, "metrics": rows,
    }


def _count(values) -> dict:
    out: dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


def markdown(result: dict) -> str:
    a, b = result["labels"]
    lines = [
        f"# Paired comparison: {b} minus {a}",
        "",
        f"Scenes paired: {len(result['scenes'])}"
        + (f" (unpaired, ignored: {', '.join(result['missing'])})" if result["missing"] else ""),
        "",
    ]
    if result["same_arm"]:
        verdict = "PASS: identical step for step" if result["identical_steps"] else "FAIL: steps differ"
        lines += [f"Negative control (same arm both sides): **{verdict}**", ""]
    lines += [
        f"End reasons {a}: `{result['end_reasons'][a]}`",
        f"End reasons {b}: `{result['end_reasons'][b]}`",
        "",
        "| metric | better is | mean A | mean B | mean diff | 95% CI | better / equal / worse | evidence |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]
    for metric, row in result["metrics"].items():
        lo, hi = row["ci95"]
        lines.append(
            f"| {metric} | {row['direction']} | {row['mean_a']:.4g} | {row['mean_b']:.4g} | "
            f"{row['mean_diff']:+.4g} | [{lo:+.4g}, {hi:+.4g}] | "
            f"{row['better']} / {row['equal']} / {row['worse']} | {row['evidence']} |"
        )
    lines += [
        "",
        "`evidence` is `none` whenever the interval contains zero.  "
        "A count of scenes that moved is not evidence on its own.  "
        "`timing-only` rows are wall clock and depend on the machine.",
    ]
    return "\n".join(lines) + "\n"
