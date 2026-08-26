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
match run ID and commits the generated registry/ledger/replay. At wave 14 it
writes the final season summary and sets `active=false`.

**Wave application is the monitor session's job, not CI's**: applying the
next preregistered wave edits the collection/learning workflow files, and
the Actions token cannot push `.github/workflows` changes (this is what
broke the first wave-7 finalizer pushes). After a finalizer's ledger push
lands, the monitor session runs `apply_season_wave.py --wave <state.wave>`,
runs the workflow tests, and pushes; that push starts the next collection
via the collection workflow's own push trigger.

The state is `reports/league/season/state.json`. If infrastructure interrupts
the chain, resume the current stage with the same wave and recorded upstream
run IDs; re-running the same title-match finalizer cannot append a duplicate
season row.

After any manual recovery, merge or status edit, run exactly one local check:

```text
python scripts/league_season_status.py
```

It verifies the current round/wave against the preregistered plan, the state
champion against the registry, and both collection/learning matrices and their
count guards against each other. This replaces the old multi-file visual
inspection; normal successful rounds require no manual update at all.

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
