"""cf_table.py: the counterfactual results as markdown (data/cf_results.jsonl).

Per episode: the agent's own continuation from every branched step (the noise
reference: same arm, same machine, the record's board at k), then every alternative
against the baseline at the same k.  'rescue' = the alternative crosses (placed >=
threshold) where the baseline at the same k does not.
"""

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    out = []
    for line in open(os.path.join(HERE, "data", "cf_results.jsonl")):
        e = json.loads(line)
        if "error" in e:
            continue
        out.append(e)
    return out


def main():
    rows = load()
    by = collections.defaultdict(list)
    for e in rows:
        if e.get("wrap"):
            continue
        by[(e["scene"], e.get("arm", "record"))].append(e)
    rescues = []
    for (scene, arm), L in sorted(by.items()):
        base = {e["k"]: e for e in L if e["spec"] == "agent"}
        thr = L[0]["thr"]
        print(
            f"\n#### {scene} ({arm} arm; threshold {thr}; record {L[0]['record_placed']})\n"
        )
        ks = sorted(base)
        print("agent from k: " + ", ".join(f"{k}: {base[k]['mg']:+d}" for k in ks))
        print("\n| k | alternative | pose | placed | margin | baseline at k | |")
        print("|---:|---|---|---:|---:|---:|---|")
        for e in sorted(L, key=lambda e: (e["k"], e["spec"])):
            if e["spec"] == "agent":
                continue
            a = e.get("alt") or {}
            b = base.get(e["k"])
            if e["end"] == "override-none":
                pose = "none: " + str(a.get("none", ""))
                print(
                    f"| {e['k']} | {e['spec']} | {pose} | - | - | {b['mg'] if b else ''} | |"
                )
                continue
            pose = f"{a.get('on')} @ {a.get('bottom')} m, c{a.get('ci')}" if a else ""
            flag = ""
            if b is not None and e["mg"] >= 0 > b["mg"]:
                flag = "rescue"
                rescues.append(e)
            elif b is not None and b["mg"] >= 0 > e["mg"]:
                flag = "loses"
            first = (
                "" if e.get("first_ok", True) else " (the pose failed in the simulator)"
            )
            print(
                f"| {e['k']} | {e['spec']} | {pose}{first} | {e['placed']} | {e['mg']:+d} | {b['mg'] if b else ''} | {flag} |"
            )
    comp = [e for e in rows if e.get("wrap") is not None]
    if comp:
        print("\n#### compaction (k = 0, whole episodes)\n")
        print(
            "| scene | arm | baseline placed / margin / soft covered | compact all | compact first 6 |"
        )
        print("|---|---|---|---|---|")
        g = collections.defaultdict(dict)
        for e in comp:
            if e["k"] == 0 and e["spec"] == "agent":
                g[(e["scene"], e.get("arm", "record"))][e.get("wrap", "")] = e
        for (scene, arm), d in sorted(g.items()):

            def f(e):
                if e is None:
                    return ""
                m = e.get("metrics") or {}
                return f"{e['placed']} / {e['mg']:+d} / {m.get('soft_covered')} of {m.get('soft_count')}"

            print(
                f"| {scene} | {arm} | {f(d.get(''))} | {f(d.get('compact'))} | {f(d.get('compact:6'))} |"
            )
    json.dump(rescues, open(os.path.join(HERE, "data", "rescues.json"), "w"), indent=0)


if __name__ == "__main__":
    main()
