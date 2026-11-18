"""Validation for the Controls Submittal Review Agent (P5-C1, P5-C2).

Runs every always-run scenario: the P0-C3 fixtures, every generated development
set and its clean twin, and the malformed set. Scores the agent against labels
it never sees, by the I8 scoring spec, and scores the rules-only baseline (every
R1 to R5 finding issued as a comment, no model step) from the same runs.

  TP  distinct seeded errors issued as real_error with the right rule and
      complete rule evidence
  FN  seeded errors minus TP (conventions, unresolved and never-surfaced count)
  FP  issued comments that match no seeded error or lack complete evidence
  Recall = TP/(TP+FN) >= 0.80; Precision = TP/(TP+FP) >= 0.80
  Zero comments on a seeded set: precision N/A, recall 0, FAIL
  Every clean twin must have zero comments (strict)
  Every comment must trace to its rule, its quoted text and its model call; a
  failed trace fails the run even when TP is high.

Results go to validation/results/. Counts are reported per rule plus totals;
percentages are never averaged across sets.

  .venv\\Scripts\\python.exe tools\\validate.py                 development sets
  .venv\\Scripts\\python.exe tools\\validate.py --register      pre-register the holdout (once)
  .venv\\Scripts\\python.exe tools\\validate.py --final         score the holdout, once
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import submittal_review as sr  # noqa: E402
import holdout  # noqa: E402

FIX, EVAL = ROOT / "tests" / "fixtures", ROOT / "eval_sets"
DEV_PAIRS = [(FIX / "seeded", FIX / "clean")] + [(EVAL / n, EVAL / f"{n}_clean") for n in ("dev_a", "dev_b", "dev_c")]
MALFORMED = FIX / "malformed"
OUT = ROOT / "validation"
LIMITATIONS = [
    "Generated drawings are cleaner than real ones; extraction from a real exported set is unproven.",
    "The blind holdout seeded by a working controls engineer does not exist yet; every result is graded "
    "against errors the student seeded through the generator.",
    "Version one reads text only; errors in drawing geometry are out of reach.",
]


def labels_for(folder: Path) -> dict:
    return json.loads((folder / "error_labels.json").read_text(encoding="utf-8"))


def _empty() -> dict:
    return {r: {"tp": 0, "fn": 0, "fp": 0} for r in sr.RULE_IDS}


# Build Guide: P5-C1
# Decision: I8 scoring per rule; the same run scores the agent and the rules-only baseline
def score(state: dict, labels: dict) -> dict:
    seeded = {e["finding_id"]: e["rule_id"] for e in labels.get("seeded_errors", [])}
    by_id = {c.finding.finding_id: c for c in state["classified_findings"]}
    held = {c.finding.finding_id for c in state["unresolved_findings"] if c.reason.startswith("not issued:")}
    agent, rules = _empty(), _empty()
    issued = [c.finding_id for c in state["ordered_comments"]]
    caught = {f for f in issued if f in seeded and f.startswith(seeded[f] + ":") and sr.evidence_complete(by_id[f].finding)}
    for fid, rule in seeded.items():
        agent[rule]["tp" if fid in caught else "fn"] += 1
    for fid in issued:
        if fid not in caught:
            agent[by_id[fid].finding.rule_id]["fp"] += 1
    found = {f.finding_id: f for f in state["suspected_findings"]}
    for fid, rule in seeded.items():
        ok = fid in found and sr.evidence_complete(found[fid])
        rules[rule]["tp" if ok else "fn"] += 1
    for fid, f in found.items():
        if fid not in seeded or not sr.evidence_complete(f):
            rules[f.rule_id]["fp"] += 1
    confusion = {}
    for fid in seeded:
        c = by_id.get(fid)
        confusion[fid] = ("caught" if fid in caught else "never surfaced by the rules" if c is None
                          else "held back for incomplete evidence" if fid in held
                          else "called a drafting convention" if c.verdict == "drafting_convention" else "left unresolved")
    return {"agent": agent, "rules_only": rules, "confusion": confusion,
            "wrong_comments": [f for f in issued if f not in caught],
            "conventions": len(state["convention_findings"]), "unresolved": len(state["unresolved_findings"])}


def totals(per_rule: dict) -> dict:
    tp, fn, fp = (sum(v[k] for v in per_rule.values()) for k in ("tp", "fn", "fp"))
    return {"tp": tp, "fn": fn, "fp": fp, "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None}


def add(into: dict, more: dict) -> None:
    for r in sr.RULE_IDS:
        for k in ("tp", "fn", "fp"):
            into[r][k] += more[r][k]


# Build Guide: P5-C1, P4-C3
# Decision: every comment traces to its rule, its quoted text and its model call, or the run fails
def trace_problems(state: dict) -> list[str]:
    run_dir = Path(state["output_folder_path"])
    fired = {e["finding_id"] for e in map(json.loads, (run_dir / "audit_log.jsonl").read_text(encoding="utf-8").splitlines())
             if e["event"] == "rule_fired"}
    calls = {e["finding_id"]: e for e in map(json.loads, (run_dir / "classify_log.jsonl").read_text(encoding="utf-8").splitlines())}
    by_id = {c.finding.finding_id: c for c in state["classified_findings"]}
    problems = []
    for c in state["ordered_comments"]:
        if c.finding_id not in fired:
            problems.append(f"{c.finding_id}: no rule_fired entry in the audit log")
        if not calls.get(c.finding_id, {}).get("attempts"):
            problems.append(f"{c.finding_id}: no model call in the classify log")
        if not c.supporting_quote:
            problems.append(f"{c.finding_id}: no supporting quote")
        if not sr.evidence_complete(by_id[c.finding_id].finding):
            problems.append(f"{c.finding_id}: evidence incomplete for {c.rule_id}")
    return problems


def conclusion(agent: dict, rules: dict) -> str:
    if agent["tp"] < rules["tp"]:
        lost = rules["tp"] - agent["tp"]
        cut = rules["fp"] - agent["fp"]
        return (f"The model step lost {lost} seeded error(s) the rules alone caught, while cutting {cut} wrong "
                f"comment(s). If that trade is not worth it, the rules-only variant is a defensible shipping choice.")
    if agent["fp"] < rules["fp"]:
        return (f"The model step cut wrong comments from {rules['fp']} to {agent['fp']} without losing seeded errors, "
                f"so it adds measurable value over the rules alone.")
    return "The model step made no measurable difference; the rules were the answer and the model was extra complexity."


def run_pairs(pairs, client, config, runs_dir: Path) -> dict:
    agent, rules = _empty(), _empty()
    sets, problems = [], []
    for seeded_dir, clean_dir in pairs:
        for kind, folder in (("seeded", seeded_dir), ("clean", clean_dir)):
            started = time.monotonic()
            state = sr.run_review(folder, runs_dir, client, config)
            result = score(state, labels_for(folder))
            trace = trace_problems(state)
            comments = len(state["ordered_comments"])
            entry = {"set": folder.name, "kind": kind, "dataset": state["run_metadata"].dataset,
                     "source_hashes": {k: v["sha256"] for k, v in state["run_metadata"].source_files.items()},
                     "comments": comments, "seconds": round(time.monotonic() - started, 1),
                     "trace_problems": trace, **result}
            if kind == "seeded":
                add(agent, result["agent"])
                add(rules, result["rules_only"])
                if comments == 0:
                    problems.append(f"{folder.name}: zero comments on a seeded set (precision N/A, recall 0)")
            elif comments:
                problems.append(f"{folder.name}: clean twin has {comments} comment(s), must be 0")
            problems += [f"{folder.name}: {p}" for p in trace]
            sets.append(entry)
    return {"sets": sets, "agent_per_rule": agent, "rules_only_per_rule": rules,
            "agent_totals": totals(agent), "rules_only_totals": totals(rules), "problems": problems}


# Build Guide: P5-C1
# Decision: the malformed set is an always-run scenario and must stop loudly at N2, naming page and column
def malformed_check(client, config, runs_dir: Path) -> list[str]:
    try:
        sr.run_review(MALFORMED, runs_dir, client, config)
    except ValueError as exc:
        text = str(exc)
        missing = [w for w in ("no text layer", "missing required column") if w not in text]
        return [f"malformed: stop message does not mention {', '.join(missing)}"] if missing else []
    return ["malformed: the run did not stop"]


def verdict(record: dict) -> list[str]:
    a = record["agent_totals"]
    problems = list(record["problems"])
    if a["recall"] is None or a["recall"] < 0.8:
        problems.append(f"recall {a['recall']} under 0.80")
    if a["precision"] is not None and a["precision"] < 0.8:
        problems.append(f"precision {a['precision']} under 0.80")
    return problems


def print_record(record: dict) -> None:
    print(f"[validate] {record['model']} on {', '.join(s['set'] for s in record['sets'])}")
    print("  rule   agent tp/fn/fp   rules-only tp/fn/fp")
    for r in sr.RULE_IDS:
        a, b = record["agent_per_rule"][r], record["rules_only_per_rule"][r]
        print(f"  {r}     {a['tp']}/{a['fn']}/{a['fp']}            {b['tp']}/{b['fn']}/{b['fp']}")
    a, b = record["agent_totals"], record["rules_only_totals"]
    print(f"  total  agent recall {a['recall']} precision {a['precision']} | "
          f"rules-only recall {b['recall']} precision {b['precision']}")
    print(f"  {record['conclusion']}")
    for p in record["failed"]:
        print(f"  FAIL  {p}")
    print("VALIDATION PASS" if not record["failed"] else "VALIDATION FAIL")


def register() -> int:
    if holdout.REGISTRATION.is_file() and holdout.registration().get("final_run"):
        print("This holdout was already scored. Generate a new hidden holdout before registering again.")
        return 1
    manifest = json.loads((EVAL / "datasets.json").read_text(encoding="utf-8"))
    cases = {}
    for name, info in manifest["datasets"].items():
        if info.get("holdout"):
            files = info["files"]
            cases[name] = {"folder": name, "kind": info["kind"],
                           "inputs": {k: v for k, v in files.items() if k in sr.REQUIRED_FILES.values()},
                           "labels": {"error_labels.json": files["error_labels.json"]}}
    reg = {"registered_on": date.today().isoformat(), "generator_version": manifest["generator_version"],
           "metric_script_sha256": holdout.sha256(holdout.METRIC_SCRIPT), "cases": cases, "final_run": None}
    holdout.REGISTRATION.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")
    print(f"Registered {len(cases)} holdout cases and the metric script. Score them once with --final.")
    return 0


# Build Guide: P5-C2
# Decision: the holdout is scored once, only if it and the metric script are unchanged since registration
def final(client, config) -> int:
    reg = holdout.registration()
    if not reg:
        print("No holdout registered.")
        return 1
    if reg.get("final_run"):
        print(f"The holdout was already scored on {reg['final_run']['at']}. One final evaluation is allowed; "
              "generate a new hidden holdout for a later revision.")
        return 1
    changed = holdout.untouched()
    if changed:
        print("Refusing the final run: " + "; ".join(changed))
        return 1
    seeded = next(EVAL / c["folder"] for c in reg["cases"].values() if c["kind"] == "seeded")
    clean = next(EVAL / c["folder"] for c in reg["cases"].values() if c["kind"] == "clean")
    record = run_pairs([(seeded, clean)], client, config, OUT / "final_runs")
    record.update(model=client.name, model_digest=getattr(client, "model_digest", "n/a"), holdout=True,
                  conclusion=conclusion(record["agent_totals"], record["rules_only_totals"]), limitations=LIMITATIONS)
    record["failed"] = verdict(record)
    out = OUT / "results" / f"final_holdout_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    reg["final_run"] = {"at": datetime.now().isoformat(timespec="seconds"), "result": out.name}
    holdout.REGISTRATION.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")
    print_record(record)
    return 0 if not record["failed"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validation (P5-C1, P5-C2)")
    ap.add_argument("--classifier", choices=("ollama", "recorded"), default="ollama")
    ap.add_argument("--ollama-url", default=sr.DEFAULT_OLLAMA_URL)
    ap.add_argument("--config", default=str(sr.DEFAULT_CONFIG))
    ap.add_argument("--register", action="store_true", help="pre-register the holdout and this script")
    ap.add_argument("--final", action="store_true", help="score the registered holdout, once")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    if args.register:
        return register()
    config = sr.load_config(Path(args.config))
    client = (sr.OllamaClient(config, args.ollama_url) if args.classifier == "ollama"
              else sr.RecordedResponseClient(sr.DEFAULT_RESPONSES))
    if args.final:
        return final(client, config)
    for seeded_dir, clean_dir in DEV_PAIRS:
        holdout.refuse(seeded_dir, "validate")
        holdout.refuse(clean_dir, "validate")
    out = Path(args.out)
    record = run_pairs(DEV_PAIRS, client, config, out / "runs")
    record["problems"] += malformed_check(client, config, out / "runs")
    record.update(model=client.name, model_digest=getattr(client, "model_digest", "n/a"),
                  prompt_version=sr.PROMPT_VERSION, holdout=False,
                  conclusion=conclusion(record["agent_totals"], record["rules_only_totals"]), limitations=LIMITATIONS)
    record["failed"] = verdict(record)
    path = out / "results" / f"validate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print_record(record)
    print(f"  -> {path}")
    return 0 if not record["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
