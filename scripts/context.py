from __future__ import annotations

import argparse
import ast
import json
import pathlib
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "context" / "manifest.json"
EVIDENCE_PATH = ROOT / "context" / "evidence.json"
DEFAULT_SYMBOL_FILE = "agent/agent.py"


def load_manifest(path: pathlib.Path = MANIFEST_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("version") != 1 or not isinstance(manifest.get("profiles"), dict):
        raise ValueError("unsupported context manifest")
    return manifest


def resolve_repo_path(relative_path: str) -> pathlib.Path:
    candidate = (ROOT / relative_path).resolve()
    try:
        candidate.relative_to(ROOT)
    except ValueError as error:
        raise ValueError(f"context path escapes repository: {relative_path}") from error
    if not candidate.is_file():
        raise FileNotFoundError(f"context file not found: {relative_path}")
    return candidate


def profile_files(
    manifest: dict[str, Any],
    profile_name: str,
    full: bool = False,
) -> list[str]:
    profiles = manifest["profiles"]
    if profile_name not in profiles:
        available = ", ".join(sorted(profiles))
        raise KeyError(f"unknown profile '{profile_name}'; available: {available}")
    profile = profiles[profile_name]
    files = list(profile.get("summary", []))
    if full:
        files.extend(profile.get("details", []))
    return files


def render_profile(
    manifest: dict[str, Any],
    profile_name: str,
    full: bool = False,
) -> str:
    profile = manifest["profiles"][profile_name]
    lines = [
        f"# Context profile: {profile_name}",
        "",
        profile["description"],
        "",
        f"Mode: {'full' if full else 'summary'}",
    ]
    for relative_path in profile_files(manifest, profile_name, full=full):
        path = resolve_repo_path(relative_path)
        lines.extend(
            [
                "",
                f"--- BEGIN {relative_path} ---",
                path.read_text(encoding="utf-8").rstrip(),
                f"--- END {relative_path} ---",
            ]
        )
    return "\n".join(lines) + "\n"


def _symbol_nodes(tree: ast.Module):
    for node in tree.body:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            yield node.name, node
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(
                        child, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ):
                        yield f"{node.name}.{child.name}", child


def list_symbols(relative_path: str = DEFAULT_SYMBOL_FILE) -> list[str]:
    path = resolve_repo_path(relative_path)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        f"{name}\t{node.lineno}-{node.end_lineno}"
        for name, node in _symbol_nodes(tree)
    ]


def extract_symbol(
    symbol: str, relative_path: str = DEFAULT_SYMBOL_FILE
) -> str:
    """
    Pull one function, class, or ``Class.method`` from a source file so a
    reader never has to load the whole module for a local question.
    """
    path = resolve_repo_path(relative_path)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    matches = {name: node for name, node in _symbol_nodes(tree)}
    node = matches.get(symbol)
    if node is None:
        suggestions = [name for name in matches if symbol in name]
        hint = (
            f"; close matches: {', '.join(sorted(suggestions)[:8])}"
            if suggestions
            else ""
        )
        raise KeyError(
            f"symbol '{symbol}' not found in {relative_path}{hint}"
        )
    lines = source.splitlines()
    start = node.lineno
    if node.decorator_list:
        start = min(dec.lineno for dec in node.decorator_list)
    segment = "\n".join(lines[start - 1: node.end_lineno])
    header = f"# {relative_path}:{start}-{node.end_lineno} {symbol}"
    return f"{header}\n{segment}\n"


def load_evidence(path: pathlib.Path = EVIDENCE_PATH) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("version") != 1 or not isinstance(
        payload.get("entries"), list
    ):
        raise ValueError("unsupported evidence ledger")
    return payload["entries"]


def render_evidence(
    entries: list[dict[str, Any]],
    topic: str | None = None,
    include_inactive: bool = False,
) -> str:
    lines = []
    for entry in entries:
        if topic is not None and entry.get("topic") != topic:
            continue
        status = entry.get("status", "active")
        if status != "active" and not include_inactive:
            continue
        lines.append(
            f"[{entry['id']}] ({entry.get('topic')}, {status}, "
            f"{entry.get('date')})"
        )
        lines.append(f"  {entry['claim']}")
        if entry.get("values"):
            lines.append(f"  values: {entry['values']}")
        if entry.get("source"):
            lines.append(f"  source: {entry['source']}")
        if entry.get("superseded_by"):
            lines.append(f"  superseded_by: {entry['superseded_by']}")
        lines.append("")
    if not lines:
        scope = f"topic '{topic}'" if topic else "ledger"
        return f"no active evidence for {scope}\n"
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Return only the repository context needed for one task area."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List available context profiles.")

    for command, help_text in (
        ("show", "Print the selected context."),
        ("files", "Print only the selected context file paths."),
    ):
        command_parser = subparsers.add_parser(command, help=help_text)
        command_parser.add_argument("profile")
        command_parser.add_argument(
            "--full",
            action="store_true",
            help="Include detailed source material in addition to the short summary.",
        )

    symbol_parser = subparsers.add_parser(
        "symbol",
        help=(
            "Print one function/class/Class.method from a source file "
            "instead of loading the whole module."
        ),
    )
    symbol_parser.add_argument(
        "name",
        nargs="?",
        help="Symbol name; omit with --list to enumerate symbols.",
    )
    symbol_parser.add_argument(
        "--file",
        default=DEFAULT_SYMBOL_FILE,
        help=f"Repository-relative source file (default {DEFAULT_SYMBOL_FILE}).",
    )
    symbol_parser.add_argument(
        "--list",
        action="store_true",
        help="List symbols and line ranges instead of printing source.",
    )

    evidence_parser = subparsers.add_parser(
        "evidence",
        help="Print the machine-readable ledger of measured facts.",
    )
    evidence_parser.add_argument(
        "--topic", help="Filter to one topic (e.g. risk, ranker, coverage)."
    )
    evidence_parser.add_argument(
        "--all",
        action="store_true",
        help="Include superseded and historical entries.",
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    manifest = load_manifest()

    if args.command == "list":
        for name, profile in manifest["profiles"].items():
            print(f"{name}\t{profile['description']}")
        return 0

    if args.command == "symbol":
        try:
            if args.list or not args.name:
                print("\n".join(list_symbols(args.file)))
            else:
                print(extract_symbol(args.name, args.file), end="")
        except (KeyError, FileNotFoundError, ValueError) as error:
            raise SystemExit(str(error)) from error
        return 0

    if args.command == "evidence":
        try:
            entries = load_evidence()
        except FileNotFoundError as error:
            raise SystemExit(str(error)) from error
        print(
            render_evidence(
                entries, topic=args.topic, include_inactive=args.all
            ),
            end="",
        )
        return 0

    try:
        files = profile_files(manifest, args.profile, full=args.full)
    except KeyError as error:
        raise SystemExit(str(error)) from error

    if args.command == "files":
        print("\n".join(files))
    else:
        print(render_profile(manifest, args.profile, full=args.full), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
