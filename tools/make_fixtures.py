"""Fixture generator for the Controls Submittal Review Agent (P0-C3, P3-C2).

Writes three synthetic submittal folders under tests/fixtures/:
  seeded/     one seeded error per rule R1 to R5, plus one drafting-convention
              candidate and one unresolved candidate
  clean/      the clean twin: same set with the five seeded errors removed
  malformed/  a PDF page with no text layer and a points list missing a column

Each good set also gets extraction_truth.json (what N3 should extract) and
error_labels.json (seeded errors and intended verdicts). The agent never
reads either answer file during a review; only the tests do.

This generator is a test tool. It is never shipped as part of the agent.
Run from the repo root:  python tools/make_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

GENERATOR_VERSION = "0.1.0"
# Build Guide: P3-C2
# Decision: explicit dataset versions; this generator uses no random numbers, so there is no seed to record
FIXTURE_SCHEMA_VERSION = "1"  # the P0-C1 input grammar and the two answer-file formats
GENERATOR_SEED = "none: deterministic, no random numbers"
ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"

PANELS = ("CP-01", "CP-02")
PANEL_POINTS = (
    # (tag suffix, point type, terminal, description)
    ("SAT", "AI", "AI-01", "Supply air temperature"),
    ("RAT", "AI", "AI-02", "Return air temperature"),
    ("CHWV", "AO", "AO-01", "Chilled water valve"),
    ("SF-STS", "DI", "DI-01", "Supply fan status"),
    ("SF-CMD", "DO", "DO-01", "Supply fan command"),
)
CAPACITY = {"AI": 8, "AO": 4, "DI": 8, "DO": 4}


def tag(panel: str, suffix: str) -> str:
    return f"AHU-{panel[-2:]}-{suffix}"


def build_set(seeded: bool) -> dict:
    """Return the sheets, points rows and sequence lines for one set."""
    io_title_cp02 = "Panel CP-02 I/O" if seeded else "Panel CP-02 IO"  # seeded R4
    cbl001_w101 = 340 if seeded else 287  # seeded R5
    reserved_cp02_do = 3 if seeded else 0  # seeded R3

    index = [
        ("G-001", "Drawing Index"),
        ("G-002", "Network Riser"),
        ("G-003", "Legend and General Notes"),
        ("M-101", "AHU-01 Control Schematic"),
        ("M-102", "AHU-02 Control Schematic"),
        ("P-101", "Panel CP-01 Layout"),
        ("IO-101", "Panel CP-01 IO"),
        ("W-101", "Panel CP-01 Wiring"),
        ("P-102", "Panel CP-02 Layout"),
        ("IO-102", "Panel CP-02 IO"),
        ("W-102", "Panel CP-02 Wiring"),
        ("T-201", "Typical AHU Field Wiring"),
    ]
    titles = dict(index)
    titles["IO-102"] = io_title_cp02

    all_tags = [tag(p, s[0]) for p in PANELS for s in PANEL_POINTS]
    lines: dict[str, list[str]] = {}
    lines["G-001"] = [f"INDEX: {n} | {t}" for n, t in index] + [
        f"SCOPE: {t} | DOCS=DRAWINGS,POINTS,SEQUENCE" for t in all_tags
    ]
    lines["G-002"] = [
        "NOTE: BACNET IP TRUNK FROM BAS SWITCH TO EACH PANEL.",
        "CABLE: CBL-001 | LENGTH_FT: 287",
        "CABLE: CBL-002 | LENGTH_FT: 310",
        "REF: W-101",
        "REF: W-102",
    ]
    lines["G-003"] = [
        "NOTE: TAG FORMAT IS AHU-NN-POINT.",
        "NOTE: ALL CABLE LENGTHS IN FEET UNLESS NOTED.",
    ]
    for n, panel in enumerate(PANELS, start=1):
        lines[f"M-10{n}"] = [
            f"NOTE: AHU-0{n} CONTROLLED BY PANEL {panel}.",
            f"REF: IO-10{n}",
            "REF: T-201",
        ]
        reserved_do = reserved_cp02_do if panel == "CP-02" else 0
        reserved_ai = 2 if panel == "CP-01" else 0
        lines[f"P-10{n}"] = [
            f"BOM: CONTROLLER {panel} | QTY: 1",
            "BOM: 24VAC TRANSFORMER | QTY: 1",
            f"CAPACITY: {panel} | AI={CAPACITY['AI']} | AO={CAPACITY['AO']} | "
            f"DI={CAPACITY['DI']} | DO={CAPACITY['DO']}",
            f"RESERVED: {panel} | AI={reserved_ai} | AO=0 | DI=0 | DO={reserved_do}",
        ]
        lines[f"IO-10{n}"] = [
            f"TAG: {tag(panel, s)} | PANEL: {panel} | TYPE: {t} | TERM: {term}"
            for s, t, term, _ in PANEL_POINTS
        ] + [f"REF: W-10{n}"]
    lines["W-101"] = [f"CABLE: CBL-001 | LENGTH_FT: {cbl001_w101}", "CABLE: CBL-101 | LENGTH_FT: 45"]
    lines["W-102"] = ["CABLE: CBL-002 | LENGTH_FT: 310", "CABLE: CBL-102 | LENGTH_FT: 62"]
    lines["T-201"] = [
        "TYPICAL: APPLIES_TO=CP-01,CP-02",
        "NOTE: CABLE LENGTHS ON THIS TYPICAL ARE NOMINAL. FIELD LENGTHS PER PANEL WIRING SHEET.",
        "CABLE: CBL-102 | LENGTH_FT: 50",
    ]

    points = []
    for panel in PANELS:
        for s, t, term, desc in PANEL_POINTS:
            ptype = t
            if seeded and panel == "CP-01" and s == "RAT":
                ptype = "DI"  # seeded R2: points list type disagrees with IO-101
            points.append([tag(panel, s), panel, term, ptype, desc])

    sequence = []
    for n, panel in enumerate(PANELS, start=1):
        t = lambda s: tag(panel, s)  # noqa: E731
        if seeded and panel == "CP-02":
            sequence.append(f"SEQ: {panel} controls discharge air using {t('CHWV')}")  # seeded R1
        else:
            sequence.append(f"SEQ: {panel} controls {t('SAT')} using {t('CHWV')}")
        sequence.append(f"SEQ: {panel} starts {t('SF-CMD')} and proves {t('SF-STS')}")
        sequence.append(f"SEQ: {panel} monitors {t('RAT')}")
    sequence.append("SEQ: CP-01 reads AHU-01-OAT from the BAS network")

    return {"index": index, "titles": titles, "lines": lines, "points": points, "sequence": sequence}


def write_pdf(path: Path, pages: list[tuple[str, str, list[str]]], blank_pages: tuple[int, ...] = ()) -> None:
    """One page per sheet. blank_pages are drawn with linework only, no text."""
    c = canvas.Canvas(str(path), pagesize=landscape(letter), invariant=1)
    width, height = landscape(letter)
    for i, (number, title, body) in enumerate(pages, start=1):
        c.rect(24, 24, width - 48, height - 48)
        c.rect(width - 300, 24, 276, 60)
        if i not in blank_pages:
            c.setFont("Helvetica", 10)
            c.drawString(40, height - 50, f"SHEET: {number} | TITLE: {title}")
            y = height - 80
            for line in body:
                c.drawString(40, y, line)
                y -= 16
            c.setFont("Helvetica", 8)
            c.drawString(width - 290, 60, "SYNTHETIC TEST SET - NOT FOR CONSTRUCTION")
        c.showPage()
    c.save()


def write_points(path: Path, rows: list[list[str]], headers: list[str]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Points"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)


def truth_for(data: dict) -> dict:
    sheets = []
    for page, (number, _) in enumerate(data["index"], start=1):
        body = data["lines"][number]
        sheets.append(
            {
                "sheet_number": number,
                "title": data["titles"][number],
                "pdf_page_number_1based": page,
                "tags": [ln.split("|")[0].split(":", 1)[1].strip() for ln in body if ln.startswith("TAG:")],
                "cables": [
                    {"cable_id": ln.split("|")[0].split(":", 1)[1].strip(),
                     "length_value": float(ln.split(":")[-1].strip())}
                    for ln in body if ln.startswith("CABLE:")
                ],
            }
        )
    seq_tags = []
    for ln in data["sequence"]:
        seq_tags += [w for w in ln.split() if w.startswith("AHU-")]
    return {
        "generator_version": GENERATOR_VERSION,
        "sheets": sheets,
        "index_entries": [{"sheet_number": n, "title": t} for n, t in data["index"]],
        "points_row_count": len(data["points"]),
        "sequence_tags": seq_tags,
    }


SEEDED_LABELS = {
    "generator_version": GENERATOR_VERSION,
    "seeded_errors": [
        {"finding_id": "R1:AHU-02-SAT:MISSING_FROM_SEQUENCE", "rule_id": "R1", "sheets": ["G-001"]},
        {"finding_id": "R2:CP-01:AI-02:TYPE_MISMATCH", "rule_id": "R2", "sheets": ["IO-101"]},
        {"finding_id": "R3:CP-02:DO", "rule_id": "R3", "sheets": ["P-102"]},
        {"finding_id": "R4:IO-102:TITLE_MISMATCH", "rule_id": "R4", "sheets": ["G-001", "IO-102"]},
        {"finding_id": "R5:CBL-001", "rule_id": "R5", "sheets": ["G-002", "W-101"]},
    ],
    "expected_other_verdicts": [
        {"finding_id": "R5:CBL-102", "verdict": "drafting_convention"},
        {"finding_id": "R1:AHU-01-OAT:NO_SCOPE", "verdict": "unresolved"},
    ],
}

RECORDED_RESPONSES = {
    "R1:AHU-02-SAT:MISSING_FROM_SEQUENCE": {
        "verdict": "real_error",
        "supporting_quote": "SCOPE: AHU-02-SAT | DOCS=DRAWINGS,POINTS,SEQUENCE",
        "reason": "The index requires AHU-02-SAT in the sequence and no sequence line names it.",
    },
    "R1:AHU-01-OAT:NO_SCOPE": {
        "verdict": "unresolved",
        "supporting_quote": "SEQ: CP-01 reads AHU-01-OAT from the BAS network",
        "reason": "The sheets do not say whether a network point needs drawing or points list entries.",
    },
    "R2:CP-01:AI-02:TYPE_MISMATCH": {
        "verdict": "real_error",
        "supporting_quote": "TAG: AHU-01-RAT | PANEL: CP-01 | TYPE: AI | TERM: AI-02",
        "reason": "The IO sheet lands a temperature on an AI terminal while the points list calls it DI.",
    },
    "R3:CP-02:DO": {
        "verdict": "real_error",
        "supporting_quote": "RESERVED: CP-02 | AI=0 | AO=0 | DI=0 | DO=3",
        "reason": "Reserved and used outputs leave no spare DO on CP-02.",
    },
    "R4:IO-102:TITLE_MISMATCH": {
        "verdict": "real_error",
        "supporting_quote": "INDEX: IO-102 | Panel CP-02 IO",
        "reason": "The index title and the sheet header title differ.",
    },
    "R5:CBL-001": {
        "verdict": "real_error",
        "supporting_quote": "CABLE: CBL-001 | LENGTH_FT: 340",
        "reason": "The riser and the wiring sheet show different lengths for the same cable.",
    },
    "R5:CBL-102": {
        "verdict": "drafting_convention",
        "supporting_quote": "NOTE: CABLE LENGTHS ON THIS TYPICAL ARE NOMINAL. FIELD LENGTHS PER PANEL WIRING SHEET.",
        "reason": "The typical states its lengths are nominal and applies to CP-01 and CP-02.",
    },
}

HEADERS = ["tag", "controller", "terminal", "point_type", "description"]


def main() -> None:
    for name, seeded in (("seeded", True), ("clean", False)):
        folder = FIXTURES / name
        folder.mkdir(parents=True, exist_ok=True)
        data = build_set(seeded)
        pages = [(n, data["titles"][n], data["lines"][n]) for n, _ in data["index"]]
        write_pdf(folder / "drawings.pdf", pages)
        write_points(folder / "points.xlsx", data["points"], HEADERS)
        (folder / "sequence.txt").write_text("\n".join(data["sequence"]) + "\n", encoding="utf-8")
        (folder / "extraction_truth.json").write_text(json.dumps(truth_for(data), indent=2) + "\n", encoding="utf-8")
        labels = SEEDED_LABELS if seeded else {
            "generator_version": GENERATOR_VERSION,
            "seeded_errors": [],
            "expected_other_verdicts": SEEDED_LABELS["expected_other_verdicts"],
        }
        (folder / "error_labels.json").write_text(json.dumps(labels, indent=2) + "\n", encoding="utf-8")

    bad = FIXTURES / "malformed"
    bad.mkdir(parents=True, exist_ok=True)
    data = build_set(False)
    pages = [(n, data["titles"][n], data["lines"][n]) for n, _ in data["index"][:3]]
    write_pdf(bad / "drawings.pdf", pages, blank_pages=(2,))
    rows = [[r[0], r[1], r[3], r[4]] for r in data["points"]]
    write_points(bad / "points.xlsx", rows, ["tag", "controller", "point_type", "description"])
    (bad / "sequence.txt").write_text("\n".join(data["sequence"]) + "\n", encoding="utf-8")

    (FIXTURES / "recorded_responses.json").write_text(json.dumps(RECORDED_RESPONSES, indent=2) + "\n", encoding="utf-8")
    print(f"Fixtures written to {FIXTURES}")


if __name__ == "__main__":
    main()
