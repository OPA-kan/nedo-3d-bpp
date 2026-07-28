# Colab migration record — 2026-07-26

This is a historical execution record migrated from
`archive/colab/NEDO.ipynb`. It is not a fresh GitHub Actions run.

## Environment and inputs

- Runtime: Google Colab Linux, Python 3.12
- Physics engine: PyBullet 3.2.7, built from source
- Simulator: Drive `simulator.zip`
- Agent: Drive `agent_v2.py`, 62,400 bytes
- Configuration: `configs/sample_config.json`
- Wall-clock runtime: 207.1009 seconds

## Observed result

The sample run did not complete successfully.

### Case 1

- Items 39, 33, 5, 9, 11, 19, and 20 reached the placement step.
- Item 22 was rejected after collisions:
  - with item 11 at distance 0.0074441 m
  - with item 19 at distance 0.0076364 m
- Item 11 subsequently failed the container boundary check.

### Case 2

- Items 1, 4, 11, 3, 12, 14, and 0 reached the placement step.
- Item 2 was rejected after a collision with item 0 at distance
  0.0097828 m.
- Item 0 subsequently failed the container boundary check.

## Interpretation

The failure is consistent with a mismatch between the planning geometry and
the physics validator near contact and boundary surfaces. It is retained as a
regression reference; the canonical fresh result is `reports/latest.md`.

## Provenance

- Drive notebook ID: `1oVBcQ3Aa7IO40ZkJIbuESiqRZX3HfjdT`
- Drive agent ID: `1ERbfmjGdn4e9aI5ksDemNFRcankSIKkc`
- Notebook execution count for the simulator cell: 21
