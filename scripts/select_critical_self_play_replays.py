"""Select learning-critical Self-Play games and build a compact replay gallery."""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.render_self_play_replay import build_payload, render_html


TERMINAL_WEIGHT = {
    "selected_action_failure": 120.0,
    "no_retained_candidate": 80.0,
    "stream_exhausted": 40.0,
}
TERMINAL_REASON = {
    "selected_action_failure": "physical rejection",
    "no_retained_candidate": "candidate exhaustion",
    "stream_exhausted": "stream terminal",
}


def rank_games(entries: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for label, manifest in entries:
        for game_index, game in enumerate(manifest.get("games", [])):
            terminal = str(game.get("terminal_reason", "unknown"))
            violations = float(game.get("new_attribute_violations", 0) or 0)
            ranks = [
                int(record.get("selected_rank", 0) or 0)
                for record in game.get("records", [])
            ]
            max_rank = max(ranks, default=0)
            non_rank0 = int(game.get("non_rank0_action_count", 0))
            captures = list(game.get("captures", []))
            unique = len({
                row.get("board_fingerprint") for row in captures
                if row.get("board_fingerprint")
            })
            novelty = unique / len(captures) if captures else 0.0
            score = (
                TERMINAL_WEIGHT.get(terminal, 0.0)
                + 30.0 * violations
                + 6.0 * max_rank
                + 1.5 * non_rank0
                + 10.0 * novelty
                + 0.1 * int(game.get("handoff_count", 0))
            )
            reasons = []
            if terminal in TERMINAL_REASON:
                reasons.append(TERMINAL_REASON[terminal])
            if violations:
                reasons.append(f"attribute violation +{violations:g}")
            if max_rank:
                reasons.append(f"rank-{max_rank} exploration")
            if novelty:
                reasons.append(f"state novelty {novelty:.0%}")
            rows.append({
                "label": label,
                "case_id": manifest.get("case_id", label),
                "game_index": game_index,
                "critical_score": score,
                "reasons": reasons or ["scenario coverage"],
                "terminal_reason": terminal,
                "new_attribute_violations": violations,
                "max_selected_rank": max_rank,
                "non_rank0_actions": non_rank0,
                "state_novelty": novelty,
            })
    return sorted(
        rows, key=lambda row: (
            -float(row["critical_score"]), str(row["label"]),
            int(row["game_index"]),
        )
    )


def select_diverse(rows: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    if top_k < 1:
        raise ValueError("top_k must be positive")
    selected = []
    seen = set()
    for row in rows:
        if row["label"] not in seen:
            selected.append(row)
            seen.add(row["label"])
    selected = sorted(selected, key=lambda row: -float(row["critical_score"]))[:top_k]
    chosen = {(row["label"], row["game_index"]) for row in selected}
    for row in rows:
        key = (row["label"], row["game_index"])
        if len(selected) >= top_k:
            break
        if key not in chosen:
            selected.append(row)
            chosen.add(key)
    return sorted(selected, key=lambda row: -float(row["critical_score"]))


def _gallery(selected: list[dict[str, Any]]) -> str:
    cards = []
    for rank, row in enumerate(selected, 1):
        filename = row["replay_path"]
        reasons = " · ".join(html.escape(reason) for reason in row["reasons"])
        cards.append(
            f'<a class="card" href="{html.escape(filename)}">'
            f'<b>#{rank} {html.escape(row["case_id"])}</b>'
            f'<span>game {row["game_index"]} · critical {row["critical_score"]:.1f}</span>'
            f'<em>{reasons}</em></a>'
        )
    return """<!doctype html><meta charset="utf-8"><title>Critical Self-Play Replays</title>
<style>body{font:16px system-ui;background:#07111f;color:#eaf2ff;max-width:900px;margin:40px auto;padding:0 20px}h1{color:#51d6ff}.card{display:flex;flex-direction:column;gap:7px;margin:14px 0;padding:18px;border:1px solid #355577;border-radius:14px;background:#10233a;color:inherit;text-decoration:none}.card:hover{border-color:#51d6ff;transform:translateY(-1px)}span{color:#a9bdd4}em{color:#ffd45c}</style>
<h1>Critical Self-Play Replays</h1><p>Learning-relevant events first, with scenario coverage guaranteed.</p>""" + "".join(cards)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    loaded = []
    paths = {}
    for spec in args.manifest:
        label, separator, raw_path = spec.partition("=")
        path = pathlib.Path(raw_path if separator else label)
        if not separator:
            label = path.parent.parent.name
        loaded.append((label, json.loads(path.read_text(encoding="utf-8"))))
        paths[label] = path
    selected = select_diverse(rank_games(loaded), args.top_k)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for rank, row in enumerate(selected, 1):
        filename = f"{rank:02d}-{row['label']}-game-{row['game_index']}.html"
        payload = build_payload(paths[row["label"]], int(row["game_index"]))
        payload["title"] = f"CRITICAL #{rank} · {row['case_id']} · game {row['game_index']}"
        payload["critical"] = {
            "score": row["critical_score"], "reasons": row["reasons"],
        }
        (args.output_dir / filename).write_text(
            render_html(payload), encoding="utf-8"
        )
        row["replay_path"] = filename
    (args.output_dir / "selection.json").write_text(
        json.dumps({"selected": selected}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "index.html").write_text(
        _gallery(selected), encoding="utf-8"
    )
    print(args.output_dir / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
