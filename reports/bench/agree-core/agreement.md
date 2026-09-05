# Analytic model vs official validator: `ladder`

Probes: 5582

| | physics accepts | physics rejects |
|---|---:|---:|
| analytic accepts | 4005 | 10 |
| analytic rejects | 839 | 728 |

False-accept rate (analytic accepts, physics rejects): 0.002
False-reject rate (analytic rejects, physics accepts): 0.535
Agreement: 0.848

## By probe kind

| kind | n | both accept | analytic only | physics only | both reject |
|---|---:|---:|---:|---:|---:|
| chosen | 997 | 995 | 2 | 0 | 0 |
| perturbed | 2991 | 1419 | 5 | 839 | 728 |
| survivor | 1594 | 1591 | 3 | 0 | 0 |

## By analytic reason

| analytic reason | n | physics accepted |
|---|---:|---:|
| centre-of-mass-outside-support | 34 | 31 |
| no-support | 736 | 724 |
| ok | 1424 | 1419 |
| outside-container | 48 | 48 |
| overlaps-main_shelf | 9 | 0 |
| overlaps-packed-item | 295 | 28 |
| overlaps-small_shelf | 1 | 1 |
| settled-pose-outside | 424 | 6 |
| survivor | 2591 | 2586 |
| transport-hits-packed-item | 20 | 1 |
