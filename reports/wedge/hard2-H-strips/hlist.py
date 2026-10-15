"""The H (no level patch) episodes of the v50 hard2 records, from the taxonomy's
tables.md, with scene facts and the agent's own count-threshold estimate
(count_mode_items_per_container 41 x containers, strict: floor(total/2)+1)."""
import json, re, sys, os
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
TAB = f'{REPO}/reports/wedge/hard2-miss-taxonomy/tables.md'
REC = {'C': 'gate0-hard2', 'B': 'gate0-hard2-b', 'Cdet': 'gate0det-hard2', 'Br2': 'gate0-hard2-b-r2'}

def h_scenes():
    out = {}
    sec = None
    for line in open(TAB):
        if line.startswith('####'):
            sec = line
            continue
        m = re.match(r'\| ([bc]-hard2-s\d+) \| (\w+) \| ([\d.]+) \| (\d+)/(\d+) \| (-?\d+) \| (\w+) \| ([^|]*) \| H \|', line)
        if m and sec and 'every miss' in sec:
            out[m.group(1)] = dict(stratum=m.group(2), need=float(m.group(3)), placed=int(m.group(4)), thr=int(m.group(5)), mg=int(m.group(6)))
    return out

if __name__ == '__main__':
    H = h_scenes()
    rows = []
    for sc, v in sorted(H.items()):
        task = sc[0].upper()
        r = json.load(open(f'{REPO}/reports/bench/{REC[task]}/{sc}.json'))
        sp = r['scene_spec']; m = r['metrics']
        n = sp['containers_n']; N = m['total_items']
        est = (41 * n) // 2 + 1
        rows.append(dict(scene=sc, **v, N=N, containers=n, shelves=sp['shelves'], order=sp['order'], mix=sp['mix'],
                         agent_thr=est, pool=sp['pool'], end=m['end_reason']))
        print(f"{sc} {v['stratum']:8s} mg {v['mg']:4d} placed {v['placed']}/{v['thr']} N {N} ctr {n} shelves {sp['shelves']} agent_thr {est} order {sp['order']} mix {sp['mix']}")
    json.dump(rows, open(os.path.join(os.path.dirname(__file__), 'hlist.json'), 'w'), indent=1)
