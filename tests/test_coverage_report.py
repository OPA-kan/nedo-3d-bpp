import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "coverage_report", ROOT / "scripts" / "coverage_report.py"
)
coverage_report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = coverage_report
SPEC.loader.exec_module(coverage_report)


class RegistryIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = coverage_report.load_all()

    def test_every_question_names_a_declared_axis(self) -> None:
        axes = set(self.data["axes"]["axes"])
        for question in self.data["questions"]["questions"]:
            with self.subTest(question=question["id"]):
                self.assertIn(question["axis"], axes)

    def test_every_instrument_varies_a_declared_axis(self) -> None:
        axes = set(self.data["axes"]["axes"])
        for path, spec in self.data["measurements"]["instruments"].items():
            with self.subTest(instrument=path):
                self.assertTrue(spec["varied_axis"])
                for axis in spec["varied_axis"]:
                    self.assertIn(axis, axes)

    def test_registered_instruments_exist_on_disk(self) -> None:
        for path in self.data["measurements"]["instruments"]:
            with self.subTest(instrument=path):
                self.assertTrue(
                    (ROOT / path).is_file(),
                    f"{path} is registered but not present; a registry that "
                    f"points at a script nobody wrote is worse than no "
                    f"registry, because it reads as coverage",
                )

    def test_every_instrument_declares_what_it_cannot_answer(self) -> None:
        """
        The registry exists for `cannot_answer`. An entry without it has
        not been thought through: the failure mode is an instrument whose
        conditioning is invisible in its output, so it reads as answering
        a broader question than it does.
        """
        for path, spec in self.data["measurements"]["instruments"].items():
            with self.subTest(instrument=path):
                self.assertTrue(spec.get("cannot_answer"))
                self.assertTrue(spec.get("conditioned_on"))

    def test_instrument_claims_resolve_to_ledger_entries(self) -> None:
        known = {e["id"] for e in self.data["evidence"]["entries"]}
        for path, spec in self.data["measurements"]["instruments"].items():
            for claim in spec.get("supports", []):
                with self.subTest(instrument=path, claim=claim):
                    self.assertIn(claim, known)

    def test_axis_evidence_resolves_to_ledger_entries(self) -> None:
        known = {e["id"] for e in self.data["evidence"]["entries"]}
        for name, axis in self.data["axes"]["axes"].items():
            for claim in axis.get("evidence", []):
                with self.subTest(axis=name, claim=claim):
                    self.assertIn(claim, known)

    def test_open_questions_state_how_they_would_close(self) -> None:
        for question in self.data["questions"]["questions"]:
            if question["status"] != "open":
                continue
            with self.subTest(question=question["id"]):
                self.assertTrue(question["closure_criteria"])
                self.assertTrue(question["intervention"])
                self.assertTrue(question["required_variation"])

    def test_a_question_with_no_instrument_answers_insufficient(self) -> None:
        """
        The reverse lookup must be able to say 'nothing here can answer
        this'. Silently returning a neighbouring instrument is the
        over-generalisation the registry exists to stop.
        """
        rendered = coverage_report.answer(
            self.data, "item-cap-omits-useful-items"
        )
        self.assertIn("INSUFFICIENT", rendered)
        self.assertIn("Required instrument", rendered)

    def test_zero_knob_axis_raises_a_structural_alarm(self) -> None:
        rows = coverage_report.coverage_rows(self.data)
        by_axis = {row["axis"]: row for row in rows}
        self.assertEqual(by_axis["state_shaping"]["knobs"], 0)
        found = coverage_report.alarms(rows)
        self.assertTrue(
            any("ZERO knobs" in a for a in found),
            "an axis with no knob must be reported: nothing on it can be "
            "varied, so its emptiness is structural rather than a finding",
        )

    def test_item_axis_records_the_cap_as_a_blind_spot(self) -> None:
        """
        MAX_POOL_ITEMS_EVALUATED is a source constant with no override, so
        it is not a knob and must not be counted as one.
        """
        item = self.data["axes"]["axes"]["item"]
        self.assertNotIn(
            "MAX_POOL_ITEMS_EVALUATED",
            " ".join(item["knobs"]),
        )
        self.assertIn(
            "MAX_POOL_ITEMS_EVALUATED",
            " ".join(item["blind_spots"]),
        )


if __name__ == "__main__":
    unittest.main()
