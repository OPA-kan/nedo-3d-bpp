# Analytic model vs official validator: `ladder`

Probes: 580

| | physics accepts | physics rejects |
|---|---:|---:|
| analytic accepts | 414 | 2 |
| analytic rejects | 81 | 83 |

False-accept rate (analytic accepts, physics rejects): 0.005
False-reject rate (analytic rejects, physics accepts): 0.494
Agreement: 0.857

## By probe kind

| kind | n | both accept | analytic only | physics only | both reject |
|---|---:|---:|---:|---:|---:|
| chosen | 80 | 80 | 0 | 0 | 0 |
| perturbed | 320 | 155 | 1 | 81 | 83 |
| survivor | 180 | 179 | 1 | 0 | 0 |

## By analytic reason

| analytic reason | n | physics accepted |
|---|---:|---:|
| centre-of-mass-outside-support | 4 | 4 |
| no-support | 70 | 69 |
| ok | 156 | 155 |
| outside-container | 5 | 5 |
| overlaps-main_shelf | 3 | 0 |
| overlaps-packed-item | 32 | 2 |
| settled-pose-outside | 47 | 0 |
| survivor | 260 | 259 |
| transport-hits-packed-item | 3 | 1 |
