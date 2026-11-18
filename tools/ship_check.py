"""Ship checklist for the Controls Submittal Review Agent (P5-C6).

An update is safe to ship only when all of these hold:
  1. every test passes (node tests, parser ground truth, evidence schema,
     normalization collisions, versioned scoring)
  2. the P4-C7 benchmark runs and loses no ground against the baseline
  3. the P5-C2 holdout is unchanged since registration and no tuning run used it
  4. the run log still traces every comment to its rule, its quoted text and its
     model call
and the latest validation records whether the model beats the rules alone; if it
does not, the rules-only variant is a defensible shipping choice.

Run from the repo root, with Ollama running:
  .venv\\Scripts\\python.exe tools\\ship_check.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import submittal_review as sr  # noqa: E402
import benchmark  # noqa: E402
import holdout  # noqa: E402
import validate  # noqa: E402

TUNING_RUN_DIRS = ("benchmarks/runs", "validation/runs", "out", "out_eval")


# Build Guide: P5-C6
# Decision: no tuning run may have read the holdout; only validation/final_runs may
def holdout_runs(base: Path = ROOT, dirs=TUNING_RUN_DIRS) -> list[str]:
    names = {c["folder"] for c in holdout.registration().get("cases", {}).values()}
    hits = []
    for d in dirs:
        for log in (base / d).glob("run_*/run_log.txt"):
            line = next((l for l in log.read_text(encoding="utf-8").splitlines() if l.startswith("input_folder:")), "")
            if Path(line.split(":", 1)[-1].strip()).name in names:
                hits.append(str(log.relative_to(base)))
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Ship checklist (P5-C6)")
    ap.add_argument("--classifier", choices=("ollama", "recorded"), default="ollama")
    ap.add_argument("--skip-pytest", action="store_true", help="used by the test suite itself")
    ap.add_argument("--bench-dir", default=str(benchmark.BENCH))
    ap.add_argument("--validation-dir", default=str(validate.OUT))
    args = ap.parse_args(argv)
    checks: list[tuple[str, bool, str]] = []

    if not args.skip_pytest:
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True)
        checks.append(("1 tests", proc.returncode == 0, (proc.stdout.strip().splitlines() or ["no output"])[-1]))
    else:
        checks.append(("1 tests", True, "skipped by --skip-pytest"))

    bench_args = ["--classifier", args.classifier, "--bench-dir", args.bench_dir]
    has_baseline = (Path(args.bench_dir) / "baseline.json").is_file()
    code = benchmark.main(bench_args) if has_baseline else 1
    checks.append(("2 benchmark", has_baseline and code == 0,
                   "no ground lost" if has_baseline and code == 0 else
                   "no baseline (run tools\\benchmark.py --accept)" if not has_baseline else "lost ground"))

    changed, used = holdout.untouched(), holdout_runs()
    checks.append(("3 holdout", not changed and not used,
                   "unchanged and unused" if not changed and not used else "; ".join(changed + [f"used by {u}" for u in used])))

    config = sr.load_config(sr.DEFAULT_CONFIG)
    client = (sr.OllamaClient(config) if args.classifier == "ollama" else sr.RecordedResponseClient(sr.DEFAULT_RESPONSES))
    with tempfile.TemporaryDirectory() as tmp:
        state = sr.run_review(validate.FIX / "seeded", Path(tmp), client, config)
        trace = validate.trace_problems(state)
    checks.append(("4 trace", not trace and bool(state["ordered_comments"]),
                   f"{len(state['ordered_comments'])} comments traced" if not trace else "; ".join(trace)))

    # P5-C1 / P5-C6: the latest development validation must have passed; a failed one is not shippable
    results = sorted((Path(args.validation_dir) / "results").glob("validate_*.json"))
    latest = json.loads(results[-1].read_text(encoding="utf-8")) if results else None
    passed = bool(latest) and latest.get("failed") == []
    checks.append(("5 validation", passed,
                   f"{results[-1].name} passed" if passed else
                   "no validation result yet (run tools\\validate.py)" if not latest else
                   f"{results[-1].name}: " + "; ".join(latest.get("failed") or ["no verdict recorded"])))
    note = latest["conclusion"] if latest else "no validation result yet"
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<12} {detail}")
    print(f"  model vs rules only: {note}")
    ok = all(c[1] for c in checks)
    print("SHIP CHECK PASS" if ok else "SHIP CHECK FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
