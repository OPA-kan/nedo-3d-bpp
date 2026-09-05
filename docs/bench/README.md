# bench — 測定基盤

`bench/` は、積み付け方策を公式シミュレーター上で比較するための測定基盤です。
目的は「二つの方策を、同じシーンで、同じ終端量で、固定仕事量のもとで比べ、
解析モデルの判定を公式判定と突き合わせる」ことに限ります。スコアは定義しません。

```bash
.venv312/bin/python -m bench scenes  --suite core                       # シーン一覧
.venv312/bin/python -m bench run     --arm ladder --suite core --out reports/bench/ladder-core
.venv312/bin/python -m bench run     --arm ladder --suite core --out reports/bench/ladder-core-repeat
.venv312/bin/python -m bench compare reports/bench/ladder-core reports/bench/ladder-core-repeat \
                                     --out reports/bench/ladder-core-control.md   # 負の対照
.venv312/bin/python -m bench agree   --arm ladder --suite core --out reports/bench/agree-core
.venv312/bin/python -m unittest tests.test_bench
```

シミュレーターは Python 3.12 が必要です（`requirements-simulator.txt`）。

## 1. シーン（`bench/scenes.py`）

シーンは seed とレイアウトと課題で一意に決まります。同じ seed は同じ荷物列を返すので、
二つの腕は必ず同じ入力を見ます。

| 要素 | 内容 |
|---|---|
| 荷物 | 公式 `sample_config.json` の 7 SKU を、そこでの出現頻度で抽出。寸法・質量・摩擦・剛性も SKU ごとに公式値 |
| priority | 各荷物に 4/41 の確率で付与（soft なら soft+priority） |
| レイアウト | `c1` 棚なし1台、`c1s` 棚あり1台、`c2` 棚あり+棚なし2台、`c2p` priority 専用（棚あり）+ 通常 2台 |
| 荷物数 | 1台 41 個、2台 82 個 |
| 課題 | `A` は optimize あり・pool 1、`B` は optimize なし・pool 10、`C` は optimize なし・pool 1 |
| pool 補充 | `max_space = 1`（sample_config と同じ。1 個取るたびに補充） |

課題の違いは公式 `EvaluationApp.run` の流れに従います。`optimize()` が呼ばれるのは A だけです。
rule-alpha のこれまでの数値（task 000 で 24/41 など）は manifest を渡した A の流れで測られています。
C では manifest が渡らないので、同じ規則でも結果は変わります。`smoke` と `smoke-a` を比べると
その差が読めます。

既配置荷物ありの初期状態は未対応です（生成には物理で settle した合法配置が要り、別途作ります）。

## 2. 終端量（`bench/metrics.py`）

すべて PyBullet の settle 後の状態から読みます。計画側の意図は使いません。

| 量 | 意味 |
|---|---|
| `placed_count`, `placed_fraction` | 積めた個数と割合 |
| `fill_volume` | 積んだ箱体積 ÷ 有効容積。包含判定なし |
| `fill_evaluator_shipped` | 公式評価器の fill、`inclusion_margin = -0.005`（配布設定） |
| `fill_evaluator_tolerant` | 同じ評価器で `+0.005`。壁際・床際で落ちる荷物の影響を分離するため |
| `com_z_above_floor_ratio` | 質量加重の重心高さを床基準でコンテナ高さで割ったもの |
| `priority_covered`, `soft_covered` | 上に異属性の荷物が接している priority / soft の個数（公開規則の写し） |
| `priority_misrouted` | priority 専用コンテナがあるのに通常コンテナへ入った priority の個数 |
| `shake_*` | 重力を 0.3 g 傾けて 4 方向に揺らしたときの平均・最大移動、転倒数、運動エネルギー最大値。状態は復元する |
| `policy_time_max`, `over_budget_steps` | 1 手の最大時間と、8 秒を超えた手数。**強制はしない** |
| `end_reason` | `stream-exhausted` / `declined` / `inclusion` / `transport` / `settle` / `format` / `max-steps` |

三つの fill を並べる理由は、配布設定の margin 符号では settle 後に境界へ寄った荷物が
体積から落ちるためです。どれを使ったかを常に記録します。どれも公式スコアではありません。

## 3. 対比較（`bench/compare.py`）

同じ suite の二つの run をシーン名で対にし、各量について B − A の対差、平均、
平均のブートストラップ 95 % 区間、改善・同値・悪化のシーン数を出します。
区間が 0 を含めば `evidence = none` です。動いたシーン数だけでは証拠にしません。

両側が同じ腕なら、手順が一手ずつ同一かを判定します（負の対照）。
bench や planner を変えたら、まずこれを通してから比較を信じます。

## 4. 解析判定と公式判定の一致（`bench/agreement.py`）

各決定で、rule-alpha の veto を生き残った候補（`Decision.survivors`）から数個と、
その候補を数 cm ずらしたり浮かせたりした摂動候補を作り、
解析 `validate()` と公式の包含・搬入・settle を両方に掛けます。
状態は `saveState` / `restoreState` で戻すので、エピソード本体は変わりません。

出力は 2×2 の混同行列と、解析側の拒否理由ごとの物理受理数です。

- 解析受理・物理拒否 = 計画側の過信（これが 0 でないなら解析モデル上の比較は信用できない）
- 解析拒否・物理受理 = 解析モデルが禁じているが競技では通る置き方（候補生成が捨てている領域）

## 4b. 解析モデルでの同じエピソード（`bench/analytic.py`）

`run --sim analytic` は、同じシーン・同じ腕を rule-alpha の解析モデル（`validate`、搬入掃引、静的安定）
の上で走らせ、物理と同じスキーマの記録を出します。物理でしか出ない量（評価器 fill、揺れ）は
省きます。学習ループは解析モデルの上で回すので、物理の run と `compare` で並べ、
シーン単位で終端量が追随するか、先頭何手まで同じ配置を選ぶか（`common_prefix`）を確かめます。

注意点として、解析エピソードは物理の 1.5〜2 倍しか速くありません。1 手あたりの時間の大半は
rule-alpha の計画（候補生成と特徴量）で、PyBullet の settle ではないからです。
反事実ラベルのための rollout は、この計画コストで見積もる必要があります。

## 5. 腕（`bench/arms.py`）

`ladder` は rule-alpha の配布設定そのままです。`ladder@field=value,...` で
`RuleAlphaConfig` の項目を上書きできます（例: `ladder@layer2_family_quota=48`）。
新しい方策は `make_arm` に登録します。

## 6. 出力

`reports/bench/<label>/` に、シーンごとの JSON（終端量、各手の記録、settle 後の配置）と
`summary.md` / `summary.json`。`agree` はさらに `agreement.md` / `agreement.json`。

## 7. 既知の制約

- policy の時間制限は計測のみで、超過しても打ち切りません。壁時計依存の結果を作らないためです。評価環境（4 vCPU）での 8 秒は別のゲートとして読みます。
- policy が `None` を返すと `declined` で終了します。公式ではランダム行動が入って失敗します。
- 揺れ試験は公開されていない公式手順の代理で、蓋は無く、強度・時間も推定です。方向の比較にだけ使います。
- 1 エピソードは 30〜90 秒、probe は 1 件 0.3 秒程度です。
