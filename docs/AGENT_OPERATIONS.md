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
- 古い結論を再測定で**置き換えた**ら: 旧エントリを `status: superseded` +
  `superseded_by` にし、新エントリを追加する。
- 再測定が置き換えではなく**再現**だったら: `replicates: <id>` を持つ新
  エントリを足し、**両方 active のままにする**。確認済みの結果を
  superseded にすると「元が誤りだった」と読めるうえ、superseded は既定
  ビューから隠れるので、確認そのものが埋もれる。
  これは**記録の仕方**の規則であって、追試が不滅という意味ではない。
  追試もその後は普通のエントリで、さらに新しい測定に置き換えられうる
  (実例: `task-a-bounded128-replicated`)。禁じられているのは
  **自分が再現した相手に superseded されること**だけである。
- **値の書き換えは禁止**(履歴が消える)。初回コミット前の修正は自由だが、
  コミット後は新エントリを足す以外の手段を取らない。
- 並び順はどの利用側にも意味を持たないが、CLIの表示順そのものである。
  **間に挿し込まず末尾に足す。**
- 台帳どうしのマージは加法的に行う(idで和集合を取る)。同じidで内容が違う
  場合は supersession では解けない(supersession は異なる2つのidを要求
  する)。status が進んでいる側を採るか、主張が本当に別物なら片方をリネーム
  する。

`tests/test_context.py` が強制するのは**構造だけ**である。id の一意性、
`status` の値域、`claim`/`source` が空でないこと、`superseded_by` と
`replicates` の参照先が実在すること、replication が active であること。
**値が書き換えられていないことは検出できない**(比較基準が無い)。この規則は
レビューで守るものであって、テストが守ってくれるものではない。

## 1.5 問いからの逆引き(実験を設計する前に)

```bash
python3 scripts/coverage_report.py                      # 軸ごとの被覆と警報
python3 scripts/coverage_report.py --question <id>      # 1つの問いを逆引き
```

順方向(既存ログ → 測れる量 → 次の仮説)で考えない。candidate単位のデータ
しか無ければ、世界全体がcandidate問題に見える。**逆向きに引く**:

    仮説 → 変動させる軸 → 必要な観測単位 → 既存計器で測れるか

- `context/axes.json`: 軸の定義、**振れるノブ**、blind spots。
  **ノブの集合が仮説の集合を定義する。** ノブ0の軸は「重要でない」のではなく
  「実験不能」であり、永遠に空のままになる。環境変数で上書きできない定数は
  ノブではない。blind_spots に理由を書く。
- `context/measurements.json`: 各計器の `conditioned_on` と
  **`cannot_answer`**。後者が本体である。ファイル名は常に実態より広い問いに
  答えているように読める(`measure_anchor_recall` は「配置のoracle」ではなく
  「**capが通した10個の荷物の**配置のoracle」)。
- `context/questions.json`: open questionと `closure_criteria`。
  **状態はclaimに付ける。実装はclaimを閉じない。**
  「class-awareを実装したから済み」は答えではない。

計器が無い問いには「不足」と答えること。隣接する計器で誤魔化さない。
`--question` はその形で返す。

反復を設計するときは**その反復が何の分散を標本しているか**を書く。同一config
を3回回してビット一致なら、それは精密な3標本ではなく
`n_order = 1, n_runtime = 3` であり、runtime noiseが0なら情報量は実質1である。

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
- `--parallel N` で最大N job同時実行。物理replay生成は1プロセス1コア
  なので、`コア数-1` まで(4コア環境なら3)。**同じ出力ディレクトリに
  書くjobは並列にしない。**
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

1. 変更したら `python3 -m unittest discover -s tests`(3.12以上; 正式検証はLinux CI)。
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

## 5.0 計測器を検証するまで、その出力は結論ではない

同じ失敗が2回起きた。どちらも「計器の出力」を「世界の事実」として台帳に
載せ、後から計器の欠陥が見つかって撤回した。

1. **dead-end認定(2026-08-02)**: 生成器の列挙を全数と思い込み「真の詰み」を
   認定。密グリッド対照で16件の反例(`task-c-wall-is-anchor-parameterisation-
   not-the-board` 系列)。
2. **horizon分岐(2026-08-03)**: replayが毎回live policyを再実行しており
   (deadline駆動=負荷依存)、rank間で候補リストが入れ替わっていた。
   「選択価値2–4 placed」を台帳に載せた後で、score列の非単調性から発覚。

規則:

- **新しい計測器・計測経路の最初の出力は draft。** 台帳に載せる前に最低
  ひとつの検証を通す: 決定性チェック(同条件2回で一致するか)、陰性対照
  (信号が無いはずの所で無を返すか)、または独立計器との照合。
  どれを通したかをエントリの `source` か `caveats` に書く。
- 検証前に共有したくなったら、報告の語尾を「計器Xによれば」に固定し、
  台帳エントリには入れない。台帳は「計器を疑い終えた事実」の置き場である。
- 出力の中に**その計器では生成できないはずのパターン**(ソート済みのはずの
  列の非単調、決定的なはずの値の揺れ)が見えたら、それは発見ではなく
  計器のバグである。まず計器を疑う。
- pocket margin が陰性対照で落ちて ranking へ進まなかったのは、この規則が
  機能した例である(§理論文書0.1)。機能させ損ねた上の2件と同じ重みで
  参照すること。

## 5.05 局所の2成分で選択を変えない

公式スコアは6成分だが、ローカル `evaluate()` が返すのは fill と placed の
2つだけである(`OFFICIAL_SCORE_LOG.md` §1)。**cog / stability / placement /
soft はローカルで一度も計算されない。** したがって placed と fill だけで
採否を決めた選択系の変更は、残り4成分に請求書が回っていても見えない。

実例(2026-08-04、death-band gate): ローカル m2-k15 で placed μ22.0→30.6 を
根拠に出荷 ON にしたところ、公式は 35.375→29.959(**−15.3%**)。6成分すべて
低下し、下げ幅の最大は stability −22.4% と cog −20.7% だった。機構は
`Ranker.score` の定義から予測可能だった: gate が意図的に上書きする score は
`+2.0*support +0.35y −0.18*z*mass` で構成されており、**cog と stability を
操舵している唯一の項**である。低スコアの手を選ぶ設計は、その2成分を直接
支払う。

さらに悪いことに、**警告はローカルデータの中に既にあった。** `run_risk_ablation`
の各 run は `shake_response`(env が持つ振動プロキシ)と `final_com_z` を
記録している。m2-k15 の gate 腕は base に対し peak kinetic energy +74%、
max_shift +33%、shifted items +20% だった。私は毎 run これを保存しながら
一度も見なかった。

**ただし shake 自体の分解能は低い(2026-08-04 監査)。** 同一 case・同一 arm の
反復間で、`shake_max_shift` は中央値 22.7%、`shake_peak_kinetic_energy` は
74.6%、`shake_items_shifted` は 42.9% 振れる(20セル)。death-band の差は
それぞれ +10.0% / +15.1% / +1.7% で、**全部が雑音床の内側**だった。
「shake なら止められた」は運であって分解能ではない
(evidence `shake-veto-is-inside-its-own-noise-floor`)。

規則:

- **選択・順序・配分を変える介入の採否には、`shake_response`(最低でも
  `shake_max_shift` と `shake_peak_kinetic_energy`)を placed/fill と並べて
  報告する。** 悪化していれば、placed が伸びていても採用しない。
  ただしこれは**多数のペア run をプールした比較でのみ**成立する。単一 run・
  単一 case の shake 差は読まない。15〜20% 未満の差は n≈25 でも分解できない。
- **より確実なのは、代理で事後検証することではなく、トレードが構造的に
  起きない設計にすることである。** 例: 差し替えを「P_rot が下がり、かつ
  support_ratio が下がらない」という支配条件に限れば、安定性を売って安全を
  買うことが定義上できない。係数もゼロで済む。
- `final_com_z` は補助にとどめる。cog の正規化が非公開なので方向しか読めず、
  実際 m2 では com_z が改善しているのに公式 cog は落ちた。**shake の方が
  当たった。**
- ローカル代理と公式が反対を向いた事例として
  evidence `death-band-official-regression-15pct` を必ず参照すること。

## 5.1 重み付き和へ逃げない

**これはAIが最も踏みやすい穴である。全エージェントに対する明示的な警告として
置く。**

複数の量をどう組み合わせるか分からないとき、\(\alpha A+\beta B+\gamma C\) と
書いて係数を調整したくなる。これは**答えを出したように見えて、未解決の問いを
自由パラメータに変換して隠す操作**である。測定が曖昧だったという事実が、
チューニング可能な係数として消える。

### 実測

このリポジトリは既に3回、同じ穴で失敗している。

- `risk-weighted-kappa-state-value-negative`: 選択肢を生存確率で重み付ける規則を
  3通り（union-bound / max / 独立積）試し、**全部が悪化**した
  （Spearman 0.503 → 0.251 / 0.251 / 0.214）。しかも同エントリが構造的理由を
  書いている: 「エピソードは方策が実際に取ったactionで失敗するのであって、
  選択肢プールの平均安全性で失敗するのではない」。**調整の失敗ではなく形の誤り**
  であり、係数をいくら動かしても届かない。
- `stage-a-calibrated-negative`: 記述子を足して回帰へ入れた結果、
  LOSO MAE が 0.979 → 1.456 と悪化した。
- `TASK_C_BOARD_VALUE.md` 初版の
  \(\Phi=\sum_c w_c\log(1+R_c)+\lambda H-\mu B-\nu U\) には、
  \(\log\) にも総和にも \(\lambda,\mu,\nu\) にも**導出が無かった**。便利だから
  そう書いただけである。

### 規則

自由係数を入れてよいのは、次のどちらかを満たすときだけである。

1. **外部から決まっている。** 既知の分布、物理定数、単位変換。例えば公開7型の
   到着分布 \(p_c\) を使った
   \(\Pr[\text{次の到着物が置けない}]=\sum_c p_c\mathbf 1[\mu_c\le0]\)
   は「重み付き和」ではなく**既知分布上の期待値**で、調整の自由が無い。
2. **事前登録したablationで選ばれた。** `RELEASE_RISK_RERANK_LAMBDA=1.0` と
   `RELEASE_RISK_SLIDE_LAMBDA=0.5` はこちらで、
   `docs/RELEASE_RISK_PROTOCOL.md` の手順に沿って候補値を並べ、
   落ちた側も記録した上で採用されている。**係数を発明したのではなく測って選んだ。**

どちらでもないなら、係数の要らない形を先に試す。

- **順序統計**: \(\min_c\), \(\max_c\), 個数, 指示関数。係数ゼロ。
- **辞書式順序**: 優先順位が明示され、議論の対象になる。係数に埋めると議論できない。
- **各項を別々にshadow計測する**: 合成する前に、どれが効いているのかを確定させる。

### 書くときの一文

新しい合成量を提案するときは、**係数がどこから来たかを式のすぐ隣に書く**。
書けないなら、その量はまだ提案の段階に達していない。

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
- **導出の無い係数で複数の量を足し、調整して先へ進む(§5.1)。**

## 7. この手順書の更新

新しい照会手段・実行手段を足したら、この文書と `AGENTS.md` の該当節を
同じコミットで更新する。手順が現実とずれた瞬間に、エージェントは
高コストな旧手順に戻る。
