# Verification reports

`python scripts/run_checks.py` がCPUテスト結果を `latest.md` と `latest.json` に保存します。

`--simulator` を付けると公式PyBulletシミュレーターも実行し、評価JSONを同じレポートへ含めます。`--keep-history` を付けた場合だけ、タイムスタンプ付き履歴を `history/` に保存します。

