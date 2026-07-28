# Handoff for the next model

Updated: 2026-07-28 JST

## Start here

Repository: https://github.com/OPA-kan/nedo-3d-bpp  
Default branch: `main`  
Current work branch: `agent/context-routing`  
Draft PR: https://github.com/OPA-kan/nedo-3d-bpp/pull/1

Run:

```powershell
python scripts/context.py show handoff
python scripts/context.py list
```

Do not load the entire repository first. Select `agent`, `simulator`, `theory`,
or `experiments`, and add `--full` only when source-level detail is needed.

## User's goal

Build a competitive CPU-first agent for the NEDO airport-baggage constrained
3D bin-packing competition. GitHub is the single source of truth for code,
mathematical reasoning, simulator snapshots, tests, and reproducible reports.
Colab and Google Drive are archives or sources for large derived artifacts,
not the normal execution path.

The original mathematical question is:

> Given baggage subsets that can form useful local geometric structures,
> how should the candidate subset family be generated and selected so that
> the downstream packing objective is maximized?

The current engineering interpretation is on-demand local macro generation,
not exhaustive block enumeration or exact hypergraph optimization.

## What is implemented

- Canonical submission code: `agent/agent.py`
- Official simulator snapshot: `simulator/`
- Geometry contract: `docs/GEOMETRY_RULES.md`
- Offline strategy: `docs/adr/ADR-001-offline-optimization.md`
- Unified formulation: `docs/theory/MATHEMATICAL_MODEL.md`
- CPU unit/report runner: `scripts/run_checks.py`
- Submission builder: `scripts/build_submission.py`
- GitHub Actions unit and manual PyBullet jobs
- Constructive ordering, common-core dry-run, Or-opt/swap, and executable
  two-item subsequence templates
- Physics-aware validation reporting: process exit zero is not enough;
  inclusion, validity, and placed-safely states must all pass

## Current PR

PR #1 adds progressive AI context routing:

- root and scoped `AGENTS.md` files
- short `CONTEXT.md` capsules for agent, simulator, and theory
- `context/manifest.json`
- `scripts/context.py` with summary and explicit `--full` modes
- the user-provided simulator decomposition at
  `docs/simulator/API_REFERENCE.md`
- context path-safety and Windows UTF-8 tests

The production agent is intentionally unchanged in PR #1. The supplied
simulator guide exposed no new binding contract that justified changing
placement behavior.

## Fresh verification evidence

Local command:

```powershell
python scripts/run_checks.py
```

Result on the context branch: 35 tests passed.

Progressive disclosure check:

- simulator summary: about 1,060 characters
- simulator full context: about 82,751 characters

Last corrected GitHub CPU physics run:

https://github.com/OPA-kan/nedo-3d-bpp/actions/runs/30318345750

- Unit tests passed.
- PyBullet simulator completed on Ubuntu CPU.
- Report correctly returned `FAIL (physics validation)`.
- Case 000: fill 11.954775870881182, 7/41 placed.
- Case 001: fill 7.825700311249446, 7/42 placed.
- Both ended with `is_valid=false` and `is_placed_safe=false`.

This red simulator job is a real agent defect, not an Actions infrastructure
failure. The report artifact is uploaded even when physics validation fails.

## Next engineering task

Do not start by changing scores, macros, or the mathematical model. First find
the earliest divergence between the planning geometry and PyBullet:

1. Download the latest simulator artifact and inspect the captured simulator
   output.
2. Identify the first item whose transport, settle, or boundary state becomes
   invalid.
3. Reproduce that transition with the smallest deterministic regression test.
4. Trace it through `simulator/src/ground_handling/env.py`,
   `validator.py`, and `containers.py`.
5. Change `agent/agent.py` only after the mismatch is specific.
6. Run all unit tests, then dispatch the CPU simulator through GitHub Actions.
7. Record the commit SHA, item/case, score, placed count, and physics flags.

Known historical failures include close-distance collisions followed by a
boundary failure after settle. Treat the current Actions artifact as fresher
evidence than the Colab archive.

## Important invariants

- Candidate placement uses container-local coordinates.
- Packed observations and container plane data use world coordinates.
- Local/world conversion changes only the container X offset.
- Shelf geometry is derived from simulator dimensions, not hard-coded.
- Internal boundary guard is 16 mm.
- Transport/lateral clearance is 16 mm.
- Vertical contact with a valid support surface is allowed.
- Settled quaternion determines the subsequent packed-item AABB.
- Soft and priority items are not future support surfaces.
- Single-item neighborhoods remain available when macro neighborhoods exist.
- Block templates are replayed item by item through the common placement core.

## Do not

- Do not edit the official simulator to make the agent pass.
- Do not treat `docs/simulator/API_REFERENCE.md` as exhaustive; it omits
  private methods and branching conditions.
- Do not treat proposed theory as an implemented contract.
- Do not call a physics run successful because the process returned zero.
- Do not make Drive or Colab the code source of truth again.
- Do not commit large model/log artifacts listed in `docs/DRIVE_SOURCES.md`.

## Operational notes

- Windows Python 3.12 cannot readily build PyBullet 3.2.7 without MSVC.
  Use the GitHub Actions Ubuntu CPU simulator job for routine full validation.
- GitHub App PR creation returned 404 for this newly created private repo.
  Authenticated GitHub CLI works and created PR #1.
- `main` currently points to commit `d3986a9`.
- The context-routing implementation commit is `6bc9784`; this handoff is a
  follow-up commit on the same PR branch.

