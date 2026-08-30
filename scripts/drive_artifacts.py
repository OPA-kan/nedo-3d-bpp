"""
CI raw output outlives the store it is kept in -- unless we move it.

`AGENTS.md` states the design plainly: heavy raw data stays in Actions
artifacts, and only compact summaries are committed. It even warns the
reader not to read "not in git" as "not measured". That design is sound,
but it rests on an assumption nobody had checked: that the artifact store
keeps what we put in it.

It does not. None of the 18 workflows calling `actions/upload-artifact`
set `retention-days`, so every one inherits GitHub's 90-day default. The
earliest CI record here is dated 2026-08-02. From late October the raw
traces behind our ablation verdicts start to disappear, one run at a time,
while the compact summaries citing them stay in git forever. An evidence
ledger whose citations resolve to deleted artifacts is worse than one with
no citations at all: it still reads as substantiated.

This script closes that hole. It copies raw run output to Google Drive,
which does not expire, and writes a small `drive.json` pointer next to the
summary. The pointer carries the Drive file id, byte count and SHA-256 of
every archived file, so a later reader can both retrieve the raw data and
prove the copy is the one the summary was computed from.

Uploads are idempotent -- a file whose SHA-256 already matches the Drive
copy is skipped -- so re-running a workflow re-uses the existing objects
instead of duplicating them.

    # in CI, with GOOGLE_SERVICE_ACCOUNT_JSON set
    python3 scripts/drive_artifacts.py upload \
        --source reports/anchor-fallback/downloads \
        --remote anchor-fallback/12345 \
        --pointer reports/anchor-fallback/aggregate/drive.json

    # locally, to pull the raw data back
    python3 scripts/drive_artifacts.py fetch \
        --pointer reports/anchor-fallback/aggregate/drive.json

    # to check that every committed pointer still resolves
    python3 scripts/drive_artifacts.py verify

Authentication is a service account, supplied either as raw JSON in
`GOOGLE_SERVICE_ACCOUNT_JSON` (how CI passes a repository secret) or as a
path in `GOOGLE_APPLICATION_CREDENTIALS`. A service account has no Drive
storage quota of its own, so it cannot be the owner of what it writes: the
destination folder is owned by a human and shared with the service account
as Editor. `docs/DRIVE_ARTIFACTS.md` records the folder and the setup.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
POINTER_NAME = "drive.json"

# Folder "nedo-3d-bpp/ci-artifacts" in the maintainer's Drive. Override with
# NEDO_DRIVE_FOLDER_ID to archive somewhere else without editing this file.
DEFAULT_FOLDER_ID = "1bT3bypRgB-npoF0BS-5pMq62FJnujgtu"

FOLDER_MIME = "application/vnd.google-apps.folder"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Drive rejects a resumable upload that streams in chunks smaller than this.
CHUNK_BYTES = 8 * 1024 * 1024


def sha256_of(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclasses.dataclass
class Entry:
    """One archived file, as recorded in a pointer."""

    path: str
    file_id: str
    bytes: int
    sha256: str

    @classmethod
    def from_json(cls, raw: dict) -> "Entry":
        return cls(
            path=raw["path"],
            file_id=raw["file_id"],
            bytes=raw["bytes"],
            sha256=raw["sha256"],
        )


def build_service():
    """Authenticate and return a Drive client.

    Two credential shapes are accepted, because one of them does not always
    work. A service account owns whatever it creates, and a bare service
    account has no Drive storage quota of its own, so writing into a folder
    shared from a consumer (gmail.com) My Drive can fail with
    `storageQuotaExceeded`. That path is fine against a Workspace shared
    drive, where the drive owns the files. Where it is not, supply an OAuth
    refresh token for a human account instead: the human owns the uploads and
    they count against the 15 GB that account already has.
    """
    try:
        from google.oauth2 import service_account
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise SystemExit(
            "Google API client libraries are missing. Install them with:\n"
            "    python3 -m pip install -r requirements-drive.txt"
        ) from exc

    refresh_token = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN")
    if refresh_token:
        client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
        client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
        if not (client_id and client_secret):
            raise SystemExit(
                "GOOGLE_OAUTH_REFRESH_TOKEN is set, but GOOGLE_OAUTH_CLIENT_ID "
                "and GOOGLE_OAUTH_CLIENT_SECRET are needed to redeem it."
            )
        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES,
        )
        return build(
            "drive", "v3", credentials=credentials, cache_discovery=False
        )

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit(
                "GOOGLE_SERVICE_ACCOUNT_JSON is set but is not valid JSON. "
                "Store the key file's contents verbatim, not a path to it."
            ) from exc
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
    else:
        key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not key_path:
            raise SystemExit(
                "No credentials. Set one of:\n"
                "  GOOGLE_SERVICE_ACCOUNT_JSON     service account key JSON\n"
                "  GOOGLE_APPLICATION_CREDENTIALS  path to that key file\n"
                "  GOOGLE_OAUTH_REFRESH_TOKEN      with CLIENT_ID and "
                "CLIENT_SECRET\n"
                "Setup: docs/DRIVE_ARTIFACTS.md"
            )
        credentials = service_account.Credentials.from_service_account_file(
            key_path, scopes=SCOPES
        )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def root_folder_id() -> str:
    return os.environ.get("NEDO_DRIVE_FOLDER_ID", DEFAULT_FOLDER_ID)


def escape(value: str) -> str:
    """Quote a literal for the Drive query language."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def find_child(service, parent_id: str, name: str, folder: bool) -> dict | None:
    clauses = [
        f"name = '{escape(name)}'",
        f"'{escape(parent_id)}' in parents",
        "trashed = false",
    ]
    if folder:
        clauses.append(f"mimeType = '{FOLDER_MIME}'")
    else:
        clauses.append(f"mimeType != '{FOLDER_MIME}'")
    response = (
        service.files()
        .list(
            q=" and ".join(clauses),
            fields="files(id, name, size, appProperties)",
            pageSize=1,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = response.get("files", [])
    return files[0] if files else None


def ensure_folder(service, parent_id: str, name: str) -> str:
    existing = find_child(service, parent_id, name, folder=True)
    if existing:
        return existing["id"]
    created = (
        service.files()
        .create(
            body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )
    return created["id"]


def resolve_path(service, remote: str, cache: dict[str, str]) -> str:
    """Create (or reuse) the folder chain for a slash-separated remote path."""
    parent = root_folder_id()
    walked = ""
    for part in [p for p in remote.split("/") if p]:
        walked = f"{walked}/{part}"
        if walked not in cache:
            cache[walked] = ensure_folder(service, parent, part)
        parent = cache[walked]
    return parent


def upload_file(
    service, local: pathlib.Path, parent_id: str, digest: str
) -> tuple[str, bool]:
    """Upload one file, or reuse the Drive copy if it already matches.

    Returns the Drive file id and whether bytes were actually transferred.
    """
    from googleapiclient.http import MediaFileUpload

    existing = find_child(service, parent_id, local.name, folder=False)
    if existing and (existing.get("appProperties") or {}).get("sha256") == digest:
        return existing["id"], False

    media = MediaFileUpload(
        str(local),
        mimetype="application/octet-stream",
        chunksize=CHUNK_BYTES,
        resumable=True,
    )
    metadata = {"name": local.name, "appProperties": {"sha256": digest}}
    if existing:
        request = service.files().update(
            fileId=existing["id"],
            body=metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )
    else:
        metadata["parents"] = [parent_id]
        request = service.files().create(
            body=metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )

    response = None
    while response is None:
        _, response = request.next_chunk(num_retries=4)
    return response["id"], True


def collect(sources: list[pathlib.Path]) -> list[tuple[pathlib.Path, str]]:
    """Pair every file under the sources with its path relative to the base.

    The base is the parent of each source, so the source directory's own name
    survives into Drive and two sources cannot collide there.
    """
    found: list[tuple[pathlib.Path, str]] = []
    for source in sources:
        if not source.exists():
            print(f"skipping absent source {source}", file=sys.stderr)
            continue
        files = sorted(p for p in source.rglob("*") if p.is_file())
        for path in files:
            if path.name == POINTER_NAME:
                continue
            found.append((path, path.relative_to(source.parent).as_posix()))
    return found


def record_base(base: pathlib.Path) -> str:
    """Describe the restore root, relative to the repository where possible.

    A pointer that travels with the repository should not carry one machine's
    absolute paths, but an archive step may legitimately run over a directory
    outside the checkout, and that must not crash the upload.
    """
    try:
        return base.relative_to(ROOT).as_posix()
    except ValueError:
        return base.as_posix()


def common_base(sources: list[pathlib.Path]) -> pathlib.Path:
    bases = {source.parent.resolve() for source in sources}
    if len(bases) != 1:
        raise SystemExit(
            "every --source must share one parent directory, because the "
            "pointer records a single base to restore into; got: "
            + ", ".join(sorted(str(b) for b in bases))
        )
    return bases.pop()


def cmd_upload(args: argparse.Namespace) -> int:
    sources = [pathlib.Path(s) for s in args.source]
    payload = collect(sources)
    if not payload:
        print("nothing to archive")
        return 0

    base = common_base(sources)
    total = sum(path.stat().st_size for path, _ in payload)
    print(f"archiving {len(payload)} files ({total / 1048576:.1f} MB)")

    entries: list[Entry] = []
    if args.dry_run:
        for path, rel in payload:
            entries.append(
                Entry(
                    path=rel,
                    file_id="dry-run",
                    bytes=path.stat().st_size,
                    sha256=sha256_of(path),
                )
            )
            print(f"  would upload {args.remote}/{rel}")
        sent = 0
    else:
        service = build_service()
        cache: dict[str, str] = {}
        sent = 0
        for path, rel in payload:
            digest = sha256_of(path)
            folder = pathlib.PurePosixPath(rel).parent.as_posix()
            remote_dir = args.remote if folder == "." else f"{args.remote}/{folder}"
            parent_id = resolve_path(service, remote_dir, cache)
            file_id, transferred = upload_file(service, path, parent_id, digest)
            sent += transferred
            entries.append(
                Entry(
                    path=rel,
                    file_id=file_id,
                    bytes=path.stat().st_size,
                    sha256=digest,
                )
            )
            print(f"  {'sent' if transferred else 'reused'} {rel}")
        print(f"{sent} uploaded, {len(entries) - sent} already present")

    pointer = pathlib.Path(args.pointer)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "version": 1,
        "remote": args.remote,
        "base": record_base(base),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "bytes": total,
        "entries": [dataclasses.asdict(entry) for entry in sorted(
            entries, key=lambda e: e.path
        )],
    }
    pointer.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {pointer}")
    return 0


def load_pointer(path: pathlib.Path) -> tuple[dict, list[Entry]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return document, [Entry.from_json(raw) for raw in document["entries"]]


def cmd_fetch(args: argparse.Namespace) -> int:
    from googleapiclient.http import MediaIoBaseDownload

    pointer = pathlib.Path(args.pointer)
    document, entries = load_pointer(pointer)
    destination = (
        pathlib.Path(args.dest) if args.dest else ROOT / document["base"]
    )
    service = build_service()

    restored = 0
    for entry in entries:
        target = destination / entry.path
        if target.exists() and sha256_of(target) == entry.sha256:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        request = service.files().get_media(
            fileId=entry.file_id, supportsAllDrives=True
        )
        with target.open("wb") as handle:
            downloader = MediaIoBaseDownload(handle, request, chunksize=CHUNK_BYTES)
            done = False
            while not done:
                _, done = downloader.next_chunk(num_retries=4)
        if sha256_of(target) != entry.sha256:
            raise SystemExit(
                f"{target} does not match the SHA-256 recorded in {pointer}. "
                "The Drive copy has been altered; do not treat it as the "
                "input the summary was computed from."
            )
        restored += 1
        print(f"  restored {entry.path}")

    print(f"{restored} restored, {len(entries) - restored} already local")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    if args.pointer:
        pointers = [pathlib.Path(p) for p in args.pointer]
    else:
        pointers = sorted(REPORTS.rglob(POINTER_NAME))
    if not pointers:
        print("no pointers found")
        return 0

    service = build_service()
    broken = 0
    for pointer in pointers:
        document, entries = load_pointer(pointer)
        faults: list[str] = []
        for entry in entries:
            try:
                remote = (
                    service.files()
                    .get(
                        fileId=entry.file_id,
                        fields="id, size, trashed, appProperties",
                        supportsAllDrives=True,
                    )
                    .execute()
                )
            except Exception as exc:  # noqa: BLE001 - report, do not abort
                faults.append(f"{entry.path}: unreachable ({exc})")
                continue
            if remote.get("trashed"):
                faults.append(f"{entry.path}: trashed in Drive")
            elif (remote.get("appProperties") or {}).get("sha256") != entry.sha256:
                faults.append(f"{entry.path}: SHA-256 differs from the pointer")
        rel = pointer.relative_to(ROOT)
        if faults:
            broken += 1
            print(f"FAIL {rel} ({document['remote']})")
            for fault in faults:
                print(f"       {fault}")
        else:
            print(f"ok   {rel} -- {len(entries)} files")

    if broken:
        print(f"\n{broken} of {len(pointers)} pointers no longer resolve")
        return 1
    print(f"\nall {len(pointers)} pointers resolve")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("upload", help="archive raw output to Drive")
    up.add_argument(
        "--source",
        action="append",
        required=True,
        help="directory to archive; repeatable, all sharing one parent",
    )
    up.add_argument(
        "--remote", required=True, help="folder path under the Drive root"
    )
    up.add_argument(
        "--pointer", required=True, help=f"where to write the {POINTER_NAME}"
    )
    up.add_argument(
        "--dry-run",
        action="store_true",
        help="hash and list what would be sent, without contacting Drive",
    )
    up.set_defaults(func=cmd_upload)

    down = sub.add_parser("fetch", help="restore archived output from Drive")
    down.add_argument("--pointer", required=True)
    down.add_argument("--dest", help="restore under this directory instead")
    down.set_defaults(func=cmd_fetch)

    check = sub.add_parser("verify", help="check that pointers still resolve")
    check.add_argument(
        "--pointer",
        action="append",
        help=f"pointer to check; default is every {POINTER_NAME} under reports/",
    )
    check.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
