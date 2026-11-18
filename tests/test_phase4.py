"""Phase 4 tests: the safety and operations decisions P4-C1 to P4-C8.

P4-C1 safety: no approve or reject language; no comment without complete evidence; a convention needs an
      explicit clause AND code-checked proof that it covers this exact finding, or it becomes unresolved.
P4-C2 licensing and privacy: every dependency and model is in THIRD_PARTY_NOTICES.txt; outputs and real
      packages are never committed.
P4-C3 audit: every run writes an audit log (nodes, counts, timings, every rule that fired, stops) and ties
      itself to source hashes, dataset, code and model; full prompt text only for frozen synthetic data.
P4-C4 feedback: blank reviewer columns in the CSV.
P4-C5 transparency: evidence laid out per rule; conventions show why they apply.
P4-C6 monitoring: a run summary, compared with the last run of the same package.
P4-C7 regression: the benchmark records the numbers and refuses a version that loses ground.
P4-C8 manual tuning only: nothing the agent or the benchmark runs changes the config.

Run from the repo root:  python -m pytest -q
"""

from __future__ import annotations

import csv
import hashlib
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
RECORDED = json.loads(RESPONSES.read_text(encoding="utf-8"))

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).parent))
import benchmark  # noqa: E402
from test_phase2 import FakeOllama  # noqa: E402


@pytest.fixture
def ollama():
    fake = FakeOllama()
    yield fake
    fake.close()


def run(folder, out, client=None, config=None):
    return sr.run_review(folder, out, client or sr.RecordedResponseClient(RESPONSES), config or sr.ReviewConfig())


def classified(state):
    return {c.finding.finding_id: c for c in state["classified_findings"]}


def read_jsonl(path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines()]


def context_for(finding_id: str):
    state = {"submittal_folder_path": str(SEEDED)}
    for step in (sr.n1_ingest, sr.n2_validate, sr.n3_extract, sr.n4_cross_reference, sr.n5_rule_checks,
                 sr.n6_gather_context):
        state.update(step(state))
    return next(i for i in state["findings_with_context"] if i.finding.finding_id == finding_id)


# ---- P4-C1: safety rules ------------------------------------------------------

NOTE = "NOTE: CABLE LENGTHS ON THIS TYPICAL ARE NOMINAL. FIELD LENGTHS PER PANEL WIRING SHEET."


def test_a_note_from_a_sheet_that_does_not_show_the_finding_cannot_excuse_it(tmp_path, ollama):
    # the failure gemma made on 2026-11-17: the typical's cable note used to excuse a missing sequence entry
    wrong = {"verdict": "drafting_convention", "supporting_quote": NOTE, "reason": "The typical note covers it."}
    ollama.overrides["R1:AHU-02-SAT:MISSING_FROM_SEQUENCE"] = [wrong, wrong]
    c = classified(run(SEEDED, tmp_path, sr.OllamaClient(sr.ReviewConfig(), ollama.url)))[
        "R1:AHU-02-SAT:MISSING_FROM_SEQUENCE"]
    assert c.verdict == "unresolved" and c.model_attempt_count == 2
    # p2-v4: code already knows no NOTE or TYPICAL line covers this finding, so the verdict itself is refused
    assert all("drafting_convention is not an allowed verdict" in f for f in c.attempt_failures)
    sent = [p for p in ollama.payloads if "R1:AHU-02-SAT:MISSING_FROM_SEQUENCE" in p["prompt"]]
    assert sent and all(p["format"]["properties"]["verdict"]["enum"] == ["real_error", "unresolved"] for p in sent)


def test_a_convention_needs_an_explicit_note_or_typical_clause():
    item = context_for("R5:CBL-102")
    reply = sr.ModelReply(verdict="drafting_convention", supporting_quote="CABLE: CBL-102 | LENGTH_FT: 50", reason="x")
    problem, *_ = sr.check_convention(reply, item)
    assert "explicit NOTE or TYPICAL clause" in problem


def test_the_real_convention_passes_with_its_applicability_recorded(tmp_path):
    state = run(SEEDED, tmp_path)
    c = classified(state)["R5:CBL-102"]
    assert c.verdict == "drafting_convention" and c.convention_sheet == "T-201"
    assert "CABLE: CBL-102 | LENGTH_FT: 50" in c.applicability_quote and "APPLIES_TO=CP-01,CP-02" in c.applicability_quote
    report = Path(state["review_outputs"].report_txt_path).read_text(encoding="utf-8")
    assert 'Applies here because T-201 shows: "CABLE: CBL-102 | LENGTH_FT: 50 / TYPICAL: APPLIES_TO=CP-01,CP-02"' in report


@pytest.mark.parametrize("reason", ["The sheet is approved.", "Reject this sheet.", "Revise and resubmit.",
                                    "No exceptions taken."])
def test_approve_or_reject_language_is_a_failed_attempt(reason):
    reply = sr.ModelReply(verdict="real_error", supporting_quote="CABLE: CBL-001 | LENGTH_FT: 340", reason=reason)
    assert "approve or reject" in sr.check_reply(reply, "CABLE: CBL-001 | LENGTH_FT: 340")


def test_a_real_error_without_complete_evidence_is_never_issued():
    item = context_for("R5:CBL-001")
    thin = item.finding.model_copy(update={"evidence": [e for e in item.finding.evidence if e.role != "calculation"]})
    c = sr.ClassifiedFinding(finding=thin, context_sheet_numbers=[], verdict="real_error",
                             supporting_quote="CABLE: CBL-001 | LENGTH_FT: 340", reason="lengths differ",
                             model_attempt_count=1)
    out = sr.n8_order({"classified_findings": [c]})
    assert out["ordered_comments"] == []
    assert out["unresolved_findings"][0].reason.startswith("not issued: the R5 evidence is incomplete")


def test_the_report_never_approves_and_says_so(tmp_path):
    text = Path(run(SEEDED, tmp_path)["review_outputs"].report_txt_path).read_text(encoding="utf-8").lower()
    assert "the agent does not approve or reject submittals" in text
    body = text.split("the agent does not approve or reject submittals", 1)[1]
    assert not any(p in body for p in ("is approved", "no exceptions taken", "resubmit"))


# ---- P4-C2: licensing and privacy ---------------------------------------------

def test_every_dependency_and_model_is_in_the_notices():
    notices = (ROOT / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8").lower()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            assert line.strip().lower() in notices
    models = {sr.ReviewConfig().model_name} | {json.loads(p.read_text())["model_name"] for p in (ROOT / "configs").glob("*.json")}
    assert all(m in notices for m in models) and "ollama" in notices and "gemma terms of use" in notices


def test_outputs_and_real_packages_are_never_committed():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for pattern in ("out/", "out_*/", "benchmarks/runs/", "real_packages/"):
        assert pattern in ignored


# ---- P4-C3: audit trail ---------------------------------------------------------

def test_every_run_writes_a_full_audit_log(tmp_path):
    state = run(SEEDED, tmp_path)
    run_dir = Path(state["output_folder_path"])
    events = read_jsonl(run_dir / "audit_log.jsonl")
    assert events[0]["event"] == "run_start" and events[-1]["event"] == "run_end"
    nodes = [e for e in events if e["event"] == "node"]
    assert [e["node"] for e in nodes] == [name for name, _ in sr.NODES]
    assert all(e["seconds"] >= 0 and e["outputs"] for e in nodes)
    fired = [e for e in events if e["event"] == "rule_fired"]
    assert {e["finding_id"] for e in fired} == {f.finding_id for f in state["suspected_findings"]}
    assert all(e["evidence"] and "entity_spellings" in e for e in fired)
    assert set(events[0]["source_files"]) == {"drawings.pdf", "points.xlsx", "sequence.txt"}
    assert all(len(v["sha256"]) == 64 for v in events[0]["source_files"].values())


def test_run_is_tied_to_dataset_code_and_model(tmp_path):
    state = run(SEEDED, tmp_path)
    log = Path(state["review_outputs"].run_log_path).read_text(encoding="utf-8")
    assert "dataset: seeded (generator 0.1.0" in log and "full_text_logging: True" in log
    assert "code_version:" in log and "submittal_review.py sha256" in log
    assert "prompt_version: p2-v4" in log and "config_values:" in log


def test_full_prompts_and_replies_are_logged_for_synthetic_data(tmp_path):
    state = run(SEEDED, tmp_path)
    entries = read_jsonl(state["review_outputs"].classify_log_path)
    asked = [e for e in entries if e["attempts"]]
    assert asked and all(e["prompt"].startswith(sr.PROMPT_HEADER) for e in asked)
    assert all(a["reply"] for e in asked for a in e["attempt_records"])


def test_prompts_and_replies_are_withheld_for_any_other_package(tmp_path):
    other = tmp_path / "pkg"
    shutil.copytree(SEEDED, other)
    (other / "sequence.txt").write_text((SEEDED / "sequence.txt").read_text() + "SEQ: note for a non-frozen copy\n")
    state = run(other, tmp_path / "out")
    assert state["run_metadata"].full_text_logging is False
    for e in read_jsonl(state["review_outputs"].classify_log_path):
        assert e["prompt"].startswith("withheld") and all("reply" not in a for a in e["attempt_records"])
        if e["attempts"]:
            assert len(e["prompt_sha256"]) == 64


def test_token_counts_from_the_model_are_recorded(tmp_path):
    class Counting(sr.RecordedResponseClient):
        def classify(self, item, prompt=""):
            self.last_usage = {"prompt_tokens": len(prompt) // 4, "reply_tokens": 40}
            return super().classify(item, prompt)

    entries = read_jsonl(run(SEEDED, tmp_path, Counting(RESPONSES))["review_outputs"].classify_log_path)
    usage = [a["usage"] for e in entries for a in e["attempt_records"]]
    assert usage and all(u["reply_tokens"] == 40 and u["prompt_tokens"] > 0 for u in usage)


def test_a_stopped_run_keeps_a_partial_audit_log(tmp_path):
    cfg = sr.ReviewConfig(max_suspected_findings=3)
    with pytest.raises(sr.SizeLimitError):
        run(SEEDED, tmp_path, config=cfg)
    events = read_jsonl(next(tmp_path.glob("run_*/audit_log.jsonl")))
    assert events[-1]["event"] == "run_stopped" and "SizeLimitError" in events[-1]["error"]
    assert [e["node"] for e in events if e["event"] == "node"][-1] == "N4_cross_reference"


# ---- P4-C4: feedback columns ------------------------------------------------------

def test_csv_has_blank_reviewer_columns_on_every_row(tmp_path):
    path = run(SEEDED, tmp_path)["review_outputs"].report_csv_path
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert rows and all(r["reviewer_decision"] == "" and r["reviewer_note"] == "" for r in rows)
    assert open(path, encoding="utf-8").readline().strip().endswith("reviewer_decision,reviewer_note")


# ---- P4-C5: reviewer-facing evidence ------------------------------------------------

def test_evidence_is_laid_out_per_rule(tmp_path):
    state = run(SEEDED, tmp_path)
    views = {c.finding_id: c.evidence_lines for c in state["ordered_comments"]}
    assert views["R2:CP-01:AI-02:TYPE_MISMATCH"][0] == "Side by side:"
    assert views["R3:CP-02:DO"][0].startswith("Installed 4, used 1, reserved 3, spare 0:")
    assert "limit 15" in views["R3:CP-02:DO"][0]
    r1 = views["R1:AHU-02-SAT:MISSING_FROM_SEQUENCE"]
    assert any(l.startswith("Absent: not found after searching") for l in r1)
    assert not any("SEQUENCE" in l and "|" in l and "sequence.txt" in l for l in r1)  # absence is never a made-up quote
    assert any(l.startswith("Lengths in feet:") and "limit 10" in l for l in views["R5:CBL-001"])


# ---- P4-C6: monitoring ---------------------------------------------------------------

def test_run_summary_is_written_and_compared_with_the_last_run(tmp_path, capsys):
    first = run(SEEDED, tmp_path)
    second = run(SEEDED, tmp_path)
    s1 = json.loads((Path(first["output_folder_path"]) / "run_summary.json").read_text())
    s2 = json.loads((Path(second["output_folder_path"]) / "run_summary.json").read_text())
    assert s1["compared_to"] is None and s1["sheets_read"] == 12 and s1["tags_extracted"] == 11
    assert s1["findings_per_rule"] == {"R1": 2, "R2": 1, "R3": 1, "R4": 1, "R5": 2}
    assert s2["compared_to"] == s1["run_id"] and s2["changes_from_last_run"] == []
    assert "[monitor] no change from the last run of this package" in capsys.readouterr().out


def test_a_change_on_the_same_package_is_flagged(tmp_path, capsys):
    first = run(SEEDED, tmp_path)
    path = Path(first["output_folder_path"]) / "run_summary.json"
    s = json.loads(path.read_text())
    s["tags_extracted"], s["verdicts"]["unresolved"] = 14, 4
    path.write_text(json.dumps(s))
    second = json.loads((Path(run(SEEDED, tmp_path)["output_folder_path"]) / "run_summary.json").read_text())
    assert any("tags_extracted 14 -> 11" in c for c in second["changes_from_last_run"])
    assert any("unresolved 4 -> 1" in c for c in second["changes_from_last_run"])


# ---- P4-C7: regression benchmark ------------------------------------------------------

@pytest.mark.parametrize("new, ok", [
    ({"caught": 4, "wrong_comments": 0}, True),
    ({"caught": 5, "wrong_comments": 0}, True),
    ({"caught": 3, "wrong_comments": 0}, False),
    ({"caught": 4, "wrong_comments": 1}, False),
])
def test_a_version_may_not_lose_ground(new, ok):
    assert (benchmark.compare(new, {"caught": 4, "wrong_comments": 0}) == []) is ok


def test_benchmark_records_versions_and_refuses_a_worse_baseline(tmp_path, capsys, monkeypatch):
    # Phase 5 added the generated dev sets to the benchmark; the recorded replies cover the fixtures pair only
    monkeypatch.setattr(benchmark, "BENCHMARK_PAIRS", benchmark.BENCHMARK_PAIRS[:1])
    assert benchmark.main(["--classifier", "recorded", "--bench-dir", str(tmp_path), "--accept"]) == 0
    result = json.loads(next((tmp_path / "results").glob("*.json")).read_text())
    assert result["totals"]["caught"] == 5 and result["totals"]["clean_set_comments"] == 0
    assert result["totals"]["precision"] == 1.0 and result["totals"]["recall"] == 1.0
    assert result["per_set"][0]["dataset"].startswith("seeded (generator 0.1.0")
    assert result["config_sha256"] and result["prompt_version"] == sr.PROMPT_VERSION
    base = json.loads((tmp_path / "baseline.json").read_text())
    base["totals"]["caught"] = 6  # pretend the baseline caught more
    (tmp_path / "baseline.json").write_text(json.dumps(base))
    assert benchmark.main(["--classifier", "recorded", "--bench-dir", str(tmp_path), "--accept"]) == 1
    assert "Not accepted" in capsys.readouterr().out
    assert json.loads((tmp_path / "baseline.json").read_text())["totals"]["caught"] == 6


# ---- P4-C8: manual tuning only --------------------------------------------------------

def test_nothing_the_agent_or_benchmark_runs_changes_the_config(tmp_path):
    before = hashlib.sha256((ROOT / "review_config.json").read_bytes()).hexdigest()
    run(SEEDED, tmp_path / "a")
    benchmark.main(["--classifier", "recorded", "--bench-dir", str(tmp_path / "b"), "--accept"])
    assert hashlib.sha256((ROOT / "review_config.json").read_bytes()).hexdigest() == before
