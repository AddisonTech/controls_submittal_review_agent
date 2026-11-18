"""Phase 1 tests: the foundation decisions P1-C1 to P1-C5.

P1-C1 memory: no state carries from one run to the next; same input, same comments.
P1-C2 reasoning: fixed pipeline; the classifier is called only inside N7.
P1-C3 feedback: thresholds and limits come from a config file a person edits and every run logs.
P1-C4 architecture: one agent, nine nodes, one straight line.
P1-C5 interaction: one command, one input folder, one output folder, no prompts.

Run from the repo root:  python -m pytest -q
"""


from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import submittal_review as sr

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"
SEEDED, CLEAN = FIX / "seeded", FIX / "clean"
RESPONSES = FIX / "recorded_responses.json"


def write_config(tmp_path: Path, **values) -> Path:
    data = json.loads((ROOT / "review_config.json").read_text(encoding="utf-8"))
    data.update(values)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def comment_ids(state) -> list[str]:
    return [c.finding_id for c in state["ordered_comments"]]


def report_body(state) -> str:
    """The report text without the run-specific header lines."""
    lines = Path(state["review_outputs"].report_txt_path).read_text(encoding="utf-8").splitlines()
    return "\n".join(l for l in lines if not l.startswith(("Run:", "Input:")))


class CountingClient(sr.RecordedResponseClient):
    """Recorded replies that also count every call, to prove where the model is used."""

    def __init__(self, path: Path):
        super().__init__(path)
        self.calls = 0

    def classify(self, *args, **kwargs):
        self.calls += 1
        return super().classify(*args, **kwargs)


# ---- P1-C3: config file ------------------------------------------------------

def test_shipped_config_matches_the_build_guide_defaults():
    cfg = sr.load_config(ROOT / "review_config.json")
    assert (cfg.spare_io_threshold_pct, cfg.cable_length_tolerance_pct) == (15, 10)
    assert (cfg.temperature, cfg.model_timeout_seconds, cfg.model_attempts) == (0, 120, 2)
    assert (cfg.max_prompt_tokens, cfg.max_context_tokens) == (4096, 3000)
    assert (cfg.max_pdf_pages, cfg.max_suspected_findings) == (250, 150)
    assert cfg.model_name
    assert cfg == sr.ReviewConfig()


def test_config_has_no_severity_weights_or_ordering():
    fields = set(sr.ReviewConfig.model_fields)
    assert not any("severity" in f or "weight" in f or "order" in f for f in fields)


@pytest.mark.parametrize("values", [
    {"spare_io_threshold_pct": 0},
    {"cable_length_tolerance_pct": 100},
    {"model_attempts": 3},
    {"model_timeout_seconds": 0},
    {"max_context_tokens": 5000},
    {"max_pdf_pages": -1},
    {"model_name": ""},
    {"severity_weights": {"R1": 2}},
    {"cable_tolerance_pct": 10},
])
def test_bad_config_stops_the_run_before_any_node(tmp_path, values):
    with pytest.raises(ValueError):
        sr.load_config(write_config(tmp_path, **values))


def test_missing_or_broken_config_file_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError):
        sr.load_config(tmp_path / "nope.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        sr.load_config(broken)


def test_cable_tolerance_comes_from_config(tmp_path):
    loose = sr.ReviewConfig(cable_length_tolerance_pct=20.0)
    state = sr.run_review(SEEDED, tmp_path, sr.RecordedResponseClient(RESPONSES), loose)
    found = {f.finding_id for f in state["suspected_findings"]}
    assert "R5:CBL-001" not in found  # 15.6 percent passes a 20 percent tolerance
    assert "R5:CBL-001" in comment_ids(sr.run_review(SEEDED, tmp_path, sr.RecordedResponseClient(RESPONSES)))


def test_spare_threshold_comes_from_config(tmp_path):
    strict = sr.ReviewConfig(spare_io_threshold_pct=80.0)
    found = {f.finding_id for f in sr.run_review(SEEDED, tmp_path, sr.RecordedResponseClient(RESPONSES),
                                                 strict)["suspected_findings"]}
    default = {f.finding_id for f in sr.run_review(SEEDED, tmp_path, sr.RecordedResponseClient(RESPONSES))[
        "suspected_findings"]}
    assert {f for f in found if f.startswith("R3:")} > {f for f in default if f.startswith("R3:")}


def test_config_changes_never_reorder_comments(tmp_path):
    default = sr.run_review(SEEDED, tmp_path, sr.RecordedResponseClient(RESPONSES))
    other = sr.run_review(SEEDED, tmp_path, sr.RecordedResponseClient(RESPONSES),
                          sr.ReviewConfig(model_timeout_seconds=30, max_suspected_findings=30))
    assert [c.rule_id for c in default["ordered_comments"]] == ["R1", "R2", "R3", "R4", "R5"]
    assert comment_ids(default) == comment_ids(other)


def test_run_log_records_the_config_used(tmp_path):
    import hashlib
    cfg_path = write_config(tmp_path, cable_length_tolerance_pct=12.5)
    sha = hashlib.sha256(cfg_path.read_bytes()).hexdigest()
    state = sr.run_review(SEEDED, tmp_path / "out", sr.RecordedResponseClient(RESPONSES),
                          sr.load_config(cfg_path), str(cfg_path), sha)
    log = Path(state["review_outputs"].run_log_path).read_text(encoding="utf-8")
    assert f"config_file: {cfg_path}" in log
    assert f"config_sha256: {sha}" in log
    assert '"cable_length_tolerance_pct":12.5' in log


# ---- P1-C1: no memory across runs --------------------------------------------

def test_same_input_gives_the_same_report_every_run(tmp_path):
    first = sr.run_review(SEEDED, tmp_path, sr.RecordedResponseClient(RESPONSES))
    sr.run_review(CLEAN, tmp_path, sr.RecordedResponseClient(RESPONSES))  # an unrelated run in between
    second = sr.run_review(SEEDED, tmp_path, sr.RecordedResponseClient(RESPONSES))
    assert first["output_folder_path"] != second["output_folder_path"]
    assert report_body(first) == report_body(second)


def test_a_run_starts_from_only_what_the_cli_sets(tmp_path):
    state = sr.run_review(CLEAN, tmp_path, sr.RecordedResponseClient(RESPONSES))
    node_fields = set(sr.ReviewState.__annotations__) - {"submittal_folder_path", "output_folder_path",
                                                          "run_metadata", "review_config"}
    assert node_fields <= set(state)  # every node field was written by this run's nodes


# ---- P1-C2 and P1-C4: fixed pipeline, one agent ------------------------------

def test_graph_is_nine_nodes_in_one_straight_line():
    graph = sr.build_graph(sr.RecordedResponseClient(RESPONSES)).get_graph()
    names = [n for n in graph.nodes if n not in ("__start__", "__end__")]
    assert names == [name for name, _ in sr.NODES] and len(names) == 9
    edges = sorted((e.source, e.target) for e in graph.edges)
    chain = ["__start__"] + names + ["__end__"]
    assert edges == sorted(zip(chain, chain[1:]))
    assert not any(e.conditional for e in graph.edges)


def test_classifier_is_called_only_inside_n7(tmp_path):
    client = CountingClient(RESPONSES)
    state = {"submittal_folder_path": str(SEEDED)}
    for step in (sr.n1_ingest, sr.n2_validate, sr.n3_extract, sr.n4_cross_reference, sr.n5_rule_checks,
                 sr.n6_gather_context):
        state.update(step(state))
    assert client.calls == 0
    state.update(sr.n7_classify(state, client))
    computable = [f for f in state["suspected_findings"] if not f.candidate_reason.startswith(sr.UNRESOLVED_INPUT)]
    assert client.calls == len(computable)


# ---- P1-C5: one command, no prompts ------------------------------------------

def test_cli_runs_without_any_prompt(tmp_path):
    proc = subprocess.run([sys.executable, "-m", "submittal_review", "--input", str(SEEDED), "--output", str(tmp_path),
                           "--classifier", "recorded"],
                          cwd=ROOT, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "[config] review_config.json" in proc.stdout
    assert proc.stdout.strip().splitlines()[-1].startswith("Done. Open ")


def test_cli_with_a_bad_config_fails_before_the_graph(tmp_path):
    bad = write_config(tmp_path, model_attempts=5)
    proc = subprocess.run([sys.executable, "-m", "submittal_review", "--input", str(SEEDED), "--output",
                           str(tmp_path / "out"), "--config", str(bad)],
                          cwd=ROOT, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
    assert proc.returncode != 0
    assert "[N1 ingest]" not in proc.stdout
    assert not (tmp_path / "out").exists()
