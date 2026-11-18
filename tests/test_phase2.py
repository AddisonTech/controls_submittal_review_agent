"""Phase 2 tests: the core agent decisions P2-C1 to P2-C5.

P2-C1 model: N7 talks to a local Ollama model named in the config, temperature 0, fixed prompt version.
P2-C2 tools: localhost only, sources opened read only, nothing written outside the output folder.
P2-C3 errors: schema and word-for-word quote check, one retry, then unresolved; timeouts, missing
      model and size caps handled as decided; context filled in priority order within the budget.
P2-C4 flow: no streaming; one progress line per node.
P2-C5 early eval: the harness scores a run against the labels, never the agent itself.

The real OllamaClient is exercised against a fake Ollama server on 127.0.0.1, so no model is needed.
Run from the repo root:  python -m pytest -q
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import submittal_review as sr

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"
SEEDED, CLEAN = FIX / "seeded", FIX / "clean"
RESPONSES = FIX / "recorded_responses.json"
RECORDED = json.loads(RESPONSES.read_text(encoding="utf-8"))

sys.path.insert(0, str(ROOT / "tools"))
import eval_early  # noqa: E402


class FakeOllama:
    """A local stand-in for Ollama: /api/tags lists models, /api/generate answers from the recorded replies.

    overrides maps a finding_id to a list of behaviors used one per attempt: a dict reply, a raw string,
    or ("sleep", seconds) to stall past the timeout.
    """

    def __init__(self, models=("gemma3:4b",)):
        self.models, self.overrides, self.payloads = list(models), {}, []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, body: dict):
                data = json.dumps(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._send({"models": [{"name": m, "digest": f"sha256:{m.replace(':', '-')}"} for m in fake.models]})

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.payloads.append(payload)
                fid = re.search(r"^FINDING ID: (\S+)$", payload["prompt"], re.M).group(1)
                queue = fake.overrides.get(fid)
                behavior = queue.pop(0) if queue else RECORDED.get(fid, {"verdict": "unresolved", "reason": "none"})
                if isinstance(behavior, tuple) and behavior[0] == "sleep":
                    time.sleep(behavior[1])
                    behavior = RECORDED[fid]
                text = behavior if isinstance(behavior, str) else json.dumps(behavior)
                self._send({"model": payload["model"], "response": text, "done": True})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def ollama():
    fake = FakeOllama()
    yield fake
    fake.close()


def run(folder, out, client, config=None):
    return sr.run_review(folder, out, client, config or sr.ReviewConfig())


def by_id(state):
    return {c.finding.finding_id: c for c in state["classified_findings"]}


def file_hashes(folder: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}


# ---- P2-C1: local model from config ------------------------------------------

def test_full_run_through_the_ollama_client(tmp_path, ollama):
    client = sr.OllamaClient(sr.ReviewConfig(), ollama.url)
    state = run(SEEDED, tmp_path, client)
    assert [c.finding_id for c in state["ordered_comments"]] == [e["finding_id"] for e in
                                                                 json.loads((SEEDED / "error_labels.json").read_text())["seeded_errors"]]
    assert client.model_digest == "sha256:gemma3-4b"
    log = Path(state["review_outputs"].run_log_path).read_text(encoding="utf-8")
    assert "classifier_name: ollama:gemma3:4b" in log and "model_digest: sha256:gemma3-4b" in log
    assert f"prompt_version: {sr.PROMPT_VERSION}" in log


def test_model_name_and_temperature_come_from_config(tmp_path):
    fake = FakeOllama(models=("qwen2.5:3b",))
    try:
        cfg = sr.ReviewConfig(model_name="qwen2.5:3b", temperature=0)
        run(SEEDED, tmp_path, sr.OllamaClient(cfg, fake.url), cfg)
        assert {p["model"] for p in fake.payloads} == {"qwen2.5:3b"}
        assert all(p["options"]["temperature"] == 0 for p in fake.payloads)
    finally:
        fake.close()


def test_prompt_is_fixed_and_carries_the_version_inputs(tmp_path, ollama):
    run(SEEDED, tmp_path, sr.OllamaClient(sr.ReviewConfig(), ollama.url))
    first = {p["prompt"] for p in ollama.payloads}
    ollama.payloads.clear()
    run(SEEDED, tmp_path, sr.OllamaClient(sr.ReviewConfig(), ollama.url))
    assert {p["prompt"] for p in ollama.payloads} == first  # same set in, same prompts out
    assert all(p["prompt"].startswith(sr.PROMPT_HEADER) for p in ollama.payloads)


# ---- P2-C2: localhost only, read-only sources --------------------------------

@pytest.mark.parametrize("url", ["http://203.0.113.6:11434", "https://api.example.com", "http://ollama.lan:11434"])
def test_model_must_be_on_this_machine(url):
    with pytest.raises(ValueError, match="localhost"):
        sr.OllamaClient(sr.ReviewConfig(), url)


def test_sources_are_never_changed_and_nothing_is_written_beside_them(tmp_path, ollama):
    before = file_hashes(SEEDED)
    run(SEEDED, tmp_path / "out", sr.OllamaClient(sr.ReviewConfig(), ollama.url))
    assert file_hashes(SEEDED) == before


# ---- P2-C3: reply checks, retry, unresolved ----------------------------------

def test_bad_reply_then_good_reply_is_accepted_on_the_retry(tmp_path, ollama):
    ollama.overrides["R2:CP-01:AI-02:TYPE_MISMATCH"] = ["not json at all"]
    c = by_id(run(SEEDED, tmp_path, sr.OllamaClient(sr.ReviewConfig(), ollama.url)))["R2:CP-01:AI-02:TYPE_MISMATCH"]
    assert c.verdict == "real_error" and c.model_attempt_count == 2
    assert len(c.attempt_failures) == 1 and "ValidationError" in c.attempt_failures[0]


def test_quote_not_in_context_twice_goes_to_unresolved_and_the_run_continues(tmp_path, ollama):
    invented = {"verdict": "real_error", "supporting_quote": "TAG: MADE-UP | PANEL: CP-09", "reason": "invented"}
    ollama.overrides["R4:IO-102:TITLE_MISMATCH"] = [invented, invented]
    state = run(SEEDED, tmp_path, sr.OllamaClient(sr.ReviewConfig(), ollama.url))
    c = by_id(state)["R4:IO-102:TITLE_MISMATCH"]
    assert c.verdict == "unresolved" and c.model_attempt_count == 2
    assert "word for word" in c.reason
    assert len(state["ordered_comments"]) == 4  # the other seeded errors still come out


def test_error_or_convention_without_a_quote_is_a_failed_attempt():
    ctx = "CABLE: CBL-001 | LENGTH_FT: 340"
    assert sr.check_reply(sr.ModelReply(verdict="real_error", reason="x"), ctx)
    assert sr.check_reply(sr.ModelReply(verdict="drafting_convention", supporting_quote=" ", reason="x"), ctx)
    assert sr.check_reply(sr.ModelReply(verdict="unresolved", reason="x"), ctx) is None
    assert sr.check_reply(sr.ModelReply(verdict="real_error", supporting_quote="CABLE:  CBL-001 | LENGTH_FT:  340",
                                        reason="x"), ctx) is None  # spacing differences are not word differences


def test_a_quote_of_several_lines_passes_only_if_every_line_is_in_the_context():
    ctx = "[evidence E1 left]\nINDEX: IO-102 | Panel CP-02 IO\n\n[evidence E2 right]\nSHEET: IO-102 | TITLE: Panel CP-02 I/O"
    two = "INDEX: IO-102 | Panel CP-02 IO\nSHEET: IO-102 | TITLE: Panel CP-02 I/O"
    assert sr.check_reply(sr.ModelReply(verdict="real_error", supporting_quote=two, reason="x"), ctx) is None
    bad = "INDEX: IO-102 | Panel CP-02 IO\nSHEET: IO-102 | TITLE: Panel CP-09 I/O"
    assert "CP-09" in sr.check_reply(sr.ModelReply(verdict="real_error", supporting_quote=bad, reason="x"), ctx)


def test_the_rule_text_is_outside_the_quotable_context():
    item_state = {"submittal_folder_path": str(SEEDED)}
    for step in (sr.n1_ingest, sr.n2_validate, sr.n3_extract, sr.n4_cross_reference, sr.n5_rule_checks,
                 sr.n6_gather_context):
        item_state.update(step(item_state))
    item = next(i for i in item_state["findings_with_context"] if i.finding.rule_id == "R2")
    pkg = sr.build_prompt(item, sr.ReviewConfig())
    rule_text = sr.ModelReply(verdict="real_error", supporting_quote=item.finding.candidate_reason, reason="x")
    assert "do not quote" in pkg.prompt and sr.check_reply(rule_text, pkg.context_text)


def test_timeout_is_a_failed_attempt_and_two_strikes_is_unresolved(tmp_path, ollama):
    ollama.overrides["R3:CP-02:DO"] = [("sleep", 2), ("sleep", 2)]
    cfg = sr.ReviewConfig(model_timeout_seconds=1)
    started = time.monotonic()
    state = run(SEEDED, tmp_path, sr.OllamaClient(cfg, ollama.url), cfg)
    c = by_id(state)["R3:CP-02:DO"]
    assert c.verdict == "unresolved" and c.model_attempt_count == 2
    assert all("TimeoutError" in f for f in c.attempt_failures)
    assert time.monotonic() - started < 15
    assert len(state["ordered_comments"]) == 4


def test_never_more_than_two_attempts_per_finding(tmp_path, ollama):
    for fid in RECORDED:
        ollama.overrides[fid] = ["{}"] * 5
    state = run(SEEDED, tmp_path, sr.OllamaClient(sr.ReviewConfig(), ollama.url))
    computable = [c for c in state["classified_findings"] if c.model_attempt_count]
    assert len(ollama.payloads) == 2 * len(computable)
    assert all(c.verdict == "unresolved" for c in state["classified_findings"])


def test_missing_ollama_stops_before_any_node(tmp_path):
    client = sr.OllamaClient(sr.ReviewConfig(), "http://127.0.0.1:9")
    with pytest.raises(sr.ModelUnavailableError, match="Start Ollama"):
        run(SEEDED, tmp_path / "out", client)
    assert not (tmp_path / "out").exists()


def test_model_not_pulled_says_how_to_pull_it(tmp_path):
    fake = FakeOllama(models=("llama3.2:1b",))
    try:
        with pytest.raises(sr.ModelUnavailableError, match="ollama pull gemma3:4b"):
            run(SEEDED, tmp_path, sr.OllamaClient(sr.ReviewConfig(), fake.url))
        assert fake.payloads == []
    finally:
        fake.close()


def test_page_cap_stops_at_n2(tmp_path, ollama):
    with pytest.raises(sr.SizeLimitError, match="Split the package"):
        run(SEEDED, tmp_path, sr.OllamaClient(sr.ReviewConfig(max_pdf_pages=5), ollama.url),
            sr.ReviewConfig(max_pdf_pages=5))
    assert ollama.payloads == []


def test_finding_cap_stops_before_any_model_call(tmp_path, ollama):
    cfg = sr.ReviewConfig(max_suspected_findings=3)
    with pytest.raises(sr.SizeLimitError, match="7 suspected findings"):
        run(SEEDED, tmp_path, sr.OllamaClient(cfg, ollama.url), cfg)
    assert ollama.payloads == []


def test_context_is_filled_in_priority_order_and_omissions_are_recorded(tmp_path, ollama):
    cfg = sr.ReviewConfig(max_context_tokens=700)
    state = run(SEEDED, tmp_path, sr.OllamaClient(cfg, ollama.url), cfg)
    for c in state["classified_findings"]:
        if not c.model_attempt_count:
            continue
        evidence = [x for x in c.context_included if x.startswith("evidence")]
        assert evidence and c.context_included[:len(evidence)] == evidence  # mandatory evidence always first
        assert not any(x.startswith("evidence") for x in c.context_omitted)
        assert c.prompt_tokens_est <= cfg.max_prompt_tokens
    assert any(c.context_omitted for c in state["classified_findings"])
    log = [json.loads(l) for l in Path(state["review_outputs"].classify_log_path).read_text().splitlines()]
    assert any(entry["context_omitted"] for entry in log)


def test_evidence_over_the_budget_is_unresolved_without_a_model_call(tmp_path, ollama):
    cfg = sr.ReviewConfig(max_context_tokens=40)
    state = run(SEEDED, tmp_path, sr.OllamaClient(cfg, ollama.url), cfg)
    assert ollama.payloads == []
    assert all(c.verdict == "unresolved" for c in state["classified_findings"])
    assert any(c.reason.startswith(sr.CONTEXT_BUDGET_EXCEEDED) for c in state["classified_findings"])


# ---- P2-C4: not conversational ---------------------------------------------

def test_no_streaming_and_one_progress_line_per_node(tmp_path, ollama, capsys):
    run(SEEDED, tmp_path, sr.OllamaClient(sr.ReviewConfig(), ollama.url))
    assert ollama.payloads and all(p["stream"] is False for p in ollama.payloads)
    nodes = re.findall(r"^\[N(\d) ", capsys.readouterr().out, re.M)
    assert nodes == [str(n) for n in range(1, 10)]


def test_cli_with_no_ollama_stops_with_a_clear_message(tmp_path):
    proc = subprocess.run([sys.executable, "-m", "submittal_review", "--input", str(SEEDED), "--output",
                           str(tmp_path / "out"), "--ollama-url", "http://127.0.0.1:9"],
                          cwd=ROOT, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
    assert proc.returncode == 1
    assert "[stopped] Ollama is not reachable" in proc.stdout and "[N1" not in proc.stdout


# ---- P2-C5: early evaluation --------------------------------------------------

def test_early_eval_passes_on_the_seeded_set(tmp_path, ollama):
    state = run(SEEDED, tmp_path, sr.OllamaClient(sr.ReviewConfig(), ollama.url))
    result = eval_early.score(state, json.loads((SEEDED / "error_labels.json").read_text()))
    assert result["passed"], result["checks"]


def test_early_eval_passes_on_the_clean_twin(tmp_path, ollama):
    state = run(CLEAN, tmp_path, sr.OllamaClient(sr.ReviewConfig(), ollama.url))
    result = eval_early.score(state, json.loads((CLEAN / "error_labels.json").read_text()))
    assert result["passed"] and state["ordered_comments"] == []


def test_early_eval_fails_when_errors_are_missed(tmp_path, ollama):
    for fid in ("R1:AHU-02-SAT:MISSING_FROM_SEQUENCE", "R2:CP-01:AI-02:TYPE_MISMATCH"):
        ollama.overrides[fid] = [{"verdict": "unresolved", "reason": "x"}]
    state = run(SEEDED, tmp_path, sr.OllamaClient(sr.ReviewConfig(), ollama.url))
    result = eval_early.score(state, json.loads((SEEDED / "error_labels.json").read_text()))
    assert not result["checks"]["capture"][0] and not result["passed"]


def test_early_eval_fails_on_a_forbidden_phrase(tmp_path, ollama):
    # P4-C1 now stops approval language at N7 (a failed attempt), so it never reaches a comment ...
    ollama.overrides["R5:CBL-001"] = [dict(RECORDED["R5:CBL-001"], reason="The cable schedule is approved as drawn.")]
    state = run(SEEDED, tmp_path, sr.OllamaClient(sr.ReviewConfig(), ollama.url))
    c = {x.finding.finding_id: x for x in state["classified_findings"]}["R5:CBL-001"]
    assert "approve or reject language" in c.attempt_failures[0] and "approved" not in c.reason
    # ... and the early eval still fails any comment that carries it, as a second line of defense
    comment = state["ordered_comments"][-1]
    state["ordered_comments"][-1] = comment.model_copy(update={"reason": "The cable schedule is approved as drawn."})
    result = eval_early.score(state, json.loads((SEEDED / "error_labels.json").read_text()))
    assert not result["checks"]["phrases"][0]


def test_early_eval_fails_when_the_convention_becomes_an_error(tmp_path, ollama):
    ollama.overrides["R5:CBL-102"] = [dict(RECORDED["R5:CBL-102"], verdict="real_error")]
    state = run(SEEDED, tmp_path, sr.OllamaClient(sr.ReviewConfig(), ollama.url))
    result = eval_early.score(state, json.loads((SEEDED / "error_labels.json").read_text()))
    assert not result["checks"]["convention"][0] and not result["passed"]
    assert "1 wrong of 6" in result["checks"]["wrong"][1]  # 17 percent is inside the 20 percent limit on its own


def test_eval_command_runs_offline(tmp_path):
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "eval_early.py"), "--input", str(SEEDED), "--output",
                           str(tmp_path), "--classifier", "recorded"],
                          cwd=ROOT, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip().endswith("EVAL PASS")
