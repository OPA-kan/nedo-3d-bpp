# GitHub Actions CPU simulator report — run 30317807712

- Repository: `OPA-kan/nedo-3d-bpp`
- Commit: `7b2b4853df393c3d715f578a48b6abc0a55cf660`
- Environment: Ubuntu 24.04, Python 3.12.13, x86_64 CPU
- Unit tests: process passed in 4.815 seconds
- Simulator: process completed in 198.404 seconds
- Overall physical result: failed

## Case 000

- Fill score: 11.954775870881182
- Placed fraction: 0.17073170731707318 (7/41)
- Included: true
- Valid: false
- Placed safely: false
- Offline optimization: 149.544 seconds
- Online policy maximum: 3.078 seconds

## Case 001

- Fill score: 7.825700311249446
- Placed fraction: 0.16666666666666666 (7/42)
- Included: true
- Valid: false
- Placed safely: false
- Offline optimization: 0 seconds
- Online policy maximum: 6.546 seconds

## Conclusion

The Colab-free CPU execution path works. The current agent does not yet pass
the simulator's physical validity and post-placement safety checks. This run
also exposed a reporting defect: a zero process exit code had been labeled
`PASS` even when `is_valid` or `is_placed_safe` was false. The report runner
was updated after this run to make those conditions fail the verification.

Run URL:
https://github.com/OPA-kan/nedo-3d-bpp/actions/runs/30317807712
