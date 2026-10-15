"""cf_stats.py: the counterfactual branches (cf.py output), tabulated.

Per episode and branch step k (counted as placements before the end of the
reference run, "lead" = n - k): the null branch (the agent's own answer at k,
replayed), and every alternative's final margin against the count threshold.
Writes cf_stats.md and cf_summary.json (compact)."""

from __future__ import annotations

import collections
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CF = "/home/user/inv-H-scratch/cf"
REF = "/home/user/inv-H-scratch/ref"


def kind(label):
    if label.startswith("vetoed:"):
        return "a pose the ladder vetoed"
    if label.startswith("veto"):
        return "veto (agent's next answer)"
    if label.startswith("rung1"):
        return "ladder pick (vetoed downstream)"
    if label.startswith("rung"):
        return "next in the rung"
    if label.startswith("other:"):
        return "another rung's best"
    if label.startswith("vetoed:"):
        return "a pose the ladder vetoed"
    if label.startswith("maxsurf"):
        return "most usable surface left"
    return label


def main():
    out = {}
    lines = [
        "# Counterfactual branches (cf.py)",
        "",
        "Each branch forces the reference run up to step k, changes the placement at k, and lets the v50 agent "
        '(deterministic budgets) play to the end in the official simulator.  "lead" = placements before the '
        "reference run's end.  Margins against the count threshold (>= 0 crosses).  \"null\" = the agent's own answer "
        "at k replayed (the reference, up to the clocks of the resort and the shadow).",
        "",
    ]
    summary_rows = []
    kind_stats = collections.defaultdict(
        lambda: [0, 0, 0]
    )  # tried, crossed, improved over null
    for f in sorted(glob.glob(f"{CF}/cf-[bc]-*.json")):
        d = json.load(open(f))
        sc = d["scene"]
        n = d["n_steps"]
        ref_margin = d.get("ref_placed", 0) - d["thr"]
        lines.append(
            f"## {sc}: reference placed {d.get('ref_placed')} (thr {d['thr']}, margin {ref_margin:+d}); record placed {d['record_placed']}"
        )
        lines.append("")
        lines.append(
            "| k (lead) | at k the agent placed | null | alternatives: label -> margin (pose at k ok?) | best | crossing branches |"
        )
        lines.append("|---|---|---:|---|---:|---:|")
        per_k = {}
        for k in sorted(d["branches"], key=lambda s: -int(s)):
            B = d["branches"][k]
            if "null" not in B:
                continue
            null = B["null"]
            alts = [
                (lab, v)
                for lab, v in B.items()
                if not lab.startswith("_")
                and lab != "null"
                and isinstance(v, dict)
                and "margin" in v
            ]
            best = max([null["margin"]] + [v["margin"] for _l, v in alts])
            cross = [lab for lab, v in alts if v["margin"] >= 0]
            for lab, v in alts:
                ks = kind(lab)
                kind_stats[ks][0] += 1
                kind_stats[ks][1] += int(v["margin"] >= 0)
                kind_stats[ks][2] += int(v["margin"] > null["margin"])
            at = null.get("at_k") or {}
            altxt = "; ".join(
                f"{lab} {v['margin']:+d}{'' if (v.get('at_k') or {}).get('ok', True) else ' (fails)'}"
                for lab, v in alts
            )
            lines.append(
                f"| {k} ({n - int(k)}) | {at.get('arch')} | {null['margin']:+d} | {altxt} | {best:+d} | {len(cross)} of {len(alts)} |"
            )
            per_k[int(k)] = {
                "lead": n - int(k),
                "null": null["margin"],
                "best": best,
                "n_alts": len(alts),
                "crossing": cross,
                "margins": {lab: v["margin"] for lab, v in alts},
                "agent_at_k": at.get("arch"),
            }
        lines.append("")
        rescued = [kk for kk, v in per_k.items() if v["crossing"]]
        nearest = max(rescued) if rescued else None
        summary_rows.append(
            (
                sc,
                ref_margin,
                n,
                nearest,
                (n - nearest) if nearest is not None else None,
                sorted({kind(l) for kk in rescued for l in per_k[kk]["crossing"]}),
                {kk: per_k[kk]["null"] for kk in per_k},
            )
        )
        out[sc] = {"ref_margin": ref_margin, "n": n, "per_k": per_k}
    lines.insert(4, "## Summary")
    tbl = [
        "",
        "| scene | ref margin | n | nearest rescuing k (lead) | rescuing kinds | null margins by k |",
        "|---|---:|---:|---|---|---|",
    ]
    for sc, rm, n, nk, lead, kinds, nulls in summary_rows:
        tbl.append(
            f"| {sc} | {rm:+d} | {n} | {nk if nk is not None else '-'} ({lead if lead is not None else '-'}) | {', '.join(kinds) or '-'} | "
            + ", ".join(f"{k}:{v:+d}" for k, v in sorted(nulls.items(), reverse=True))
            + " |"
        )
    tbl += [
        "",
        "| alternative kind | branches | crossing | better than null |",
        "|---|---:|---:|---:|",
    ]
    for ks, (t, c, b) in sorted(kind_stats.items(), key=lambda kv: -kv[1][0]):
        tbl.append(f"| {ks} | {t} | {c} | {b} |")
    tbl.append("")
    lines[5:5] = tbl
    lines += ["", "## Shipped-form confirmation (ship_confirm.py)", "",
              "Every branch that reached the threshold on the record's arm, re-run with the shipped arm "
              "(`arm_ship_c.txt` / `arm_ship_b.txt`, + deterministic budgets) from the same prefix, with its unchanged baseline (null).", "",
              "| scene | k | null: record arm / shipped arm | branch: record arm / shipped arm |", "|---|---:|---|---|"]
    for f in sorted(glob.glob(f"{CF}/cf-ship-*.json")):
        d = json.load(open(f))
        src = json.load(open(f.replace("cf-ship-", "cf-")))
        for k, B in sorted(d["branches"].items(), key=lambda kv: -int(kv[0])):
            if "null" not in B:
                continue
            S = src["branches"].get(k, {})
            br = "; ".join(f"{lab} {S[lab]['margin']:+d} / {v['margin']:+d}" for lab, v in B.items()
                           if not lab.startswith("_") and lab != "null" and isinstance(v, dict) and "margin" in v and lab in S)
            lines.append(f"| {d['scene']} | {k} | {S.get('null', {}).get('margin', 0):+d} / {B['null']['margin']:+d} | {br} |")
    open(f"{HERE}/cf_stats.md", "w").write("\n".join(lines) + "\n")
    json.dump(out, open(f"{HERE}/cf_summary.json", "w"), indent=0)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
