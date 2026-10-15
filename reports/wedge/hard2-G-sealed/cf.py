"""cf.py <plan.json> <out.jsonl> -- run counterfactual branches one after another.

The plan is a list of {"record", "scene", "t", "mode", "k", "patch", "persistent",
"defer_item", "tag"}; "patch" indexes the scene's trace patches
($SCRATCH/trace/<record>/<scene>.json) for the protect/fill modes.  Lines already
in the output (same tag) are skipped, so a run can be resumed.  Run from the
repository root (the stack option's policy path is relative)."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import branch as B  # noqa: E402
import sealkit as K  # noqa: E402

SCRATCH = os.environ.get("SCRATCH", "/home/user/inv-G-scratch")


def tag_of(job):
    base = "|".join(str(job.get(k)) for k in ("record", "scene", "t", "mode", "k", "patch", "persistent", "defer_item", "rep"))
    for k in ("arm", "arm_extra", "soft_equal"):
        if job.get(k):
            base += f"|{k}={os.path.basename(str(job[k]))}"
    return job.get("tag") or base


def main():
    plan = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    done = set()
    if os.path.exists(out):
        for line in open(out):
            if line.strip():
                done.add(json.loads(line)["tag"])
    cache = {}
    for job in plan:
        tag = tag_of(job)
        if tag in done:
            continue
        key = (job["record"], job["scene"])
        if key not in cache:
            rec = K.load_record(*key)
            cache.clear()
            cache[key] = (rec, K.Episode(rec))
        rec, ep = cache[key]
        protect = None
        if job.get("patch") is not None:
            tr = json.load(
                open(
                    os.path.join(
                        SCRATCH, "trace", job["record"], job["scene"] + ".json"
                    )
                )
            )
            protect = B.Protected(ep, tr["patches"][int(job["patch"])])
        B.ARM_SPEC = open(job['arm']).read().strip() if job.get('arm') else None
        B.ARM_EXTRA = job.get('arm_extra', '')
        B._ARMS.clear()
        orig_po = B.layer1.pool_order
        if job.get('soft_equal'):
            def po(pairs, config, _o=orig_po):
                import rule_alpha.classify as _cls
                return sorted(pairs, key=lambda pr: (0 if pr[1].cargo_class in (_cls.NORMAL_HARD, _cls.SOFT) else 1,
                                                     round(pr[1].max_footprint, 6), pr[0]))
            B.layer1.pool_order = po
        try:
            res = B.branch_rollout(
                ep,
                rec,
                int(job["t"]),
                job.get("mode", "agent"),
                int(job.get("k", 1)),
                protect,
                job.get("defer_item"),
                bool(job.get("persistent", False)),
            )
        except Exception as exc:  # keep the queue going
            res = dict(error=repr(exc))
        finally:
            B.layer1.pool_order = orig_po
        res.update(
            arm=job.get("arm"), arm_extra=job.get("arm_extra"), soft_equal=job.get("soft_equal"),
            tag=tag,
            record=job["record"],
            scene=job["scene"],
            patch=job.get("patch"),
            label=job.get("label"),
        )
        with open(out, "a") as fh:
            fh.write(json.dumps(res, default=str) + "\n")
        print(
            f"{tag}: placed {res.get('placed')} margin {res.get('margin')} first {res.get('first')} "
            f"note {res.get('note')} ({res.get('seconds')} s)",
            flush=True,
        )


if __name__ == "__main__":
    main()
