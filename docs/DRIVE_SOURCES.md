# Google Drive / Colab migration manifest

GitHubを正本とするための移植元一覧。Driveのファイルを実行時依存にはしない。

## 移植済み

| Drive上の項目 | Drive ID | GitHub内の正本・保存先 | 扱い |
|---|---|---|---|
| `agent_v2.py` | `1ERbfmjGdn4e9aI5ksDemNFRcankSIKkc` | `agent/agent.py` | 現在の実装正本 |
| `NEDO.ipynb` | `1oVBcQ3Aa7IO40ZkJIbuESiqRZX3HfjdT` | `archive/colab/NEDO.ipynb` | 実行履歴アーカイブ |
| `NEDO_clean.ipynb` | `1SsHiD2uBeoHQdDdJ-TdK-T3RrpyVTCmh` | 旧作業領域からは移行せず | `NEDO.ipynb`へ統合済みの旧版 |
| `NEDOコンペ/理論` | `1F2rgldwnUj-Aanfk28tWvYG-PJkRAzZiH9nVVC-szWU` | `docs/theory/MATHEMATICAL_MODEL.md` | 重複議論を整理した正本 |
| `simulator_guide.md` | `17hFll5JNSV_Jhnz6Cj1WCTxP41NRT8ot` | `docs/simulator/API_REFERENCE.md` | 公開API索引。物理契約は公式ソースを優先 |
| `simulator.zip` | `1_G7DmKvt2XQmpwCnxNvT-8XfoKmGIjTA` | `simulator/` | 展開済み固定スナップショット |
| `ADR-001-offline-optimization.md` | `1gGHJw8YElUPffZ8rYNyLpYG1NbNVL-ry` | `docs/adr/ADR-001-offline-optimization.md` | 設計判断 |
| `GEOMETRY_RULES.md` | `1oQtKmEEIUKsgUWWp3jA3qHeH_1g7LG0j` | `docs/GEOMETRY_RULES.md` | 幾何契約 |
| `COMPETITION_BASELINE.md` | `15OSpcQGERzL6AGrUmvnL0BHSYVtXexgf` | `docs/COMPETITION_BASELINE.md` | 過去ベースライン |

## Driveに残す大容量・派生データ

以下はコード正本ではなく、学習・分析の派生物である。Gitへ直接コミットしない。

| 項目 | Drive ID | 理由 |
|---|---|---|
| `candidate_log_all.csv` | `1sHq6V8l7Ftk33lrMU9hjHQBntzEXrDW3` | 約25 MBの生成ログ |
| `trial_meta.csv` | `1x939YHfcdPBENRq6J52d3QikQVD338Oz` | 実験メタデータ |
| `lgbm_death_model.joblib` | `1sMb8Rdy8Vv-JDiNCotjZxA9iJP3ZuxQp` | 派生モデル |
| `lgbm_death_features.json` | `1CYUYYIWbu8zB11FR7HCpS8UVF1fBM-8I` | モデル付属情報 |
| `lgbm_ranker_b_step7_v0.joblib` | `1HiaQXlcunJP2yf6ZMZx6qRnZu9wjSCkJ` | 派生モデル |
| `lgbm_ranker_b_step7_features_v0.json` | `1LkcPtpIwi3YGgQwm3ZVM5EHSySyyqRXP` | モデル付属情報 |
| `pct_lite_rollouts_v0` | `1Uu2UiMqsZSAW0GLdT1Au1qiA4pSB9yCb` | rollout群 |
| `pct_lite_rollouts_v1_noprefix_debug` | `1mMbkIx0SdCX19-6WGng4ugs2OUBuQdXo` | デバッグrollout群 |
| `pct_lite_rollouts_v2_step7` | `1FFsEvUDT9bnWT4JYRYSKciTnmMPeTpC` | rollout群 |

必要になった時点で、Drive IDとSHA-256を持つ取得スクリプトまたはGitHub Releaseへ移行する。現在のCPUエージェントはこれらへ依存しない。

## 移行ルール

- Driveから再移植するときは、ファイル名ではなくDrive IDと更新日時で同一性を確認する。
- `agent/agent.py` をDriveへ逆同期して正本を二つにしない。
- Notebookのセルから直接本番コードを編集しない。
- 実行結果は `scripts/run_checks.py` で `reports/latest.*` に生成する。
