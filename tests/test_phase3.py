"""Phase 3 tests: the knowledge decisions P3-C1 to P3-C3.

P3-C1 retrieval: exact keys only; raw text kept beside every key; T-101, T101 and T_101 stay apart unless
      an ALIAS line in the input says otherwise; every alias use is logged; two spellings that collapse to
      one key are flagged for review, never silently merged.
P3-C2 data: the fixture datasets are versioned and frozen by SHA-256, and the agent never reads the answer files.
P3-C3 currency: static; each run reads one exported package (covered by the P1-C1 reproducibility test).

Run from the repo root:  python -m pytest -q
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

import submittal_review as sr

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"
SEEDED, CLEAN = FIX / "seeded", FIX / "clean"
RESPONSES = FIX / "recorded_responses.json"

sys.path.insert(0, str(ROOT / "tools"))
import freeze_datasets  # noqa: E402
import make_fixtures  # noqa: E402


def sheet(number: str, lines: list[str]) -> sr.SheetRecord:
    rec, _ = sr.parse_page("\n".join([f"SHEET: {number} | TITLE: Test"] + lines), 1, "test.pdf")
    return rec


def xref_for(sheets, points=(), seq=()) -> dict:
    return sr.n4_cross_reference({"sheet_records": sheets, "index_entries": [], "points_list_records": list(points),
                                  "sequence_tags": list(seq)})["cross_reference_table"]


def point(tag: str, row: int = 2) -> sr.PointRecord:
    return sr.PointRecord(point_id=f"ROW{row:04d}", tag_raw=tag, tag_key=sr.normalize_key(tag), controller_raw="CP-01",
                          controller_key="CP-01", terminal_raw="AI-01", terminal_key="AI-01", point_type="AI",
                          description="test", location=sr.SourceLocation(source_file="points.xlsx", row_number_1based=row,
                                                                         raw_excerpt=f"{tag}, CP-01", field_name="Points"))


def report_body(state) -> str:
    lines = Path(state["review_outputs"].report_txt_path).read_text(encoding="utf-8").splitlines()
    return "\n".join(l for l in lines if not l.startswith(("Run:", "Input:")))


# ---- P3-C1: identifier matching policy --------------------------------------

@pytest.mark.parametrize("a, b", [("T-101", "T101"), ("T-101", "T_101"), ("T101", "T_101"), ("AI-01", "AI-1"),
                                  ("T-101", "T.101"), ("AHU-01-SAT", "SAT")])
def test_different_punctuation_or_zeros_are_different_tags(a, b):
    assert sr.normalize_key(a) != sr.normalize_key(b)


def test_without_an_alias_t101_and_t_101_are_separate_entries():
    table = xref_for([sheet("IO-1", ["TAG: T-101 | PANEL: CP-01 | TYPE: AI | TERM: AI-01"])], [point("T101")])
    assert set(table) == {"T-101", "T101"}


def test_an_alias_line_joins_them_and_every_use_is_logged():
    s = sheet("G-001", ["ALIAS: T101 = T-101", "TAG: T-101 | PANEL: CP-01 | TYPE: AI | TERM: AI-01"])
    table = xref_for([s], [point("T101")])
    assert set(table) == {"T-101"}
    aliased = [e for e in table["T-101"] if e.alias_of]
    assert len(aliased) == 1 and aliased[0].alias_of == "T101" and aliased[0].tag_raw == "T101"


def test_scope_lines_follow_the_alias_so_r1_sees_one_tag():
    s = sheet("G-001", ["ALIAS: T101 = T-101", "SCOPE: T101 | DOCS=DRAWINGS,POINTS",
                        "TAG: T-101 | PANEL: CP-01 | TYPE: AI | TERM: AI-01"])
    table = xref_for([s], [point("T101")])
    assert sr.rule_r1_tags(table, [s]) == []


def test_conflicting_or_chained_aliases_stop_the_run():
    with pytest.raises(ValueError, match="conflicting ALIAS"):
        sr.alias_map([sheet("G-001", ["ALIAS: T101 = T-101", "ALIAS: T101 = T-102"])])
    with pytest.raises(ValueError, match="chains"):
        sr.alias_map([sheet("G-001", ["ALIAS: T101 = T-101", "ALIAS: T-101 = T-1O1"])])


def test_two_spellings_that_collapse_are_flagged_not_silently_merged(tmp_path):
    s = sheet("IO-1", ["TAG: T-101 | PANEL: CP-01 | TYPE: AI | TERM: AI-01"])
    table = xref_for([s], [point("t-101")])
    assert list(table) == ["T-101"]  # same key, so R1 does not call it an error
    collisions = sr.normalization_collisions(table)
    assert list(collisions) == ["T-101"]
    assert {e.tag_raw for e in collisions["T-101"]} == {"T-101", "t-101"}


def test_collisions_and_aliases_appear_in_the_report(tmp_path):
    state = sr.run_review(SEEDED, tmp_path, sr.RecordedResponseClient(RESPONSES))
    text = Path(state["review_outputs"].report_txt_path).read_text(encoding="utf-8")
    assert "NORMALIZATION REVIEW (0 collisions, 0 alias uses)" in text


def test_every_key_keeps_its_raw_text_and_source(tmp_path):
    state = sr.run_review(SEEDED, tmp_path, sr.RecordedResponseClient(RESPONSES))
    for key, entries in state["cross_reference_table"].items():
        for e in entries:
            assert sr.normalize_key(e.tag_raw) in (key, e.alias_of)
            assert e.tag_raw in e.location.raw_excerpt  # a comment can always quote the drawing as drawn
    for s in state["sheet_records"]:
        for p in s.io_points:
            assert p.tag_raw in p.location.raw_excerpt and p.controller_key in p.location.raw_excerpt.upper()


def test_same_terminal_on_two_controllers_is_two_points():
    s = sheet("IO-1", ["TAG: AHU-01-SAT | PANEL: CP-01 | TYPE: AI | TERM: AI-01",
                       "TAG: AHU-02-SAT | PANEL: CP-02 | TYPE: AI | TERM: AI-01"])
    keys = {(p.controller_key, p.terminal_key) for p in s.io_points}
    assert keys == {("CP-01", "AI-01"), ("CP-02", "AI-01")}


# ---- P3-C2: versioned, frozen datasets ----------------------------------------

def test_fixture_datasets_match_their_frozen_hashes():
    frozen = json.loads((FIX / "datasets.json").read_text(encoding="utf-8"))
    now = freeze_datasets.snapshot()
    for name, info in frozen["datasets"].items():
        assert now["datasets"][name]["files"] == info["files"], (
            f"dataset {name} changed; bump GENERATOR_VERSION, regenerate and refreeze instead of editing it")
    assert now["shared_files"] == frozen["shared_files"]


def test_frozen_versions_match_the_generator_and_the_labels():
    frozen = json.loads((FIX / "datasets.json").read_text(encoding="utf-8"))
    assert frozen["generator_version"] == make_fixtures.GENERATOR_VERSION
    assert frozen["fixture_schema_version"] == make_fixtures.FIXTURE_SCHEMA_VERSION
    assert frozen["seed"] == make_fixtures.GENERATOR_SEED
    for name in ("seeded", "clean"):
        labels = json.loads((FIX / name / "error_labels.json").read_text(encoding="utf-8"))
        assert labels["generator_version"] == frozen["generator_version"]


def test_the_agent_never_reads_the_answer_files(tmp_path):
    bare = tmp_path / "bare"
    shutil.copytree(SEEDED, bare)
    (bare / "error_labels.json").unlink()
    (bare / "extraction_truth.json").unlink()
    with_answers = sr.run_review(SEEDED, tmp_path / "a", sr.RecordedResponseClient(RESPONSES))
    without = sr.run_review(bare, tmp_path / "b", sr.RecordedResponseClient(RESPONSES))
    assert report_body(with_answers) == report_body(without)
