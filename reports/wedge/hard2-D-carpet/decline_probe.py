"""decline_probe.py <rec> <scene> <k>: what the rescue stages tried at a declining call.

Replays the record to step k, then runs the agent's policy (deterministic budgets)
with every shadow verdict logged (pose, support kind, transport / settle / shake,
drift), and the stack option's routing and candidate count.  Prints a digest.
"""

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from instrument import _patched, _support_kind  # noqa: E402
from physbranch import state_at  # noqa: E402

from rule_alpha import classify as cls  # noqa: E402
from rule_alpha import layer1  # noqa: E402


def main():
    rec, scene, k = sys.argv[1], sys.argv[2], int(sys.argv[3])
    agent, obs = state_at(rec, scene, k)
    verdicts = []

    def wrap(orig):
        def f(sim, action, item):
            v = orig(sim, action, item)
            verdicts.append(
                {
                    k2: v.get(k2)
                    for k2 in (
                        "transport_ok",
                        "settle_ok",
                        "shake_ok",
                        "drift",
                        "drift_xy",
                        "angle_deg",
                        "ok",
                    )
                }
                | {
                    "pos": [round(float(x), 3) for x in action["place_pos"]],
                    "ori": int(action["orientation"]),
                }
            )
            return v

        return f

    stages = []

    def wrap_stage(name):
        def w(orig):
            def f(*a, **kw):
                res = orig(*a, **kw)
                stages.append((name, res is not None))
                return res

            return f

        return w

    board = layer1.Board(obs["container_list"], agent.config)
    item = obs["pool_list"][0]
    prof = cls.classify_item(int(item["index"]), item, agent.config)
    print(
        "item",
        item["index"],
        "soft",
        item.get("is_soft"),
        "dims",
        item["length"],
        item["width"],
        item["height"],
    )
    print("routing strict", layer1.routing_order(prof, board, agent.config))
    with _patched(agent, "_shadow_verdict", wrap):
        for nm in ("_last_resort", "_physics_resort", "_grid_rescue"):
            agent.__dict__.pop(nm, None)
        import contextlib

        with contextlib.ExitStack() as st:
            for nm in ("_last_resort", "_physics_resort", "_grid_rescue"):
                st.enter_context(_patched(agent, nm, wrap_stage(nm)))
            a = agent.policy(obs)
    print(
        "action",
        a is not None,
        "stages",
        stages,
        "shadow stats",
        agent.shadow_stats,
        "phase",
        agent.phase_stats,
    )
    c = collections.Counter(
        (v["transport_ok"], v["settle_ok"], v.get("shake_ok"), v["ok"])
        for v in verdicts
    )
    print("verdicts (transport, settle, shake, ok):", dict(c))
    for v in verdicts[:30]:
        print("  ", v)
    json.dump(
        {"verdicts": verdicts, "stages": stages},
        open(f"/home/user/inv-D-scratch/decline_{scene}_{k}.json", "w"),
    )


if __name__ == "__main__":
    main()
