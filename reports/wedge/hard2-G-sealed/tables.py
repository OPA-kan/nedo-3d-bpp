"""tables.py -- compact tables from the scratch outputs (trace, why, cf, census, vsim).

python3 tables.py            -> tables.md and data/*.json next to this file
"""

from __future__ import annotations

import collections
import glob
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sealkit as K  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.environ.get("SCRATCH", "/home/user/inv-G-scratch")
G_C = [
    "c-hard2-s0059",
    "c-hard2-s0027",
    "c-hard2-s0013",
    "c-hard2-s0060",
    "c-hard2-s0063",
    "c-hard2-s0055",
    "c-hard2-s0081",
    "c-hard2-s0087",
    "c-hard2-s0070",
]
G_B = [
    "b-hard2-s0007",
    "b-hard2-s0009",
    "b-hard2-s0077",
    "b-hard2-s0026",
    "b-hard2-s0064",
    "b-hard2-s0004",
    "b-hard2-s0081",
    "b-hard2-s0056",
    "b-hard2-s0030",
    "b-hard2-s0055",
    "b-hard2-s0073",
    "b-hard2-s0071",
    "b-hard2-s0075",
    "b-hard2-s0086",
]
NEAR = [
    "c-hard2-s0059",
    "c-hard2-s0027",
    "c-hard2-s0013",
    "b-hard2-s0007",
    "b-hard2-s0009",
    "b-hard2-s0077",
    "b-hard2-s0026",
    "b-hard2-s0064",
]
_EP = {}


def ep_of(record, scene):
    k = (record, scene)
    if k not in _EP:
        _EP[k] = K.Episode(K.load_record(record, scene))
    return _EP[k]


def load_trace(record):
    out = {}
    for f in sorted(glob.glob(os.path.join(SCRATCH, "trace", record, "*.json"))):
        d = json.load(open(f))
        out[d["scene"]] = d
    return out


def merge_patches(d):
    """Patches at levels within 2 cm of each other in one container are one patch
    (the trace keys levels at 1 cm); keeps the larger's record, the latest seal."""
    out = []
    for p in sorted(d["patches"], key=lambda p: (p["ci"], p["z"])):
        if (
            out
            and out[-1]["ci"] == p["ci"]
            and abs(out[-1]["z"] - p["z"]) <= 0.02
            and p.get("sealer", {}).get("t") == out[-1].get("sealer", {}).get("t")
        ):
            if p["n_spots"] > out[-1]["n_spots"]:
                out[-1] = p
            continue
        out.append(p)
    return out


def seal_t(p):
    return (
        p.get("seal_t") if p["kind"] == "sealed-after-open" else p.get("last_blocker_t")
    )


def door_dist(ep, p):
    """Distance from the sealer's door-side face to the floor's door edge (m)."""
    s = p.get("sealer")
    if not s:
        return None
    m = ep.models[s["ci"]]
    return round(s["pos"][1] - s["size"][1] / 2 - m.floor_rect.y_min, 3)


def end_state(d):
    lvl = any(v["level"] > 0 for v in d["visible"])
    rex = any(v["reach_exact"] > 0 for v in d["visible"])
    rce = any(v["reach_cells"] > 0 for v in d["visible"])
    return lvl, rex, rce


def md_table(rows, head):
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        lines.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(lines)


def sec_end_states(md, data):
    md.append(
        "## End states: level and reachable spots for the visible items (all episodes)\n"
    )
    rows = []
    for record, label in (
        ("gate0-hard2", "C (next item)"),
        ("gate0-hard2-v10", "C (next 10 items)"),
        ("gate0-hard2-b", "B (pool of 10)"),
    ):
        tr = load_trace(record)
        for group in ("miss", "cross"):
            ds = [
                d
                for d in tr.values()
                if (d["margin"] < 0) == (group == "miss") and d["visible"]
            ]
            n = len(ds)
            lv = sum(1 for d in ds if end_state(d)[0])
            sealed = sum(1 for d in ds if end_state(d)[0] and not end_state(d)[1])
            sealed_cells = sum(1 for d in ds if end_state(d)[0] and not end_state(d)[2])
            disagree = sum(1 for d in ds if end_state(d)[1] != end_state(d)[2])
            noreach = sum(1 for d in ds if not end_state(d)[1])
            rows.append([label, group, n, lv, sealed, sealed_cells, disagree, noreach,
                         f"{sealed} ({sealed / max(1, noreach):.2f})"])
    md.append(
        md_table(
            rows,
            [
                "record",
                "group",
                "episodes ending with visible items",
                "some level spot",
                "level, none reachable (exact)",
                "level, none reachable (cells)",
                "exact/cells disagree",
                "no reachable spot",
                "of which some level spot",
            ],
        )
    )
    md.append("")
    data["end_states"] = rows


def sec_g_patches(md, data):
    md.append(
        "## The sealed patches of the G episodes (v50, `gate0-hard2` / `gate0-hard2-b`)\n"
    )
    md.append(
        "One row per patch (container, support level) holding a level, sealed spot for a visible item at the end. "
        "`open` = prefixes during which some spot of the patch was level with a clear path; `seal` = the placement "
        "that closed the last open spot; `lead` = placements from the seal to the end; `door` = distance from the "
        "sealer's door-side face to the floor's door edge.\n"
    )
    rows = []
    allp = []
    for record, scenes in (("gate0-hard2", G_C), ("gate0-hard2-b", G_B)):
        tr = load_trace(record)
        for sc in scenes:
            d = tr[sc]
            ep = ep_of(record, sc)
            for p in merge_patches(d):
                s = p.get("sealer") or {}
                t = seal_t(p)
                rec = dict(
                    scene=sc,
                    task=d["task"],
                    margin=d["margin"],
                    T=d["T"],
                    ci=p["ci"],
                    z=p["z"],
                    floor=p["on_floor"],
                    n=p["n_spots"],
                    kind=p["kind"],
                    y=p["y_range"],
                    open=(p.get("open_from"), t)
                    if p["kind"] == "sealed-after-open"
                    else None,
                    seal_t=t,
                    lead=(d["T"] - t) if t is not None else None,
                    arch=s.get("arch"),
                    door=door_dist(ep, p),
                    top=round(s["pos"][2] + s["size"][2] / 2, 2) if s else None,
                    standing=s.get("standing"),
                    soft=s.get("soft"),
                    prio=s.get("prio"),
                    closers=len(p.get("closers") or []) or None,
                )
                allp.append(rec)
                rows.append(
                    [
                        sc,
                        d["margin"],
                        d["T"],
                        p["ci"],
                        f"{p['z']:.2f}" + (" floor" if p["on_floor"] else ""),
                        p["n_spots"],
                        f"{p['y_range'][0]:+.2f}..{p['y_range'][1]:+.2f}",
                        (
                            f"{p.get('open_from')}..{t}"
                            if p["kind"] == "sealed-after-open"
                            else "born sealed"
                        ),
                        t,
                        rec["lead"],
                        s.get("arch"),
                        rec["door"],
                        rec["top"],
                        ("standing " if s.get("standing") else "")
                        + ("soft " if s.get("soft") else "")
                        + ("prio" if s.get("prio") else ""),
                    ]
                )
    md.append(
        md_table(
            rows,
            [
                "scene",
                "margin",
                "placed",
                "ci",
                "level (m)",
                "spots",
                "spot y",
                "open",
                "seal",
                "lead",
                "sealer rung",
                "door (m)",
                "sealer top (m)",
                "sealer",
            ],
        )
    )
    md.append("")
    data["g_patches"] = allp
    # summaries
    for task in ("C", "B"):
        ps = [p for p in allp if p["task"] == task]
        arch = collections.Counter(p["arch"] for p in ps)
        door = [p["door"] for p in ps if p["door"] is not None]
        md.append(
            f"- **{task}:** {len(ps)} patches in {len({p['scene'] for p in ps})} episodes; "
            f"sealed after open {sum(1 for p in ps if p['kind'] == 'sealed-after-open')}, born sealed "
            f"{sum(1 for p in ps if p['kind'] != 'sealed-after-open')}; floor patches {sum(1 for p in ps if p['floor'])}; "
            f"sealer within 0.15 m of the door edge {sum(1 for x in door if x <= 0.15)} of {len(door)} "
            f"(median {statistics.median(door):.2f} m); standing sealers {sum(1 for p in ps if p['standing'])}; "
            f"soft {sum(1 for p in ps if p['soft'])}, priority {sum(1 for p in ps if p['prio'])}; "
            f"lead median {statistics.median([p['lead'] for p in ps if p['lead'] is not None])}; "
            f"sealer rungs: " + ", ".join(f"{k} {v}" for k, v in arch.most_common())
        )
    md.append("")


def sec_crossings(md, data):
    md.append(
        "## Crossings that end sealed: when the patch was sealed against the threshold\n"
    )
    rows = []
    for record in ("gate0-hard2", "gate0-hard2-b"):
        tr = load_trace(record)
        for group in ("G", "cross-sealed"):
            if group == "G":
                ds = [tr[s] for s in (G_C if record == "gate0-hard2" else G_B)]
            else:
                ds = [
                    d
                    for d in tr.values()
                    if d["margin"] >= 0
                    and d["visible"]
                    and end_state(d)[0]
                    and not end_state(d)[1]
                ]
            before = after = 0
            leads = []
            arch = collections.Counter()
            for d in ds:
                for p in merge_patches(d):
                    t = seal_t(p)
                    if t is None:
                        continue
                    if t < d["thr"] - 1:
                        before += 1
                    else:
                        after += 1
                    leads.append(d["T"] - t)
                    arch[(p.get("sealer") or {}).get("arch")] += 1
            rows.append(
                [
                    record,
                    group,
                    len(ds),
                    before,
                    after,
                    statistics.median(leads) if leads else "-",
                    ", ".join(f"{k} {v}" for k, v in arch.most_common(4)),
                ]
            )
    md.append(
        md_table(
            rows,
            [
                "record",
                "group",
                "episodes",
                "patches sealed before the threshold placement",
                "at or after it",
                "lead (median)",
                "sealer rungs (top 4)",
            ],
        )
    )
    md.append("")
    data["crossings"] = rows


def main():
    md = [
        "# hard2 G (sealed patch): tables",
        "",
        "Generated by `tables.py` from the scratch outputs of `trace.py`, "
        "`why.py`, `cf.py`, `census.py` and `validate_sim.py`.",
        "",
    ]
    data = {}
    sec_end_states(md, data)
    sec_g_patches(md, data)
    sec_crossings(md, data)
    for extra in ("sec_census", "sec_why", "sec_cf_summary", "sec_pool", "sec_seal", "sec_ship", "sec_soft", "sec_cf", "sec_vsim"):
        f = globals().get(extra)
        if f is not None:
            f(md, data)
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    open(os.path.join(HERE, "tables.md"), "w").write("\n".join(md) + "\n")
    json.dump(
        data,
        open(os.path.join(HERE, "data", "tables.json"), "w"),
        indent=0,
        default=str,
    )
    print("\n".join(md))




def _group(scene, margin, task):
    if scene in G_C or scene in G_B:
        return 'G'
    return 'miss-other' if margin < 0 else 'cross'


def sec_census(md, data):
    rows, rung_rows, know_rows = [], [], []
    out = {}
    for record in ('gate0-hard2', 'gate0-hard2-b'):
        path = os.path.join(SCRATCH, 'census', record + '.json')
        if not os.path.exists(path):
            continue
        cen = json.load(open(path))
        by = collections.defaultdict(list)
        for e in cen:
            by[_group(e['scene'], e['margin'], e['task'])].append(e)
        rung_use = collections.Counter(); rung_ev = collections.Counter(); rung_area = collections.Counter()
        for g in ('G', 'miss-other', 'cross'):
            es = by.get(g, [])
            if not es:
                continue
            npl = sum(len(e['events']) for e in es)
            ev = [x for e in es for x in e['events'] if x['sealed'][0] >= 0.1]
            area = sum(x['sealed'][0] for e in es for x in e['events'])
            door = sum(1 for x in ev if x['pos'][1] - x['size'][1] / 2 < -0.35)
            early = [x for e in es for x in e['events'] if x['sealed'][0] >= 0.1 and x['t'] < min(e['T'], 40)]
            rows.append([record, g, len(es), npl, len(ev), f"{len(ev) / max(1, npl):.3f}", f"{area / max(1, npl):.3f}",
                         f"{door / max(1, len(ev)):.2f}", f"{sum(1 for x in ev if x['standing']) / max(1, len(ev)):.2f}"])
        for e in cen:
            for x in e['events']:
                rung_use[x['arch']] += 1
                if x['sealed'][0] >= 0.1:
                    rung_ev[x['arch']] += 1
                rung_area[x['arch']] += x['sealed'][0]
        for a, n in rung_use.most_common(14):
            rung_rows.append([record, a, n, rung_ev[a], f"{rung_ev[a] / n:.2f}", f"{rung_area[a] / n:.3f}"])
        # the agent's readings on the sealing placements
        ev = [x for e in cen for x in e['events'] if x['sealed'][0] >= 0.1 and 'shade' in x]
        if ev:
            n = len(ev)
            know_rows.append([record, n,
                              sum(1 for x in ev if x['shade'] > 0.15), sum(1 for x in ev if x['shade'] > 0.0),
                              sum(1 for x in ev if x['sealed_added'] > 0.3), sum(1 for x in ev if x['sealed_added'] > 0.0),
                              f"{statistics.median(x['sealed'][0] for x in ev):.2f}", f"{statistics.median(x['shade'] for x in ev):.2f}",
                              f"{statistics.median(x['sealed_added'] for x in ev):.2f}"])
        out[record] = dict(rows=[r for r in rows if r[0] == record])
    md.append('## Census: sealing placements in every episode (class 0.55 x 0.40 x 0.24)\n')
    md.append('A placement *seals* a spot when the spot was level and reachable before it, is still level after it, and '
              'is no longer reachable (exact sweep).  Event = sealed area >= 0.1 m^2.\n')
    md.append(md_table(rows, ['record', 'group', 'episodes', 'placements', 'sealing events', 'events / placement',
                              'sealed m^2 / placement', 'event sealer door-side (y_min < -0.35)', 'standing sealer']))
    md.append('')
    md.append(md_table(rung_rows, ['record', 'rung', 'placements', 'sealing events', 'events / placement', 'sealed m^2 / placement']))
    md.append('')
    md.append("The agent's own readings on the sealing placements: `shade` = `wedge_rl.stack.shade_area` (the C veto fires "
              "above 0.15), `sealed_added` = the ladder's reach_at reading (its floor veto fires above 0.3).\n")
    md.append(md_table(know_rows, ['record', 'events', 'shade > 0.15', 'shade > 0', 'sealed_added > 0.3', 'sealed_added > 0',
                                   'true sealed m^2 (median)', 'shade (median)', 'sealed_added (median)']))
    md.append('')
    data['census'] = dict(rows=rows, rungs=rung_rows, knowledge=know_rows)


def sec_why(md, data):
    rows = []
    for record, scenes in (('gate0-hard2', G_C), ('gate0-hard2-b', G_B)):
        for sc in scenes:
            path = os.path.join(SCRATCH, 'why', record, sc + '.json')
            if not os.path.exists(path):
                continue
            for w in json.load(open(path)):
                if not w['patches_sealed_here']:
                    continue
                a = w.get('action') or {}
                lad = [l for l in w['ladders'] if l['item'] == a.get('item')]
                lad = lad[-1] if lad else None
                for n in w['patches_sealed_here']:
                    key = str(n)
                    n_ok = n_all = 0
                    first = None
                    chosen_open = None
                    if lad:
                        rank = 0
                        for r in lad['rungs']:
                            for c in r['top']:
                                rank += 1
                                s = c['seals'].get(key) or c['seals'].get(n)
                                if s is None:
                                    continue
                                n_all += 1
                                ok = s[0] == 0 or s[1] > 0
                                n_ok += ok
                                if ok and first is None:
                                    first = f"{rank}:{r['name']}"
                    em = [e for e in w['emits'] if e['accepted']]
                    shade = em[-1]['shade'] if em else None
                    ch = (lad or {}).get('chosen') or {}
                    rows.append([sc, w['t'], n, a.get('arch'), w.get('same'), (lad or {}).get('archetype', '-'),
                                 (lad or {}).get('n_survivors', '-'), f"{n_ok}/{n_all}" if lad else '-', first or '-',
                                 ch.get('sealed_added', '-'), shade if shade is not None else '-',
                                 ', '.join(f"{k} {v}" for k, v in sorted(((lad or {}).get('veto_counts') or {}).items(), key=lambda kv: -kv[1])[:3]),
                                 ' > '.join(w['stages']) or '-'])
    md.append('## Decision archaeology at the sealing placements\n')
    md.append('The agent re-run on the recorded board before each sealing placement (`why.py`).  `ladder` = the ladder '
              "decision for the placed item; `leave open` = its listed candidates (top 12 of up to 4 rungs) that leave the "
              "patch reachable; `first open` = rank and rung of the first such candidate in the ladder's order; "
              "`sealed_added` = the ladder's own seal reading of the chosen candidate; `shade` = the shadow gate's reading "
              'of the emitted pose; `same` = the re-run picks the recorded pose.\n')
    md.append(md_table(rows, ['scene', 'seal t', 'patch', 'placed by', 'same', 'ladder rung', 'survivors', 'leave open',
                              'first open', 'sealed_added', 'shade', 'top vetoes', 'stages entered']))
    md.append('')
    data['why'] = rows


def sec_cf(md, data):
    path = os.path.join(SCRATCH, 'cf_near.jsonl')
    if not os.path.exists(path):
        return
    res = [json.loads(l) for l in open(path) if l.strip()]
    data['cf'] = res
    by = collections.defaultdict(list)
    for r in res:
        by[r['scene']].append(r)
    md.append('## Counterfactual rollouts (near misses)\n')
    md.append('Board after t recorded placements, one changed decision, then the shipped agent (analytic board, '
              'shadow in pybullet, deterministic budgets) to its decline.  `agent` rows are the unchanged continuation '
              '(two repeats: the clock noise).\n')
    for sc, rs in by.items():
        thr = rs[0].get('thr')
        rows = []
        for r in sorted(rs, key=lambda r: (-(r.get('t') or 0), r.get('mode', ''), r.get('k') or 0)):
            f = r.get('first') or {}
            note = r.get('note') or {}
            rows.append([r.get('t'), r.get('mode'), r.get('k') if r.get('mode') in ('kth', 'alt', 'alt-noseal') else '',
                         r.get('patch') if r.get('patch') is not None else '', 'yes' if r.get('persistent') else '',
                         f"{f.get('arch')} {f.get('centre')}" if f else 'declined', f.get('seals', ''), f.get('fills', ''),
                         r.get('placed'), r.get('margin'),
                         ('fell back' if note.get('fell_back') else '') + (' sel-unused' if r.get('mode') == 'kth' and 'picked' not in note else '')])
        md.append(f"**{sc}** (threshold {thr}, record placed {rs[0].get('record_placed')})\n")
        md.append(md_table(rows, ['t', 'mode', 'k', 'patch', 'persistent', 'first placement', 'seals', 'fills', 'placed', 'margin', 'note']))
        md.append('')



def sec_cf_summary(md, data):
    path = os.path.join(SCRATCH, 'cf_near.jsonl')
    if not os.path.exists(path):
        return
    res = [json.loads(l) for l in open(path) if l.strip()]
    res = [r for r in res if 'placed' in r]
    res = [r for r in res if not r.get('arm') and not r.get('arm_extra') and not r.get('soft_equal') and r['mode'] != 'first_item']
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in res:
        by[r['scene']][r['t']].append(r)
    rows = []
    for sc in NEAR + sorted(s for s in by if s not in NEAR):
        if sc not in by:
            continue
        rec = 'gate0-hard2' if sc.startswith('c-') else 'gate0-hard2-b'
        tr = load_trace(rec).get(sc)
        seals = {}
        for n, p in enumerate(tr['patches']):
            t = seal_t(p)
            if t is not None:
                seals.setdefault(t, []).append(n)
        for t in sorted(by[sc], reverse=True):
            rs = by[sc][t]
            thr = rs[0]['thr']

            def val(sel):
                v = [r['placed'] for r in rs if sel(r)]
                return '/'.join(str(x) for x in v) if v else ''
            base = val(lambda r: r['mode'] == 'agent')
            ctrl = val(lambda r: r['mode'] in ('kth', 'alt') and r.get('k') in (2, 3, 4))
            nos = val(lambda r: r['mode'] == 'noseal2' and not r.get('persistent'))
            nosp = val(lambda r: r['mode'] == 'noseal2' and r.get('persistent'))
            fil = val(lambda r: r['mode'] == 'fill2')
            dfr = val(lambda r: r['mode'] == 'defer')
            lead = tr['T'] - t
            what = 'seal ' + ','.join(str(n) for n in seals[t]) if t in seals else ''
            best = max(r['placed'] for r in rs)
            rows.append([sc, t, lead, what, thr, base, ctrl, nos, nosp, fil, dfr, 'yes' if best >= thr else ''])
    md.append('## Counterfactual summary (near misses first, then the other G episodes)\n')
    md.append('Placed counts at the end of each branch (several values = several branches or repeats).  '
              '`controls` = the ladder ranks 2-4 and the 2nd-4th distinct poses (`kth`, `alt`); `noseal2` / `fill2` '
              '= every stage barred from sealing / held to filling the patch, for one decision (`persistent`: until the '
              'patch is filled); `defer` = the sealing item taken out of the pool (B).\n')
    md.append(md_table(rows, ['scene', 't', 'lead', 'step', 'threshold', 'agent (repeats)', 'controls', 'noseal2',
                              'noseal2 persistent', 'fill2 (patches)', 'defer', 'some branch crosses']))
    md.append('')
    data['cf_summary'] = rows



def _cf_rows():
    path = os.path.join(SCRATCH, 'cf_near.jsonl')
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


def sec_pool(md, data):
    res = [r for r in _cf_rows() if 'placed' in r]
    by = collections.defaultdict(list)
    for r in res:
        if r['mode'] == 'first_item' and not r.get('arm'):
            by[(r['scene'], r['t'])].append(r)
    if not by:
        return
    rows = []
    for (sc, t), rs in sorted(by.items()):
        ep = ep_of('gate0-hard2-b', sc)
        base = [r['placed'] for r in res if r['scene'] == sc and r['t'] == t and r['mode'] == 'agent' and not r.get('arm') and not r.get('arm_extra') and not r.get('soft_equal')]
        cells = []
        for r in sorted(rs, key=lambda r: r['defer_item']):
            it = ep.byidx[r['defer_item']]
            got = (r.get('note') or {}).get('item_placed')
            tag = ('s' if it['is_soft'] else 'h') + ('p' if it['is_prioritized'] else '')
            cells.append(f"{r['defer_item']}{tag}{'' if got == r['defer_item'] else '>' + str(got)}:{r['placed']}")
        best = max(r['placed'] for r in rs)
        n_cross = sum(1 for r in rs if r['placed'] >= r['thr'])
        rows.append([sc, t, rs[0]['thr'], '/'.join(map(str, base)), ' '.join(cells), best, f"{n_cross}/{len(rs)}"])
    md.append('## Choosing among the pool (B): every pool item tried first\n')
    md.append('`first_item`: the pool item is moved to the front of `pool_order` for that one decision (every stage that walks '
              'the order sees it first; if it gets no pose the agent goes on as usual).  Cell = item index, s/h (soft/hard), p '
              '(priority), `>n` when another item was placed instead, then the final count.\n')
    md.append(md_table(rows, ['scene', 't', 'threshold', 'agent', 'item first: placed', 'best', 'crossing items']))
    md.append('')
    data['pool'] = rows


def sec_seal(md, data):
    res = [r for r in _cf_rows() if 'placed' in r]
    by = collections.defaultdict(dict)
    for r in res:
        if r['scene'].startswith('b-') and r['mode'] == 'agent' and not r.get('arm') and not r.get('soft_equal') and r['t'] > 0:
            by[(r['scene'], r['t'])].setdefault(r.get('arm_extra') or 'agent', []).append(r['placed'])
    rows = []
    for (sc, t), d in sorted(by.items()):
        if not any(k != 'agent' for k in d):
            continue
        thr = next(r['thr'] for r in res if r['scene'] == sc)
        rows.append([sc, t, thr, '/'.join(map(str, d.get('agent', []))),
                     '/'.join(map(str, d.get('seal_check_all_surfaces=true', []))),
                     '/'.join(map(str, d.get('seal_ranks_terraces=true', []))),
                     '/'.join(map(str, d.get('seal_check_all_surfaces=true,seal_ranks_terraces=true', [])))])
    if rows:
        md.append('## Pricing the seal on every surface (B terrace-extension sealing steps)\n')
        md.append('The record arm with the flags appended for the rest of the episode from the sealing step.\n')
        md.append(md_table(rows, ['scene', 't', 'threshold', 'agent', 'seal_check_all_surfaces', 'seal_ranks_terraces', 'both']))
        md.append('')
        data['seal'] = rows


def sec_ship(md, data):
    res = [r for r in _cf_rows() if 'placed' in r]
    rec = {}
    for r in res:
        if not r.get('arm') and not r.get('arm_extra') and not r.get('soft_equal'):
            key = (r['scene'], r['t'], r['mode'], r.get('k'), r.get('patch'), bool(r.get('persistent')), r.get('defer_item'))
            rec.setdefault(key, []).append(r['placed'])
    rows = []
    for r in res:
        if not r.get('arm'):
            continue
        key = (r['scene'], r['t'], r['mode'], r.get('k'), r.get('patch'), bool(r.get('persistent')), r.get('defer_item'))
        rows.append([r['scene'], r['t'], r['mode'] + ('' if r['mode'] == 'agent' else f" k{r.get('k')} p{r.get('patch')}{' pers' if r.get('persistent') else ''}{' item ' + str(r.get('defer_item')) if r.get('defer_item') is not None else ''}"),
                     r['thr'], '/'.join(map(str, rec.get(key, []))), r['placed'], 'yes' if r['placed'] >= r['thr'] else ''])
    if rows:
        rows.sort(key=lambda x: (x[0], -x[1], x[2]))
        md.append('## The rescuing branches on the shipped arm (`arm_ship_c` / `arm_ship_b`)\n')
        md.append('Every branch that reached the threshold on the record arm, and the unchanged continuation at the same step, '
                  're-run with the shipped-form arm from `origin/claude/rl-packing-policy-ftogt3` (9e4ada85, '
                  '`reports/bench/arms/`).\n')
        md.append(md_table(rows, ['scene', 't', 'branch', 'threshold', 'record arm', 'shipped arm', 'crosses (shipped)']))
        md.append('')
        data['ship'] = rows


def sec_soft(md, data):
    res = [r for r in _cf_rows() if 'placed' in r and r['t'] == 0 and r['scene'].startswith('b-')]
    by = collections.defaultdict(dict)
    for r in res:
        k = 'soft_equal' if r.get('soft_equal') else (r.get('arm_extra') or 'agent')
        by[r['scene']][k] = r['placed']
    rows = []
    for sc, d in sorted(by.items()):
        thr = next(r['thr'] for r in res if r['scene'] == sc)
        rec_placed = next(r['record_placed'] for r in res if r['scene'] == sc)
        rows.append([sc, thr, rec_placed, d.get('agent', ''), d.get('soft_first_when_free=true', ''), d.get('soft_equal', '')])
    p = os.path.join(HERE, 'data', 'softtime.json')
    if os.path.exists(p):
        st = {x['scene']: x for x in json.load(open(p))}
        md.append('## The oldest deferred soft box on the B G boards\n')
        md.append(md_table([[x['scene'], x['item'], 'x'.join(map(str, x['dims'])), x['enter'], x['T'], x['first_reach'], x['last_reach'],
                             x['reach_steps'], x['end_soft_share']] for x in st.values()],
                           ['scene', 'item', 'dims', 'in the pool from', 'placements', 'first reachable spot', 'last reachable spot',
                            'prefixes with one', 'end pool soft share']))
        md.append('')
    if rows:
        md.append('## Soft boxes interleaved from the start (B G scenes, whole episodes on the analytic board)\n')
        md.append('`soft_first_when_free`: the shipped flag (off) that lets a soft item go first when its pose costs the hard '
                  'cargo nothing; `soft_equal`: the pool order with soft in the hard bucket (footprint order only).\n')
        md.append(md_table(rows, ['scene', 'threshold', 'record', 'agent (analytic)', 'soft_first_when_free', 'soft_equal']))
        md.append('')
        data['soft'] = rows

if __name__ == "__main__":
    main()
