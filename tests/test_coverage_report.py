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

    def test_reverse_lookup_can_report_insufficient(self) -> None:
        """
        The machinery must be able to say 'nothing here can answer this'.

        Tested against a synthetic registry rather than whichever question
        happens to lack an instrument today: the previous version asserted
        on a real id, and went red the moment that question acquired one --
        an instance assertion pretending to be an invariant, which is the
        same mistake that pinned "the cap is not a knob".
        """
        data = {
            "questions": {"questions": [{
                "id": "synthetic-unanswerable",
                "question": "Is there an instrument for this?",
                "axis": "item",
                "status": "open",
                "priority": "high",
                "observation_unit": "state x item",
                "existing_instruments": [],
                "missing_instrument": "a paired sweep nobody has built",
                "intervention": "build it",
                "required_variation": "two multisets",
                "rationale": "synthetic",
                "closure_criteria": ["build the instrument"],
            }]},
            "measurements": {"instruments": {}},
        }

        rendered = coverage_report.answer(data, "synthetic-unanswerable")

        self.assertIn("INSUFFICIENT", rendered)
        self.assertIn("Required instrument", rendered)
        self.assertIn("a paired sweep nobody has built", rendered)

    def test_open_questions_with_instruments_show_their_limits(self) -> None:
        """
        The other half: when an instrument does exist, the reverse lookup
        must surface what it cannot answer, or it hands back a false
        positive.
        """
        answered = [
            q for q in self.data["questions"]["questions"]
            if q.get("existing_instruments")
        ]
        self.assertTrue(answered)
        for question in answered:
            with self.subTest(question=question["id"]):
                rendered = coverage_report.answer(self.data, question["id"])
                self.assertIn("cannot answer:", rendered)

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

    def test_registries_declare_the_commits_they_were_verified_against(
        self,
    ) -> None:
        """
        The failure this guards actually happened: these registries were
        written against a checkout that predated the env-isation of
        MAX_POOL_ITEMS_EVALUATED, and confidently reported the cap as an
        unvariable constant while another branch had already swept it. A
        reverse-lookup registry is only as current as its checkout, so
        correct machinery over a stale tree emits precise misinformation
        rather than an visible gap.
        """
        for name in ("axes", "measurements", "questions"):
            with self.subTest(registry=name):
                provenance = self.data[name].get("provenance")
                self.assertTrue(provenance, f"{name} has no provenance block")
                merge = provenance["verified_against_merge_of"]
                self.assertTrue(merge["ours"])
                self.assertTrue(merge["theirs"])

    def test_knobs_are_only_things_that_can_actually_be_varied(self) -> None:
        """
        A constant with no override is not a knob. Counting one as a knob
        makes an unexplorable axis look explored, which is the exact
        inversion this registry exists to prevent -- so every declared knob
        must name an environment variable or an enumerated mode.
        """
        import re

        for name, axis in self.data["axes"]["axes"].items():
            for knob in axis["knobs"]:
                with self.subTest(axis=name, knob=knob):
                    self.assertTrue(
                        re.match(r"^[A-Z][A-Z0-9_]+", knob),
                        f"{knob!r} does not name a settable variable",
                    )


if __name__ == "__main__":
    unittest.main()
