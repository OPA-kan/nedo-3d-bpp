"""
Do the local proxies point the same way as the official components?

Every adoption decision on this branch has been made on `placed`, because
`placed` is the only local quantity whose official direction is known -- the
cutoff-gate model held across three submissions at 14x, 6.7x and 7.6x
amplification, once with the sign flipped. The other four official
components (cog, stability, placement, soft) are computed only by the
evaluation service, and the local raw quantities that stand in for them have
never been checked against a single official observation.

That gap is what stops adoption. The attribute guard measured on this branch
loses placements and drives priority violations to zero: a clean trade, and
nothing local can say which side is worth more.

`docs/BLOCKED_WORK.md` section 0 states the way out, and this is it. Three
of the four scored submissions are reconstructible as knob settings on the
current agent, all with published six-component breakdowns:

    base           submissiontrueenvelope   total 35.375
    death_band     submissiondeathband      total 29.959
    box_envelope   submission3334 level     total 23.246

Run all three locally, read the raw proxies, and check whether each proxy
orders the three configurations the same way its official component does.
Three points cannot fit coefficients. They can refute a direction, and a
proxy that points the wrong way across a 12-point official spread is not
evidence about anything.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# From docs/OFFICIAL_SCORE_LOG.md. Each is a submission whose configuration
# this run reproduces with a knob.
OFFICIAL = {
    "base": {
        "submission": "trueenvelope",
        "total": 35.375, "fill": 34.246, "cog": 40.683,
        "stability": 53.240, "placement": 16.95, "soft": 21.30,
        "placed": 0.5047,
    },
    "death_band": {
        "submission": "deathband",
        "total": 29.959, "fill": 33.635, "cog": 32.243,
        "stability": 41.288, "placement": 14.70, "soft": 17.45,
        "placed": 0.4915,
    },
    "box_envelope": {
        "submission": "3334",
        "total": 23.246, "fill": 31.413, "cog": 21.505,
        "stability": 29.424, "placement": 10.85, "soft": 12.65,
        "placed": 0.4524,
    },
}

# proxy -> (official component, expected sign of the relationship)
#
# `sign` is what the proxy's DIRECTION should be relative to the component:
# +1 means a higher proxy should accompany a higher official score, -1 means
# a higher proxy should accompany a LOWER one. cog and stability score
# higher when the cargo is lower and moves less, so their raw proxies are
# inverted.
PROXIES = {
    "fill": ("fill", +1),
    "placed": ("placed", +1),
    "com_z": ("cog", -1),
    "shake_max_shift": ("stability", -1),
    "shake_items_toppled": ("stability", -1),
    "priority_covered_by_other": ("placement", -1),
    "soft_covered_by_other": ("soft", -1),
}


def metrics(case: dict) -> dict:
    out = {
        "placed": case.get("placed_fraction"),
        "fill": case.get("fill_score"),
        "com_z": case.get("final_com_z"),
    }
    attribute = case.get("attribute_placement") or {}
    for key in ("priority_covered_by_other", "soft_covered_by_other"):
        if attribute.get(key) is not None:
            out[key] = float(attribute[key])
    shake = case.get("shake_response") or {}
    for key in ("shake_max_shift", "shake_items_toppled"):
        if shake.get(key) is not None:
            out[key] = float(shake[key])
    return {k: v for k, v in out.items() if v is not None}


def collect(root: pathlib.Path):
    per_arm = collections.defaultdict(lambda: collections.defaultdict(list))
    for path in sorted(glob.glob(f"{root}/**/rows.jsonl", recursive=True)):
        for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            arm = row.get("arm")
            if arm not in OFFICIAL and arm != "base_null":
                continue
            for case in (row.get("cases") or {}).values():
                if case.get("status") != "success":
                    continue
                for name, value in metrics(case).items():
                    per_arm[arm][name].append(float(value))
    return per_arm


def concordant(pairs):
    """Kendall-style agreement over the three ordered configurations."""
    agree = 0
    total = 0
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            (lx, ox), (ly, oy) = pairs[i], pairs[j]
            if abs(ox - oy) < 1e-12 or abs(lx - ly) < 1e-12:
                continue
            total += 1
            if (lx - ly) * (ox - oy) > 0:
                agree += 1
    return agree, total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    per_arm = collect(args.root)
    arms = [a for a in OFFICIAL if a in per_arm]
    if len(arms) < 3:
        print(f"only {len(arms)} of 3 configurations present: {arms}",
              file=sys.stderr)

    # the noise floor, from the two identical configurations
    floor = {}
    if "base" in per_arm and "base_null" in per_arm:
        for name in set(per_arm["base"]) & set(per_arm["base_null"]):
            b, n = per_arm["base"][name], per_arm["base_null"][name]
            floor[name] = max(
                abs(statistics.fmean(b) - statistics.fmean(n)),
                (max(b) - min(b)) if len(b) > 1 else 0.0,
                (max(n) - min(n)) if len(n) > 1 else 0.0,
            )

    print(f'{"proxy":26s} {"official":>10s} ' + "".join(f"{a:>14s}" for a in arms))
    report = {}
    for proxy, (component, sign) in PROXIES.items():
        if not all(proxy in per_arm[a] for a in arms):
            continue
        local = {a: statistics.fmean(per_arm[a][proxy]) for a in arms}
        line = f"{proxy:26s} {component:>10s} "
        for a in arms:
            line += f"{local[a]:14.3f}"
        print(line)
        official_line = f'{"":26s} {"official":>10s} '
        for a in arms:
            official_line += f"{OFFICIAL[a][component]:14.3f}"
        print(official_line)

        pairs = [(sign * local[a], OFFICIAL[a][component]) for a in arms]
        agree, total = concordant(pairs)
        span = max(local.values()) - min(local.values())
        f = floor.get(proxy, 0.0)
        verdict = (
            "UNRESOLVED (spread inside the noise floor)"
            if span <= f
            else ("agrees" if agree == total and total else
                  "DISAGREES" if agree == 0 and total else
                  f"partial {agree}/{total}")
        )
        print(f'{"":26s} {"->":>10s}  {verdict}   '
              f'local span {span:.3f} vs floor {f:.3f}\n')
        report[proxy] = {
            "component": component,
            "sign": sign,
            "local": local,
            "concordant": agree,
            "comparisons": total,
            "span": span,
            "floor": f,
            "verdict": verdict,
        }

    print(
        "Three points cannot fit weights. They can refute a direction: a "
        "proxy that DISAGREES across a 12-point official spread is not "
        "evidence about its component, and one whose local spread sits "
        "inside the noise floor has not been tested at all."
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
