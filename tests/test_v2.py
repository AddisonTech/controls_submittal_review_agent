"""v2 tests: Claude engines behind a flag (API mocked), spend hard stop, test set v2, holdout refusal, scoring.

No test here calls a real model or the Anthropic API.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import engines as en  # noqa: E402
import make_v2_sets  # noqa: E402
import score_v2  # noqa: E402
import spec_review as srv  # noqa: E402
import submittal_review as sr  # noqa: E402
import validate_v2  # noqa: E402

V2 = ROOT / "validation" / "v2"
DEV_CASE = V2 / "dev" / "v2c07_ahu_mz"
SENTINEL_KEY = "TEST-SENTINEL-NOT-A-REAL-KEY-7731"


# ---- fakes ---------------------------------------------------------------------

class FakeMessages:
    def __init__(self, replies, stop="end_turn"):
        self.replies, self.stop, self.calls = list(replies), stop, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.replies.pop(0) if self.replies else json.dumps({"issues": []})
        usage = SimpleNamespace(input_tokens=1000, cache_creation_input_tokens=600, cache_read_input_tokens=0,
                                output_tokens=200)
        return SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
                               usage=usage, stop_reason=self.stop, id="msg_test", _request_id="req_test")


def fake_client(replies=(), stop="end_turn"):
    return SimpleNamespace(messages=FakeMessages(replies, stop))


def guard(tmp_path, cap=50.0):
    return en.SpendGuard(tmp_path / "ledger.jsonl", cap)


# ---- engine switch ----------------------------------------------------------------

def test_default_engine_is_the_local_gemma_model():
    assert en.DEFAULT_ENGINE == "gemma3:4b" and en.ENGINE_CHOICES == ("gemma3:4b", "claude-haiku", "claude-sonnet")
    eng = en.make_engine("gemma3:4b", sr.ReviewConfig())
    assert isinstance(eng, en.OllamaEngine) and isinstance(eng, sr.OllamaClient) and eng.name == "ollama:gemma3:4b"
    assert sr.ReviewConfig().model_name == "gemma3:4b"


@pytest.mark.parametrize("engine,model", [("claude-haiku", "claude-haiku-5-5"), ("claude-sonnet", "claude-sonnet-5-5")])
def test_claude_engines_map_to_current_models_with_caching_and_structured_output(tmp_path, engine, model):
    client = fake_client([json.dumps({"issues": []})])
    eng = en.make_engine(engine, sr.ReviewConfig(), guard=guard(tmp_path), client=client)
    assert isinstance(eng, en.ClaudeEngine) and eng.model == model
    out = eng.generate(srv.PROSE_SYSTEM, "SPECIFICATION SECTION 3.1\n3.1.1 x\n", srv.PROSE_SCHEMA, tag="t")
    assert json.loads(out) == {"issues": []}
    call = client.messages.calls[0]
    assert call["model"] == model and call["max_tokens"] == en.CLAUDE_MAX_TOKENS
    assert call["system"] == [{"type": "text", "text": srv.PROSE_SYSTEM, "cache_control": {"type": "ephemeral"}}]
    assert call["output_config"]["effort"] == en.CLAUDE_EFFORT
    fmt = call["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"]["additionalProperties"] is False
    assert fmt["schema"]["properties"]["issues"]["items"]["additionalProperties"] is False
    assert "temperature" not in call and "thinking" not in call


def test_the_same_prompt_and_schema_go_to_every_engine(tmp_path, monkeypatch):
    sent = {}

    def fake_ollama(self, path, payload, timeout):
        sent["ollama"] = payload
        return {"response": json.dumps({"issues": []}), "prompt_eval_count": 1, "eval_count": 1}
    monkeypatch.setattr(sr.OllamaClient, "_call", fake_ollama)
    en.make_engine("gemma3:4b", sr.ReviewConfig()).generate(srv.PROSE_SYSTEM, "USER TEXT", srv.PROSE_SCHEMA)
    client = fake_client([json.dumps({"issues": []})])
    en.make_engine("claude-haiku", sr.ReviewConfig(), guard=guard(tmp_path), client=client).generate(
        srv.PROSE_SYSTEM, "USER TEXT", srv.PROSE_SCHEMA)
    c = client.messages.calls[0]
    assert sent["ollama"]["system"] == c["system"][0]["text"] == srv.PROSE_SYSTEM
    assert sent["ollama"]["prompt"] == c["messages"][0]["content"] == "USER TEXT"
    assert sent["ollama"]["format"] == c["output_config"]["format"]["schema"] == en.strict_schema(srv.PROSE_SCHEMA)
    assert sent["ollama"]["options"]["temperature"] == 0


def test_the_spec_reference_reaches_every_engine_as_the_same_text_and_is_cached_for_claude(tmp_path, monkeypatch):
    sent = {}

    def fake_ollama(self, path, payload, timeout):
        sent["ollama"] = payload
        return {"response": json.dumps({"issues": []})}
    monkeypatch.setattr(sr.OllamaClient, "_call", fake_ollama)
    pkg = srv.parse_package(DEV_CASE / "clean")
    srv.check_section(en.make_engine("gemma3:4b", sr.ReviewConfig()), pkg, "3.3", 2, "t", [])
    client = fake_client([json.dumps({"issues": []})])
    srv.check_section(en.make_engine("claude-haiku", sr.ReviewConfig(), guard=guard(tmp_path), client=client), pkg, "3.3", 2, "t", [])
    blocks = client.messages.calls[0]["messages"][0]["content"]
    ref = srv.spec_reference(pkg)
    assert blocks[0] == {"type": "text", "text": ref, "cache_control": {"type": "ephemeral"}}
    assert sent["ollama"]["prompt"] == blocks[0]["text"] + blocks[1]["text"] and sent["ollama"]["prompt"].startswith(ref)
    assert "SECTION 3.4 Freeze Protection" in ref and "POINTS SCHEDULE" in ref


def test_v1_n7_uses_the_same_prompt_and_reply_format_with_claude(tmp_path):
    client = fake_client([json.dumps({"verdict": "unresolved", "supporting_quote": "", "reason": "test"})] * 20)
    eng = en.make_engine("claude-sonnet", sr.ReviewConfig(), guard=guard(tmp_path), client=client)
    state = sr.run_review(ROOT / "tests" / "fixtures" / "seeded", tmp_path / "out", eng)
    assert state["run_metadata"].classifier_name == "anthropic:claude-sonnet-5-5"
    first = client.messages.calls[0]
    assert first["messages"][0]["content"].startswith(sr.PROMPT_HEADER) and first["cache_control"] == {"type": "ephemeral"}
    assert first["output_config"]["format"]["schema"]["properties"]["verdict"]["enum"]


def test_cli_engine_flag_parses_and_cloud_engine_refuses_a_package_that_is_not_frozen(tmp_path, capsys):
    pkg = tmp_path / "mine"
    shutil.copytree(DEV_CASE / "seeded", pkg)
    (pkg / "spec.txt").write_text((pkg / "spec.txt").read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8")
    assert srv.main(["--input", str(pkg), "--output", str(tmp_path / "o"), "--engine", "claude-haiku"]) == 1
    assert "stays on this machine" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        srv.main(["--input", str(pkg), "--output", str(tmp_path / "o"), "--engine", "gpt"])
    assert en.frozen_public_set(DEV_CASE / "seeded") and not en.frozen_public_set(pkg)
    en.check_cloud_allowed("claude-haiku", pkg, allow_cloud=True)  # the explicit flag lets it through
    en.check_cloud_allowed("gemma3:4b", pkg, allow_cloud=False)  # the local engine never needs it


def test_missing_api_key_stops_before_any_call_and_names_no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    eng = en.ClaudeEngine("claude-haiku", sr.ReviewConfig())
    with pytest.raises(sr.ModelUnavailableError, match="ANTHROPIC_API_KEY is not set"):
        eng.preflight()


def test_the_api_key_is_never_written_to_the_ledger_or_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL_KEY)
    client = fake_client()
    eng = en.make_engine("claude-haiku", sr.ReviewConfig(), guard=guard(tmp_path), client=client)
    srv.run_spec_review(DEV_CASE / "clean", tmp_path / "out", eng)
    for p in tmp_path.rglob("*"):
        if p.is_file():
            assert SENTINEL_KEY not in p.read_text(encoding="utf-8", errors="replace")
    src = (ROOT / "engines.py").read_text(encoding="utf-8")
    assert "print(os.environ" not in src and "ANTHROPIC_API_KEY\"]" not in src


# ---- spend guard ------------------------------------------------------------------

def test_cost_is_priced_from_usage_and_written_to_the_ledger(tmp_path):
    g = guard(tmp_path)
    eng = en.make_engine("claude-sonnet", sr.ReviewConfig(), guard=g, client=fake_client([json.dumps({"issues": []})]))
    eng.generate("S", "U", srv.PROSE_SCHEMA, tag="case/x")
    want = (1000 * 2.00 + 600 * 2.50 + 200 * 10.00) / 1e6
    assert abs(g.spent() - want) < 1e-9
    row = json.loads((tmp_path / "ledger.jsonl").read_text(encoding="utf-8"))
    assert row["model"] == "claude-sonnet-5-5" and row["item"] == "case/x" and row["output_tokens"] == 200
    short = SimpleNamespace(input_tokens=50_000, cache_creation_input_tokens=0, cache_read_input_tokens=40_000, output_tokens=0)
    assert abs(en.cost_usd("claude-haiku-5-5", short) - (50_000 * 0.10 + 40_000 * 0.01) / 1e6) < 1e-12
    long = SimpleNamespace(input_tokens=150_000, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=0)
    assert abs(en.cost_usd("claude-haiku-5-5", long) - 150_000 * 0.50 / 1e6) < 1e-12  # Haiku 5.5 over 100K tokens


def test_hard_stop_refuses_a_call_that_could_pass_the_budget_and_never_sends_it(tmp_path):
    g = guard(tmp_path, cap=0.05)
    client = fake_client([json.dumps({"issues": []})])
    eng = en.make_engine("claude-sonnet", sr.ReviewConfig(), guard=g, client=client)
    with pytest.raises(en.BudgetExceeded, match="hard stop"):
        eng.generate("S", "U" * 10, srv.PROSE_SCHEMA)  # worst case 8000 output tokens at $10/M = $0.08
    assert client.messages.calls == [] and g.spent() == 0


def test_budget_stop_ends_a_review_cleanly_instead_of_counting_as_a_failed_reply(tmp_path):
    g = guard(tmp_path, cap=0.0001)
    eng = en.make_engine("claude-haiku", sr.ReviewConfig(), guard=g, client=fake_client())
    with pytest.raises(en.BudgetExceeded):
        srv.run_spec_review(DEV_CASE / "clean", tmp_path / "out", eng)
    eng1 = en.make_engine("claude-haiku", sr.ReviewConfig(), guard=g, client=fake_client())
    with pytest.raises(en.BudgetExceeded):
        sr.run_review(ROOT / "tests" / "fixtures" / "seeded", tmp_path / "v1", eng1)


def test_task_budget_is_fifty_dollars():
    assert en.TASK_BUDGET_USD == 50.00 and en.SpendGuard().cap == 50.00


def test_a_refusal_or_cut_off_reply_is_a_failed_attempt(tmp_path):
    for stop in ("refusal", "max_tokens"):
        eng = en.make_engine("claude-haiku", sr.ReviewConfig(), guard=guard(tmp_path), client=fake_client(stop=stop))
        r = srv.check_section(eng, srv.parse_package(DEV_CASE / "clean"), "3.1", 2, "t", [])
        assert r["comments"] == [] and r["unresolved"] and len(r["failures"]) == 2


# ---- the review checks ------------------------------------------------------------

def test_prose_quotes_must_point_at_exactly_one_paragraph():
    pkg = srv.parse_package(DEV_CASE / "seeded")
    spec = list(pkg.spec_sections["3.1"].paras.values())
    sub = list(pkg.sub_sections["3.1"].paras.values())
    s5, p5 = pkg.sub_sections["3.1"].paras["3.1.5"][6:], pkg.spec_sections["3.1"].paras["3.1.5"][6:]
    ok = srv.ProseIssue(error_type="sequence_contradiction", submittal_quote=s5, spec_quote=p5, reason="x")
    assert srv.check_prose_issue(ok, spec, sub) == (None, "3.1.5", "3.1.5")
    bad = ok.model_copy(update={"submittal_quote": "a sentence that is not in the submittal"})
    assert "not found" in srv.check_prose_issue(bad, spec, sub)[0]
    vague = ok.model_copy(update={"submittal_quote": "supply fan"})
    assert "more than one" in srv.check_prose_issue(vague, spec, sub)[0]
    absent = ok.model_copy(update={"submittal_quote": ""})
    assert srv.check_prose_issue(absent, spec, sub) == (None, "", "3.1.5")
    rude = ok.model_copy(update={"reason": "Rejected, resubmit."})
    assert "approve or reject" in srv.check_prose_issue(rude, spec, sub)[0]


def test_an_entry_the_model_marks_compliant_is_dropped_by_code(tmp_path):
    pkg = srv.parse_package(DEV_CASE / "seeded")
    s5, p5 = pkg.sub_sections["3.1"].paras["3.1.5"][6:], pkg.spec_sections["3.1"].paras["3.1.5"][6:]
    s6, p6 = pkg.sub_sections["3.1"].paras["3.1.6"][6:], pkg.spec_sections["3.1"].paras["3.1.6"][6:]
    reply = {"issues": [
        {"error_type": "sequence_contradiction", "submittal_quote": s5, "spec_quote": p5, "reason": "airflow, not pressure",
         "submittal_meets_spec": False},
        {"error_type": "setpoint_out_of_spec", "submittal_quote": s6, "spec_quote": p6, "reason": "this matches",
         "submittal_meets_spec": True}]}
    eng = en.make_engine("claude-haiku", sr.ReviewConfig(), guard=guard(tmp_path), client=fake_client([json.dumps(reply)]))
    r = srv.check_section(eng, pkg, "3.1", 2, "t", [])
    assert [c["sub_para"] for c in r["comments"]] == ["3.1.5"] and r["unresolved"] == []


def test_table_rules_find_every_planted_table_error_on_dev():
    for case in sorted((V2 / "dev").iterdir()):
        cands = {tuple(c.anchor) for c in srv.table_rules(srv.parse_package(case / "seeded"))}
        for e in json.loads((case / "seeded" / "labels.json").read_text(encoding="utf-8"))["errors"]:
            if e["anchors"][0][0] in ("points", "spec_points", "drawing"):
                assert any(tuple(a) in cands for a in e["anchors"]), (case.name, e["description"])


def test_agent_never_reads_the_labels(tmp_path):
    pkg = tmp_path / "pkg"
    shutil.copytree(DEV_CASE / "seeded", pkg)
    (pkg / "labels.json").unlink()

    class Echo:
        name, engine, last_usage, context = "echo", "echo", None, ""

        def generate(self, system, user, schema, tag="", prefix=""):
            return json.dumps({"issues": []}) if system is srv.PROSE_SYSTEM else json.dumps(
                {"verdict": "unresolved", "supporting_quote": "", "reason": "n/a"})
    a = srv.run_spec_review(DEV_CASE / "seeded", tmp_path / "a", Echo(), write_files=False)
    b = srv.run_spec_review(pkg, tmp_path / "b", Echo(), write_files=False)
    assert a["candidates"] == b["candidates"] and a["unresolved"] == b["unresolved"]


# ---- test set v2 ------------------------------------------------------------------

def test_v2_set_matches_the_generator_and_the_frozen_manifest():
    assert make_v2_sets.main(["--check"]) == 0
    man = json.loads((V2 / "datasets_v2.json").read_text(encoding="utf-8"))
    for info in man["cases"].values():
        for f, h in info["files"].items():
            assert make_v2_sets.sha256_bytes((ROOT / info["folder"] / f).read_bytes()) == h


def test_v2_set_size_split_and_error_coverage():
    man = json.loads((V2 / "datasets_v2.json").read_text(encoding="utf-8"))["cases"]
    assert len(man) >= 40
    splits = [c["split"] for c in man.values()]
    assert splits.count("dev") == 30 and splits.count("holdout") == 10
    types, hard = {}, set()
    for info in man.values():
        clean = json.loads((ROOT / info["folder"] / "clean" / "labels.json").read_text(encoding="utf-8"))
        seeded = json.loads((ROOT / info["folder"] / "seeded" / "labels.json").read_text(encoding="utf-8"))
        assert clean["errors"] == [] and seeded["errors"] and clean["lookalikes"]
        for e in seeded["errors"]:
            types[e["type"]] = types.get(e["type"], 0) + 1
            hard.update(e["hard"])
    assert set(types) == set(score_v2.ERROR_TYPES) and len(types) >= 8 and min(types.values()) >= 8
    assert {"long_document", "two_in_one_section", "lookalikes_nearby"} <= hard


def test_v2_documents_have_no_en_or_em_dashes():
    for p in V2.rglob("*"):
        if p.is_file() and p.suffix in (".txt", ".csv", ".json", ".md"):
            text = p.read_text(encoding="utf-8")
            assert chr(0x2013) not in text and chr(0x2014) not in text, p


# ---- holdout ----------------------------------------------------------------------

def test_holdout_v2_pins_match_and_tools_refuse_it_without_the_final_flag(tmp_path):
    assert validate_v2.holdout_problems("an-engine-with-no-final") == []
    held = next((V2 / "holdout").iterdir())
    assert srv.holdout_v2_folder(held / "seeded")
    copy = tmp_path / "copy"
    shutil.copytree(held / "clean", copy)
    assert srv.holdout_v2_folder(copy)  # recognized by its file hashes, not just its path
    with pytest.raises(srv.HoldoutRefused):
        srv.run_spec_review(copy, tmp_path / "out", None)
    assert srv.main(["--input", str(held / "seeded"), "--output", str(tmp_path / "o")]) == 2
    assert validate_v2.main(["--rules-only", "--cases", held.name]) == 2


def test_holdout_final_refuses_after_a_scorer_change(tmp_path, monkeypatch):
    fake = tmp_path / "score_v2.py"
    fake.write_text("changed\n", encoding="utf-8")
    monkeypatch.setattr(validate_v2, "SCORER", fake)
    assert any("score_v2.py changed" in p for p in validate_v2.holdout_problems("x"))


def test_holdout_final_runs_once_per_engine(tmp_path, monkeypatch):
    finals = tmp_path / "finals.json"
    finals.write_text(json.dumps({"claude-haiku": {"result_file": "r.json"}}), encoding="utf-8")
    monkeypatch.setattr(validate_v2, "FINALS", finals)
    assert any("already has a holdout final" in p for p in validate_v2.holdout_problems("claude-haiku"))
    assert not any("already" in p for p in validate_v2.holdout_problems("claude-sonnet"))


def test_v1_holdout_is_still_spent_and_untouched():
    import holdout
    assert holdout.untouched() == []
    assert holdout.registration().get("final_run")


# ---- scoring ----------------------------------------------------------------------

def _err(eid, anchors, kind="present", typ="setpoint_out_of_spec"):
    return {"error_id": eid, "type": typ, "kind": kind, "anchors": anchors, "hard": []}


def test_scoring_rules_caught_duplicate_wrong_and_absent():
    errors = [_err("E1", [["sub", "3.1.3", ""], ["spec", "3.1.3", ""]]),
              _err("E2", [["spec", "3.5.4", ""]], kind="absent", typ="interlock_missing"),
              _err("E3", [["points", "X", "io_type"]], typ="wrong_point_type")]
    comments = [{"source": "prose", "sub_para": "3.1.3", "spec_para": "3.1.3", "error_type": "setpoint_out_of_spec"},
                {"source": "prose", "sub_para": "", "spec_para": "3.1.3", "error_type": "setpoint_out_of_spec"},
                {"source": "prose", "sub_para": "3.5.3", "spec_para": "3.5.4", "error_type": "interlock_missing"},
                {"source": "prose", "sub_para": "3.2.1", "spec_para": "3.2.1", "error_type": "sequence_contradiction"},
                {"source": "table", "anchor": ["points", "X", "io_type"], "error_type": "wrong_point_type"}]
    s = score_v2.score_twin(comments, errors)
    assert set(s["caught"]) == {"E1", "E2", "E3"} and len(s["duplicates"]) == 1 and len(s["wrong"]) == 1
    agg = score_v2.aggregate([{"case": "c", "errors": errors, "seeded_comments": comments,
                               "clean_comments": [comments[3]]}])["totals"]
    assert agg["recall"] == 1.0 and agg["wrong"] == 2 and agg["comments_made"] == 5 and agg["wrong_rate"] == 0.4
    assert not agg["passes"]


def test_pass_bar_is_recall_090_and_wrong_rate_005():
    assert score_v2.RECALL_BAR == 0.90 and score_v2.WRONG_RATE_BAR == 0.05
    errors = [_err(f"E{i}", [["points", str(i), "alarm"]]) for i in range(20)]
    hits = [{"source": "table", "anchor": ["points", str(i), "alarm"], "error_type": "alarm_wrong_or_missing"} for i in range(18)]
    wrong = [{"source": "table", "anchor": ["points", "Z", "alarm"], "error_type": "alarm_wrong_or_missing"}]
    t = score_v2.aggregate([{"case": "c", "errors": errors, "seeded_comments": hits + wrong, "clean_comments": []}])["totals"]
    assert t["recall"] == 0.9 and t["wrong_rate"] == round(1 / 19, 4) and not t["passes"]
    t2 = score_v2.aggregate([{"case": "c", "errors": errors, "seeded_comments": hits, "clean_comments": []}])["totals"]
    assert t2["passes"]


def test_changelog_states_the_v2_scoring_rules():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    v2 = text.split("## v2", 1)[1]
    for phrase in ("Recall", "Wrong comments", "0.90", "5 percent", "clean twin", "per error type"):
        assert phrase in v2, phrase
