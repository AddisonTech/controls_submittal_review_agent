"""Validation for test set v2: run an engine over the v2 pairs and score it with tools/score_v2.py.

  .venv\\Scripts\\python.exe tools\\validate_v2.py --engine gemma3:4b               every dev pair, local model
  .venv\\Scripts\\python.exe tools\\validate_v2.py --engine claude-haiku --limit 5  the first 5 dev pairs
  .venv\\Scripts\\python.exe tools\\validate_v2.py --rules-only                     rules-only baseline, no model
  .venv\\Scripts\\python.exe tools\\validate_v2.py --engine claude-sonnet --holdout-final
                                                                      the v2 holdout, once per engine

Every run writes validation/v2/results/<split>_<engine>_<stamp>.json and adds a row to validation/v2/RUNS.md
with its scores and its Claude spend. Holdout cases are refused unless --holdout-final is given; the final run
checks every holdout file and the scorer against the pins in validation/v2/HOLDOUT_V2.md and refuses an engine
that already has a final result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import engines as en  # noqa: E402
import score_v2  # noqa: E402
import spec_review as srv  # noqa: E402
import submittal_review as sr  # noqa: E402

V2 = ROOT / "validation" / "v2"
RESULTS, RUNS_DIR, RUNS_MD = V2 / "results", V2 / "runs", V2 / "RUNS.md"
HOLDOUT_MD, FINALS = V2 / "HOLDOUT_V2.md", V2 / "holdout_final_runs.json"
SCORER = ROOT / "tools" / "score_v2.py"
CLAUDE_LOCK = RUNS_DIR / ".claude_run.lock"


def manifest() -> dict:
    return json.loads((V2 / "datasets_v2.json").read_text(encoding="utf-8"))


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def select_cases(split: str, wanted: list[str] | None, limit: int | None) -> list[tuple[str, Path]]:
    cases = [(cid, ROOT / info["folder"]) for cid, info in manifest()["cases"].items() if info["split"] == split]
    if wanted:
        by = {cid: f for cid, f in cases}
        unknown = [w for w in wanted if w not in by]
        if unknown:
            held = [w for w in unknown if manifest()["cases"].get(w, {}).get("split") == "holdout"]
            if held:
                raise srv.HoldoutRefused(f"validate_v2: {', '.join(held)} are v2 holdout cases; they run only with --holdout-final")
            raise SystemExit(f"validate_v2: unknown case(s) {', '.join(unknown)}")
        cases = [(w, by[w]) for w in wanted]
    return cases[:limit] if limit else cases


# Build Guide: v2 holdout
# Decision: the final run checks every holdout file and the scorer against HOLDOUT_V2.md before any model call
def holdout_problems(engine: str) -> list[str]:
    text = HOLDOUT_MD.read_text(encoding="utf-8")
    problems = []
    m = re.search(r"Scorer: tools/score_v2.py sha256 `([0-9a-f]{64})`", text)
    if not m:
        problems.append("HOLDOUT_V2.md does not pin the scorer")
    elif sha256(SCORER) != m.group(1):
        problems.append("tools/score_v2.py changed since the holdout was pinned")
    pins = re.findall(r"^\| (\S+) \| (\S+) \| `([0-9a-f]{64})` \|$", text, re.M)
    if len(pins) != 100:
        problems.append(f"HOLDOUT_V2.md pins {len(pins)} files, expected 100 (10 cases x 2 twins x 5 files)")
    for _, rel, h in pins:
        p = ROOT / rel
        if not p.is_file() or sha256(p) != h:
            problems.append(f"{rel} does not match its pin")
    finals = json.loads(FINALS.read_text(encoding="utf-8")) if FINALS.is_file() else {}
    if engine in finals:
        problems.append(f"{engine} already has a holdout final ({finals[engine]['result_file']}); it is scored once")
    return problems


def _git() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              timeout=5).stdout.strip() or "n/a"
    except (OSError, subprocess.SubprocessError):
        return "n/a"


def _labels(folder: Path) -> dict:
    return json.loads((folder / "seeded" / "labels.json").read_text(encoding="utf-8"))


def run(engine_name: str, cases: list[tuple[str, Path]], split: str, workers: int, note: str, holdout_final: bool,
        ollama_url: str, config: sr.ReviewConfig, rules_only: bool = False) -> dict:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    label = f"{split}_{'rules-only' if rules_only else engine_name.replace(':', '-')}_{stamp}"
    guard = en.SpendGuard()
    spent0 = guard.spent()
    out_dir = RUNS_DIR / label
    results: dict[tuple[str, str], dict] = {}
    aborted = None
    started = time.monotonic()
    if rules_only:
        for cid, folder in cases:
            for twin in ("seeded", "clean"):
                pkg = srv.parse_package(folder / twin)
                r = {"candidates": [c.model_dump() for c in srv.table_rules(pkg)], "seconds": 0.0, "cost_usd": 0.0,
                     "unresolved": [], "dismissed": []}
                r["comments"] = score_v2.rules_only_comments(r)
                results[(cid, twin)] = r
    else:
        if engine_name not in en.CLAUDE_MODELS:
            workers = 1  # one local model call at a time (v1 P5-C5)
        engines_pool = [en.make_engine(engine_name, config, ollama_url, guard=guard, run_label=label) for _ in range(workers)]
        for e in engines_pool:
            e.preflight()
        free = list(engines_pool)
        lock = threading.Lock()
        stop = threading.Event()

        def job(cid: str, folder: Path, twin: str) -> tuple:
            if stop.is_set():
                return cid, twin, None
            with lock:
                eng = free.pop()
            try:
                r = srv.run_spec_review(folder / twin, out_dir / cid / twin, eng, config, tag=f"{cid}/{twin}",
                                        holdout_final=holdout_final)
                return cid, twin, r
            finally:
                with lock:
                    free.append(eng)

        jobs = [(cid, folder, twin) for cid, folder in cases for twin in ("seeded", "clean")]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(job, *j) for j in jobs]
            for f in as_completed(futures):
                try:
                    cid, twin, r = f.result()
                    if r is not None:
                        results[(cid, twin)] = r
                        print(f"[validate_v2] {cid}/{twin}: {len(r['comments'])} comments, {r['seconds']:.0f} s, "
                              f"${r['cost_usd']:.4f}; total spend ${guard.spent():.4f}")
                except en.BudgetExceeded as exc:
                    aborted = str(exc)
                    stop.set()
                    print(f"[stopped] {exc}")
    done = [(cid, folder) for cid, folder in cases if (cid, "seeded") in results and (cid, "clean") in results]
    pairs = [{"case": cid, "errors": _labels(folder)["errors"], "seeded_comments": results[(cid, "seeded")]["comments"],
              "clean_comments": results[(cid, "clean")]["comments"]} for cid, folder in done]
    base = [{"case": cid, "errors": _labels(folder)["errors"],
             "seeded_comments": score_v2.rules_only_comments(results[(cid, "seeded")]),
             "clean_comments": score_v2.rules_only_comments(results[(cid, "clean")])} for cid, folder in done]
    docs = [results[(cid, t)] for cid, _ in done for t in ("seeded", "clean")]
    spend = round(guard.spent() - spent0, 6)
    out = {"label": label, "split": split, "engine": "rules-only" if rules_only else engine_name,
           "model": en.CLAUDE_MODELS.get(engine_name, config.model_name) if not rules_only else "none",
           "effort": en.CLAUDE_EFFORT if engine_name in en.CLAUDE_MODELS and not rules_only else None,
           "prompt_version": srv.PROMPT_VERSION_V2, "agent_version": srv.VERSION, "git_commit": _git(),
           "scorer_sha256": sha256(SCORER), "note": note, "holdout_final": holdout_final,
           "cases_requested": [c for c, _ in cases], "cases_scored": [c for c, _ in done], "aborted": aborted,
           "documents": len(docs), "wall_seconds": round(time.monotonic() - started, 1),
           "seconds_per_document": round(sum(d["seconds"] for d in docs) / len(docs), 2) if docs else None,
           "spend_usd": spend, "cost_per_document_usd": round(spend / len(docs), 6) if docs else None,
           "total_spend_after_usd": round(guard.spent(), 6),
           "model_calls": sum(d.get("model_calls", 0) for d in docs),
           "failed_attempts": sum(d.get("failed_attempts", 0) for d in docs),
           "unresolved": sum(len(d["unresolved"]) for d in docs),
           "score": score_v2.aggregate(pairs), "rules_only_baseline": score_v2.aggregate(base)["totals"],
           "per_case": {cid: {"seeded": {k: results[(cid, "seeded")].get(k) for k in ("comments", "dismissed", "unresolved", "seconds", "cost_usd")},
                              "clean": {k: results[(cid, "clean")].get(k) for k in ("comments", "dismissed", "unresolved", "seconds", "cost_usd")}}
                        for cid, _ in done}}
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{label}.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    out["result_file"] = path.relative_to(ROOT).as_posix()
    _log_run(out)
    return out


def _log_run(out: dict) -> None:
    t = out["score"]["totals"]
    if not RUNS_MD.is_file():
        RUNS_MD.write_text("# v2 run log\n\nEvery v2 validation run, written by tools/validate_v2.py. Spend is Claude API "
                           "spend priced from each call's usage.\n\n| run | engine | split | pairs | recall | wrong rate | "
                           "caught/planted | wrong/made | s per doc | spend USD | total spend USD | prompt | note |\n"
                           "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n", encoding="utf-8")
    row = (f"| {out['label']} | {out['engine']} | {out['split']} | {len(out['cases_scored'])} | {t['recall']:.3f} | "
           f"{t['wrong_rate']:.3f} | {t['caught']}/{t['planted']} | {t['wrong']}/{t['comments_made']} | "
           f"{out['seconds_per_document'] or 0:.1f} | {out['spend_usd']:.4f} | {out['total_spend_after_usd']:.4f} | "
           f"{out['prompt_version']} | {(out['note'] or '') + (' ABORTED: budget' if out['aborted'] else '')} |\n")
    with RUNS_MD.open("a", encoding="utf-8") as fh:
        fh.write(row)


def print_report(out: dict) -> None:
    s, t = out["score"], out["score"]["totals"]
    print(f"\n=== {out['engine']} on v2 {out['split']} ({len(out['cases_scored'])} pairs, prompt {out['prompt_version']}) ===")
    print(f"recall {t['recall']:.3f} ({t['caught']} of {t['planted']} planted errors caught)")
    print(f"wrong comments {t['wrong']} of {t['comments_made']} comments made, rate {t['wrong_rate']:.3f} "
          f"({t['wrong_on_clean']} on clean twins, {t['wrong_on_seeded']} on seeded twins); duplicates {t['duplicates']}")
    print(f"bar: recall >= {score_v2.RECALL_BAR} and wrong rate <= {score_v2.WRONG_RATE_BAR}: "
          + ("PASS" if t["passes"] else "FAIL"))
    print(f"time per document {out['seconds_per_document']} s; spend ${out['spend_usd']:.4f} "
          f"(${out['cost_per_document_usd'] or 0:.5f} per document); total spend ${out['total_spend_after_usd']:.4f}")
    print(f"{'error type':24s} planted caught recall  wrong")
    for k, d in s["per_type"].items():
        print(f"{k:24s} {d['planted']:7d} {d['caught']:6d} {d['recall'] if d['recall'] is not None else '-':>6}  {d['wrong']:5d}")
    for h, d in s["per_hard"].items():
        print(f"hard: {h:18s} {d['planted']:7d} {d['caught']:6d} {d['recall']}")
    b = out["rules_only_baseline"]
    print(f"rules-only baseline from the same runs: recall {b['recall']:.3f}, wrong {b['wrong']} of {b['comments_made']} "
          f"(rate {b['wrong_rate']:.3f}); the rules cannot see sequence errors")
    print(f"result: {out['result_file']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Score an engine on test set v2")
    ap.add_argument("--engine", choices=en.ENGINE_CHOICES, default=en.DEFAULT_ENGINE)
    ap.add_argument("--cases", help="comma separated dev case ids")
    ap.add_argument("--limit", type=int, help="the first N dev cases")
    ap.add_argument("--workers", type=int, default=1, help="parallel documents for a Claude engine (local model: always 1)")
    ap.add_argument("--note", default="", help="why this run, written to RUNS.md")
    ap.add_argument("--rules-only", action="store_true", help="score the rules-only baseline without any model")
    ap.add_argument("--holdout-final", action="store_true", help="score the v2 holdout, once per engine")
    ap.add_argument("--ollama-url", default=sr.DEFAULT_OLLAMA_URL)
    ap.add_argument("--config", default=str(sr.DEFAULT_CONFIG))
    args = ap.parse_args(argv)
    config = sr.load_config(Path(args.config))
    try:
        if args.holdout_final:
            if args.rules_only or args.cases or args.limit:
                raise SystemExit("validate_v2: --holdout-final runs the whole holdout with a model; no other selection")
            problems = holdout_problems(args.engine)
            if problems:
                print("[stopped] holdout final refused:\n  " + "\n  ".join(problems))
                return 1
            cases, split = select_cases("holdout", None, None), "holdout"
        else:
            cases, split = select_cases("dev", args.cases.split(",") if args.cases else None, args.limit), "dev"
    except srv.HoldoutRefused as exc:
        print(f"[stopped] {exc}")
        return 2
    lock_held = False
    if args.engine in en.CLAUDE_MODELS and not args.rules_only:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        try:  # one Claude run at a time, so the spend guard sees every call
            fd = os.open(CLAUDE_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            lock_held = True
        except FileExistsError:
            print(f"[stopped] another Claude run holds {CLAUDE_LOCK}; delete it only if no run is active")
            return 1
    if args.holdout_final:  # recorded before the first call, so a stopped or crashed final still counts as the one run
        finals = json.loads(FINALS.read_text(encoding="utf-8")) if FINALS.is_file() else {}
        finals[args.engine] = {"result_file": "(started, no result yet)", "at": datetime.now().isoformat(timespec="seconds")}
        FINALS.write_text(json.dumps(finals, indent=2) + "\n", encoding="utf-8")
    try:
        out = run(args.engine, cases, split, max(1, args.workers), args.note, args.holdout_final, args.ollama_url, config,
                  rules_only=args.rules_only)
    except (sr.ModelUnavailableError, en.BudgetExceeded) as exc:
        print(f"[stopped] {exc}")
        return 1
    finally:
        if lock_held:
            CLAUDE_LOCK.unlink(missing_ok=True)
    if args.holdout_final:
        finals = json.loads(FINALS.read_text(encoding="utf-8")) if FINALS.is_file() else {}
        finals[args.engine] = {"result_file": out["result_file"], "at": datetime.now().isoformat(timespec="seconds"),
                               "recall": out["score"]["totals"]["recall"], "wrong_rate": out["score"]["totals"]["wrong_rate"],
                               "aborted": out["aborted"]}
        FINALS.write_text(json.dumps(finals, indent=2) + "\n", encoding="utf-8")
    print_report(out)
    return 0 if not out["aborted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
