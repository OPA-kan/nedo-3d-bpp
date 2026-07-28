# Simulator work

最初に `python scripts/context.py show simulator` を読む。

このディレクトリは公式シミュレータの固定スナップショットである。agentの
都合に合わせてvalidatorや物理挙動を変更しない。コンペ配布物の更新を取り込む
場合だけ変更し、差分・由来・バージョンを記録する。

`docs/simulator/API_REFERENCE.md`は自動抽出した公開API索引であり、
内部メソッドを網羅しない。判定ロジックでは必ず実ソースを優先する。

