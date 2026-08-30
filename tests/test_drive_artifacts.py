import argparse
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
import unittest.mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "drive_artifacts", ROOT / "scripts" / "drive_artifacts.py"
)
drive_artifacts = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = drive_artifacts
SPEC.loader.exec_module(drive_artifacts)

ACTION = ROOT / ".github" / "actions" / "archive-to-drive" / "action.yml"
WORKFLOWS = ROOT / ".github" / "workflows"

# Consumes artifacts produced elsewhere; it creates no raw output of
# its own, so there is nothing for it to archive.
NOT_A_PRODUCER = {"print-artifact.yml"}


class CollectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        run = self.base / "downloads" / "b000-k15-base-r0"
        run.mkdir(parents=True)
        (run / "rows.jsonl").write_text("{}\n", encoding="utf-8")
        (run / "policy-trace.jsonl").write_text("{}\n", encoding="utf-8")

    def test_relative_paths_keep_the_source_directory_name(self) -> None:
        found = drive_artifacts.collect([self.base / "downloads"])
        self.assertEqual(
            sorted(rel for _, rel in found),
            [
                "downloads/b000-k15-base-r0/policy-trace.jsonl",
                "downloads/b000-k15-base-r0/rows.jsonl",
            ],
        )

    def test_an_existing_pointer_is_never_archived_into_itself(self) -> None:
        target = self.base / "downloads" / drive_artifacts.POINTER_NAME
        target.write_text("{}", encoding="utf-8")
        found = drive_artifacts.collect([self.base / "downloads"])
        self.assertNotIn(
            drive_artifacts.POINTER_NAME, [rel.split("/")[-1] for _, rel in found]
        )

    def test_an_absent_source_is_skipped_rather_than_fatal(self) -> None:
        # Archive steps run under `if: always()`, so a cancelled job reaches
        # them with the output directory never created.
        self.assertEqual(drive_artifacts.collect([self.base / "nope"]), [])

    def test_sources_with_different_parents_are_refused(self) -> None:
        # The pointer records one base to restore into, so two parents would
        # make `fetch` write files to the wrong place.
        with self.assertRaises(SystemExit):
            drive_artifacts.common_base(
                [self.base / "downloads", self.base / "downloads" / "b000-k15-base-r0"]
            )


class QueryEscapeTests(unittest.TestCase):
    def test_apostrophes_cannot_terminate_a_query_literal(self) -> None:
        self.assertEqual(drive_artifacts.escape("b000's run"), "b000\\'s run")

    def test_backslashes_are_escaped_before_quotes(self) -> None:
        self.assertEqual(drive_artifacts.escape("a\\'b"), "a\\\\\\'b")


class PointerTests(unittest.TestCase):
    def test_dry_run_writes_a_pointer_that_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            base = pathlib.Path(name)
            source = base / "aggregate"
            source.mkdir()
            (source / "rows.jsonl").write_text('{"placed": 21}\n', encoding="utf-8")
            pointer = base / "drive.json"

            code = drive_artifacts.cmd_upload(
                argparse.Namespace(
                    source=[str(source)],
                    remote="anchor-fallback/123",
                    pointer=str(pointer),
                    dry_run=True,
                )
            )

            self.assertEqual(code, 0)
            document, entries = drive_artifacts.load_pointer(pointer)
            self.assertEqual(document["remote"], "anchor-fallback/123")
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].path, "aggregate/rows.jsonl")
            # The digest is what lets a reader prove the archived bytes are
            # the ones the committed summary was computed from.
            self.assertEqual(len(entries[0].sha256), 64)
            self.assertEqual(entries[0].bytes, 15)

    def test_nothing_to_archive_is_success_and_writes_no_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            pointer = pathlib.Path(name) / "drive.json"
            code = drive_artifacts.cmd_upload(
                argparse.Namespace(
                    source=[str(pathlib.Path(name) / "absent")],
                    remote="x/1",
                    pointer=str(pointer),
                    dry_run=True,
                )
            )
            self.assertEqual(code, 0)
            self.assertFalse(pointer.exists())

    def test_entries_are_sorted_so_reruns_produce_a_readable_diff(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            base = pathlib.Path(name)
            source = base / "aggregate"
            source.mkdir()
            for leaf in ("zeta.json", "alpha.json", "mid.json"):
                (source / leaf).write_text("{}", encoding="utf-8")
            pointer = base / "drive.json"
            drive_artifacts.cmd_upload(
                argparse.Namespace(
                    source=[str(source)],
                    remote="x/1",
                    pointer=str(pointer),
                    dry_run=True,
                )
            )
            paths = [e["path"] for e in json.loads(pointer.read_text())["entries"]]
            self.assertEqual(paths, sorted(paths))


class ArchiveActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = ACTION.read_text(encoding="utf-8")

    def test_a_missing_secret_skips_instead_of_failing_the_run(self) -> None:
        # The action is wired into every ablation workflow. If it failed hard
        # on a repository without the secret, adding it would turn all of CI
        # red rather than leaving archival switched off.
        self.assertIn('if [ -z "${GOOGLE_SERVICE_ACCOUNT_JSON}" ]; then', self.text)
        self.assertIn("::notice::", self.text)

    def test_inputs_reach_the_shell_through_the_environment(self) -> None:
        # Interpolating ${{ inputs.* }} into the script body would let a value
        # containing shell syntax execute on the runner.
        self.assertIn("ARCHIVE_SOURCE: ${{ inputs.source }}", self.text)
        self.assertNotIn("--remote \"${{ inputs.remote }}\"", self.text)

    def test_the_pointer_is_only_committed_when_it_was_written(self) -> None:
        self.assertIn("inputs.commit == 'true' && inputs.credentials != ''", self.text)


class FakeFiles:
    """The slice of the Drive files() API these tests exercise."""

    def __init__(self, existing=None):
        self.existing = list(existing or [])
        self.created = []
        self.queries = []

    def _result(self, value):
        holder = unittest.mock.MagicMock()
        holder.execute.return_value = value
        return holder

    def list(self, *, q, **_):
        self.queries.append(q)
        for item in self.existing:
            if f"name = '{item['name']}'" in q and f"'{item['parent']}' in parents" in q:
                is_folder = "mimeType = 'application/vnd.google-apps.folder'" in q
                if is_folder == item["folder"]:
                    return self._result({"files": [item]})
        return self._result({"files": []})

    def create(self, *, body, **_):
        record = {
            "id": f"id-{len(self.created)}",
            "name": body["name"],
            "parent": (body.get("parents") or [None])[0],
            "folder": body.get("mimeType") == drive_artifacts.FOLDER_MIME,
            "appProperties": body.get("appProperties", {}),
        }
        self.created.append(record)
        self.existing.append(record)
        return self._result({"id": record["id"]})


class FakeService:
    def __init__(self, existing=None):
        self._files = FakeFiles(existing)

    def files(self):
        return self._files


class FolderResolutionTests(unittest.TestCase):
    def test_a_remote_path_creates_each_folder_once(self) -> None:
        service = FakeService()
        cache: dict[str, str] = {}
        first = drive_artifacts.resolve_path(service, "task-c/12345/case-000", cache)
        names = [c["name"] for c in service.files().created]
        self.assertEqual(names, ["task-c", "12345", "case-000"])

        # A second file in the same folder must reuse the cache, not re-create
        # the chain -- 300 files in one run would otherwise be 900 API calls.
        again = drive_artifacts.resolve_path(service, "task-c/12345/case-000", cache)
        self.assertEqual(first, again)
        self.assertEqual(len(service.files().created), 3)

    def test_an_existing_folder_is_reused_rather_than_duplicated(self) -> None:
        root = drive_artifacts.root_folder_id()
        service = FakeService(
            [{"id": "existing", "name": "task-c", "parent": root, "folder": True}]
        )
        resolved = drive_artifacts.resolve_path(service, "task-c", {})
        self.assertEqual(resolved, "existing")
        self.assertEqual(service.files().created, [])

    def test_the_lookup_separates_folders_from_files(self) -> None:
        # Without the mimeType clause a run directory and a file of the same
        # name would be indistinguishable.
        service = FakeService()
        drive_artifacts.find_child(service, "parent", "rows.jsonl", folder=False)
        self.assertIn(
            "mimeType != 'application/vnd.google-apps.folder'",
            service.files().queries[-1],
        )


class UploadReuseTests(unittest.TestCase):
    def test_an_unchanged_file_is_not_uploaded_again(self) -> None:
        # Re-running a workflow must not re-send gigabytes that Drive already
        # holds, nor create a second copy beside the first.
        service = FakeService(
            [{
                "id": "already-there",
                "name": "rows.jsonl",
                "parent": "folder",
                "folder": False,
                "appProperties": {"sha256": "abc"},
            }]
        )
        file_id, transferred = drive_artifacts.upload_file(
            service, pathlib.Path("rows.jsonl"), "folder", "abc"
        )
        self.assertEqual(file_id, "already-there")
        self.assertFalse(transferred)


class WorkflowCoverageTests(unittest.TestCase):
    """Every workflow that produces raw output must also archive it.

    Actions artifacts are deleted after 90 days. A workflow that uploads an
    artifact and stops there is writing its raw measurement onto a timer,
    which is precisely the failure this archive step exists to prevent.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.files = {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(WORKFLOWS.glob("*.yml"))
        }

    def test_every_producer_archives_to_drive(self) -> None:
        for name, text in self.files.items():
            if name in NOT_A_PRODUCER or "upload-artifact" not in text:
                continue
            with self.subTest(workflow=name):
                self.assertIn("./.github/actions/archive-to-drive", text)

    def test_every_archive_step_survives_a_cancelled_job(self) -> None:
        for name, text in self.files.items():
            if "archive-to-drive" not in text:
                continue
            with self.subTest(workflow=name):
                head = text[: text.index("uses: ./.github/actions/archive-to-drive")]
                self.assertTrue(head.rstrip().endswith("if: always()"))

    def test_every_archive_step_is_given_the_secret(self) -> None:
        for name, text in self.files.items():
            if "archive-to-drive" not in text:
                continue
            with self.subTest(workflow=name):
                self.assertIn(
                    "credentials: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}", text
                )

    def test_a_committing_job_is_granted_contents_write(self) -> None:
        # The pointer commit pushes. Without the grant the push returns 403
        # and turns a job red whose measurement had already succeeded.
        for name, text in self.files.items():
            if 'commit: "true"' not in text:
                continue
            with self.subTest(workflow=name):
                self.assertIn("contents: write", text)


if __name__ == "__main__":
    unittest.main()
