# Agent work

最初に `python scripts/context.py show agent` を読む。

詳細が必要な場合だけ、目的に応じて次を読む。

- 幾何・座標・棚・マージン: `docs/GEOMETRY_RULES.md`
- オフライン順序探索: `docs/adr/ADR-001-offline-optimization.md`
- 直近の物理失敗: `reports/github-actions-30317807712.md`
- 実装全体: `python scripts/context.py show agent --full`

`agent/agent.py`が提出コードの唯一の正本である。変更後に
`simulator/agent.py`を手編集せず、`scripts/run_checks.py --simulator`
による同期を使う。少なくとも `python scripts/run_checks.py` を実行する。

