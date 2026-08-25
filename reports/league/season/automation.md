# League season automation and spectator contract

The preregistered waves 5–14 are driven as an event chain, not one six-hour
workflow:

```text
teacher collection
  → preference distillation
  → frozen ten-cell title match
  → registry + season ledger + replay publication
  → apply the next preregistered wave
  → next teacher collection
```

Each expensive workflow has a `season_wave` input. An empty value preserves
the old standalone behavior. A non-empty value dispatches the next stage only
after its own required job succeeds. The title-match finalizer is idempotent by
match run ID, commits the generated registry/ledger/replay, and explicitly
dispatches the next collection. At wave 14 it writes the final season summary,
sets `active=false`, and does not dispatch another run.

The state is `reports/league/season/state.json`. If infrastructure interrupts
the chain, resume the current stage with the same wave and recorded upstream
run IDs; re-running the same title-match finalizer cannot append a duplicate
season row.

## Spectator publication

Every season title match uploads `packing-league-room-<run>` as a standalone
static-site artifact. If repository variable `LEAGUE_SPECTATOR_PAGES=true`
and GitHub Pages is configured for Actions, the same site is deployed to
Pages.

The room reuses the self-play replay contracts:

- actual ULD cut profile, shelf plates and dedicated-container rims;
- settled PyBullet item poses rather than commanded targets;
- soft/priority item styling;
- transition-aligned published-rule violation deltas;
- first divergence and preference-switch events.

While served over HTTP it polls the public Actions runs/jobs endpoints every 120
seconds. This is honest **stage/cell-job live coverage**. GitHub Actions does
not expose a still-running episode artifact, so placement-by-placement video
is available only after that cell finishes. True per-placement streaming would
require the runner to publish frames to an external object store or websocket
service and is deliberately not simulated by delayed data.

Spectating remains read-only: frozen-eval observations never alter the teacher
matrix or model settings.
