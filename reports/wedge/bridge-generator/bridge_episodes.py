"""bridge_episodes.py <base_dir> <new_dir>: the episodes of <new_dir> with a
plateau-merge or bridge-slide placement -- step, pose, placed and topples
against the base -- and the topples of every changed episode."""
import glob, json, os, sys


def load(d):
    out = {}
    for f in glob.glob(os.path.join(d, '[abc]-*.json')):
        r = json.load(open(f)); out[r['scene']] = r
    return out


base, new = load(sys.argv[1]), load(sys.argv[2])
tb = tn = 0
for s in sorted(new):
    r = new[s]; b = base.get(s)
    if b is None:
        continue
    mb, mn = b['metrics'], r['metrics']
    tb += mb.get('shake_topples', 0); tn += mn.get('shake_topples', 0)
    br = [st for st in r['steps'] if st.get('archetype') in ('plateau-merge', 'bridge-slide')]
    if br:
        desc = '; '.join(f"step {st['step']} {st['archetype']} z {st.get('pos_local', [0, 0, 0])[2]:.2f} "
                         f"size {st.get('size')} safe {st.get('is_placed_safe')}" for st in br)
        print(f"{s}: placed {mb['placed_count']} -> {mn['placed_count']}, topples "
              f"{mb.get('shake_topples', 0)} -> {mn.get('shake_topples', 0)}; {desc}")
print('topples total', tb, '->', tn)
