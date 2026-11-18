"""Evaluation set generator for the Controls Submittal Review Agent (P5-C2, P3-C2).

Writes generated evaluation sets under eval_sets/, each with a clean twin, that
vary panel count, controller type and whether a typical sheet (a drafting
convention) is used, so validation shows whether the agent works generally or
only on one drawing style. Each seeded set holds one seeded error per rule R1 to
R5, placed by a recorded seed, plus the unresolved network-point candidate and,
when a typical is used, one drafting-convention candidate.

Uses the same P0-C1 input grammar and the same PDF and workbook writers as the
fixture generator. Labels exist by construction (error_labels.json); the agent
never reads them. The holdout set is generated with everything else and then
sealed by tools/validate.py --register (P5-C2).

Run from the repo root:  python tools/make_eval_sets.py
Then freeze:             python tools/make_eval_sets.py --freeze-only
"""

# Future (P5-C2): a sanitized real submittal as a second, independent test.

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from make_fixtures import write_pdf, write_points  # noqa: E402

EVAL_GENERATOR_VERSION = "1.0.0"
EVAL_SCHEMA_VERSION = "1"  # same P0-C1 grammar and answer-file formats as the fixtures
EVAL_ROOT = ROOT / "eval_sets"
MANIFEST = EVAL_ROOT / "datasets.json"
HEADERS = ["tag", "controller", "terminal", "point_type", "description"]

# Build Guide: P5-C2
# Decision: development sets vary panel count, controller type and convention use; one holdout is set aside
CONTROLLERS = {  # controller type -> installed IO capacity per panel
    "ECY-600": {"AI": 8, "AO": 4, "DI": 8, "DO": 4},
    "ECY-S1000": {"AI": 16, "AO": 8, "DI": 16, "DO": 8},
    "PLC-1769": {"AI": 32, "AO": 16, "DI": 32, "DO": 16},
}
EVAL_SETS = [
    # name, panels, controller type, typical sheet used, seed, holdout
    ("dev_a", 3, "ECY-600", True, 11, False),
    ("dev_b", 4, "ECY-S1000", False, 22, False),
    ("dev_c", 2, "PLC-1769", True, 33, False),
    ("holdout_1", 5, "ECY-600", True, 9001, True),
]
POINTS = (
    ("SAT", "AI", "AI-01", "Supply air temperature"),
    ("RAT", "AI", "AI-02", "Return air temperature"),
    ("CHWV", "AO", "AO-01", "Chilled water valve"),
    ("SF-STS", "DI", "DI-01", "Supply fan status"),
    ("SF-CMD", "DO", "DO-01", "Supply fan command"),
)
OTHER_TYPE = {"AI": "DI", "AO": "DO", "DI": "AI", "DO": "AO"}


def panel_name(n: int) -> str:
    return f"CP-{n:02d}"


def tag(n: int, suffix: str) -> str:
    return f"AHU-{n:02d}-{suffix}"


# Build Guide: P5-C2, P3-C2
# Decision: one deterministic builder; the seed picks where each rule's error goes and is recorded in the labels
def build(n_panels: int, controller: str, typical: bool, seed: int, seeded: bool) -> dict:
    rng = random.Random(seed)
    cap = CONTROLLERS[controller]
    panels = list(range(1, n_panels + 1))
    r1_panel, r1_suffix = rng.choice(panels), rng.choice(["SAT", "RAT"])
    r2_panel, r2_point = rng.choice(panels), rng.choice(POINTS)
    r3_panel, r3_type = rng.choice(panels), rng.choice(["AI", "AO", "DI", "DO"])
    r4_panel = rng.choice(panels)
    r5_panel = rng.choice(panels)
    conv_panel = rng.choice(panels)

    index = [("G-001", "Drawing Index"), ("G-002", "Network Riser"), ("G-003", "Legend and General Notes")]
    for n in panels:
        index += [(f"M-1{n:02d}", f"AHU-{n:02d} Control Schematic"), (f"P-1{n:02d}", f"Panel {panel_name(n)} Layout"),
                  (f"IO-1{n:02d}", f"Panel {panel_name(n)} IO"), (f"W-1{n:02d}", f"Panel {panel_name(n)} Wiring")]
    if typical:
        index.append(("T-201", "Typical AHU Field Wiring"))
    titles = dict(index)
    if seeded:
        titles[f"IO-1{r4_panel:02d}"] = f"Panel {panel_name(r4_panel)} I/O"  # seeded R4

    all_tags = [tag(n, p[0]) for n in panels for p in POINTS]
    trunk = {n: 250 + 15 * n for n in panels}
    field = {n: 40 + 5 * n for n in panels}
    lines: dict[str, list[str]] = {
        "G-001": [f"INDEX: {num} | {t}" for num, t in index] + [f"SCOPE: {t} | DOCS=DRAWINGS,POINTS,SEQUENCE" for t in all_tags],
        "G-002": ["NOTE: BACNET IP TRUNK FROM BAS SWITCH TO EACH PANEL."]
                 + [f"CABLE: CBL-{n:03d} | LENGTH_FT: {trunk[n]}" for n in panels] + [f"REF: W-1{n:02d}" for n in panels],
        "G-003": ["NOTE: TAG FORMAT IS AHU-NN-POINT.", "NOTE: ALL CABLE LENGTHS IN FEET UNLESS NOTED."],
    }
    for n in panels:
        p = panel_name(n)
        lines[f"M-1{n:02d}"] = [f"NOTE: AHU-{n:02d} CONTROLLED BY PANEL {p}.", f"REF: IO-1{n:02d}"] + (
            ["REF: T-201"] if typical else [])
        used = {t: sum(1 for _, pt, _, _ in POINTS if pt == t) for t in cap}
        reserved = {t: (cap[t] - used[t] if seeded and n == r3_panel and t == r3_type else 0) for t in cap}  # seeded R3
        lines[f"P-1{n:02d}"] = [f"BOM: CONTROLLER {controller} {p} | QTY: 1", "BOM: 24VAC TRANSFORMER | QTY: 1",
                                f"CAPACITY: {p} | " + " | ".join(f"{t}={cap[t]}" for t in cap),
                                f"RESERVED: {p} | " + " | ".join(f"{t}={reserved[t]}" for t in cap)]
        lines[f"IO-1{n:02d}"] = [f"TAG: {tag(n, s)} | PANEL: {p} | TYPE: {t} | TERM: {term}"
                                 for s, t, term, _ in POINTS] + [f"REF: W-1{n:02d}"]
        w_trunk = round(trunk[n] * 1.2) if seeded and n == r5_panel else trunk[n]  # seeded R5: 20 percent longer
        lines[f"W-1{n:02d}"] = [f"CABLE: CBL-{n:03d} | LENGTH_FT: {w_trunk}", f"CABLE: CBL-1{n:02d} | LENGTH_FT: {field[n]}"]
    if typical:
        lines["T-201"] = ["TYPICAL: APPLIES_TO=" + ",".join(panel_name(n) for n in panels),
                          "NOTE: CABLE LENGTHS ON THIS TYPICAL ARE NOMINAL. FIELD LENGTHS PER PANEL WIRING SHEET.",
                          f"CABLE: CBL-1{conv_panel:02d} | LENGTH_FT: {round(field[conv_panel] * 0.75)}"]

    points = []
    for n in panels:
        for s, t, term, desc in POINTS:
            ptype = OTHER_TYPE[t] if seeded and n == r2_panel and s == r2_point[0] else t  # seeded R2
            points.append([tag(n, s), panel_name(n), term, ptype, desc])

    sequence = []
    for n in panels:
        p = panel_name(n)
        sat = "discharge air" if seeded and n == r1_panel and r1_suffix == "SAT" else tag(n, "SAT")  # seeded R1
        rat = "return air" if seeded and n == r1_panel and r1_suffix == "RAT" else tag(n, "RAT")
        sequence += [f"SEQ: {p} controls {sat} using {tag(n, 'CHWV')}",
                     f"SEQ: {p} starts {tag(n, 'SF-CMD')} and proves {tag(n, 'SF-STS')}", f"SEQ: {p} monitors {rat}"]
    sequence.append("SEQ: CP-01 reads AHU-01-OAT from the BAS network")

    errors = [] if not seeded else [
        {"finding_id": f"R1:{tag(r1_panel, r1_suffix)}:MISSING_FROM_SEQUENCE", "rule_id": "R1", "sheets": ["G-001"]},
        {"finding_id": f"R2:{panel_name(r2_panel)}:{r2_point[2]}:TYPE_MISMATCH", "rule_id": "R2",
         "sheets": [f"IO-1{r2_panel:02d}"]},
        {"finding_id": f"R3:{panel_name(r3_panel)}:{r3_type}", "rule_id": "R3", "sheets": [f"P-1{r3_panel:02d}"]},
        {"finding_id": f"R4:IO-1{r4_panel:02d}:TITLE_MISMATCH", "rule_id": "R4", "sheets": ["G-001", f"IO-1{r4_panel:02d}"]},
        {"finding_id": f"R5:CBL-{r5_panel:03d}", "rule_id": "R5", "sheets": ["G-002", f"W-1{r5_panel:02d}"]},
    ]
    others = [{"finding_id": "R1:AHU-01-OAT:NO_SCOPE", "verdict": "unresolved"}]
    if typical:
        others.insert(0, {"finding_id": f"R5:CBL-1{conv_panel:02d}", "verdict": "drafting_convention"})
    labels = {"generator": "make_eval_sets", "generator_version": EVAL_GENERATOR_VERSION, "seed": seed,
              "panels": n_panels, "controller": controller, "typical": typical,
              "seeded_errors": errors, "expected_other_verdicts": others}
    return {"index": index, "titles": titles, "lines": lines, "points": points, "sequence": sequence, "labels": labels}


def write_set(folder: Path, data: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    write_pdf(folder / "drawings.pdf", [(n, data["titles"][n], data["lines"][n]) for n, _ in data["index"]])
    write_points(folder / "points.xlsx", data["points"], HEADERS)
    (folder / "sequence.txt").write_text("\n".join(data["sequence"]) + "\n", encoding="utf-8")
    (folder / "error_labels.json").write_text(json.dumps(data["labels"], indent=2) + "\n", encoding="utf-8")


# Build Guide: P3-C2, P5-C2
# Decision: every evaluation set is frozen by SHA-256 with its generator version and seed
def snapshot() -> dict:
    sets = {}
    for name, panels, controller, typical, seed, holdout in EVAL_SETS:
        for suffix in ("", "_clean"):
            folder = EVAL_ROOT / f"{name}{suffix}"
            sets[folder.name] = {"seed": seed, "panels": panels, "controller": controller, "typical": typical,
                                 "holdout": holdout, "kind": "clean" if suffix else "seeded",
                                 "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                           for p in sorted(folder.iterdir()) if p.is_file()}}
    return {"generator": "make_eval_sets", "generator_version": EVAL_GENERATOR_VERSION,
            "fixture_schema_version": EVAL_SCHEMA_VERSION, "datasets": sets}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Generate and freeze the evaluation sets (P5-C2)")
    ap.add_argument("--freeze-only", action="store_true")
    args = ap.parse_args(argv)
    if not args.freeze_only:
        for name, panels, controller, typical, seed, _ in EVAL_SETS:
            write_set(EVAL_ROOT / name, build(panels, controller, typical, seed, seeded=True))
            write_set(EVAL_ROOT / f"{name}_clean", build(panels, controller, typical, seed, seeded=False))
    data = snapshot()
    data["frozen_on"] = date.today().isoformat()
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote and froze {len(data['datasets'])} evaluation sets at generator {EVAL_GENERATOR_VERSION} to {EVAL_ROOT}")


if __name__ == "__main__":
    main()
