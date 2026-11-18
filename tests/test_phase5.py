"""Phase 5 tests: the validation decisions P5-C1 to P5-C7.

P5-C1 success criteria: I8 scoring per rule, the rules-only baseline from the same runs, strict clean twins,
      the malformed set, and a trace check that fails the run even when TP is high.
P5-C2 comparison and holdout: generated sets vary panels, controller and conventions; the holdout is
      pre-registered, refused by every tuning tool, and scored once.
P5-C3 feedback into iteration: out of scope for version one (no code, no test).
P5-C4 tradeoffs: serial calls, a known worst case, progress per finding, Ctrl-C keeps the logs.
P5-C5 concurrency: one run, one model call at a time.
P5-C6 ship checklist: tests, benchmark, holdout, trace, and the rules-only record.
P5-C7 load: page and finding counts with their caps are reported at N3 and N5, before any model call.

The model is never called; tests use the recorded replies or a test-only oracle (tests/oracle.py).
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
FIX, EVAL = ROOT / "tests" / "fixtures", ROOT / "eval_sets"
RESPONSES = FIX / "recorded_responses.json"

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).parent))
import benchmark  # noqa: E402
import eval_early  # noqa: E402
import holdout  # noqa: E402
import make_eval_sets  # noqa: E402
import ship_check  # noqa: E402
import validate  # noqa: E402
from oracle import OracleClient  # noqa: E402


@pytest.fixture
def sealed(tmp_path, monkeypatch):
    """A private copy of the holdout registration, so tests never consume the real one."""
    reg = tmp_path / "holdout_registration.json"
    monkeypatch.setattr(holdout, "REGISTRATION", reg)
    assert validate.register() == 0
    monkeypatch.setattr(validate, "OUT", tmp_path / "validation")
    return reg


# ---- P5-C1: success criteria and scoring ------------------------------------------

def test_validation_passes_for_a_correct_classifier_and_records_the_rules_only_baseline(tmp_path):
    record = validate.run_pairs(validate.DEV_PAIRS, OracleClient(), sr.ReviewConfig(), tmp_path)
    a, b = record["agent_totals"], record["rules_only_totals"]
    assert record["problems"] == [] and (a["tp"], a["fn"], a["fp"]) == (20, 0, 0)
    assert (b["tp"], b["fn"]) == (20, 0) and b["fp"] == 7  # 4 network points + 3 typical cable notes
    assert b["precision"] < 0.8 <= a["precision"]
    assert "cut wrong comments from 7 to 0 without losing seeded errors" in validate.conclusion(a, b)
    assert set(record["agent_per_rule"]) == set(sr.RULE_IDS)
    assert all(v["tp"] == 4 for v in record["agent_per_rule"].values())  # every rule counted on its own


def test_an_agent_that_calls_everything_an_error_fails_on_the_clean_twins(tmp_path):
    record = validate.run_pairs(validate.DEV_PAIRS, OracleClient(everything_is_an_error=True), sr.ReviewConfig(), tmp_path)
    assert any("clean twin has" in p for p in record["problems"])
    assert record["agent_totals"]["fp"] > 0


def test_zero_comments_on_a_seeded_set_fails(tmp_path):
    record = validate.run_pairs(validate.DEV_PAIRS[1:2], sr.RecordedResponseClient(RESPONSES), sr.ReviewConfig(), tmp_path)
    assert any("zero comments on a seeded set" in p for p in record["problems"])
    record.update(failed=[])
    assert any("recall" in p for p in validate.verdict(record))


def test_scoring_spec_edge_cases():
    assert validate.totals(validate._empty()) == {"tp": 0, "fn": 0, "fp": 0, "recall": None, "precision": None}
    per = validate._empty()
    per["R1"].update(tp=3, fn=1)
    per["R5"].update(tp=1, fp=1)
    t = validate.totals(per)
    assert (t["recall"], t["precision"]) == (0.8, 0.8)  # summed counts, never averaged percentages


def test_a_comment_that_does_not_trace_fails_the_run(tmp_path):
    state = sr.run_review(FIX / "seeded", tmp_path, sr.RecordedResponseClient(RESPONSES))
    assert validate.trace_problems(state) == []
    log = Path(state["output_folder_path"]) / "audit_log.jsonl"
    log.write_text("\n".join(l for l in log.read_text().splitlines() if "R2:CP-01:AI-02" not in l) + "\n")
    assert validate.trace_problems(state) == ["R2:CP-01:AI-02:TYPE_MISMATCH: no rule_fired entry in the audit log"]


def test_the_malformed_set_must_stop_loudly(tmp_path):
    assert validate.malformed_check(sr.RecordedResponseClient(RESPONSES), sr.ReviewConfig(), tmp_path) == []


def test_confusion_categories_are_reported(tmp_path):
    record = validate.run_pairs(validate.DEV_PAIRS[:1], sr.RecordedResponseClient(RESPONSES), sr.ReviewConfig(), tmp_path)
    assert set(record["sets"][0]["confusion"].values()) == {"caught"}


# ---- P5-C2: generated sets and the holdout ------------------------------------------

def test_evaluation_sets_vary_panels_controller_and_conventions():
    manifest = json.loads((EVAL / "datasets.json").read_text())
    dev = {k: v for k, v in manifest["datasets"].items() if not v["holdout"] and v["kind"] == "seeded"}
    assert len({v["panels"] for v in dev.values()}) == 3 and len({v["controller"] for v in dev.values()}) == 3
    assert {v["typical"] for v in dev.values()} == {True, False}
    assert manifest["generator_version"] == make_eval_sets.EVAL_GENERATOR_VERSION


def test_evaluation_sets_match_their_frozen_hashes_and_seeds():
    frozen = json.loads((EVAL / "datasets.json").read_text())
    now = make_eval_sets.snapshot()
    for name, info in frozen["datasets"].items():
        assert now["datasets"][name]["files"] == info["files"], f"{name} changed; bump the generator and refreeze"
    for name, panels, controller, typical, seed, _ in make_eval_sets.EVAL_SETS:
        labels = json.loads((EVAL / name / "error_labels.json").read_text())
        assert (labels["seed"], labels["panels"], labels["controller"], labels["typical"]) == (seed, panels, controller, typical)


def test_the_generated_runs_are_recognized_as_frozen_synthetic_data(tmp_path):
    state = sr.run_review(EVAL / "dev_b", tmp_path, sr.RecordedResponseClient(RESPONSES))
    assert state["run_metadata"].dataset.startswith("dev_b (generator 1.0.0") and state["run_metadata"].full_text_logging


@pytest.mark.parametrize("tool", ["eval_early", "benchmark", "validate"])
def test_every_tuning_tool_refuses_the_holdout(tool):
    with pytest.raises(SystemExit, match="registered holdout"):
        holdout.refuse(EVAL / "holdout_1", tool)
    with pytest.raises(SystemExit, match="registered holdout"):
        eval_early.main(["--input", str(EVAL / "holdout_1"), "--output", "unused", "--classifier", "recorded"])


def test_the_holdout_is_not_a_benchmark_or_development_set():
    used = {p.name for pair in benchmark.BENCHMARK_PAIRS + validate.DEV_PAIRS for p in pair}
    assert not any(n.startswith("holdout") for n in used)


def test_the_shipped_registration_matches_the_holdout_and_metric_script():
    assert holdout.untouched() == []
    reg = holdout.registration()
    assert set(reg["cases"]) == {"holdout_1", "holdout_1_clean"}
    final_run = reg["final_run"]
    if final_run is not None:
        # The holdout was scored once (2026-11-17); the recorded result must exist and show a pass.
        result_file = ROOT / "validation" / "results" / final_run["result"]
        assert result_file.is_file()
        result = json.loads(result_file.read_text())
        totals = result["agent_totals"]
        assert result["holdout"] is True and result["failed"] == []
        assert totals["tp"] == 5 and totals["fn"] == 0 and totals["fp"] == 0
        assert all(s["wrong_comments"] == [] for s in result["sets"])


def test_final_refuses_if_the_metric_script_changed(sealed, tmp_path, monkeypatch):
    other = tmp_path / "validate_copy.py"
    other.write_text(holdout.METRIC_SCRIPT.read_text() + "\n# edited\n")
    monkeypatch.setattr(holdout, "METRIC_SCRIPT", other)
    assert validate.final(sr.RecordedResponseClient(RESPONSES), sr.ReviewConfig()) == 1
    assert json.loads(sealed.read_text())["final_run"] is None


def test_the_holdout_is_scored_once(sealed, capsys):
    validate.final(sr.RecordedResponseClient(RESPONSES), sr.ReviewConfig())
    reg = json.loads(sealed.read_text())
    assert reg["final_run"] and reg["final_run"]["result"].startswith("final_holdout_")
    result = json.loads(next((validate.OUT / "results").glob("final_holdout_*.json")).read_text())
    assert result["holdout"] and result["limitations"] and "confusion" in result["sets"][0]
    assert validate.final(sr.RecordedResponseClient(RESPONSES), sr.ReviewConfig()) == 1
    assert "One final evaluation is allowed" in capsys.readouterr().out
    assert validate.register() == 1  # a scored holdout cannot be re-registered; a new one must be generated


# ---- P5-C4: tradeoffs, progress, Ctrl-C -------------------------------------------------

def test_worst_case_and_progress_per_finding_are_printed(tmp_path, capsys):
    sr.run_review(FIX / "seeded", tmp_path, sr.RecordedResponseClient(RESPONSES))
    out = capsys.readouterr().out
    assert "[N7 plan] 7 findings for the model, at most 14 calls one at a time, worst case 28 min" in out
    assert all(f"  [N7 {k}/7] " in out for k in range(1, 8))
    lines = (next(tmp_path.glob("run_*")) / "classify_progress.jsonl").read_text().splitlines()
    assert [json.loads(l)["n"] for l in lines] == list(range(1, 8))


def test_ctrl_c_stops_the_run_and_keeps_partial_logs(tmp_path, monkeypatch):
    calls = {"n": 0}
    original = sr.RecordedResponseClient.classify

    def interrupt_on_third(self, item, prompt=""):
        calls["n"] += 1
        if calls["n"] == 3:
            raise KeyboardInterrupt
        return original(self, item, prompt)

    monkeypatch.setattr(sr.RecordedResponseClient, "classify", interrupt_on_third)
    code = sr.main(["--input", str(FIX / "seeded"), "--output", str(tmp_path), "--classifier", "recorded"])
    assert code == 130
    run_dir = next(tmp_path.glob("run_*"))
    events = [json.loads(l) for l in (run_dir / "audit_log.jsonl").read_text().splitlines()]
    assert events[-1]["event"] == "run_stopped" and "KeyboardInterrupt" in events[-1]["error"]
    assert len((run_dir / "classify_progress.jsonl").read_text().splitlines()) == 2


# ---- P5-C5: one call at a time -------------------------------------------------------------

def test_model_calls_are_serial(tmp_path):
    class Watch(sr.RecordedResponseClient):
        active = peak = 0

        def classify(self, item, prompt=""):
            Watch.active += 1
            Watch.peak = max(Watch.peak, Watch.active)
            try:
                return super().classify(item, prompt)
            finally:
                Watch.active -= 1

    sr.run_review(FIX / "seeded", tmp_path, Watch(RESPONSES))
    assert Watch.peak == 1


# ---- P5-C6: ship checklist -------------------------------------------------------------------

def test_ship_check_passes_when_every_item_holds(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, "BENCHMARK_PAIRS", benchmark.BENCHMARK_PAIRS[:1])
    assert benchmark.main(["--classifier", "recorded", "--bench-dir", str(tmp_path / "bench"), "--accept"]) == 0
    (tmp_path / "val" / "results").mkdir(parents=True)
    (tmp_path / "val" / "results" / "validate_1.json").write_text(json.dumps({"conclusion": "recorded", "failed": []}))
    assert ship_check.main(["--classifier", "recorded", "--skip-pytest", "--bench-dir", str(tmp_path / "bench"),
                            "--validation-dir", str(tmp_path / "val")]) == 0
    # the latest validation failing makes the ship check fail, whatever else passes
    (tmp_path / "val" / "results" / "validate_2.json").write_text(
        json.dumps({"conclusion": "recorded", "failed": ["recall 0.55 under 0.80"]}))
    assert ship_check.main(["--classifier", "recorded", "--skip-pytest", "--bench-dir", str(tmp_path / "bench"),
                            "--validation-dir", str(tmp_path / "val")]) == 1


def test_ship_check_fails_without_a_baseline(tmp_path):
    assert ship_check.main(["--classifier", "recorded", "--skip-pytest", "--bench-dir", str(tmp_path / "none"),
                            "--validation-dir", str(tmp_path / "val")]) == 1


def test_ship_check_catches_a_tuning_run_that_read_the_holdout(tmp_path):
    run = tmp_path / "out" / "run_1"
    run.mkdir(parents=True)
    (run / "run_log.txt").write_text(f"input_folder: {EVAL / 'holdout_1'}\n")
    assert ship_check.holdout_runs(tmp_path, ("out",)) == [str(Path("out") / "run_1" / "run_log.txt")]


# ---- P5-C7: load ---------------------------------------------------------------------------

def test_counts_and_caps_are_reported_before_any_model_call(tmp_path, capsys):
    sr.run_review(FIX / "seeded", tmp_path, sr.RecordedResponseClient(RESPONSES))
    out = capsys.readouterr().out
    n3, n5, n7 = out.index("[N3 extract] 12 sheets (250-page cap)"), out.index("7 suspected findings (150-finding cap)"), \
        out.index("[N7 plan]")
    assert n3 < n5 < n7


# ---- p2-v4: lessons from the first live validation (2026-11-17) ------------------------------

def _items(folder):
    class Cap(sr.RecordedResponseClient):
        def __init__(self):
            self.name, self.items = "cap", {}

        def classify(self, item, prompt=""):
            self.items[item.finding.finding_id] = (item, prompt)
            return json.dumps({"verdict": "unresolved", "supporting_quote": "", "reason": "captured"})

    import contextlib
    import io
    import tempfile
    c = Cap()
    with tempfile.TemporaryDirectory() as t, contextlib.redirect_stdout(io.StringIO()):
        sr.run_review(folder, Path(t), c)
    return c.items


def test_code_offers_drafting_convention_only_where_a_note_on_the_subject_covers_the_finding():
    for folder in (FIX / "seeded", EVAL / "dev_a", EVAL / "dev_b", EVAL / "dev_c"):
        for fid, (item, prompt) in _items(folder).items():
            allowed = sr.allowed_verdicts(item)
            if fid == "R5:CBL-102":  # the one real convention: T-201's cable length note
                assert allowed == ["real_error", "drafting_convention", "unresolved"], folder
                assert "CODE CHECKED: the CONTEXT has a NOTE" in prompt
            else:  # the BACnet trunk note on G-002 shows the cable but is not about its length
                assert allowed == ["real_error", "unresolved"], (folder, fid)
                assert "drafting_convention is not allowed" in prompt


def test_the_reply_format_lists_only_the_allowed_verdicts_and_requires_a_quote():
    schema = sr.reply_schema(["real_error", "unresolved"])
    assert schema["properties"]["verdict"]["enum"] == ["real_error", "unresolved"]
    assert schema["required"] == ["verdict", "supporting_quote", "reason"]
    assert sr.REPLY_SCHEMA["properties"]["verdict"]["enum"] == ["real_error", "drafting_convention", "unresolved"]


def test_r1_prompts_state_the_scope_line_code_found():
    items = _items(EVAL / "dev_a")
    _, prompt = items["R1:AHU-02-RAT:MISSING_FROM_SEQUENCE"]
    assert "CODE CHECKED: SCOPE line for AHU-02-RAT: SCOPE: AHU-02-RAT | DOCS=DRAWINGS,POINTS,SEQUENCE" in prompt
    _, prompt = items["R1:AHU-01-OAT:NO_SCOPE"]
    assert "CODE CHECKED: SCOPE line for AHU-01-OAT: none in the CONTEXT" in prompt


def test_a_quote_of_whole_context_lines_joined_by_a_comma_passes_and_a_partial_one_does_not():
    ctx = "[a]\nCABLE: CBL-003 | LENGTH_FT: 295\n[b]\nCABLE: CBL-003 | LENGTH_FT: 354\n"
    joined = "CABLE: CBL-003 | LENGTH_FT: 295, CABLE: CBL-003 | LENGTH_FT: 354"  # gemma's dev_b reply
    assert sr.check_reply(sr.ModelReply(verdict="real_error", supporting_quote=joined, reason="x"), ctx) is None
    bad = "CABLE: CBL-003 | LENGTH_FT: 295, CABLE: CBL-003 | LENGTH_FT: 999"
    assert "not found word for word" in sr.check_reply(sr.ModelReply(verdict="real_error", supporting_quote=bad,
                                                                      reason="x"), ctx)
    part = "CBL-003 | LENGTH_FT: 295, CABLE: CBL-003"  # pieces that are not whole lines
    assert "not found word for word" in sr.check_reply(sr.ModelReply(verdict="real_error", supporting_quote=part,
                                                                      reason="x"), ctx)


def test_an_unresolved_reply_needs_no_quote_check():
    reply = sr.ModelReply(verdict="unresolved", supporting_quote="something not in the context", reason="x")
    assert sr.check_reply(reply, "[a]\nTAG: X\n") is None


def test_a_convention_quoting_a_note_on_another_subject_is_refused():
    # before p2-v4 this passed: G-002 shows CBL-001, but its note is about the BACnet trunk, not cable length
    item, _ = _items(FIX / "seeded")["R5:CBL-001"]
    note = "NOTE: BACNET IP TRUNK FROM BAS SWITCH TO EACH PANEL."
    problem, *_ = sr.check_convention(sr.ModelReply(verdict="drafting_convention", supporting_quote=note, reason="x"),
                                      item)
    assert "not about the subject of R5:CBL-001" in problem
