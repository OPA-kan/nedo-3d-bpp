# Tilt-margin ablation: rejected

Date: 2026-08-03. Local 4 vCPU, run_queue parallel 3, 3 repeats per cell.
Pre-registered criteria: adopt only if fill recovers >= +3 points with placed non-worse.

| case | arm | placed | fill |
|---|---|---|---|
| c000-k1 | base | [22, 22, 19] | [21.13, 21.13, 17.48] (mean 19.91) |
| c000-k1 | tilt_margin2 | [20, 20, 20] | [11.54, 11.54, 11.54] (mean 11.54) |
| c000-k1 | tilt_margin4 | [21, 20, 20] | [19.81, 21.13, 21.13] (mean 20.69) |
| c001-k1 | base | [20, 21, 21] | [25.37, 26.67, 26.67] (mean 26.24) |
| c001-k1 | tilt_margin2 | [19, 20, 18] | [25.37, 24.86, 19.45] (mean 23.23) |
| c001-k1 | tilt_margin4 | [20, 20, 19] | [25.37, 25.37, 25.37] (mean 25.37) |

The 7.49-point forfeit estimate was a static counterfactual on a fixed
trajectory. The intervention changes the trajectory: items lean against
neighbours as well as walls, so the forfeit is not prevented, and the
narrowed wall band costs placed. Rejected; knob stays at default 0 as a
measured-off arm. See ledger
`tilt-margin-rejected-fill-forfeit-not-recoverable-by-envelope-retreat`.
