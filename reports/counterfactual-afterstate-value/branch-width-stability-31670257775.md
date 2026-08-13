# H3 branch-width label stability

- Actions run: `31670257775`
- Physical H3/B3 graphs completed: 4/4
- Directly comparable and stable: 1/4
- Model work may resume: no

| Target | B3 result |
|---|---|
| source-001 dual-empty step 15 | required depth-1 parent path absent |
| reverse-000 dual-empty step 15 | relation stable (`lower_afterstate_better`) |
| reverse-000 dual-shelf step 15 | required sibling pair absent |
| interleave dual-preloaded step 15 | required depth-1 parent path absent |

Widening the top-B search changed which candidate paths survived. Three B2
error rows are therefore not fixed-label supervised examples under B3. The
next collector must force each preregistered parent path and sibling pair,
then compare wider continuation subtrees from those identical afterstates.
