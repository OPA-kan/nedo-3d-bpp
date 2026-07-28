# AI context router

このリポジトリでは、最初から全資料を読み込まない。作業対象に合う
context profileだけを段階的に取得する。

## 開始手順

1. `python scripts/context.py list` でprofileを確認する。
2. `python scripts/context.py show <profile>` で短い文脈だけ読む。
3. 実装判断に詳細が必要になった場合だけ `--full` を付ける。
4. 複数領域を変更する場合も、関係するprofileだけを個別に読む。

新しいモデルは最初に `handoff` を使う。主要profileは `agent`、
`simulator`、`theory`。実験結果を扱う場合は `experiments`、全体の入口には
`overview` を使う。

## 情報の優先順位

矛盾がある場合は、次の順で扱う。

1. 実行中の公式シミュレータソースと設定
2. 自動テストで固定された契約
3. `docs/GEOMETRY_RULES.md` とAccepted ADR
4. 各領域の `CONTEXT.md`
5. 自動抽出API索引
6. Proposedな理論、過去レポート、Colabアーカイブ

理論資料は探索設計の根拠だが、採用済みADRまたはテストへ反映されるまで
実装契約ではない。過去の成功・失敗レポートも現在の結果として扱わない。

## 更新規則

- agent APIや幾何契約を変えたら `agent/CONTEXT.md` も更新する。
- simulatorスナップショットを変えたら `simulator/CONTEXT.md` とAPI索引を確認する。
- 数学モデルの状態を変えたら `docs/theory/CONTEXT.md` で
  Proposed / Accepted / Implementedを明示する。
- `context/manifest.json`には短い入口と詳細資料を分けて登録する。
- agent変更後は `python scripts/run_checks.py` を実行する。
