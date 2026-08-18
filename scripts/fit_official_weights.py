"""Fit the official component weights from the recorded submissions.

`official-score-log-submission22` established that the weights are not
identifiable from ONE submission: 83 vectors on a 0.05 grid reproduce
that single total to within 0.05. That reading was correct for one
observation and is superseded by this script, which uses all of them --
five totals against four free weights is overdetermined, and some of the
weights fall out.

Two things it is careful about, because both were got wrong before:

* `simulator/README.md`'s 評価指標 lists FOUR scored items -- 充填率 /
  重心 / 配置 / 安定性. `num_placed_items` is NOT among them; it is the
  gate variable of the loading cutoff. It is therefore excluded from
  the fit rather than treated as a component.
* `placement_score` and `soft_item_score` are the priority and soft
  halves of the single 配置スコア, evaluated independently. They enter
  as separate columns, but their SUM is what the fit can pin, and the
  report says so rather than quoting either alone.

Identifiability is reported by enumeration, not by a covariance
estimate: every grid vector under the tolerance is listed and each
weight's range across them is the honest interval.
"""

from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np

COMPONENTS = (
    "fill_score",
    "cog_score",
    "placement_score",
    "soft_item_score",
    "stability_score",
)


def parse_log(path: pathlib.Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks = []
    for start, line in enumerate(lines):
        if not line.startswith('{"fill_score"'):
            continue
        buffer = ""
        for offset in range(start, min(start + 8, len(lines))):
            buffer += lines[offset]
            try:
                blocks.append(json.loads(buffer))
                break
            except json.JSONDecodeError:
                continue
    return blocks


def enumerate_fits(matrix, totals, step: float, tolerance: float):
    fits = []
    grid = np.arange(0.0, 1.0 + 1e-9, step)
    for w1 in grid:
        for w2 in grid[grid <= 1.0 - w1 + 1e-9]:
            for w3 in grid[grid <= 1.0 - w1 - w2 + 1e-9]:
                for w4 in grid[grid <= 1.0 - w1 - w2 - w3 + 1e-9]:
                    w5 = 1.0 - w1 - w2 - w3 - w4
                    if w5 < -1e-9:
                        continue
                    weights = np.array([w1, w2, w3, w4, max(0.0, w5)])
                    residual = matrix @ weights - totals
                    rmse = float(np.sqrt(residual @ residual / len(totals)))
                    if rmse < tolerance:
                        fits.append((rmse, weights))
    return fits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log",
        type=pathlib.Path,
        default=pathlib.Path("docs/OFFICIAL_SCORE_LOG.md"),
    )
    parser.add_argument(
        "--totals",
        default="17.58143419644042,23.245587753037217,35.37542828677423,"
        "29.959,35.19513400148694",
    )
    parser.add_argument("--step", type=float, default=0.01)
    parser.add_argument("--tolerance", type=float, default=0.05)
    parser.add_argument("--output-json", type=pathlib.Path, required=True)
    parser.add_argument("--output-md", type=pathlib.Path)
    args = parser.parse_args()

    blocks = parse_log(args.log)
    totals = np.array([float(v) for v in args.totals.split(",")])
    if len(blocks) != len(totals):
        raise SystemExit(
            f"parsed {len(blocks)} feedback blocks but got "
            f"{len(totals)} totals"
        )
    matrix = np.array([[b[k] for k in COMPONENTS] for b in blocks])

    fits = enumerate_fits(matrix, totals, args.step, args.tolerance)
    if not fits:
        raise SystemExit("no weight vector fits within the tolerance")
    fits.sort(key=lambda item: item[0])
    best_rmse, best = fits[0]
    stack = np.array([w for _rmse, w in fits])

    bounds = {
        name: [float(stack[:, i].min()), float(stack[:, i].max())]
        for i, name in enumerate(COMPONENTS)
    }
    place_sum = stack[:, 2] + stack[:, 3]
    latest = matrix[-1]
    headroom = {
        name: [
            float(bounds[name][0] * (100.0 - latest[i])),
            float(bounds[name][1] * (100.0 - latest[i])),
        ]
        for i, name in enumerate(COMPONENTS)
    }

    result = {
        "submissions": len(totals),
        "tolerance_rmse": args.tolerance,
        "grid_step": args.step,
        "best_weights": dict(zip(COMPONENTS, [float(v) for v in best])),
        "best_rmse": best_rmse,
        "fitting_vectors": len(fits),
        "weight_bounds": bounds,
        "placement_plus_soft_bounds": [
            float(place_sum.min()),
            float(place_sum.max()),
        ],
        "latest_components": dict(
            zip(COMPONENTS, [float(v) for v in latest])
        ),
        "headroom_points": headroom,
        "note": (
            "num_placed_items is excluded on purpose: README's 評価指標 "
            "lists four scored items and placed is the cutoff gate, not "
            "a component. placement_score and soft_item_score are the "
            "two halves of 配置スコア, so only their SUM is quotable."
        ),
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(args.output_json)

    if args.output_md:
        lines = [
            "# 公式成分の重み — 5提出からの部分同定",
            "",
            f"- 提出数: {len(totals)}",
            f"- 許容 RMSE < {args.tolerance}、格子 {args.step}",
            f"- 適合するベクトル: {len(fits)} 通り",
            f"- 最小二乗解の RMSE: {best_rmse:.4f}",
            "",
            "| 成分 | 最良重み | 重み幅 | 現在値 | 残り伸びしろ(総合点) |",
            "|---|---:|---|---:|---|",
        ]
        for i, name in enumerate(COMPONENTS):
            lo, hi = bounds[name]
            h_lo, h_hi = headroom[name]
            lines.append(
                f"| `{name}` | {best[i]:.2f} | {lo:.2f}-{hi:.2f} | "
                f"{latest[i]:.2f} | {h_lo:.1f} - {h_hi:.1f} |"
            )
        lines += [
            "",
            f"**配置スコア (placement + soft) の重み合計: "
            f"{place_sum.min():.2f} - {place_sum.max():.2f}** — "
            "個別には緩いが合計は締まる。二つは公開規則上ひとつの成分の"
            "半分どうしなので、引用するならこの合計。",
            "",
            "`num_placed_items` は採点成分ではなくカットオフのゲート変数"
            "なので、この当てはめから除いてある。",
        ]
        args.output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(args.output_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
