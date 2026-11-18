"""Phase 0 tests: one per node, end to end on the seeded set and the clean twin,
plus the P0-C3 additions (ground truth, normalization, evidence schema, stable
IDs, zero capacity, unknown cable unit).

The classifier is always the recorded or fake client, never a live model.
Run from the repo root:  python -m pytest -q
"""

# Future (P0-C3): fixtures for more panel types and for drawing sets exported from other drafting tools.

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import submittal_review as sr

FIX = Path(__file__).parent / "fixtures"
SEEDED, CLEAN, MALFORMED = FIX / "seeded", FIX / "clean", FIX / "malformed"
RESPONSES = FIX / "recorded_responses.json"


def labels(folder: Path) -> dict:
    return json.loads((folder / "error_labels.json").read_text(encoding="utf-8"))


def run_until(folder: Path, last: int, client=None) -> dict:
    """Run nodes N1..N<last> directly, the same order the graph uses."""
    client = client or sr.RecordedResponseClient(RESPONSES)
    state: dict = {"submittal_folder_path": str(folder)}
    steps = [sr.n1_ingest, sr.n2_validate, sr.n3_extract, sr.n4_cross_reference, sr.n5_rule_checks,
             sr.n6_gather_context, lambda s: sr.n7_classify(s, client), sr.n8_order]
    for step in steps[:last]:
        state.update(step(state))
    return state


# ---- one test per node ------------------------------------------------------

def test_n1_ingest_locates_the_three_files():
    out = sr.n1_ingest({"submittal_folder_path": str(SEEDED)})
    assert Path(out["drawing_pdf_path"]).name == "drawings.pdf"
    assert Path(out["points_list_path"]).name == "points.xlsx"
    assert Path(out["sequence_path"]).name == "sequence.txt"


def test_n2_validate_accepts_seeded_set():
    v = run_until(SEEDED, 2)["validated_sources"]
    assert (v.pdf_page_count, v.points_row_count, v.sequence_line_count) == (12, 10, 7)


def test_n2_validate_names_page_and_column_on_malformed_set():
    state = sr.n1_ingest({"submittal_folder_path": str(MALFORMED)})
    with pytest.raises(ValueError) as err:
        sr.n2_validate(state)
    assert "drawings.pdf page 2: no text layer" in str(err.value)
    assert "missing required column 'terminal'" in str(err.value)


def test_n3_extract_matches_generator_ground_truth():
    truth = json.loads((SEEDED / "extraction_truth.json").read_text(encoding="utf-8"))
    state = run_until(SEEDED, 3)
    got = [{"sheet_number": s.sheet_number, "title": s.title, "pdf_page_number_1based": s.pdf_page_number_1based,
            "tags": s.tags, "cables": [{"cable_id": c.cable_id, "length_value": c.length_value} for c in s.cables]}
           for s in state["sheet_records"]]
    assert got == truth["sheets"]
    assert [{"sheet_number": e.sheet_number, "title": e.title} for e in state["index_entries"]] == truth["index_entries"]
    assert len(state["points_list_records"]) == truth["points_row_count"]
    assert [t.tag_raw for t in state["sequence_tags"]] == truth["sequence_tags"]


def test_n3_keeps_pdf_page_and_sheet_number_distinct():
    sheets = run_until(SEEDED, 3)["sheet_records"]
    io102 = next(s for s in sheets if s.sheet_number == "IO-102")
    assert io102.pdf_page_number_1based == 10
    assert io102.io_points[0].location.sheet_number == "IO-102"
    assert io102.io_points[0].location.pdf_page_number_1based == 10


def test_n4_cross_reference_lists_every_place_a_tag_appears():
    xref = run_until(SEEDED, 4)["cross_reference_table"]
    assert sorted({e.document for e in xref["AHU-01-SAT"]}) == ["DRAWINGS", "POINTS", "SEQUENCE"]
    assert {e.document for e in xref["AHU-02-SAT"]} == {"DRAWINGS", "POINTS"}
    assert [e.document for e in xref["AHU-01-OAT"]] == ["SEQUENCE"]


def test_n5_rule_checks_find_exactly_the_seeded_and_expected_candidates():
    found = {f.finding_id for f in run_until(SEEDED, 5)["suspected_findings"]}
    lab = labels(SEEDED)
    expected = {e["finding_id"] for e in lab["seeded_errors"]} | {e["finding_id"] for e in lab["expected_other_verdicts"]}
    assert found == expected


def test_n5_clean_twin_only_raises_the_non_error_candidates():
    found = {f.finding_id for f in run_until(CLEAN, 5)["suspected_findings"]}
    assert found == {e["finding_id"] for e in labels(CLEAN)["expected_other_verdicts"]}


def test_n5_evidence_fits_each_rule():
    by_id = {f.finding_id: f for f in run_until(SEEDED, 5)["suspected_findings"]}
    r1 = by_id["R1:AHU-02-SAT:MISSING_FROM_SEQUENCE"].evidence
    absence = [e for e in r1 if e.role == "absence"]
    assert absence and absence[0].searched_scope and absence[0].quotation is None  # absence is never a made-up quote
    r2 = by_id["R2:CP-01:AI-02:TYPE_MISMATCH"].evidence
    assert len([e for e in r2 if e.quotation]) == 2
    r3 = by_id["R3:CP-02:DO"].evidence[0]
    assert r3.role == "calculation" and r3.computed_value == 0.0 and r3.numeric_inputs["reserved"] == 3
    r4 = by_id["R4:IO-102:TITLE_MISMATCH"].evidence
    assert [e.role for e in r4] == ["left", "right"]
    r5 = by_id["R5:CBL-001"].evidence
    assert r5[-1].role == "calculation" and r5[-1].computed_value == pytest.approx(15.59, abs=0.01)


def test_n6_gather_context_adds_typical_and_index_sheets():
    ctx = {c.finding.finding_id: c for c in run_until(SEEDED, 6)["findings_with_context"]}
    sheets = {r.sheet_number: r.why_included for r in ctx["R1:AHU-02-SAT:MISSING_FROM_SEQUENCE"].related_sheets}
    assert sheets["G-001"] == "evidence" and sheets["T-201"] == "typical"
    assert "G-001" in {r.sheet_number for r in ctx["R5:CBL-001"].related_sheets}


class CountingClient:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def classify(self, item, prompt=""):
        self.calls += 1
        return json.dumps({"verdict": "unresolved", "supporting_quote": None, "reason": "fake"})


def test_n7_classify_uses_the_injected_client_once_per_finding():
    client = CountingClient()
    state = run_until(SEEDED, 7, client)
    assert client.calls == 7
    assert all(c.verdict == "unresolved" and c.model_attempt_count == 1 for c in state["classified_findings"])


def test_n7_skips_the_model_when_a_rule_could_not_compute():
    finding = sr.SuspectedFinding(finding_id="R3:CP-09:AI:UNKNOWN_CAPACITY", rule_id="R3", affected_entity_key="CP-09:AI",
                                  evidence=[], candidate_reason=f"{sr.UNRESOLVED_INPUT}: zero or unknown AI capacity")
    client = CountingClient()
    out = sr.n7_classify({"findings_with_context": [sr.FindingWithContext(finding=finding, related_sheets=[])]}, client)
    assert client.calls == 0 and out["classified_findings"][0].verdict == "unresolved"


def test_n8_order_groups_by_rule_then_sheet():
    state = run_until(SEEDED, 8)
    assert [c.rule_id for c in state["ordered_comments"]] == ["R1", "R2", "R3", "R4", "R5"]
    assert all(c.suggested_fix for c in state["ordered_comments"])
    assert [c.finding.finding_id for c in state["convention_findings"]] == ["R5:CBL-102"]
    assert [c.finding.finding_id for c in state["unresolved_findings"]] == ["R1:AHU-01-OAT:NO_SCOPE"]


def test_n9_report_writes_text_csv_and_log(tmp_path):
    state = run_until(SEEDED, 8)
    state["output_folder_path"] = str(tmp_path / "run_test")
    state["run_metadata"] = sr.RunMetadata(run_id="run_test", started_at="t", input_folder=str(SEEDED),
                                           output_run_folder=str(tmp_path / "run_test"), classifier_name="recorded")
    out = sr.n9_report(state)["review_outputs"]
    text = Path(out.report_txt_path).read_text(encoding="utf-8")
    assert "REAL ERRORS (5)" in text and "DRAFTING CONVENTIONS (1)" in text and "UNRESOLVED (1)" in text
    assert len(Path(out.report_csv_path).read_text(encoding="utf-8").strip().splitlines()) == 1 + 5 + 1 + 1
    assert "run_id: run_test" in Path(out.run_log_path).read_text(encoding="utf-8")


# ---- end to end through the compiled LangGraph graph -----------------------

def test_end_to_end_seeded_catches_every_seeded_error(tmp_path):
    result = sr.run_review(SEEDED, tmp_path, sr.RecordedResponseClient(RESPONSES))
    issued = {c.finding_id for c in result["ordered_comments"]}
    assert issued == {e["finding_id"] for e in labels(SEEDED)["seeded_errors"]}
    assert all(c.cited_sheets and c.evidence_lines for c in result["ordered_comments"])
    assert Path(result["review_outputs"].report_txt_path).is_file()


def test_end_to_end_clean_twin_issues_no_comments(tmp_path):
    result = sr.run_review(CLEAN, tmp_path, sr.RecordedResponseClient(RESPONSES))
    assert result["ordered_comments"] == []


def test_runs_never_overwrite_and_ids_are_stable(tmp_path):
    a = sr.run_review(SEEDED, tmp_path, sr.RecordedResponseClient(RESPONSES))
    b = sr.run_review(SEEDED, tmp_path, sr.RecordedResponseClient(RESPONSES))
    assert a["output_folder_path"] != b["output_folder_path"]
    assert [f.finding_id for f in a["suspected_findings"]] == [f.finding_id for f in b["suspected_findings"]]


def test_output_inside_input_is_refused():
    with pytest.raises(ValueError):
        sr.run_review(SEEDED, SEEDED / "out", sr.RecordedResponseClient(RESPONSES))


# ---- P0-C3 additions ----------------------------------------------------------

@pytest.mark.parametrize("raw, key", [
    ("  ahu-01-sat ", "AHU-01-SAT"),
    ("T - 101", "T-101"),
    ("T-101", "T-101"),
    ("T101", "T101"),  # punctuation is kept: T101 and T-101 stay distinct
    ("T_101", "T_101"),
    ("AI-01", "AI-01"),  # leading zeros kept: AI-01 is not AI-1
])
def test_normalize_key_is_conservative(raw, key):
    assert sr.normalize_key(raw) == key


def _sheet(number: str, lines: list[str]) -> sr.SheetRecord:
    rec, _ = sr.parse_page("\n".join([f"SHEET: {number} | TITLE: Test"] + lines), 1, "test.pdf")
    return rec


def test_r3_zero_capacity_is_unresolved_input_not_a_crash():
    s = _sheet("P-1", ["CAPACITY: CP-09 | AI=0 | AO=4 | DI=8 | DO=4",
                       "TAG: AHU-09-SAT | PANEL: CP-09 | TYPE: AI | TERM: AI-01"])
    found = sr.rule_r3_spare([s])
    assert [f.finding_id for f in found] == ["R3:CP-09:AI:UNKNOWN_CAPACITY"]
    assert found[0].candidate_reason.startswith(sr.UNRESOLVED_INPUT)


def test_r5_unknown_cable_unit_is_unresolved_input():
    a = _sheet("W-1", ["CABLE: CBL-9 | LENGTH: 30"])
    b = _sheet("W-2", ["CABLE: CBL-9 | LENGTH_FT: 30"])
    found = sr.rule_r5_cables([a, b])
    assert [f.finding_id for f in found] == ["R5:CBL-9:UNIT_UNKNOWN"]


def test_r5_converts_meters_and_exactly_ten_percent_passes():
    a = _sheet("W-1", ["CABLE: CBL-8 | LENGTH_M: 10"])
    b = _sheet("W-2", ["CABLE: CBL-8 | LENGTH_FT: 32.8084"])
    c = _sheet("W-3", ["CABLE: CBL-7 | LENGTH_FT: 90"])
    d = _sheet("W-4", ["CABLE: CBL-7 | LENGTH_FT: 100"])
    assert sr.rule_r5_cables([a, b, c, d]) == []


def test_r3_exactly_fifteen_percent_passes():
    s = _sheet("P-1", ["CAPACITY: CP-05 | AI=20 | AO=0 | DI=0 | DO=0",
                       "RESERVED: CP-05 | AI=17 | AO=0 | DI=0 | DO=0"])
    assert sr.rule_r3_spare([s]) == []


# ---- Rule 11 structural gate: every node carries its wrapper comment --------

@pytest.mark.parametrize("fn", [sr.n1_ingest, sr.n2_validate, sr.n3_extract, sr.n4_cross_reference, sr.n5_rule_checks,
                                sr.n6_gather_context, sr.n7_classify, sr.n8_order, sr.n9_report])
def test_every_node_has_its_wrapper_comment(fn):
    comments = inspect.getcomments(fn) or ""
    for label in ("# Build Guide:", "# Decision:", "# Reads:", "# Writes:", "# Why:", "# May change:", "# Wraps:"):
        assert label in comments, f"{fn.__name__} missing {label}"
