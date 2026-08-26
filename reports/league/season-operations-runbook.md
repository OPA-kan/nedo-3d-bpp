# Season operations runbook (for the Codex session)

Goal: the season — including **generation promotion** — runs with zero
Claude involvement. Promotion itself is already CI's decision
(`evaluate_league.py --promote-on-pass` inside the title match; the
finalizer commits the registry, ledger, replay and advances
`season/state.json`; challenger names resolve automatically from
`names.json`). The ONLY thing CI cannot do is push workflow-file edits
(GITHUB_TOKEN restriction), so each round needs exactly **one session
action**: the wave turnover below.

## The round turnover (one action per round)

Trigger condition: `reports/league/season/state.json` shows
`stage=collecting` for wave N, but no collection run for wave N exists
yet (the finalizer of round N-1 just landed its ledger commit).

1. `git pull`, then run in order:
   - `python scripts/apply_season_wave.py --wave <state.wave>`
   - workflow tests:
     `python -m pytest tests/test_terminal_rollout_hard_state_workflow.py tests/test_rollout_geometry_policy_workflow.py tests/test_league_season_status.py -q`
   - `python scripts/league_season_status.py` (must be ok:true)
2. Commit **with `[skip ci]` in the commit title** and push. The skip
   marker matters: it suppresses the push-triggered collection run,
   which would start WITHOUT `season_wave` and break the chain at
   collection→learning (that is exactly what happened to wave 8).
3. Check Actions that no collection run for wave N already exists
   (Codex/Claude race guard), then dispatch
   `terminal-rollout-hard-state.yml` on `work/terminal-rollout-oracle`
   with `season_wave=<N>` (max_steps/rollout_max_steps defaults).

That is all. With `season_wave` set, the chain self-continues:
collection → (chain step) preference distillation → (chain step) title
match → gate verdict → registry promotion or rejection → ledger/replay
commit → state advances to wave N+1 → back to step 1 next round.

## Recovery matrix (only on failure or >60 min stall)

Always re-fetch Actions immediately before any dispatch and do nothing
if the stage's run already exists. Resume the CURRENT stage with the
SAME wave and the run ids recorded in `state.json`/the run inputs —
never a reseeded substitute, and never a re-run of a stage whose
verdict already exists.

| broken stage | resume action |
|---|---|
| collection failed | investigate, fix, re-dispatch collection with the same `season_wave` |
| collection ok, no learning after 60 min | dispatch `rollout-geometry-policy-learning.yml` with `source_run_id=<collection run>`, `collection_run_id=<collection run>`, `season_wave=<N>` |
| learning ok, no title match after 60 min | dispatch `league-match.yml` with `policy=learned`, `mode=challenge`, `challenger_name=<from learning run name or pi{gen+1}-pref-w{N}>`, `model_run_id=<learning run>`, `model_artifact=rollout-policy-model`, `collection_run_id=<collection run>`, `season_wave=<N>` |
| title match failed AFTER its verdict printed | do NOT re-run the match: reconstruct the ledger deterministically from the run's own `league-result-<run>` artifact via `league_season.py finish` with the recorded run ids, commit from the session (precedent and exact commands: the wave-7 recovery, `coordination-status-20260826.md` addendum + commit "Season wave 7: record title match; move wave application out of CI") |
| title match failed BEFORE episodes finished | fix, re-dispatch once with identical inputs |

Record every recovery and every duplicate frozen-eval execution in the
match report / coordination notes (look accounting).

## Promotion rules (sessions never decide)

- The gate verdict inside the title match run is the ONLY promotion
  authority. Sessions transcribe it; they never override, soften, or
  re-judge it — a rejected challenger stays rejected, a promoted one
  is champion the moment the ledger commit lands.
- Names are preregistered (`names.json`, waves 5-14). No renames, no
  new names without a registry entry.
- Wave 14's finalizer sets `active=false` and writes the season
  summary. After that: no more turnovers; leave season-2 design to a
  human-reviewed design record.

## Boundaries and coexistence

- Never modify: frozen eval variants, `waves.json` plan entries,
  dominance/gate parameters, teacher matrices beyond
  `apply_season_wave.py` output.
- No tuning of anything from league or spectator results (read-only
  contract).
- Diversity Cups (`cup-hosting-runbook.md`) coexist but the season has
  runner priority: do not dispatch a cup while a season collection or
  title match is queued.
- The claude.ai spectator artifact stays Claude-published; the
  repository `reports/league/spectator/site/` is committed by CI each
  round and is the durable room (enable GitHub Pages +
  `LEAGUE_SPECTATOR_PAGES=true` for a self-updating public URL if
  desired).
- Claude remains backstop: it intervenes only when a stage has been
  stalled for over ~2 hours AND a fresh Actions listing still shows no
  progress — same race guard in both directions.
