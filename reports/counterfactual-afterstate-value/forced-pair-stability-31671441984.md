# Forced-pair H3 branch-width stability

- Actions run: `31671441984`
- Physical graphs completed: 4/4
- Directly comparable: 4/4
- Stable relations: 2/4
- Model work may resume: no

| Target | B2 | Forced-pair B3 | Result |
|---|---|---|---|
| source-001 dual-empty step 15 | lower better | equal | B2 direction retired |
| reverse-000 dual-empty step 15 | lower better | lower better | stable model error |
| reverse-000 dual-shelf step 15 | lower better | equal | B2 direction retired |
| interleave dual-preloaded step 15 | lower better | lower better | stable model error |

No relation reversed. Two apparent representation errors were caused by B2
continuation under-sampling. The other two remain genuine errors at B3. New
teachers must be collected directly at H3/B3 and must not be pooled with B2
directional targets.
