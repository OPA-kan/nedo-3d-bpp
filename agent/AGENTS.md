# Agent work

最初に `python scripts/context.py show agent` を読む。

詳細が必要な場合だけ、目的に応じて次を読む。

- 幾何・座標・棚・マージン: `docs/GEOMETRY_RULES.md`
- オフライン順序探索: `docs/adr/ADR-001-offline-optimization.md`
- 現在の物理失敗: `HANDOFF.md` の `Established by evidence`。
  release候補のsettle転倒であり、搬入衝突ではない。
  `reports/github-actions-30317807712.md` は2026-07-28時点の
  搬入衝突を記録した過去レポートで、現在の失敗ではない。
- 候補単位の物理ラベル: `python scripts/context.py show replay-dataset`
- 実装全体: `python scripts/context.py show agent --full`

`agent/agent.py`が提出コードの唯一の正本である。変更後に
`simulator/agent.py`を手編集せず、`scripts/run_checks.py --simulator`
による同期を使う。少なくとも `python scripts/run_checks.py` を実行する。

