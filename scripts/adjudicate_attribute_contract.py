"""Adjudicate the combined attribute contract against its frozen gates.

Protocol: `reports/hazard/attribute-contract-protocol.md`, written
before the wave. The hypothesis is the ledger's own sentence -- the
settled path is stricter than the published rule and the release path
is looser -- so the two halves are applied together for the first time,
each one's measured failure mode being the other's measured fix.

Gates, none of them chosen here:

  A  BUY. Pooled `priority_covered_by_other` must fall at least 50%
     against base. The bar is conservative by construction: the release
     guard alone drove it to ZERO in every scenario
     (`attribute-guard-trades-placed-for-priority`).
  P  PAY, disqualifying. No config may breach its own
     `minimum_resolvable_placed.paired_3v3_same_run` floor from the
     frozen `reports/benchmarks/baseline.json` in the negative
     direction. One breach fails the arm whatever else holds, because
     placed is the cutoff gate and its amplification runs both ways.
  S  Pooled shake shift and peak energy reported beside placed; a
     worsening blocks adoption even if placed rises (AGENT_OPERATIONS
     section 5, HANDOFF item 6). Pooled paired runs only.
  N  NEGATIVE CONTROL, same wave. The combination must beat BOTH
     singles: fewer priority violations than the support rule alone,
     and more placed than the release guard alone. If either fails, the
     claim that the halves cancel each other's failure mode is false
     and gate A passing does not license anything.

Development only. Adoption needs a fresh-permutation confirmation.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import pathlib
import statistics
from typing import Any

ARMS = ("base", "attr_support_rule", "attr_guard_priority", "attr_contract")
COMBINED = "attr_contract"
BUY_FRACTION = 0.50


def load(rows_globs):
    by_case = collections.defaultdict(lambda: {a: [] for a in ARMS})
    for pattern in rows_globs:
        for path in sorted(glob.glob(pattern)):
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                label = row["label"]
                arm = next(
                    (
                        a
                        for a in sorted(ARMS, key=len, reverse=True)
                        if f"-{a}-" in label
                    ),
                    None,
                )
                if arm is None:
                    continue
                for case_id, summary in (row.get("cases") or {}).items():
                    by_case[case_id][arm].append(summary)
    return by_case


def mean_of(rows, *path):
    values = []
    for row in rows:
        value = row
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, (int, float)):
            values.append(float(value))
    return statistics.fmean(values) if values else None


def pool(by_case, arm):
    rows = [r for arms in by_case.values() for r in arms[arm]]
    placed = sum(r.get("placed_count") or 0 for r in rows)
    prio = sum(
        (r.get("attribute_placement") or {}).get("priority_covered_by_other")
        or 0
        for r in rows
    )
    soft = sum(
        (r.get("attribute_placement") or {}).get("soft_covered_by_other")
        or 0
        for r in rows
    )
    channels = collections.Counter(r.get("terminal_channel") for r in rows)
    return {
        "episodes": len(rows),
        "placed_total": placed,
        "priority_violations": prio,
        "soft_violations": soft,
        "priority_per_placed": (prio / placed) if placed else None,
        "shake_max_shift": mean_of(
            rows, "shake_response", "shake_max_shift"
        ),
        "shake_peak_kinetic_energy": mean_of(
            rows, "shake_response", "shake_peak_kinetic_energy"
        ),
        "physical_endings": channels.get("topple", 0)
        + channels.get("slide", 0),
        "channels": dict(channels),
    }


def adjudicate(by_case, floors) -> dict[str, Any]:
    per_config = {}
    breached = []
    for case_id, arms in sorted(by_case.items()):
        if not arms["base"] or not arms[COMBINED]:
            continue
        base_placed = mean_of(arms["base"], "placed_count")
        comb_placed = mean_of(arms[COMBINED], "placed_count")
        delta = comb_placed - base_placed
        floor = floors.get(case_id)
        verdict = (
            "no_floor"
            if floor is None
            else (
                "breaches"
                if delta <= -floor
                else ("clears" if delta >= floor else "inside_floor")
            )
        )
        if verdict == "breaches":
            breached.append(case_id)
        per_config[case_id] = {
            "placed_base": base_placed,
            "placed_contract": comb_placed,
            "placed_delta": delta,
            "floor": floor,
            "verdict": verdict,
        }

    pooled = {arm: pool(by_case, arm) for arm in ARMS}
    base_prio = pooled["base"]["priority_violations"]
    comb_prio = pooled[COMBINED]["priority_violations"]
    drop = (
        None if not base_prio else (base_prio - comb_prio) / base_prio
    )

    def worse(key):
        b, c = pooled["base"][key], pooled[COMBINED][key]
        return None if (b is None or c is None) else c > b

    gate_a = drop is not None and drop >= BUY_FRACTION
    gate_p = not breached
    gate_s = not (
        worse("shake_max_shift") or worse("shake_peak_kinetic_energy")
    )
    beats_support = (
        comb_prio < pooled["attr_support_rule"]["priority_violations"]
    )
    beats_guard = (
        pooled[COMBINED]["placed_total"]
        > pooled["attr_guard_priority"]["placed_total"]
    )
    gate_n = beats_support and beats_guard

    return {
        "per_config": per_config,
        "configs_breaching": breached,
        "pooled": pooled,
        "priority_violation_drop": drop,
        "buy_fraction": BUY_FRACTION,
        "gate_A_buy": gate_a,
        "gate_P_pay": gate_p,
        "gate_S_stability": gate_s,
        "gate_N_beats_both_singles": gate_n,
        "beats_support_on_violations": beats_support,
        "beats_guard_on_placed": beats_guard,
        "development_pass": bool(gate_a and gate_p and gate_s and gate_n),
    }


def render(result):
    p = result["pooled"]
    lines = [
        "# 属性契約（両側）— 開発裁定",
        "",
        "Protocol: `reports/hazard/attribute-contract-protocol.md`（波の"
        "投入前に凍結）。placed の床は `reports/benchmarks/baseline.json`。",
        "",
        "## 構成ごと（base 対 attr_contract、同一run ペア）",
        "",
        "| 構成 | base | contract | 差 | 床 | 判定 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for case_id, s in result["per_config"].items():
        floor = s["floor"]
        lines.append(
            f"| `{case_id}` | {s['placed_base']:.2f} | "
            f"{s['placed_contract']:.2f} | {s['placed_delta']:+.2f} | "
            f"{'-' if floor is None else f'{floor:.2f}'} | "
            f"{s['verdict']} |"
        )
    lines += [
        "",
        "## プール（4アーム）",
        "",
        "| 量 | " + " | ".join(f"`{a}`" for a in ARMS) + " |",
        "|---" * (len(ARMS) + 1) + "|",
    ]
    for key, label in (
        ("episodes", "episodes"),
        ("placed_total", "placed 合計"),
        ("priority_violations", "優先違反"),
        ("soft_violations", "soft 違反"),
        ("physical_endings", "物理死"),
    ):
        lines.append(
            f"| {label} | "
            + " | ".join(str(p[a][key]) for a in ARMS)
            + " |"
        )
    for key, label in (
        ("shake_max_shift", "shake 最大ずれ"),
        ("shake_peak_kinetic_energy", "shake ピーク運動E"),
    ):
        lines.append(
            f"| {label} | "
            + " | ".join(
                "-" if p[a][key] is None else f"{p[a][key]:.4f}"
                for a in ARMS
            )
            + " |"
        )
    drop = result["priority_violation_drop"]
    lines += [
        "",
        "## ゲート",
        "",
        "| ゲート | 結果 |",
        "|---|---|",
        f"| A 優先違反が base 比 {int(result['buy_fraction']*100)}% 以上減 | "
        f"{'-' if drop is None else f'{drop:.1%} 減'} → "
        f"{'pass' if result['gate_A_buy'] else '**fail**'} |",
        f"| P どの構成でも床を負方向に割らない | "
        f"割った構成 {result['configs_breaching']} → "
        f"{'pass' if result['gate_P_pay'] else '**fail**'} |",
        f"| S shake が悪化しない | "
        f"{'pass' if result['gate_S_stability'] else '**fail**'} |",
        f"| N 両方の単独に勝つ | 違反<支持則単独 "
        f"{result['beats_support_on_violations']}、placed>ガード単独 "
        f"{result['beats_guard_on_placed']} → "
        f"{'pass' if result['gate_N_beats_both_singles'] else '**fail**'} |",
        "",
        f"## 開発判定: **{'PASS' if result['development_pass'] else 'FAIL'}**",
        "",
    ]
    if result["development_pass"]:
        lines.append(
            "開発通過にすぎない。採用には未使用順列・新シード・無調整での"
            "確認波が要る。公式スコアの改善は主張できない — 違反数から"
            "0〜100 への写像は非公開である。"
        )
    else:
        lines.append(
            "不採用。落ちたゲートが結果であり、閾値は動かさず、この"
            "ストリームで再調整もしない。"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", action="append", required=True)
    ap.add_argument(
        "--baseline",
        type=pathlib.Path,
        default=pathlib.Path("reports/benchmarks/baseline.json"),
    )
    ap.add_argument("--output-json", type=pathlib.Path, required=True)
    ap.add_argument("--output-md", type=pathlib.Path)
    args = ap.parse_args()

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    floors = {
        c: (s.get("minimum_resolvable_placed") or {}).get(
            "paired_3v3_same_run"
        )
        for c, s in baseline["cases"].items()
    }
    by_case = load(args.rows)
    if not by_case:
        raise SystemExit("no rows matched --rows")
    result = adjudicate(by_case, floors)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(args.output_json)
    if args.output_md:
        args.output_md.write_text(render(result), encoding="utf-8")
        print(args.output_md)
    print(
        json.dumps(
            {
                "A": result["gate_A_buy"],
                "P": result["gate_P_pay"],
                "S": result["gate_S_stability"],
                "N": result["gate_N_beats_both_singles"],
                "development_pass": result["development_pass"],
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
