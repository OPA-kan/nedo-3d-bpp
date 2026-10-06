"""hard_report.py <dir> [<dir2>]: the hard suite's failure map -- crossing rate and shares by
situation (containers, count, mix, order, pool, soft share, priority rate), and the worst scenes.
With a second directory, the paired differences."""
import collections, glob, json, sys


def load(d):
    out = {}
    for f in glob.glob(d + "/[abc]-hard-*.json"):
        r = json.load(open(f)); m = r["metrics"]; sp = r["scene_spec"]
        thr = m["total_items"] // 2 + 1
        out[r["scene"]] = dict(placed=m["placed_count"], total=m["total_items"], over=m["placed_count"] >= thr,
                               share=m["placed_count"] / m["total_items"],
                               soft=(m["soft_count"] / sp["soft_total"]) if sp["soft_total"] else 1.0,
                               prio=(m["priority_count"] / sp["priority_total"]) if sp["priority_total"] else 1.0,
                               fill=m["fill_volume"], com=m["com_z_above_floor_ratio"], tmax=m["policy_time_max"],
                               end=m.get("end_reason"), topples=m.get("shake_topples", 0), contact=m.get("contact_covered", 0),
                               spec=sp, runtime=r["runtime_seconds"])
    return out


def value(r):
    gate = 1.0 if r["over"] else 0.0
    return 0.287 * r["fill"] + gate * (14.1 * r["soft"] + 14.3 * r["prio"] + 21.9 * (1 - r["com"]) + 21.0 * 0.75)


def report(rs, title):
    n = len(rs)
    print(f"== {title}: {n} scenes, over the threshold {sum(r['over'] for r in rs.values())}/{n}, "
          f"placed share {sum(r['share'] for r in rs.values())/n:.3f}, soft {sum(r['soft'] for r in rs.values())/n:.2f}, "
          f"prio {sum(r['prio'] for r in rs.values())/n:.2f}, fill {sum(r['fill'] for r in rs.values())/n:.1f}, "
          f"CoM {sum(r['com'] for r in rs.values())/n:.3f}, value/episode {sum(value(r) for r in rs.values())/n:.1f}, "
          f"tmax {max(r['tmax'] for r in rs.values()):.1f}s, ends {dict(collections.Counter(r['end'] for r in rs.values()))}")
    for key, fn in (("containers", lambda s: s["containers_n"]), ("base_count", lambda s: s["base_count"]), ("mix", lambda s: s["mix"]),
                    ("order", lambda s: s["order"]), ("pool", lambda s: s["pool"]), ("soft_share", lambda s: s["soft_share"]),
                    ("priority_rate", lambda s: s["priority_rate"]), ("priority_container", lambda s: s["priority_container"]),
                    ("shelves", lambda s: s["shelves"])):
        groups = collections.defaultdict(list)
        for r in rs.values():
            groups[fn(r["spec"])].append(r)
        row = ", ".join(f"{k}: {sum(x['over'] for x in g)}/{len(g)} over, share {sum(x['share'] for x in g)/len(g):.2f}, value {sum(value(x) for x in g)/len(g):.0f}"
                        for k, g in sorted(groups.items(), key=lambda kv: str(kv[0])))
        print(f"   by {key}: {row}")
    worst = sorted(rs.values(), key=lambda r: r["share"])[:8]
    print("   worst:", "; ".join(f"{[k for k,v in rs.items() if v is r][0]} {r['placed']}/{r['total']} ({r['spec']['mix']}/{r['spec']['order']}/n{r['spec']['containers_n']}/pool{r['spec']['pool']}, tmax {r['tmax']:.1f}s)" for r in worst))


a = load(sys.argv[1]); report(a, sys.argv[1])
if len(sys.argv) > 2:
    b = load(sys.argv[2]); report(b, sys.argv[2])
    common = sorted(set(a) & set(b))
    print(f"== paired {sys.argv[2]} - {sys.argv[1]} on {len(common)}: over {sum(a[s]['over'] for s in common)} -> {sum(b[s]['over'] for s in common)}, "
          f"placed {sum(b[s]['placed'] - a[s]['placed'] for s in common)/len(common):+.2f}, soft share {sum(b[s]['soft'] - a[s]['soft'] for s in common)/len(common):+.3f}, "
          f"prio share {sum(b[s]['prio'] - a[s]['prio'] for s in common)/len(common):+.3f}, value {sum(value(b[s]) - value(a[s]) for s in common)/len(common):+.2f}")
