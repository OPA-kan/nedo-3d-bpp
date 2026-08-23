"""Depth-ladder and within-root V validation against terminal probes.

Answers the two questions the H1-vs-H2 shadow could not:

1. Depth ladder — does the H1 (or H2) bounded fill ordering survive to
   genuine termination? tau(H1, terminal) and tau(H2, terminal) per
   root, using the rank-0 terminal probe as the deep reference.
2. Within-root V discrimination — at the sibling leaves s'_i, how well
   do the frozen V^pi_behavior predictions rank the *realized* suffix
   outcomes (terminal minus after-action metrics)? Reported as per-root
   Kendall tau and pairwise accuracy, alongside the global correlation
   that the training audit used, to make the global-vs-local gap
   explicit.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
from typing import Any

try:
    from scripts.compare_h1v_shadow import _kendall_tau, _load_roots
except ModuleNotFoundError:
    from compare_h1v_shadow import _kendall_tau, _load_roots

# metric key aliases -> ladder head name; direction kept for reference
LADDER_HEADS = {
    "fill": (("fill_score_proxy", "fill_percent_proxy"), "maximize"),
    "placed": (("placed_count",), "maximize"),
    "soft_violation": (("soft_covered_by_other",), "minimize"),
    "priority_covered": (("priority_covered_by_other",), "minimize"),
    "priority_misrouted": (("priority_misrouted",), "minimize"),
    "surface_total_variation": (("surface_total_variation",), "minimize"),
    "center_of_mass_z": (("center_of_mass_z", "com_z"), "diagnostic"),
}
# ladder head -> V^pi_behavior suffix head predicted at the leaf
V_SUFFIX_HEADS = {
    "fill": "fill_return",
    "placed": "placed_return",
    "soft_violation": "soft_violation_return",
    "priority_covered": "priority_covered_return",
    "priority_misrouted": "priority_misrouted_return",
    "surface_total_variation": "surface_total_variation_return",
    "center_of_mass_z": "center_of_mass_z_return",
}
BRANCH_HEADS = {
    "fill": "fill_gain",
    "placed": "placed_gain",
    "soft_violation": "soft_violation_gain",
    "priority_covered": "priority_covered_gain",
    "priority_misrouted": "priority_misrouted_gain",
    "surface_total_variation": "surface_total_variation_delta",
    "center_of_mass_z": "center_of_mass_z_delta",
}


def _metric(metrics: dict[str, Any], aliases: tuple[str, ...]) -> float | None:
    for key in aliases:
        value = metrics.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = float(value)
            if math.isfinite(value):
                return value
    return None


def _delta(
    before: dict[str, Any], after: dict[str, Any],
    aliases: tuple[str, ...],
) -> float | None:
    left, right = _metric(before, aliases), _metric(after, aliases)
    if left is None or right is None:
        return None
    return right - left


def probe_vectors(
    probe_rows: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, float | None]]]:
    """root -> candidate -> {head: terminal delta / suffix}, genuine only."""
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for row in probe_rows:
        root = str(row["candidate_set_id"])
        candidate = str(row["root_candidate_id"])
        entry = {"genuine": bool(row.get("genuine_terminal"))}
        if entry["genuine"]:
            entry["terminal_delta"] = {
                head: _delta(
                    row["root_metrics"], row["terminal_metrics"], aliases
                )
                for head, (aliases, _d) in LADDER_HEADS.items()
            }
            entry["realized_suffix"] = {
                head: _delta(
                    row["after_action_metrics"], row["terminal_metrics"],
                    aliases,
                )
                for head, (aliases, _d) in LADDER_HEADS.items()
            }
        result.setdefault(root, {})[candidate] = entry
    return result


def _arm_means(
    roots: dict[str, dict[str, Any]], key: str, head: str,
) -> dict[str, float]:
    """Candidate means of one measured branch head at one root."""
    branch = BRANCH_HEADS[head]
    sums: dict[str, list[float]] = collections.defaultdict(list)
    for sample in roots[key]["samples"]:
        eligibility = sample.get("head_eligibility") or {}
        vector = sample.get("raw_outcome_vector") or {}
        if eligibility.get(branch) is True and vector.get(branch) is not None:
            sums[str(sample["root_candidate_id"])].append(float(vector[branch]))
    return {
        name: sum(values) / len(values) for name, values in sums.items()
    }


def _leaf_predictions(
    roots: dict[str, dict[str, Any]], key: str,
) -> dict[str, dict[str, float]]:
    """candidate -> {ladder head: predicted suffix mean at the leaf}."""
    result: dict[str, dict[str, float]] = {}
    for sample in roots[key]["samples"]:
        candidate = str(sample["root_candidate_id"])
        if candidate in result:
            continue
        predicted = sample.get("predicted_leaf_value") or {}
        heads = predicted.get("heads")
        if not heads:
            continue
        result[candidate] = {
            head: float(heads[suffix]["mean"])
            for head, suffix in V_SUFFIX_HEADS.items()
            if suffix in heads
        }
    return result


def _pairwise_accuracy(
    predicted: dict[str, float], actual: dict[str, float],
) -> tuple[int, int]:
    names = sorted(set(predicted) & set(actual))
    correct = total = 0
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if actual[a] == actual[b] or predicted[a] == predicted[b]:
                continue
            total += 1
            correct += int(
                (predicted[a] - predicted[b]) * (actual[a] - actual[b]) > 0
            )
    return correct, total


def evaluate(
    probe_rows: list[dict[str, Any]],
    h1_roots: dict[str, dict[str, Any]],
    h2_roots: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    terminal = probe_vectors(probe_rows)
    ladder_taus: dict[str, dict[str, list[float]]] = {
        "h1_vs_terminal": collections.defaultdict(list),
        "h2_vs_terminal": collections.defaultdict(list),
        "h1_vs_h2": collections.defaultdict(list),
    }
    v_taus: dict[str, list[float]] = collections.defaultdict(list)
    v_pairs: dict[str, list[tuple[int, int]]] = collections.defaultdict(list)
    v_global: dict[str, list[tuple[float, float]]] = collections.defaultdict(list)
    censored_roots = 0
    used_roots = 0
    for key, candidates in sorted(terminal.items()):
        genuine = {
            name: entry for name, entry in candidates.items()
            if entry["genuine"]
        }
        if len(genuine) < 2:
            censored_roots += 1
            continue
        used_roots += 1
        terminal_means = {
            head: {
                name: entry["terminal_delta"][head]
                for name, entry in genuine.items()
                if entry["terminal_delta"][head] is not None
            }
            for head in LADDER_HEADS
        }
        for head in LADDER_HEADS:
            reference = terminal_means[head]
            if key in h1_roots:
                tau = _kendall_tau(_arm_means(h1_roots, key, head), reference)
                if tau is not None:
                    ladder_taus["h1_vs_terminal"][head].append(tau)
            if key in h2_roots:
                tau = _kendall_tau(_arm_means(h2_roots, key, head), reference)
                if tau is not None:
                    ladder_taus["h2_vs_terminal"][head].append(tau)
            if key in h1_roots and key in h2_roots:
                tau = _kendall_tau(
                    _arm_means(h1_roots, key, head),
                    _arm_means(h2_roots, key, head),
                )
                if tau is not None:
                    ladder_taus["h1_vs_h2"][head].append(tau)
        if key in h1_roots:
            predictions = _leaf_predictions(h1_roots, key)
            for head in V_SUFFIX_HEADS:
                predicted = {
                    name: values[head]
                    for name, values in predictions.items()
                    if head in values and name in genuine
                }
                actual = {
                    name: entry["realized_suffix"][head]
                    for name, entry in genuine.items()
                    if entry["realized_suffix"][head] is not None
                }
                tau = _kendall_tau(predicted, actual)
                if tau is not None:
                    v_taus[head].append(tau)
                v_pairs[head].append(_pairwise_accuracy(predicted, actual))
                for name in set(predicted) & set(actual):
                    v_global[head].append((predicted[name], actual[name]))

    def _tau_summary(store):
        return {
            head: {"mean": sum(v) / len(v), "count": len(v)}
            for head, v in sorted(store.items()) if v
        }

    def _pearson(pairs):
        if len(pairs) < 3:
            return None
        xs = [p for p, _ in pairs]
        ys = [a for _, a in pairs]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
        sy = math.sqrt(sum((y - my) ** 2 for y in ys))
        if sx == 0.0 or sy == 0.0:
            return None
        return sum(
            (x - mx) * (y - my) for x, y in zip(xs, ys)
        ) / (sx * sy)

    return {
        "roots_with_terminal_pairs": used_roots,
        "roots_censored": censored_roots,
        "depth_ladder_tau": {
            arm: _tau_summary(store) for arm, store in ladder_taus.items()
        },
        "v_within_root": {
            head: {
                "tau_mean": sum(taus) / len(taus) if taus else None,
                "tau_count": len(taus),
                "pairwise_correct": sum(c for c, _t in v_pairs[head]),
                "pairwise_total": sum(t for _c, t in v_pairs[head]),
                "pairwise_accuracy": (
                    sum(c for c, _t in v_pairs[head])
                    / sum(t for _c, t in v_pairs[head])
                    if sum(t for _c, t in v_pairs[head]) else None
                ),
                "global_pearson_probe_set": _pearson(v_global[head]),
                "global_pairs": len(v_global[head]),
            }
            for head, taus in sorted(v_taus.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--probe", action="append", required=True, metavar="CELL=PROBE_JSON",
    )
    parser.add_argument(
        "--h1-run", action="append", required=True, metavar="CELL=DIR",
    )
    parser.add_argument(
        "--h2-run", action="append", required=True, metavar="CELL=DIR",
    )
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    def parse(specs):
        result = {}
        for spec in specs:
            cell, _, path = spec.partition("=")
            if not path:
                raise SystemExit(f"expected CELL=PATH, got: {spec}")
            result[cell] = pathlib.Path(path)
        return result

    probes = parse(args.probe)
    h1_runs = parse(args.h1_run)
    h2_runs = parse(args.h2_run)
    cells = {}
    for cell, probe_path in sorted(probes.items()):
        probe = json.loads(probe_path.read_text(encoding="utf-8"))
        cells[cell] = evaluate(
            probe["rows"],
            _load_roots(h1_runs[cell]) if cell in h1_runs else {},
            _load_roots(h2_runs[cell]) if cell in h2_runs else {},
        )
    merged_rows = []
    for cell, probe_path in sorted(probes.items()):
        probe = json.loads(probe_path.read_text(encoding="utf-8"))
        merged_rows.extend(probe["rows"])
    overall = evaluate(
        merged_rows,
        {
            key: value
            for cell in sorted(h1_runs)
            for key, value in _load_roots(h1_runs[cell]).items()
        },
        {
            key: value
            for cell in sorted(h2_runs)
            for key, value in _load_roots(h2_runs[cell]).items()
        },
    )
    report = {
        "schema_version": 1,
        "contract": "terminal_probe_depth_ladder_v1",
        "cells": cells,
        "overall": overall,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ladder = overall["depth_ladder_tau"]
    print(
        "fill: h1_vs_terminal="
        f"{ladder['h1_vs_terminal'].get('fill')} "
        f"h2_vs_terminal={ladder['h2_vs_terminal'].get('fill')} "
        f"h1_vs_h2={ladder['h1_vs_h2'].get('fill')}"
    )
    print("v fill within-root:", overall["v_within_root"].get("fill"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
