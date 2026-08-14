# Distributional fill offline shadow model

The serializable model is
`reports/counterfactual-afterstate-value/distributional-fill-shadow-model.json`.
It contains the fixed scales and ridge coefficients learned from discovery
rows in runs `31722131035`, `31720120600`, `31718231518`, and `31722145273`.
The artifact has three named feature contracts: packed afterstate,
packed-plus-visible afterstate, and action geometry.

`scripts/build_distributional_fill_shadow_model.py` can either fit this artifact
from declared training directories or apply it to teacher JSONL without reading
continuation labels. Application returns a stable item choice, whether the
afterstate consensus was used, the action-geometry fallback, and whether the
shadow choice changed the fallback.

## Verification

The artifact was applied label-free to all distributional late rows in the
three unopened confirmation runs. On the 114 fill-directional rows used by the
frozen evaluation, every shadow prediction and every consensus/fallback choice
matched the evaluation output exactly.

| Run | Fill-directional rows | Choices changed from action geometry |
|---:|---:|---:|
| `31728653058` | 35 | 3 |
| `31728655936` | 44 | 6 |
| `31728659539` | 35 | 8 |
| **Total** | **114** | **17** |

After labels were rejoined for evaluation, 16 changed choices corrected an
action-geometry error and one introduced an error. This is the same 16/97/1
paired result recorded by the frozen confirmation gate.

## Runtime boundary

This artifact is an offline shadow selector, not a live agent. Its packed-state
features describe the physical child after placement and settling. A live
selector must first predict those child features from the source state and
candidate action, or execute a bounded simulator. Passing the shadow gate does
not authorize reading post-settle state during live ranking.
