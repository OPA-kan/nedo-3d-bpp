"""cf.py <plan.json> : run counterfactual branches one after the other (one process).

A plan is a list of {"rec", "scene", "k", "spec"[, "pi", "extra", "tag"]}.  For each,
the record's first k actions are replayed in the official simulator, ``spec`` (see
alts.py) decides step k, and the shipped arm (the record's arm with deterministic
budgets) plays to the end.  Results are appended to
/home/user/inv-D-scratch/cf/results.jsonl (with the steps) and, compact, to
data/cf_results.jsonl.  Already-run entries (same rec/scene/k/spec/extra) are skipped.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import load_record  # noqa: E402
from alts import action_for, wrap_compact  # noqa: E402
from physbranch import run_branch  # noqa: E402

from bench.arms import make_arm  # noqa: E402

SCRATCH = "/home/user/inv-D-scratch/cf"
COMPACT = os.path.join(HERE, "data", "cf_results.jsonl")


def key(e):
    return (
        e["rec"],
        e["scene"],
        int(e["k"]),
        e["spec"],
        e.get("extra", ""),
        int(e.get("pi", -1)),
        e.get("arm", "record"),
        e.get("wrap", ""),
    )


def done_keys():
    out = set()
    if os.path.exists(COMPACT):
        for line in open(COMPACT):
            e = json.loads(line)
            out.add(key(e))
    return out


def run_one(e):
    r = load_record(e["rec"], e["scene"])
    rs = [s for s in r["steps"] if s.get("event") == "step"]
    k = int(e["k"])
    pi = int(e.get("pi", -1))
    if pi < 0:
        pi = int(rs[k]["pool_index"]) if k < len(rs) else 0
    info = {}

    def override(agent, obs, env):
        a, inf = action_for(e["spec"], agent, obs, pi)
        info.update(inf)
        return a

    extra = "deterministic_budgets=true" + ("," + e["extra"] if e.get("extra") else "")
    t0 = time.perf_counter()
    wrapper = None
    if e.get("wrap", "").startswith("compact"):
        n = e["wrap"].partition(":")[2]
        wrapper = lambda ag: wrap_compact(ag, int(n) if n else None)  # noqa: E731
    arm = None
    if e.get("arm") == "ship":
        # the shipped form (submission/agent.py) as the bench arm files of
        # origin/claude/rl-packing-policy-ftogt3 (9e4ada85) give it; duplicate keys, last wins
        task = r["scene_spec"]["task"].lower()
        spec = open(os.path.join(HERE, "arms", f"arm_ship_{task}.txt")).read().strip()
        arm = make_arm(spec + "," + extra)
    out = run_branch(
        e["rec"],
        e["scene"],
        k,
        override=None if e["spec"] == "agent-native" else override,
        extra=extra,
        r=r,
        arm=arm,
        wrap=wrapper,
    )
    after = [
        s
        for s in out["steps"]
        if s.get("step", -1) >= k and s.get("event") != "declined"
    ]
    first = after[0] if after else {}
    res = {
        "rec": e["rec"],
        "scene": e["scene"],
        "k": k,
        "spec": e["spec"],
        "extra": e.get("extra", ""),
        "pi": int(e.get("pi", -1)),
        "tag": e.get("tag", ""),
        "arm": e.get("arm", "record"),
        "wrap": e.get("wrap", ""),
        "metrics": out.get("metrics"),
        "placed": out["placed"],
        "thr": out["thr"],
        "mg": out["mg"],
        "end": out["end"],
        "record_placed": r["metrics"]["placed_count"],
        "alt": info,
        "first_ok": first.get("ok"),
        "n_after": len(after),
        "soft_after": sum(1 for s in after if s.get("soft")),
        "rescue_after": sum(
            1
            for s in after
            if (s.get("rung") or "")
            in (
                "physics-resort",
                "count-mode",
                "grid-rescue",
                "grid-rescue-cover",
                "fallback",
            )
        ),
        "seconds": round(time.perf_counter() - t0, 1),
    }
    return res, out


def main():
    plan = json.load(open(sys.argv[1]))
    os.makedirs(SCRATCH, exist_ok=True)
    os.makedirs(os.path.dirname(COMPACT), exist_ok=True)
    done = done_keys()
    for e in plan:
        if key(e) in done:
            continue
        try:
            res, out = run_one(e)
        except Exception as exc:  # keep going; the failure is a result too
            import traceback

            res = {
                **{k: e.get(k) for k in ("rec", "scene", "k", "spec", "extra", "tag")},
                "pi": int(e.get("pi", -1)),
                "error": repr(exc),
                "trace": traceback.format_exc()[-800:],
            }
            out = None
        with open(COMPACT, "a") as fh:
            fh.write(json.dumps(res, default=float) + "\n")
        if out is not None:
            with open(os.path.join(SCRATCH, "results.jsonl"), "a") as fh:
                fh.write(
                    json.dumps({**res, "steps": out["steps"]}, default=float) + "\n"
                )
        done.add(key(e))
        print(
            json.dumps(
                {
                    k: res.get(k)
                    for k in (
                        "scene",
                        "k",
                        "spec",
                        "placed",
                        "thr",
                        "mg",
                        "end",
                        "seconds",
                        "error",
                    )
                }
            ),
            (res.get("alt") or {}).get("on"),
            (res.get("alt") or {}).get("bottom"),
            flush=True,
        )


if __name__ == "__main__":
    main()
