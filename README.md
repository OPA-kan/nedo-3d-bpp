# NEDO constrained 3D BPP

空港手荷物の制約付き3D Bin Packingコンペ用リポジトリです。GitHubをコード・理論・実験結果の正本とし、Google DriveとColabは過去資料の参照元およびアーカイブとして扱います。通常の開発と評価はCPUだけで完結します。

## 正本

- `agent/agent.py`: 提出対象のエージェント実装
- `tests/test_agent.py`: 幾何、順序探索、マクロ探索の回帰テスト
- `simulator/`: 公式PyBulletシミュレーターの固定スナップショット
- `docs/theory/MATHEMATICAL_MODEL.md`: 数学的な根幹と現在の統一定式化
- `docs/adr/`: 採用済み設計判断
- `reports/latest.md`: 最後に実行したCPU検証の要約
- `docs/DRIVE_SOURCES.md`: Drive/Colab移植元と、Git管理しない大容量物の索引

`archive/colab/` は過去の実行履歴を保存するだけで、開発手順の正本ではありません。

## rule-alpha（第1層ルールベース試作）

`rule_alpha/` は、第1層だけを組むルールベースの**独立した試作**です。スコア
改善が目的ではなく、「このルールを入れると実際にどう積むのか」を人が目視して
次の設計議論に入れる状態を作るためのものです。`agent/agent.py`（提出対象の
production policy）には一切触れず、そこにある幾何・搬送・物理ユーティリティを
読み取り専用で再利用します。

```powershell
python -m rule_alpha.runner --out reports/rule_alpha
```

- ルール・分類・画像の読み方・既知の制約: `docs/rule_alpha/README.md`
- 12シナリオの結果一覧と画像: `reports/rule_alpha/report.md`

## CPUで実行

Python 3.12を推奨します。

```powershell
python -m pip install -r requirements.txt
python scripts/run_checks.py
```

公式物理シミュレーターまで実行する場合:

```powershell
python -m pip install -r requirements-simulator.txt
python scripts/run_checks.py --simulator
```

Windows上のPython 3.12では、PyBullet 3.2.7のビルドにMicrosoft
C++ Build Toolsが必要です。常用の物理検証はGitHub Actionsの
`CPU verification`を手動実行し、`run_simulator=true`を選ぶ運用を標準とします。
Ubuntuランナー上でCPUのみを使ってビルド・実行し、結果をartifactとして保存します。

結果は `reports/latest.md` と `reports/latest.json` に出力されます。履歴を残す場合は `--keep-history` を追加します。

## 提出物

```powershell
python scripts/build_submission.py
```

`dist/submission.zip` に、正本の `agent/agent.py` を `agent.py` として格納します。

## 運用ルール

1. エージェント変更と理論上の前提変更は同じPRで対応する。
2. `agent/agent.py` 以外を提出コードの正本にしない。
3. 実験結果はコマンド、Git SHA、CPU情報、結果JSONを伴うレポートとして残す。
4. Colab固有のDriveマウントやセル実行を新しい標準手順にしない。
5. GPUが必要な学習を導入した場合だけ、学習成果物をDrive/GitHub Release等へ分離する。
