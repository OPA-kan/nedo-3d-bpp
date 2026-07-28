from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "context" / "manifest.json"


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
