# Frozen distributional fill fallback confirmation

## Result

**PASS: offline shadow integration is licensed; live ranking is not.**

The policy was frozen before the three target runs. It uses the fill-afterstate
consensus when the packed-only and packed-plus-visible models agree, and falls
back to action geometry otherwise. Training remained fixed to discovery rows
from runs `31722131035`, `31720120600`, `31718231518`, and `31722145273`.

| Seed | Run | Correct | Action geometry | Afterstate use | Paired W/T/L | Non-regression |
|---:|---:|---:|---:|---:|---:|---|
| 46 | `31728653058` | 29/35 | 26/35 | 23/35 | 3/32/0 | yes |
| 47 | `31728655936` | 38/44 | 32/44 | 30/44 | 6/38/0 | yes |
| 48 | `31728659539` | 27/35 | 21/35 | 22/35 | 7/27/1 | yes |
| **Pooled** | - | **94/114** | **79/114** | **75/114** | **16/97/1** | **yes** |

The pooled exact two-sided sign-test p-value is `0.000274658`. Accuracy is
82.5% for the frozen fallback policy and 69.3% for action geometry. Every
target run is non-regressing, and the target IDs exactly match the frozen
policy contract.

## Scope of the claim

This establishes prospective synthetic H3 continuation-value signal across
three new physical seeds. It is enough to build an offline shadow selector and
measure its counterfactual decisions. It does not establish an online feature
source, a live selector, or episode-score improvement. Physical afterstates
used here are available only after simulation/settling, so using them directly
in live ranking would leak future information.
