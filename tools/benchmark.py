"""Regression benchmark for the Controls Submittal Review Agent (P4-C7).

Runs the agent over every frozen benchmark pair (a seeded set and its clean
twin), scores it against the labels, and writes benchmarks/results/<stamp>.json
tied to the dataset and generator version, the source hashes, the model and its
digest, and the config. Then it compares with benchmarks/baseline.json:

  a new version passes only if seeded errors caught does not drop and wrong
  comments do not rise (P4-C7). Precision, recall, clean-set comments,
  unresolved count and run time are recorded too (I7/I8).

--accept makes this run the new baseline, and refuses if it loses ground.
Nothing here changes review_config.json or any threshold (P4-C8).

Run from the repo root, with Ollama running:
  .venv\\Scripts\\python.exe tools\\benchmark.py
  .venv\\Scripts\\python.exe tools\\benchmark.py --accept
"""

# Future (P4-C7): the benchmark run automatically on every commit.

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import submittal_review as sr  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

FIX, EVAL = ROOT / "tests" / "fixtures", ROOT / "eval_sets"
BENCH = ROOT / "benchmarks"
# Build Guide: P4-C7, P5-C2
# Decision: the frozen benchmark is the P0-C3 fixtures plus the generated development sets and their clean twins
BENCHMARK_PAIRS = [(FIX / "seeded", FIX / "clean")] + [(EVAL / n, EVAL / f"{n}_clean") for n in ("dev_a", "dev_b", "dev_c")]


# Build Guide: P4-C7
# Decision: count distinct seeded errors caught, wrong comments, clean-set comments and unresolved, per set
def score_set(state: dict, labels: dict) -> dict:
    seeded = {e["finding_id"] for e in labels.get("seeded_errors", [])}
    by_id = {c.finding.finding_id: c for c in state["classified_findings"]}
    issued = [c.finding_id for c in state["ordered_comments"]]
    tp = len({f for f in issued if f in seeded and sr.evidence_complete(by_id[f].finding)})
    return {"seeded": len(seeded), "tp": tp, "fn": len(seeded) - tp, "fp": len(issued) - tp,
            "comments": len(issued), "unresolved": len(state["unresolved_findings"]),
            "conventions": len(state["convention_findings"])}


def totals(per_set: list[dict]) -> dict:
    seeded = [s for s in per_set if s["kind"] == "seeded"]
    clean = [s for s in per_set if s["kind"] == "clean"]
    tp, fn, fp = (sum(s[k] for s in seeded) for k in ("tp", "fn", "fp"))
    return {"seeded_errors": tp + fn, "caught": tp, "missed": fn, "wrong_comments": fp,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "clean_set_comments": sum(s["comments"] for s in clean),
            "unresolved": sum(s["unresolved"] for s in per_set),
            "seconds": round(sum(s["seconds"] for s in per_set), 1)}


# Build Guide: P4-C7
# Decision: replace the current version only if caught does not drop and wrong comments do not rise
def compare(new: dict, baseline: dict, new_sets=None, baseline_sets=None) -> list[str]:
    if new_sets is not None and baseline_sets is not None and new_sets != baseline_sets:
        return [f"the baseline covers different sets ({', '.join(baseline_sets)}); "
                "accept a new baseline on the current sets first"]
    problems = []
    if new["caught"] < baseline["caught"]:
        problems.append(f"seeded errors caught dropped {baseline['caught']} -> {new['caught']}")
    if new["wrong_comments"] > baseline["wrong_comments"]:
        problems.append(f"wrong comments rose {baseline['wrong_comments']} -> {new['wrong_comments']}")
    return problems


def run_benchmark(client, config: sr.ReviewConfig, config_path: Path, runs_dir: Path) -> dict:
    per_set = []
    for pair in BENCHMARK_PAIRS:
        for kind, folder in zip(("seeded", "clean"), pair):
            holdout.refuse(folder, "benchmark")  # P5-C2: the holdout is never a benchmark set
            started = time.monotonic()
            state = sr.run_review(folder, runs_dir, client, config, str(config_path),
                                  hashlib.sha256(config_path.read_bytes()).hexdigest())
            labels = json.loads((folder / "error_labels.json").read_text(encoding="utf-8"))
            meta = state["run_metadata"]
            per_set.append({"set": folder.name, "kind": kind, "dataset": meta.dataset, "seconds": time.monotonic() - started,
                            "source_hashes": {k: v["sha256"] for k, v in meta.source_files.items()},
                            **score_set(state, labels)})
    return {"recorded_at": datetime.now().isoformat(timespec="seconds"), "model": client.name,
            "model_digest": getattr(client, "model_digest", "n/a"), "prompt_version": sr.PROMPT_VERSION,
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "config_values": json.loads(config.model_dump_json()), "sets": [s["set"] for s in per_set],
            "per_set": per_set, "totals": totals(per_set)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Regression benchmark (P4-C7)")
    ap.add_argument("--classifier", choices=("ollama", "recorded"), default="ollama")
    ap.add_argument("--ollama-url", default=sr.DEFAULT_OLLAMA_URL)
    ap.add_argument("--config", default=str(sr.DEFAULT_CONFIG))
    ap.add_argument("--bench-dir", default=str(BENCH))
    ap.add_argument("--accept", action="store_true", help="make this run the baseline (refused if it loses ground)")
    args = ap.parse_args(argv)
    bench, config_path = Path(args.bench_dir), Path(args.config)
    config = sr.load_config(config_path)
    client = (sr.OllamaClient(config, args.ollama_url) if args.classifier == "ollama"
              else sr.RecordedResponseClient(sr.DEFAULT_RESPONSES))
    record = run_benchmark(client, config, config_path, bench / "runs")
    (bench / "results").mkdir(parents=True, exist_ok=True)
    stamp, n = datetime.now().strftime("%Y%m%d_%H%M%S"), 2
    out = bench / "results" / f"bench_{stamp}.json"
    while out.exists():  # never overwrite an earlier result
        out, n = bench / "results" / f"bench_{stamp}_{n}.json", n + 1
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    t = record["totals"]
    print(f"[benchmark] {record['model']}: caught {t['caught']} of {t['seeded_errors']}, wrong {t['wrong_comments']}, "
          f"clean-set comments {t['clean_set_comments']}, unresolved {t['unresolved']}, precision {t['precision']}, "
          f"recall {t['recall']}, {t['seconds']} s -> {out.name}")
    baseline_path = bench / "baseline.json"
    problems = []
    if baseline_path.is_file():
        base = json.loads(baseline_path.read_text(encoding="utf-8"))
        problems = compare(t, base["totals"], record["sets"], base.get("sets", ["seeded", "clean"]))
        print("BENCHMARK PASS: no ground lost against the baseline" if not problems
              else "BENCHMARK FAIL: " + "; ".join(problems))
    elif not args.accept:
        print("No baseline yet. Run again with --accept to set this result as the baseline.")
    if args.accept and problems and problems[0].startswith("the baseline covers different sets"):
        problems = []  # a new benchmark set list needs a fresh baseline; that is a person's choice, logged here
        print("The benchmark sets changed, so this run starts a new baseline.")
    if args.accept:
        if problems:
            print("Not accepted: a new baseline may not lose ground.")
            return 1
        shutil.copyfile(out, baseline_path)
        print(f"Baseline set to {out.name}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
