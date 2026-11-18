"""Early evaluation for the Controls Submittal Review Agent (P2-C5).

Runs the agent on one fixture set, then scores the result against that set's
error_labels.json. The agent never reads the labels; only this script does.
The agent never rates its own output: every check here passes or fails against
a seeded label or a fixed rule.

Checks:
  1. capture       at least four of every five seeded errors come out as
                   real_error comments with complete rule evidence
  2. wrong         wrong comments / all comments at or under 20 percent
  3. evidence      every comment carries complete rule-appropriate evidence
  4. convention    every labeled drafting convention came out as one
  5. phrases       no comment approves, rejects or tells the reviewer to
                   resubmit (fixed list of forbidden phrases)

Run from the repo root, with Ollama running:
  .venv\\Scripts\\python.exe tools\\eval_early.py --input tests\\fixtures\\seeded --output out_eval
Offline, against the recorded replies:
  .venv\\Scripts\\python.exe tools\\eval_early.py --input tests\\fixtures\\seeded --output out_eval --classifier recorded
"""

# Future (P2-C5): a reviewer rubric for how usable the comment wording is, separate from correctness.

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import submittal_review as sr  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

FORBIDDEN_PHRASES = sr.FORBIDDEN_PHRASES  # one list, owned by the agent since P4-C1
evidence_complete = sr.evidence_complete  # one definition, owned by the agent since P4-C1


# Build Guide: P2-C5
# Decision: score one run against its labels; every check is pass or fail
def score(state: dict, labels: dict) -> dict:
    seeded = {e["finding_id"] for e in labels.get("seeded_errors", [])}
    by_id = {c.finding.finding_id: c for c in state["classified_findings"]}
    comments = state["ordered_comments"]
    complete = {c.finding_id: evidence_complete(by_id[c.finding_id].finding) for c in comments}
    caught = {c.finding_id for c in comments if c.finding_id in seeded and complete[c.finding_id]}
    wrong = [c.finding_id for c in comments if c.finding_id not in seeded]
    need = math.ceil(0.8 * len(seeded))
    conventions = [e["finding_id"] for e in labels.get("expected_other_verdicts", [])
                   if e.get("verdict") == "drafting_convention"]
    missed_conventions = [f for f in conventions if f not in by_id or by_id[f].verdict != "drafting_convention"]
    flagged = [c.finding_id for c in comments
               if any(p in f"{c.reason} {c.suggested_fix}".lower() for p in FORBIDDEN_PHRASES)]
    rate = len(wrong) / len(comments) if comments else 0.0
    checks = {
        "capture": (len(caught) >= need if seeded else True, f"{len(caught)} of {len(seeded)} seeded errors caught"
                    + (f", need {need}" if seeded else ", clean set")),
        "wrong": (rate <= 0.20, f"{len(wrong)} wrong of {len(comments)} comments ({rate:.0%})"
                  + (f": {', '.join(wrong)}" if wrong else "")),
        "evidence": (all(complete.values()), f"{sum(complete.values())} of {len(comments)} comments complete"),
        "convention": (not missed_conventions, f"{len(conventions) - len(missed_conventions)} of {len(conventions)} "
                       "labeled conventions came out as conventions"),
        "phrases": (not flagged, "no forbidden phrases" if not flagged else f"forbidden phrase in {', '.join(flagged)}"),
    }
    counts = {v: sum(c.verdict == v for c in state["classified_findings"])
              for v in ("real_error", "drafting_convention", "unresolved")}
    return {"checks": checks, "verdict_counts": counts, "passed": all(ok for ok, _ in checks.values())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Early evaluation (P2-C5)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--classifier", choices=("ollama", "recorded"), default="ollama")
    ap.add_argument("--ollama-url", default=sr.DEFAULT_OLLAMA_URL)
    ap.add_argument("--config", default=str(sr.DEFAULT_CONFIG))
    args = ap.parse_args(argv)
    holdout.refuse(Path(args.input), "eval_early")  # P5-C2: tuning tools never touch the holdout
    config = sr.load_config(Path(args.config))
    client = (sr.OllamaClient(config, args.ollama_url) if args.classifier == "ollama"
              else sr.RecordedResponseClient(sr.DEFAULT_RESPONSES))
    state = sr.run_review(Path(args.input), Path(args.output), client, config, str(args.config))
    labels = json.loads((Path(args.input) / "error_labels.json").read_text(encoding="utf-8"))
    result = score(state, labels)
    print(f"[eval] {Path(args.input).name} with {client.name}")
    for name, (ok, detail) in result["checks"].items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<10} {detail}")
    print(f"  verdicts: {result['verdict_counts']}")
    print("EVAL PASS" if result["passed"] else "EVAL FAIL")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
