"""lattice.py: the stability lattice re-read. Parses the platform results
table and the refit's bench table, and fits stability = (100/N) * sum over
counted episodes of s_e under candidate N and models of s."""
import re, json, sys, math
import numpy as np
ROOT='/home/user/nedo-3d-bpp/'
plat={}
for line in open(ROOT+'reports/submission/official-results.md'):
    m=re.match(r'\|\s*(v\d+)[^|]*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]*)\s*\|\s*([\d.]*)\s*\|', line)
    if m:
        v=m.group(1); vals=[float(x) if x else None for x in m.groups()[1:]]
        if v in plat and 'first form' in line: continue
        plat[v]=dict(zip(['fill','cog','stab','place','soft','frac','opt','pol'],vals))
bench={}
for line in open(ROOT+'reports/wedge/platform-refit.md'):
    m=re.match(r'\|\s*(v\d+)\s*\|([^|]*)\|'+r'\s*([-\d.]+)\s*\|'*9, line)
    if m:
        v=m.group(1); c=[x.strip() for x in line.split('|')[1:-1]]
        try:
            bench[v]=dict(k=float(c[9]), bfill=float(c[10]), bfrac=float(c[11]), X=c[12], cogc=float(c[13]), softc=float(c[14]), prioc=float(c[15]), top=float(c[16]), ke=float(c[17]))
        except Exception as e:
            pass
# official sample placed counts per build (docs/submission.md: "Official sample: A f / n, B f / n, C f / n")
samp={}
txt=open(ROOT+'docs/submission.md').read()
for m in re.finditer(r'\((v\d+)\):(.*?)(?=\n\n[A-Z][a-z-]+ build|\Z)', txt, re.S):
    v=m.group(1); body=m.group(2)
    s=re.search(r'Official sample:\s*A\s*([\d.]+)\s*/\s*(\d+),\s*B\s*([\d.]+)\s*/\s*(\d+),\s*C\s*([\d.]+)\s*/\s*(\d+)', body)
    if s: samp[v]=dict(A=int(s.group(2)),B=int(s.group(4)),C=int(s.group(6)))
print('platform builds', len(plat), 'bench rows', len(bench), 'sample rows', len(samp))
rows=[]
for v,p in plat.items():
    if p['stab'] is None: continue
    k=round(p['stab']/4.175); step=p['stab']/k
    rows.append((v,p,k,step))
print('\n| build | stab | k (stab/4.175) | stab/k | frac | fill | sample placed A/B/C | bench topples/ep |')
print('|---|---:|---:|---:|---:|---:|---|---:|')
for v,p,k,step in rows:
    sp=samp.get(v); b=bench.get(v)
    print(f"| {v} | {p['stab']:.2f} | {k} ({p['stab']/4.175:.2f}) | {step:.4f} | {p['frac']:.4f} | {p['fill']:.2f} | {sp['A'] if sp else '-'}/{sp['B'] if sp else '-'}/{sp['C'] if sp else '-'} | {b['top'] if b else '-'} |")
# candidate N and the implied constant s
steps=np.array([r[3] for r in rows]); ks=np.array([r[2] for r in rows])
print('\nstep: mean %.4f sd %.4f min %.4f max %.4f (n=%d)'%(steps.mean(),steps.std(),steps.min(),steps.max(),len(steps)))
# exclude v24 outlier and the two builds with known topple residuals (v49, v50)
mask=np.array([r[0] not in ('v24','v49','v50') for r in rows])
print('step without v24/v49/v50: mean %.4f sd %.4f'%(steps[mask].mean(), steps[mask].std()))
print('\n| N | s implied (step*N/100) | per-episode cog/place/soft at v50 (x N/19) | fill per counted ep if gated |')
print('|---|---:|---|---:|')
p50=plat['v50']
for N in range(19,25):
    s=steps[mask].mean()*N/100
    print(f"| {N} | {s:.4f} | {p50['cog']*N/19:.1f} / {p50['place']*N/19:.1f} / {p50['soft']*N/19:.1f} | {p50['fill']*N/19:.1f} |")
# model s = n/(n+1): n from the sample placed means per build (A/B/C mean)
print('\nmodel s = n/(n+1) with n = mean official-sample placed (A,B,C):')
print('| build | n | predicted step at N=23 | N=22 | N=24 | observed |')
print('|---|---:|---:|---:|---:|---:|')
for v,p,k,step in rows:
    sp=samp.get(v)
    if not sp: continue
    n=np.mean([sp['A'],sp['B'],sp['C']]); s=n/(n+1)
    print(f"| {v} | {n:.1f} | {100/23*s:.3f} | {100/22*s:.3f} | {100/24*s:.3f} | {step:.3f} |")
# correlation of step with sample n, with frac, with topples
xs=[];ys=[];zs=[];ts=[]
for v,p,k,step in rows:
    sp=samp.get(v); b=bench.get(v)
    if sp and v not in ('v24',):
        xs.append(np.mean([sp['A'],sp['B'],sp['C']])); ys.append(step); zs.append(p['frac']); ts.append(b['top'] if b else np.nan)
xs=np.array(xs);ys=np.array(ys);zs=np.array(zs);ts=np.array(ts)
print('\ncorr(step, sample n) = %.2f ; corr(step, platform frac) = %.2f'%(np.corrcoef(xs,ys)[0,1], np.corrcoef(zs,ys)[0,1]))
ok=~np.isnan(ts); print('corr(step, bench topples/ep) = %.2f (n=%d)'%(np.corrcoef(ts[ok],ys[ok])[0,1], ok.sum()))
# least squares: step = a + b*topples
A=np.vstack([np.ones(ok.sum()), ts[ok]]).T; coef=np.linalg.lstsq(A, ys[ok], rcond=None)[0]; print('step = %.4f + %.4f * topples/ep'%tuple(coef))
json.dump(dict(plat=plat,bench=bench,samp=samp), open('/tmp/claude-0/-home-user-nedo-3d-bpp/c555f0d0-1382-515f-857e-e77257cc9f93/scratchpad/deep/lattice/data.json','w'), indent=1)
