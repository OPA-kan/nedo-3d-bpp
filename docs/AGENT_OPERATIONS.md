# AI運用手順書 — 最小コンテクストで正しく作業する

対象: このリポジトリで作業する全AIエージェント。
`AGENTS.md`(開始手順)の**続き**であり、日々の作業ループの規則を定める。
迷ったらこの文書の順序に従う。

## 0. 原則

1. **読む前に引く。** ファイルを開くのは、引く手段が無いときだけ。
2. **導出しない、照会する。** 測定済みの事実は evidence 台帳にある。
   会話やHANDOFFの散文から再構築しない。
3. **1起動=1通知。** 複数の実験・生成ジョブを1つずつ起動しない。
   計画ファイルに書いて `run_queue` に渡す。
4. **生ログをgitとコンテクストに載せない。** ログは `reports/raw/`、
   コミットするのは要約と指標のみ。

## 1. 事実の照会(コードを読む前に)

```bash
python3 scripts/context.py evidence --topic risk      # 測定済み事実(activeのみ)
python3 scripts/context.py evidence --topic residual-capacity
python3 scripts/context.py evidence --all             # superseded/historical込み
```

- topic: `ranker` / `preview` / `search` / `coverage` / `risk` /
  `protocol` / `residual-capacity` / `historical`
- 各エントリは `status`(active / superseded / historical)を持つ。
  **superseded と historical は現在の根拠に使わない。**
- 古い結論を再測定で置き換えたら: 旧エントリを `status: superseded` +
  `superseded_by` にし、新エントリを追加する。**値の書き換えは禁止**
  (履歴が消える)。整合性は `tests/test_context.py` が強制する。

## 2. コードの参照(モジュールを開く前に)

```bash
python3 scripts/context.py symbol --list                    # agent.pyの索引
python3 scripts/context.py symbol PlacementCore.choose      # 関数1個だけ
python3 scripts/context.py symbol rerank_sweep --file scripts/evaluate_release_risk.py
```

- `agent/agent.py`(4,400行)を丸読みしない。まず `--list` で当たりを
  付け、`symbol` で該当関数だけ取る。
- 編集時も同じ: `symbol` で現状を取得 → 該当範囲だけ Edit する。
- 横断的な変更(定数改名など)だけ grep を使う。

## 3. 実験・生成の実行

単発ジョブでも計画ファイルを書く癖をつける。再開可能性がタダで付く。

```bash
cat > /tmp/plan.json <<'PLAN'
{
  "name": "replay-gen-20260801",
  "jobs": [
    {"id": "b000-k15-late",
     "command": ["python3", "scripts/build_replay_dataset.py",
                 "--case", "b000-k15", "--steps", "13", "14",
                 "--per-stratum", "8", "--risk-gate-mode", "shadow",
                 "--split", "development"],
     "env": {"RELEASE_RISK_SHADOW_RERANK": "1",
             "RELEASE_RISK_RERANK_LAMBDA": "1.0"},
     "timeout_seconds": 1800}
  ]
}
PLAN
python3 scripts/run_queue.py /tmp/plan.json
```

- 成功済みジョブは再実行時にスキップされる(`--no-resume` で無効化)。
- 失敗してもキューは続行(`--stop-on-failure` で停止)。
- ログ: `reports/raw/queue/<plan名>/<job id>.log`、
  状態: 同 `state.json`。**キュー完了後はstateの要約だけ読む。**
- 長時間キューはバックグラウンドで1回起動し、完了通知まで**ポーリング
  しない**。

## 4. データセットとsplitの規律

- 生成時は必ず `--split` を指定する
  (`development` / `validation` / `final_holdout`)。
  割当は `docs/RELEASE_RISK_PROTOCOL.md` §3.1 が正本。
- **final_holdout は開かない。** 分析ツールは manifest の split を見て
  自動でスキップする。`--open-final-holdout` は§7の一度きりの最終評価
  以外で渡してはならない。
- 率を読むときは必ず `sampling_weight` で再重み付けされた値を使う
  (行は不等確率標本)。
- 既存データセットの一覧・状態は各 `manifest.json` を読む。
  candidates JSONL を目視で開かない(分析スクリプトに読ませる)。

## 5. 検証と記録

1. 変更したら `python3 -m unittest discover -s tests`(3.12必須)。
2. agent変更なら `python3 scripts/run_checks.py`。
   レポートは `reports/latest.{json,md}` に**要約+末尾30行のみ**、
   生ログは `reports/raw/*.log`(gitignore済み・CIアーティファクト)。
3. 新しい測定結果が出たら:
   - レポートを `reports/replay-analysis/` 等に書く(全文をチャットや
     コミットメッセージへ貼らない。要点数値のみ引用)
   - **evidence台帳にエントリを追加**(§1の規則)
   - 結論の言い方は保守的に: 単一分割の数値より LOSO+CI、
     「同定完了」ではなく「信号あり・係数未確定」のように書く
4. コミットは論理単位で。データセット追加はrunごとで良いが、
   キュー一括生成なら1コミットにまとめる。

## 6. してはいけないこと(実例由来)

- `main` を読む(48+コミット遅れ)。live trunkは
  `experiment/anchor-recall-oracle`。
- `agent.py` / `tests/test_agent.py` の丸読み。
- 大きなレポート・較正表の `cat` 全文表示。ファイルに書いて要点だけ言う。
- ジョブを1個ずつ起動して通知往復を重ねる(§3を使う)。
- `selected_*` 混同行列をgate全体のprecision/recallとして読む。
- exit 0 を成功と読む(物理3フラグが全てtrueで初めて成功)。
- superseded/historical なevidenceを現在の根拠に使う。
- final_holdout を「ちょっと確認」で開く。

## 7. この手順書の更新

新しい照会手段・実行手段を足したら、この文書と `AGENTS.md` の該当節を
同じコミットで更新する。手順が現実とずれた瞬間に、エージェントは
高コストな旧手順に戻る。
