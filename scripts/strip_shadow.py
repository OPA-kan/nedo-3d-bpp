"""strip_shadow.py <dir> [MINW]: of the free floor cells lying in runs narrower than MINW (either axis), the share under an overhang of an upper box (its footprint covers the cell, nothing on the floor there)."""
import json, glob, sys, pathlib, collections
import numpy as np
sys.path.insert(0, str(pathlib.Path('.').resolve()))
from bench.scenes import make_scene
d = sys.argv[1]; MINW = float(sys.argv[2]) if len(sys.argv) > 2 else 0.30
CELL = 0.01
tot = collections.Counter(); per_arch = collections.Counter()
for f in sorted(glob.glob(d + '/[abc]-*.json')):
    r = json.load(open(f)); sp = r['scene_spec']
    sc = make_scene(sp['seed'], sp['layout'], sp['task'])
    steps = [s for s in r['steps'] if s.get('event') == 'step' and 'pos_local' in s]
    for ci, c in enumerate(sc.containers):
        L, W, t = c['length'], c['width'], c['thickness']
        nx, ny = int(round(L / CELL)), int(round(W / CELL))
        g = np.zeros((nx, ny), dtype=np.int8)   # 0 free, 1 floor box, 2 wall
        over = np.full((nx, ny), -1, dtype=int)  # step index of an upper box covering the cell
        tc = int(round(t / CELL)); cut = int(round((c['cut_x'] + t) / CELL))
        g[:cut, :] = 2; g[-tc:, :] = 2; g[:, :tc] = 2; g[:, -tc:] = 2
        for k, s in enumerate(steps):
            if s['container_idx'] != ci: continue
            x, y, z = s['pos_local']; sx, sy, sz = s['size']
            i0 = int((x - sx/2 + L/2) / CELL); i1 = int(round((x + sx/2 + L/2) / CELL))
            j0 = int((y - sy/2 + W/2) / CELL); j1 = int(round((y + sy/2 + W/2) / CELL))
            sl = (slice(max(i0,0), i1), slice(max(j0,0), j1))
            if z - sz / 2 < 0.06: g[sl] = np.where(g[sl] == 2, 2, 1)
            else: over[sl] = np.where(over[sl] < 0, k, over[sl])
        free = g == 0
        need = int(MINW / CELL)
        narrow = np.zeros_like(free)
        for axis in (0, 1):
            arr = free if axis == 0 else free.T
            mark = np.zeros_like(arr)
            for j in range(arr.shape[1]):
                col = arr[:, j]; i = 0
                while i < len(col):
                    if not col[i]: i += 1; continue
                    i2 = i
                    while i2 < len(col) and col[i2]: i2 += 1
                    if i2 - i < need: mark[i:i2, j] = True
                    i = i2
            narrow |= mark if axis == 0 else mark.T
        strip = narrow & free
        shadow = strip & (over >= 0)
        tot['floor'] += free.sum() + (g == 1).sum(); tot['free'] += free.sum(); tot['strip'] += strip.sum(); tot['shadow'] += shadow.sum()
        for k in np.unique(over[shadow]):
            st = steps[k]; per_arch[st.get('archetype')] += int((shadow & (over == k)).sum())
print(d, 'free/floor %.3f' % (tot['free']/tot['floor']), 'strip/free %.3f' % (tot['strip']/max(tot['free'],1)), 'shadow/strip %.3f' % (tot['shadow']/max(tot['strip'],1)))
print('  overhang owners of the shadowed strip cells:', [(k, round(v/max(tot['shadow'],1),2)) for k, v in per_arch.most_common(6)])
