"""Controls Submittal Review Agent - Phase 5 validation.

Student: Addison Smith (addsmi1720). License: MIT.
Build Guide: Smith_Controls_Submittal_Review_Agent_Build_Guide_REVISED.txt
Build Standards: 40-10 AGENT PRO BUILD STANDARDS

Nine nodes wired in one linear LangGraph graph:
  N1 ingest -> N2 validate -> N3 extract -> N4 cross reference -> N5 rule checks
  -> N6 gather context -> N7 classify -> N8 order -> N9 report

Run:   python -m submittal_review --input tests/fixtures/seeded --output out [--config review_config.json]
       (needs Ollama running locally with the configured model; --classifier recorded runs offline)
Tests: python -m pytest -q
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, Protocol, TypedDict

import openpyxl
import pdfplumber
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, field_validator

# Future (P0-C1): native Visio and spreadsheet sources, revision-to-revision compare, riser and BOM quantity checks.

HERE = Path(__file__).resolve().parent
DEFAULT_RESPONSES = HERE / "tests" / "fixtures" / "recorded_responses.json"
DEFAULT_CONFIG = HERE / "review_config.json"
RULE_IDS = ("R1", "R2", "R3", "R4", "R5")
# Future (P1-C1): keep the prior revision's findings so a rerun reports new, fixed and still open.
# Future (P1-C4): run several submittals in parallel (concurrency, not a redesign).
# Future (P3-C1): retrieval over a library of past submittal comments, to show how a similar finding was resolved.
# Future (P3-C3): project standards (tag formats, spare IO rule, cable tolerance) loaded per project from a config file.
REQUIRED_FILES = {"drawing": "drawings.pdf", "points": "points.xlsx", "sequence": "sequence.txt"}
POINTS_SHEET = "Points"
POINTS_COLUMNS = ["tag", "controller", "terminal", "point_type", "description"]
IO_TYPES = ("AI", "AO", "DI", "DO")
DOCUMENTS = ("DRAWINGS", "POINTS", "SEQUENCE")
SPARE_IO_THRESHOLD_PCT = 15.0  # P0-C1 R3 default: flag strictly less than 15 percent (P1-C3: set in review_config.json)
CABLE_LENGTH_TOLERANCE_PCT = 10.0  # P0-C1 R5 default: flag strictly greater than 10 percent (P1-C3: set in review_config.json)
FT_PER_M = 3.28084
UNRESOLVED_INPUT = "UNRESOLVED_INPUT"  # rule could not compute; N7 records unresolved without a model call
CONTEXT_BUDGET_EXCEEDED = "context_budget_exceeded"  # P2-C3: mandatory evidence alone is over the budget
PROMPT_VERSION = "p2-v4"  # P2-C1: fixed classification prompt version, logged with every run
DEFAULT_OLLAMA_URL = "http://localhost:11434"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}  # P2-C2: the model is only ever reached on this machine
# P4-C1: wording no comment may carry; the agent never approves or rejects a submittal
FORBIDDEN_PHRASES = ("approved", "approve", "reject", "no exceptions taken", "resubmit", "accepted as submitted")
FROZEN_DATASETS = HERE / "tests" / "fixtures" / "datasets.json"  # P4-C3: full prompt text is logged only for these
FROZEN_EVAL_SETS = HERE / "eval_sets" / "datasets.json"  # P5-C2: the generated evaluation sets, frozen the same way
# Future (P5-C1): severity weighting of misses, named as future work in the project statement.
# Future (P5-C3): group rejected comments by rule, adjust that rule by hand, rerun the P4-C7 benchmark.
# Future (P5-C4): batched model calls if finding counts get large.
# Future (P5-C5): parallel runs across the packages of one project.
# Future (P5-C6): automated enforcement of the ship checklist in CI.
# Future (P5-C7): section by section runs merged into one report.
# Future (P4-C2): a sanitizing step that strips customer and site names from a real package before use.
# Future (P4-C3): a replay command that rebuilds a report from its logs with no model calls.
# Future (P4-C6): service monitoring, only if the tool ever runs as a service.
# Future (P4-C5): the cited sheets rendered beside each comment.
# Future (P4-C8): proposed threshold changes from marked reviews, approved by a person.
TAG_IN_TEXT = re.compile(r"\b[A-Z]{2,4}-\d{1,3}-[A-Z][A-Z0-9-]*[A-Z0-9]\b")

Verdict = Literal["real_error", "drafting_convention", "unresolved"]


# ---------------------------------------------------------------------------
# Typed records that cross node boundaries (P0-C2, structured contracts I5)
# ---------------------------------------------------------------------------

class SourceLocation(BaseModel):
    source_file: str
    sheet_number: Optional[str] = None
    pdf_page_number_1based: Optional[int] = None
    row_number_1based: Optional[int] = None
    sequence_line_number_1based: Optional[int] = None
    raw_excerpt: str
    field_name: str


class IoPoint(BaseModel):
    tag_raw: str
    tag_key: str
    controller_key: str
    terminal_key: str
    point_type: str
    location: SourceLocation


class CableRecord(BaseModel):
    cable_id: str
    cable_key: str
    length_value: Optional[float]
    unit: Optional[str]
    location: SourceLocation


class IndexEntry(BaseModel):
    sheet_number: str
    title: str
    location: SourceLocation


class ScopeDeclaration(BaseModel):
    tag_key: str
    documents: list[str]
    location: SourceLocation


# Build Guide: P3-C1
# Decision: tag equivalence only by an explicit ALIAS line in the input, never inferred
class AliasDeclaration(BaseModel):
    alias_key: str
    canonical_key: str
    location: SourceLocation


class IoCountLine(BaseModel):
    controller_key: str
    counts: dict[str, int]
    location: SourceLocation


class SheetRecord(BaseModel):
    sheet_id: str
    sheet_number: str
    title: str
    pdf_page_number_1based: int
    raw_text: str
    header_location: SourceLocation
    tags: list[str] = Field(default_factory=list)
    io_points: list[IoPoint] = Field(default_factory=list)
    cables: list[CableRecord] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    bom_lines: list[str] = Field(default_factory=list)
    typical_applies_to: list[str] = Field(default_factory=list)
    scope_declarations: list[ScopeDeclaration] = Field(default_factory=list)
    capacity_lines: list[IoCountLine] = Field(default_factory=list)
    reserved_lines: list[IoCountLine] = Field(default_factory=list)
    alias_declarations: list[AliasDeclaration] = Field(default_factory=list)


class PointRecord(BaseModel):
    point_id: str
    tag_raw: str
    tag_key: str
    controller_raw: str
    controller_key: str
    terminal_raw: str
    terminal_key: str
    point_type: str
    description: str
    location: SourceLocation


class SequenceTag(BaseModel):
    tag_raw: str
    tag_key: str
    location: SourceLocation


class ValidatedSources(BaseModel):
    drawing_pdf_path: str
    points_list_path: str
    sequence_path: str
    pdf_page_count: int
    points_row_count: int
    sequence_line_count: int


class XrefEntry(BaseModel):
    document: str
    tag_raw: str
    location: SourceLocation
    alias_of: Optional[str] = None  # P3-C1: the key as written, when an ALIAS line mapped it to this entry's key


class Evidence(BaseModel):
    evidence_id: str
    role: Literal["left", "right", "absence", "calculation", "context"]
    locations: list[SourceLocation] = Field(default_factory=list)
    quotation: Optional[str] = None
    searched_scope: Optional[str] = None
    numeric_inputs: Optional[dict[str, float]] = None
    formula: Optional[str] = None
    computed_value: Optional[float] = None


class SuspectedFinding(BaseModel):
    finding_id: str
    rule_id: Literal["R1", "R2", "R3", "R4", "R5"]
    affected_entity_key: str
    evidence: list[Evidence]
    candidate_reason: str
    related_sheet_ids: list[str] = Field(default_factory=list)


class RelatedSheetText(BaseModel):
    sheet_number: str
    why_included: Literal["evidence", "typical", "index"]
    text: str


class FindingWithContext(BaseModel):
    finding: SuspectedFinding
    related_sheets: list[RelatedSheetText]


class ClassifiedFinding(BaseModel):
    finding: SuspectedFinding
    context_sheet_numbers: list[str]
    verdict: Verdict
    supporting_quote: Optional[str] = None
    reason: str
    model_attempt_count: int
    attempt_failures: list[str] = Field(default_factory=list)  # P2-C3: why each failed attempt failed
    context_included: list[str] = Field(default_factory=list)  # P2-C3: excerpts given to the model
    context_omitted: list[str] = Field(default_factory=list)  # P2-C3: excerpts left out for the budget
    prompt_tokens_est: int = 0
    applicability_quote: Optional[str] = None  # P4-C1: the line tying a convention to this exact finding
    convention_sheet: Optional[str] = None  # P4-C1: the sheet that holds the convention clause
    prompt_text: str = ""  # P4-C3: the full prompt, written to the classify log only for synthetic data
    attempts: list[dict] = Field(default_factory=list)  # P4-C3: per attempt: seconds, reply, problem, tokens


class ReviewComment(BaseModel):
    finding_id: str
    rule_id: str
    affected_entity_key: str
    cited_sheets: list[str]
    evidence_lines: list[str]
    context_sheet_numbers: list[str]
    verdict: Verdict
    supporting_quote: Optional[str]
    reason: str
    suggested_fix: str


class RunMetadata(BaseModel):
    run_id: str
    started_at: str
    input_folder: str
    output_run_folder: str
    classifier_name: str
    config_file: str = ""
    config_sha256: str = ""
    config_values: str = ""
    model_digest: str = "n/a"
    prompt_version: str = PROMPT_VERSION
    source_files: dict[str, dict] = Field(default_factory=dict)  # P4-C3: SHA-256, size and modified time per source
    dataset: str = "not a frozen synthetic dataset"  # P4-C3: dataset and generator version when the input matches one
    full_text_logging: bool = False  # P4-C3: full prompts and replies only for frozen synthetic datasets
    code_version: str = "n/a"  # P4-C3: git commit when available, plus the script's SHA-256


class ReviewOutputs(BaseModel):
    report_txt_path: str
    report_csv_path: str
    run_log_path: str
    classify_log_path: str = ""


# Build Guide: P1-C3
# Decision: thresholds and limits live in a config file a person edits and every run logs; no severity weights
# Future (P1-C3): threshold changes informed by recorded reviewer decisions, applied by hand between versions.
class ReviewConfig(BaseModel):
    spare_io_threshold_pct: float = Field(default=SPARE_IO_THRESHOLD_PCT, gt=0, lt=100)
    cable_length_tolerance_pct: float = Field(default=CABLE_LENGTH_TOLERANCE_PCT, gt=0, lt=100)
    # Accepted and logged now (I9); N7 and the size caps start using them in P2-C1, P2-C3 and P5-C7.
    model_name: str = Field(default="gemma3:4b", min_length=1)
    temperature: float = Field(default=0.0, ge=0)
    model_timeout_seconds: int = Field(default=120, gt=0)
    model_attempts: int = Field(default=2, ge=1, le=2)
    max_prompt_tokens: int = Field(default=4096, gt=0)
    max_context_tokens: int = Field(default=3000, gt=0)
    max_pdf_pages: int = Field(default=250, gt=0)
    max_suspected_findings: int = Field(default=150, gt=0)

    model_config = {"extra": "forbid", "protected_namespaces": ()}

    @field_validator("max_context_tokens")
    @classmethod
    def _context_fits_prompt(cls, v: int, info) -> int:
        if v > info.data.get("max_prompt_tokens", v):
            raise ValueError("max_context_tokens cannot exceed max_prompt_tokens")
        return v


class SizeLimitError(RuntimeError):
    """P2-C3: the package is over a configured size cap; the run stops rather than sampling."""


class ModelUnavailableError(RuntimeError):
    """P2-C3: Ollama or the configured model is not available; the run stops before N7."""


def load_config(path: Path) -> ReviewConfig:
    """Read and validate the review config. A bad file stops the run before any node runs."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"config file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: not valid JSON ({exc})") from exc
    return ReviewConfig(**data)


# Build Guide: P0-C2
# Decision: one typed state; every field named in the node contracts, one writer each
class ReviewState(TypedDict, total=False):
    submittal_folder_path: str  # set by CLI
    output_folder_path: str  # set by CLI (the unique run subfolder)
    run_metadata: RunMetadata  # set by CLI
    review_config: ReviewConfig  # set by CLI (P1-C3); nodes fall back to the defaults when absent
    drawing_pdf_path: str  # N1
    points_list_path: str  # N1
    sequence_path: str  # N1
    validated_sources: ValidatedSources  # N2
    sheet_records: list[SheetRecord]  # N3
    index_entries: list[IndexEntry]  # N3
    points_list_records: list[PointRecord]  # N3
    sequence_tags: list[SequenceTag]  # N3
    cross_reference_table: dict[str, list[XrefEntry]]  # N4
    suspected_findings: list[SuspectedFinding]  # N5
    findings_with_context: list[FindingWithContext]  # N6
    classified_findings: list[ClassifiedFinding]  # N7
    ordered_comments: list[ReviewComment]  # N8
    convention_findings: list[ClassifiedFinding]  # N8
    unresolved_findings: list[ClassifiedFinding]  # N8
    review_outputs: ReviewOutputs  # N9


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

# Build Guide: P0-C1
# Decision: conservative key: trim, collapse spaces, uppercase, tidy spacing around a kept hyphen
def normalize_key(raw: str) -> str:
    text = re.sub(r"\s+-\s+", "-", raw.strip())
    return re.sub(r"\s+", " ", text).upper()


def _counts(text: str) -> dict[str, int]:
    return {t: int(v) for t, v in re.findall(r"\b(AI|AO|DI|DO)=(\d+)", text)}


def _quote(e: Evidence) -> str:
    where = ", ".join(_where(loc) for loc in e.locations) or "n/a"
    if e.quotation:
        return f'{e.role} ({where}): "{e.quotation}"'
    if e.formula:
        return f"{e.role} ({where}): {e.formula} = {e.computed_value}"
    return f"{e.role}: {e.searched_scope}"


def _where(loc: SourceLocation) -> str:
    if loc.sheet_number:
        return f"{loc.sheet_number} p{loc.pdf_page_number_1based}"
    if loc.row_number_1based:
        return f"{loc.source_file} row {loc.row_number_1based}"
    if loc.sequence_line_number_1based:
        return f"{loc.source_file} line {loc.sequence_line_number_1based}"
    return loc.source_file


def _sheets_of(finding: SuspectedFinding) -> list[str]:
    seen: list[str] = []
    for e in finding.evidence:
        for loc in e.locations:
            if loc.sheet_number and loc.sheet_number not in seen:
                seen.append(loc.sheet_number)
    return seen


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

# Build Guide: P0-C1, P0-C2
# Decision: N1 ingest - locate drawings.pdf, points.xlsx and sequence.txt in the submittal folder
# Reads:    submittal_folder_path
# Writes:   drawing_pdf_path, points_list_path, sequence_path
# Why:      the reviewer points the agent at one folder; everything after works from these three files
# May change: native Visio and spreadsheet sources instead of PDF exports
# Wraps:    original
def n1_ingest(state: ReviewState) -> dict:
    folder = Path(state["submittal_folder_path"])
    paths = {kind: folder / name for kind, name in REQUIRED_FILES.items()}
    missing = [p.name for p in paths.values() if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"{folder}: missing required file(s): {', '.join(missing)}")
    extras = sorted(p.name for p in folder.iterdir() if p.name not in REQUIRED_FILES.values())
    print(f"[N1 ingest] found {', '.join(REQUIRED_FILES.values())} in {folder}"
          + (f" (ignored extra files: {', '.join(extras)})" if extras else ""))
    return {
        "drawing_pdf_path": str(paths["drawing"]),
        "points_list_path": str(paths["points"]),
        "sequence_path": str(paths["sequence"]),
    }


# Build Guide: P0-C1, P0-C2, P2-C1, P2-C3
# Decision: N2 validate - every file readable, every PDF page has text, five columns, page count under the cap
# Reads:    drawing_pdf_path, points_list_path, sequence_path, review_config
# Writes:   validated_sources
# Why:      extraction from an unreadable input would produce confident nonsense later
# May change: none
# Wraps:    original
def n2_validate(state: ReviewState) -> dict:
    problems: list[str] = []
    pdf_path = Path(state["drawing_pdf_path"])
    cfg = state.get("review_config") or ReviewConfig()
    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        if page_count > cfg.max_pdf_pages:
            raise SizeLimitError(f"{pdf_path.name} has {page_count} pages, over the {cfg.max_pdf_pages}-page limit. "
                                 "Split the package by section and review each part.")
        for i, page in enumerate(pdf.pages, start=1):
            if not (page.extract_text() or "").strip():
                problems.append(f"{pdf_path.name} page {i}: no text layer")
    points_path = Path(state["points_list_path"])
    wb = openpyxl.load_workbook(points_path, read_only=True, data_only=True)
    row_count = 0
    if POINTS_SHEET not in wb.sheetnames:
        problems.append(f"{points_path.name}: no worksheet named {POINTS_SHEET}")
    else:
        rows = list(wb[POINTS_SHEET].iter_rows(values_only=True))
        header = [str(c).strip().lower() for c in rows[0] if c is not None] if rows else []
        for col in POINTS_COLUMNS:
            if col not in header:
                problems.append(f"{points_path.name}: missing required column '{col}'")
        row_count = max(len(rows) - 1, 0)
    wb.close()
    seq_path = Path(state["sequence_path"])
    seq_lines = seq_path.read_text(encoding="utf-8").splitlines()
    if problems:
        raise ValueError("Input validation failed:\n  " + "\n  ".join(problems))
    print(f"[N2 validate] {page_count} PDF pages with text, {row_count} points rows, {len(seq_lines)} sequence lines")
    return {
        "validated_sources": ValidatedSources(
            drawing_pdf_path=str(pdf_path), points_list_path=str(points_path), sequence_path=str(seq_path),
            pdf_page_count=page_count, points_row_count=row_count, sequence_line_count=len(seq_lines),
        )
    }


_SHEET = re.compile(r"^SHEET:\s*(\S+)\s*\|\s*TITLE:\s*(.+?)\s*$")
_INDEX = re.compile(r"^INDEX:\s*(\S+)\s*\|\s*(.+?)\s*$")
_TAG = re.compile(r"^TAG:\s*(\S+)\s*\|\s*PANEL:\s*(\S+)\s*\|\s*TYPE:\s*(\S+)\s*\|\s*TERM:\s*(\S+)\s*$")
_CABLE = re.compile(r"^CABLE:\s*(\S+)\s*\|\s*LENGTH(?:_(FT|M))?:\s*([-\d.]+)\s*$")
_REF = re.compile(r"^REF:\s*(\S+)\s*$")
_BOM = re.compile(r"^BOM:\s*(.+?)\s*\|\s*QTY:\s*(\d+)\s*$")
_TYPICAL = re.compile(r"^TYPICAL:\s*APPLIES_TO=(.+?)\s*$")
_SCOPE = re.compile(r"^SCOPE:\s*(\S+)\s*\|\s*DOCS=(.+?)\s*$")
_ALIAS = re.compile(r"^ALIAS:\s*(\S+)\s*=\s*(\S+)\s*$")
_CAPACITY = re.compile(r"^(CAPACITY|RESERVED):\s*(\S+)\s*\|(.+)$")


def parse_page(text: str, page_no: int, source_file: str) -> tuple[SheetRecord, list[IndexEntry]]:
    """Read one PDF page's text by anchored field labels (the P0-C1 synthetic grammar)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    header = next((m for m in map(_SHEET.match, lines) if m), None)
    if header is None:
        raise ValueError(f"{source_file} page {page_no}: no 'SHEET: ... | TITLE: ...' line")
    number = header.group(1)

    def loc(raw: str, field: str) -> SourceLocation:
        return SourceLocation(source_file=source_file, sheet_number=number, pdf_page_number_1based=page_no,
                              raw_excerpt=raw, field_name=field)

    rec = SheetRecord(sheet_id=f"P{page_no:03d}-{number}", sheet_number=number, title=header.group(2),
                      pdf_page_number_1based=page_no, raw_text=text, header_location=loc(header.group(0), "SHEET"))
    index: list[IndexEntry] = []
    for ln in lines:
        if m := _TAG.match(ln):
            rec.tags.append(m.group(1))
            rec.io_points.append(IoPoint(tag_raw=m.group(1), tag_key=normalize_key(m.group(1)),
                                         controller_key=normalize_key(m.group(2)), terminal_key=normalize_key(m.group(4)),
                                         point_type=m.group(3).upper(), location=loc(ln, "TAG")))
        elif m := _CABLE.match(ln):
            unit = m.group(2).upper() if m.group(2) else None
            rec.cables.append(CableRecord(cable_id=m.group(1), cable_key=normalize_key(m.group(1)),
                                          length_value=float(m.group(3)), unit=unit, location=loc(ln, "CABLE")))
        elif m := _INDEX.match(ln):
            index.append(IndexEntry(sheet_number=m.group(1), title=m.group(2), location=loc(ln, "INDEX")))
        elif m := _REF.match(ln):
            rec.references.append(m.group(1))
        elif m := _BOM.match(ln):
            rec.bom_lines.append(ln)
        elif m := _TYPICAL.match(ln):
            rec.typical_applies_to = [normalize_key(p) for p in m.group(1).split(",") if p.strip()]
        elif m := _SCOPE.match(ln):
            docs = [normalize_key(d) for d in m.group(2).split(",") if d.strip()]
            rec.scope_declarations.append(ScopeDeclaration(tag_key=normalize_key(m.group(1)), documents=docs,
                                                           location=loc(ln, "SCOPE")))
        elif m := _ALIAS.match(ln):
            rec.alias_declarations.append(AliasDeclaration(alias_key=normalize_key(m.group(1)),
                                                           canonical_key=normalize_key(m.group(2)), location=loc(ln, "ALIAS")))
        elif m := _CAPACITY.match(ln):
            line = IoCountLine(controller_key=normalize_key(m.group(2)), counts=_counts(m.group(3)),
                               location=loc(ln, m.group(1)))
            (rec.capacity_lines if m.group(1) == "CAPACITY" else rec.reserved_lines).append(line)
    return rec, index


# Build Guide: P0-C1, P0-C2, P5-C7
# Decision: N3 extract - sheet by sheet records, index, points list rows and sequence tags, by anchored labels
# Reads:    validated_sources, review_config
# Writes:   sheet_records, index_entries, points_list_records, sequence_tags
# Why:      every later check is a comparison of what each document says, so this pulls exactly that
# May change: native Visio and spreadsheet sources instead of PDF exports
# Wraps:    original
def n3_extract(state: ReviewState) -> dict:
    src = state["validated_sources"]
    sheets: list[SheetRecord] = []
    index: list[IndexEntry] = []
    pdf_name = Path(src.drawing_pdf_path).name
    with pdfplumber.open(src.drawing_pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            rec, idx = parse_page(page.extract_text() or "", page_no, pdf_name)
            sheets.append(rec)
            index.extend(idx)

    points: list[PointRecord] = []
    pts_name = Path(src.points_list_path).name
    wb = openpyxl.load_workbook(src.points_list_path, read_only=True, data_only=True)
    rows = list(wb[POINTS_SHEET].iter_rows(values_only=True))
    wb.close()
    col = {str(h).strip().lower(): i for i, h in enumerate(rows[0]) if h is not None}
    for row_no, row in enumerate(rows[1:], start=2):
        val = {k: ("" if row[i] is None else str(row[i]).strip()) for k, i in col.items()}
        if not val.get("tag"):
            continue
        raw = ", ".join(val[c] for c in POINTS_COLUMNS)
        points.append(PointRecord(
            point_id=f"ROW{row_no:04d}", tag_raw=val["tag"], tag_key=normalize_key(val["tag"]),
            controller_raw=val["controller"], controller_key=normalize_key(val["controller"]),
            terminal_raw=val["terminal"], terminal_key=normalize_key(val["terminal"]),
            point_type=val["point_type"].upper(), description=val["description"],
            location=SourceLocation(source_file=pts_name, row_number_1based=row_no, raw_excerpt=raw, field_name="Points"),
        ))

    seq_tags: list[SequenceTag] = []
    seq_name = Path(src.sequence_path).name
    for line_no, line in enumerate(Path(src.sequence_path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip().startswith("SEQ:"):
            continue
        for raw in TAG_IN_TEXT.findall(line):
            seq_tags.append(SequenceTag(tag_raw=raw, tag_key=normalize_key(raw), location=SourceLocation(
                source_file=seq_name, sequence_line_number_1based=line_no, raw_excerpt=line.strip(), field_name="SEQ")))
    cfg = state.get("review_config") or ReviewConfig()
    print(f"[N3 extract] {len(sheets)} sheets ({cfg.max_pdf_pages}-page cap), {len(index)} index entries, "
          f"{len(points)} points rows, {len(seq_tags)} sequence tags")
    return {"sheet_records": sheets, "index_entries": index, "points_list_records": points, "sequence_tags": seq_tags}


# Build Guide: P0-C1, P0-C2, P3-C1
# Decision: N4 cross reference - one exact-key table; aliases only from ALIAS lines, each use logged (P3-C1)
# Reads:    sheet_records, index_entries, points_list_records, sequence_tags
# Writes:   cross_reference_table
# Why:      a tag either matches or it does not; approximate matching would make the exact step less exact
# May change: retrieval over a library of past submittal comments
# Wraps:    original
def n4_cross_reference(state: ReviewState) -> dict:
    table: dict[str, list[XrefEntry]] = {}
    aliases = alias_map(state["sheet_records"])

    def add(key: str, entry: XrefEntry) -> None:
        if key in aliases:
            entry.alias_of, key = key, aliases[key]
        table.setdefault(key, []).append(entry)

    for sheet in state["sheet_records"]:
        for p in sheet.io_points:
            add(p.tag_key, XrefEntry(document="DRAWINGS", tag_raw=p.tag_raw, location=p.location))
    for p in state["points_list_records"]:
        add(p.tag_key, XrefEntry(document="POINTS", tag_raw=p.tag_raw, location=p.location))
    for t in state["sequence_tags"]:
        add(t.tag_key, XrefEntry(document="SEQUENCE", tag_raw=t.tag_raw, location=t.location))
    table = dict(sorted(table.items()))
    used = sum(1 for entries in table.values() for e in entries if e.alias_of)
    collisions = normalization_collisions(table)
    print(f"[N4 cross reference] {len(table)} distinct tags across {len(state['index_entries'])} indexed sheets, "
          f"{used} alias uses, {len(collisions)} normalization collisions")
    return {"cross_reference_table": table}


# Build Guide: P3-C1
# Decision: an alias map comes only from ALIAS lines; a conflicting or chained alias stops the run
def alias_map(sheets: list[SheetRecord]) -> dict[str, str]:
    out: dict[str, str] = {}
    for d in (d for s in sheets for d in s.alias_declarations):
        if d.alias_key == d.canonical_key:
            continue
        if out.get(d.alias_key, d.canonical_key) != d.canonical_key:
            raise ValueError(f"conflicting ALIAS lines for {d.alias_key}: {out[d.alias_key]} and {d.canonical_key} "
                             f"({d.location.source_file} {d.location.sheet_number})")
        out[d.alias_key] = d.canonical_key
    chained = sorted(k for k, v in out.items() if v in out)
    if chained:
        raise ValueError(f"ALIAS chains are not allowed (alias of an alias): {', '.join(chained)}")
    return out


# Build Guide: P3-C1
# Decision: two different raw spellings that land on one key are flagged for review, never silently merged
def normalization_collisions(table: dict[str, list[XrefEntry]]) -> dict[str, list[XrefEntry]]:
    out = {}
    for key, entries in table.items():
        plain = [e for e in entries if not e.alias_of]
        if len({e.tag_raw for e in plain}) > 1:
            out[key] = plain
    return out


def rule_r1_tags(xref: dict[str, list[XrefEntry]], sheets: list[SheetRecord]) -> list[SuspectedFinding]:
    """R1: a tag missing from a document its SCOPE line requires, or a tag with no SCOPE line at all."""
    aliases = alias_map(sheets)
    scopes = {aliases.get(d.tag_key, d.tag_key): d for s in sheets for d in s.scope_declarations}
    findings = []
    for key in sorted(set(xref) | set(scopes)):
        entries = xref.get(key, [])
        present = {e.document for e in entries}
        seen = [Evidence(evidence_id=f"E{i}", role="left", locations=[e.location], quotation=e.location.raw_excerpt)
                for i, e in enumerate(entries[:3], start=1)]
        if key not in scopes:
            absence = Evidence(evidence_id="E9", role="absence",
                               searched_scope="every SCOPE line on every drawing sheet; none names this tag")
            findings.append(SuspectedFinding(
                finding_id=f"R1:{key}:NO_SCOPE", rule_id="R1", affected_entity_key=key, evidence=seen + [absence],
                candidate_reason=f"tag has no SCOPE declaration; appears in {', '.join(sorted(present))}"))
            continue
        decl = scopes[key]
        for doc in decl.documents:
            if doc in present:
                continue
            scope_ev = Evidence(evidence_id="E0", role="left", locations=[decl.location], quotation=decl.location.raw_excerpt)
            absence = Evidence(evidence_id="E9", role="absence",
                               searched_scope=f"every {doc} entry in the cross-reference table ({len(entries)} entries for this tag)")
            findings.append(SuspectedFinding(
                finding_id=f"R1:{key}:MISSING_FROM_{doc}", rule_id="R1", affected_entity_key=key,
                evidence=[scope_ev] + seen + [absence],
                candidate_reason=f"SCOPE requires {doc} but the tag does not appear there"))
    return findings


def rule_r2_io(sheets: list[SheetRecord], points: list[PointRecord]) -> list[SuspectedFinding]:
    """R2: one point per (controller, terminal); controller, terminal and point type must agree."""
    drawn: dict[tuple[str, str], list[IoPoint]] = {}
    listed: dict[tuple[str, str], list[PointRecord]] = {}
    for s in sheets:
        for p in s.io_points:
            drawn.setdefault((p.controller_key, p.terminal_key), []).append(p)
    for p in points:
        listed.setdefault((p.controller_key, p.terminal_key), []).append(p)
    findings = []
    for key in sorted(set(drawn) | set(listed)):
        d, l = drawn.get(key, []), listed.get(key, [])
        fid = f"R2:{key[0]}:{key[1]}"
        quotes = [Evidence(evidence_id=f"E{i}", role="left" if i <= len(d) else "right", locations=[x.location],
                           quotation=x.location.raw_excerpt) for i, x in enumerate(d + l, start=1)]
        if len(d) > 1 or len(l) > 1:
            findings.append(SuspectedFinding(finding_id=f"{fid}:DUPLICATE", rule_id="R2", affected_entity_key=f"{key[0]}:{key[1]}",
                                             evidence=quotes, candidate_reason="more than one point assigned to one terminal"))
        elif not d or not l:
            where = "drawing IO sheets" if not d else "points list"
            absence = Evidence(evidence_id="E9", role="absence", searched_scope=f"every IO point on the {where}")
            kind = "MISSING_ON_DRAWINGS" if not d else "MISSING_IN_POINTS"
            findings.append(SuspectedFinding(finding_id=f"{fid}:{kind}", rule_id="R2", affected_entity_key=f"{key[0]}:{key[1]}",
                                             evidence=quotes + [absence], candidate_reason=f"point not found on the {where}"))
        elif d[0].point_type != l[0].point_type:
            findings.append(SuspectedFinding(finding_id=f"{fid}:TYPE_MISMATCH", rule_id="R2", affected_entity_key=f"{key[0]}:{key[1]}",
                                             evidence=quotes, candidate_reason=f"drawing says {d[0].point_type}, points list says {l[0].point_type}"))
    return findings


def rule_r3_spare(sheets: list[SheetRecord], threshold_pct: float = SPARE_IO_THRESHOLD_PCT) -> list[SuspectedFinding]:
    """R3: spare_pct = 100 * (capacity - used - reserved) / capacity, per controller and IO type."""
    capacity = {c.controller_key: c for s in sheets for c in reversed(s.capacity_lines)}
    reserved = {c.controller_key: c for s in sheets for c in reversed(s.reserved_lines)}
    used: dict[tuple[str, str], list[IoPoint]] = {}
    for s in sheets:
        for p in s.io_points:
            used.setdefault((p.controller_key, p.point_type), []).append(p)
    findings = []
    for ctrl in sorted(set(capacity) | {k[0] for k in used}):
        for t in IO_TYPES:
            cap_line, res_line = capacity.get(ctrl), reserved.get(ctrl)
            cap = cap_line.counts.get(t) if cap_line else None
            res = res_line.counts.get(t, 0) if res_line else 0
            n_used = len(used.get((ctrl, t), []))
            locs = [x.location for x in (cap_line, res_line) if x] + [p.location for p in used.get((ctrl, t), [])]
            if not cap:
                if n_used or res:
                    findings.append(SuspectedFinding(
                        finding_id=f"R3:{ctrl}:{t}:UNKNOWN_CAPACITY", rule_id="R3", affected_entity_key=f"{ctrl}:{t}",
                        evidence=[Evidence(evidence_id="E1", role="calculation", locations=locs,
                                           numeric_inputs={"capacity": float(cap or 0), "used": n_used, "reserved": res},
                                           formula="capacity is zero or not declared", computed_value=None)],
                        candidate_reason=f"{UNRESOLVED_INPUT}: zero or unknown {t} capacity on {ctrl}"))
                continue
            spare_pct = 100.0 * (cap - n_used - res) / cap
            if spare_pct < threshold_pct:
                findings.append(SuspectedFinding(
                    finding_id=f"R3:{ctrl}:{t}", rule_id="R3", affected_entity_key=f"{ctrl}:{t}",
                    evidence=[Evidence(evidence_id="E1", role="calculation", locations=locs,
                                       numeric_inputs={"capacity": cap, "used": n_used, "reserved": res},
                                       formula=f"100 * ({cap} - {n_used} - {res}) / {cap}",
                                       computed_value=round(spare_pct, 2))],
                    candidate_reason=f"{t} spare is {spare_pct:.1f} percent, under {threshold_pct:g}"))
    return findings


def rule_r4_index(index: list[IndexEntry], sheets: list[SheetRecord]) -> list[SuspectedFinding]:
    """R4: index versus sheet headers; missing on either side or a title that differs."""
    by_idx = {normalize_key(e.sheet_number): e for e in index}
    by_set = {normalize_key(s.sheet_number): s for s in sheets}
    inventory = f"{len(by_set)} sheet headers on {len(sheets)} PDF pages and {len(by_idx)} index entries"
    findings = []
    for key in sorted(set(by_idx) | set(by_set)):
        e, s = by_idx.get(key), by_set.get(key)
        if e and s and normalize_key(e.title) == normalize_key(s.title):
            continue
        if e and s:
            evid = [Evidence(evidence_id="E1", role="left", locations=[e.location], quotation=e.location.raw_excerpt),
                    Evidence(evidence_id="E2", role="right", locations=[s.header_location], quotation=s.header_location.raw_excerpt)]
            kind, why = "TITLE_MISMATCH", f"index title '{e.title}' differs from sheet title '{s.title}'"
        else:
            have = e.location if e else s.header_location
            evid = [Evidence(evidence_id="E1", role="left", locations=[have], quotation=have.raw_excerpt),
                    Evidence(evidence_id="E9", role="absence", searched_scope=inventory)]
            kind = "MISSING_FROM_SET" if e else "MISSING_FROM_INDEX"
            why = "indexed sheet not in the set" if e else "sheet in the set but not in the index"
        findings.append(SuspectedFinding(finding_id=f"R4:{key}:{kind}", rule_id="R4", affected_entity_key=key,
                                         evidence=evid, candidate_reason=why))
    return findings


def rule_r5_cables(sheets: list[SheetRecord], tolerance_pct: float = CABLE_LENGTH_TOLERANCE_PCT) -> list[SuspectedFinding]:
    """R5: same cable ID on several sheets; difference_pct = 100*abs(a-b)/max(a,b) over the extremes."""
    groups: dict[str, list[CableRecord]] = {}
    for s in sheets:
        for c in s.cables:
            groups.setdefault(c.cable_key, []).append(c)
    findings = []
    for key, cables in sorted(groups.items()):
        if len(cables) < 2:
            continue
        quotes = [Evidence(evidence_id=f"E{i}", role="left", locations=[c.location], quotation=c.location.raw_excerpt)
                  for i, c in enumerate(cables, start=1)]
        if any(c.unit is None or not c.length_value or c.length_value <= 0 for c in cables):
            findings.append(SuspectedFinding(finding_id=f"R5:{key}:UNIT_UNKNOWN", rule_id="R5", affected_entity_key=key,
                                             evidence=quotes, candidate_reason=f"{UNRESOLVED_INPUT}: missing, zero or unknown length unit"))
            continue
        feet = [c.length_value * (FT_PER_M if c.unit == "M" else 1.0) for c in cables]
        a, b = min(feet), max(feet)
        diff = 100.0 * abs(a - b) / max(a, b)
        if diff > tolerance_pct:
            calc = Evidence(evidence_id="E9", role="calculation", numeric_inputs={"min_ft": round(a, 2), "max_ft": round(b, 2)},
                            formula=f"100 * abs({a:g} - {b:g}) / {b:g}", computed_value=round(diff, 2))
            findings.append(SuspectedFinding(finding_id=f"R5:{key}", rule_id="R5", affected_entity_key=key,
                                             evidence=quotes + [calc],
                                             candidate_reason=f"lengths differ by {diff:.1f} percent, over {tolerance_pct:g}"))
    return findings


# Build Guide: P0-C1, P0-C2, P2-C3, P5-C7
# Decision: N5 rule checks - plain code R1 to R5 with rule-appropriate evidence; finding count under the cap (P2-C3)
# Reads:    cross_reference_table, sheet_records, index_entries, points_list_records, review_config
# Writes:   suspected_findings
# Why:      finding a mismatch is ordinary code with a correct answer, so no model is used here
# May change: priority ordering by discrepancy type and severity weighting
# Wraps:    original
def n5_rule_checks(state: ReviewState) -> dict:
    sheets, cfg = state["sheet_records"], state.get("review_config") or ReviewConfig()
    findings = (rule_r1_tags(state["cross_reference_table"], sheets)
                + rule_r2_io(sheets, state["points_list_records"])
                + rule_r3_spare(sheets, cfg.spare_io_threshold_pct)
                + rule_r4_index(state["index_entries"], sheets)
                + rule_r5_cables(sheets, cfg.cable_length_tolerance_pct))
    for f in findings:
        f.related_sheet_ids = _sheets_of(f)
    if len(findings) > cfg.max_suspected_findings:
        raise SizeLimitError(f"{len(findings)} suspected findings, over the {cfg.max_suspected_findings}-finding limit. "
                             "Split the package by section and review each part.")
    counts = {r: sum(f.rule_id == r for f in findings) for r in RULE_IDS}
    print(f"[N5 rule checks] {len(findings)} suspected findings ({cfg.max_suspected_findings}-finding cap) "
          + " ".join(f"{k}={v}" for k, v in counts.items()))
    return {"suspected_findings": findings}


# Build Guide: P0-C1, P0-C2
# Decision: N6 gather context - code picks the related sheets: both sides, matching typicals, the index sheet
# Reads:    suspected_findings, sheet_records, cross_reference_table
# Writes:   findings_with_context
# Why:      the related sheets are a lookup with a correct answer, so the model never chooses what it sees
# May change: a comparison arm where the model chooses extra sheets (P1-C2), only after this is measured
# Wraps:    original
def n6_gather_context(state: ReviewState) -> dict:
    sheets = {s.sheet_number: s for s in state["sheet_records"]}
    xref = state["cross_reference_table"]
    index_sheets = [s.sheet_number for s in state["sheet_records"] if "INDEX:" in s.raw_text]
    controllers = {p.controller_key for s in state["sheet_records"] for p in s.io_points}
    out = []
    for f in state["suspected_findings"]:
        chosen: dict[str, str] = {n: "evidence" for n in f.related_sheet_ids}
        for e in xref.get(f.affected_entity_key, []):
            if e.location.sheet_number:
                chosen.setdefault(e.location.sheet_number, "evidence")
        text = " ".join([f.affected_entity_key] + [e.quotation or "" for e in f.evidence])
        panels = {c for c in controllers if c in text}
        for p in {e.location.raw_excerpt for e in xref.get(f.affected_entity_key, [])}:
            panels |= {c for c in controllers if c in p}
        for s in state["sheet_records"]:
            if s.typical_applies_to and (set(s.typical_applies_to) & panels):
                chosen.setdefault(s.sheet_number, "typical")
        for n in index_sheets:
            chosen.setdefault(n, "index")
        related = [RelatedSheetText(sheet_number=n, why_included=why, text=sheets[n].raw_text)
                   for n, why in chosen.items() if n in sheets]
        out.append(FindingWithContext(finding=f, related_sheets=related))
    print(f"[N6 gather context] context gathered for {len(out)} findings")
    return {"findings_with_context": out}


class ClassifierClient(Protocol):
    name: str

    def classify(self, item: FindingWithContext, prompt: str) -> str: ...


class RecordedResponseClient:
    """Offline stand-in for the local model: returns recorded replies keyed by finding_id, as reply text."""

    def __init__(self, path: Path) -> None:
        self.name = f"recorded:{Path(path).name}"
        self.responses = json.loads(Path(path).read_text(encoding="utf-8"))

    def classify(self, item: FindingWithContext, prompt: str = "") -> str:
        return json.dumps(self.responses.get(item.finding.finding_id, {
            "verdict": "unresolved", "supporting_quote": None, "reason": "no recorded response for this finding"}))


# Build Guide: P2-C3
# Decision: the model reply must parse into this schema; anything else is a failed attempt
class ModelReply(BaseModel):
    verdict: Verdict
    supporting_quote: Optional[str] = None
    reason: str = Field(min_length=1)


REPLY_SCHEMA = ModelReply.model_json_schema()


# Build Guide: P2-C3, P4-C1
# Decision: the reply format sent to the model lists only the verdicts code allows for this finding, and always asks
#           for the quote field, so a verdict with no quote cannot be produced by the grammar
def reply_schema(allowed: list[str]) -> dict:
    schema = json.loads(json.dumps(REPLY_SCHEMA))
    schema["properties"]["verdict"]["enum"] = list(allowed)
    schema["properties"]["supporting_quote"] = {"title": "Supporting Quote", "type": "string"}
    schema["required"] = ["verdict", "supporting_quote", "reason"]
    return schema


# Build Guide: P2-C1, P2-C2, P2-C3, P2-C4
# Decision: local Ollama only, temperature from config, no streaming, structured reply, wall-clock timeout per attempt
class OllamaClient:
    def __init__(self, config: ReviewConfig, base_url: str = DEFAULT_OLLAMA_URL) -> None:
        host = urllib.parse.urlparse(base_url).hostname
        if host not in LOCAL_HOSTS:
            raise ValueError(f"the model must be served on this machine; {base_url} is not localhost")
        self.base_url, self.config = base_url.rstrip("/"), config
        self.name = f"ollama:{config.model_name}"
        self.model_digest = "n/a"
        self.last_usage: Optional[dict] = None

    def _call(self, path: str, payload: Optional[dict], timeout: float) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, headers={"Content-Type": "application/json"},
                                     method="POST" if data else "GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def preflight(self) -> None:
        """Confirm Ollama answers and the configured model is pulled; record its digest (P2-C1)."""
        want = self.config.model_name
        try:
            tags = self._call("/api/tags", None, 10)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ModelUnavailableError(f"Ollama is not reachable at {self.base_url} ({exc}). "
                                        f"Start Ollama, then run: ollama pull {want}") from exc
        models = {m.get("name") or m.get("model"): m for m in tags.get("models", [])}
        found = models.get(want) or models.get(f"{want}:latest")
        if not found:
            raise ModelUnavailableError(f"model {want} is not pulled in Ollama at {self.base_url}. Run: ollama pull {want}")
        self.model_digest = found.get("digest", "n/a")

    def classify(self, item: FindingWithContext, prompt: str) -> str:
        payload = {"model": self.config.model_name, "prompt": prompt, "stream": False,
                   "format": reply_schema(allowed_verdicts(item)),
                   "options": {"temperature": self.config.temperature}}
        limit = self.config.model_timeout_seconds
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(self._call, "/api/generate", payload, limit + 5)
        try:
            body = future.result(timeout=limit)
            self.last_usage = {"prompt_tokens": body.get("prompt_eval_count"), "reply_tokens": body.get("eval_count")}
            return body["response"]
        except FutureTimeout:
            raise TimeoutError(f"no reply within {limit} seconds") from None
        finally:
            pool.shutdown(wait=False, cancel_futures=True)


PROMPT_HEADER = """You check one suspected finding from a building controls submittal review.
Plain-code rules already found a difference between the documents. Use only the CONTEXT section.
A line "SCOPE: <tag> | DOCS=..." names the documents that must list that tag.
"""

QUESTIONS_CONVENTION = """
CODE CHECKED: the CONTEXT has a NOTE or TYPICAL line on a sheet that shows this finding.
Answer these in order and stop at the first that applies:
  1. If that NOTE or TYPICAL line says the drawn value is not the one to build to for this
     panel, tag or sheet, the answer is drafting_convention.
  2. If the CONTEXT is missing what you need to decide, the answer is unresolved.
  3. Otherwise the answer is real_error.
"""

QUESTIONS_NO_CONVENTION = """
CODE CHECKED: no NOTE or TYPICAL line covers this finding; drafting_convention is not allowed.
Answer these in order and stop at the first that applies:
  1. If the CONTEXT is missing what you need to decide, the answer is unresolved.
  2. Otherwise the answer is real_error.
"""

QUOTE_RULES = """
supporting_quote: copy ONE whole line exactly as it appears in the CONTEXT section. Never join
two lines and never quote the FINDING section. For real_error quote a line that shows the
difference; for drafting_convention quote the NOTE or TYPICAL line; for unresolved write "".
reason: one sentence. Never approve or reject the submittal.
Reply with JSON only: {"verdict": "...", "supporting_quote": "...", "reason": "..."}
"""


def _scope_lines(item: "FindingWithContext") -> list[str]:
    """R1: the SCOPE line(s) of the finding's tag, from the sheets given to the classifier"""
    key = item.finding.affected_entity_key
    out = []
    for r in item.related_sheets:
        for l in r.text.splitlines():
            m = re.match(r"SCOPE:\s*(.+?)\s*\|", l)
            if m and normalize_key(m.group(1)) == key and l not in out:
                out.append(l)
    return out


# P4-C1: the words a NOTE or TYPICAL line must use to be about the same subject as a finding of each rule
SUBJECT_WORDS = {"R1": ("SEQUENCE", "POINTS", "SCOPE"), "R2": ("TYPE", "TERM"), "R3": ("SPARE", "RESERVED", "CAPACITY"),
                 "R4": ("TITLE", "INDEX"), "R5": ("LENGTH",)}


# Build Guide: P4-C1
# Decision: code decides whether a drafting convention is possible at all: a NOTE or TYPICAL line on a sheet that
#           itself shows the finding (the applicability test check_convention applies) AND about the same subject
#           (it names the entity or uses the rule's subject words); the model only judges what such a line says
def convention_clauses(item: "FindingWithContext") -> list[str]:
    f = item.finding
    homes = set(_sheets_of(f))
    out = []
    for r in item.related_sheets:
        if r.sheet_number not in homes:
            continue
        for l in r.text.splitlines():
            u = l.upper()
            if u.startswith(("NOTE:", "TYPICAL:")) and (f.affected_entity_key in u or
                                                         any(w in u for w in SUBJECT_WORDS[f.rule_id])):
                out.append(l)
    return out


def allowed_verdicts(item: "FindingWithContext") -> list[str]:
    if convention_clauses(item):
        return ["real_error", "drafting_convention", "unresolved"]
    return ["real_error", "unresolved"]


def _code_checked(item: "FindingWithContext") -> str:
    f = item.finding
    lines = []
    if f.rule_id == "R1":
        scope = _scope_lines(item)
        lines.append(f"CODE CHECKED: SCOPE line for {f.affected_entity_key}: " + (scope[0] if scope else
                     "none in the CONTEXT, so which documents must list it is not settled"))
    return ("\n".join(lines) + "\n") if lines else ""


def estimate_tokens(text: str) -> int:
    """P2-C3: conservative token count. UTF-8 bytes never undercount a byte-level tokenizer, so it fails safe."""
    return len(text.encode("utf-8"))


class PromptPackage(BaseModel):
    prompt: str
    context_text: str
    included: list[str]
    omitted: list[str]
    prompt_tokens_est: int


class ContextBudgetExceeded(Exception):
    pass


# Build Guide: P2-C3
# Decision: fill the context in priority order, never cut mandatory evidence, record what was left out
def build_prompt(item: FindingWithContext, cfg: ReviewConfig) -> PromptPackage:
    f = item.finding
    questions = QUESTIONS_CONVENTION if "drafting_convention" in allowed_verdicts(item) else QUESTIONS_NO_CONVENTION
    head = (PROMPT_HEADER + questions + QUOTE_RULES + _code_checked(item) + f"\nFINDING (do not quote)\nFINDING ID: {f.finding_id}\nRULE: {f.rule_id}\n"
            f"ENTITY: {f.affected_entity_key}\nRULE SAYS: {f.candidate_reason}\n\nCONTEXT:\n")
    budget = min(cfg.max_context_tokens, cfg.max_prompt_tokens - estimate_tokens(head))
    by_sheet = {r.sheet_number: r for r in item.related_sheets}
    tiers: list[list[tuple[str, str]]] = [[], [], [], []]
    for e in f.evidence:  # (1) rule evidence and source locations: mandatory
        where = ", ".join(_where(loc) for loc in e.locations) or "n/a"
        body = e.quotation or (f"{e.formula} = {e.computed_value} {e.numeric_inputs}" if e.formula else
                               f"searched {e.searched_scope}")
        tiers[0].append((f"evidence {e.evidence_id} {e.role}", f"[evidence {e.evidence_id} {e.role}, {where}]\n{body}"))
    for r in item.related_sheets:  # (2) the explicit applicable typical-sheet clause
        if r.why_included == "typical":
            clause = [l for l in r.text.splitlines() if l.startswith(("TYPICAL:", "NOTE:"))]
            if clause:
                tiers[1].append((f"typical clause {r.sheet_number}", f"[typical {r.sheet_number}]\n" + "\n".join(clause)))
    for e in f.evidence:  # (3) narrowly adjacent source text, two lines each side
        for loc in e.locations:
            sheet = by_sheet.get(loc.sheet_number or "")
            lines = sheet.text.splitlines() if sheet else []
            if loc.raw_excerpt in lines:
                i = lines.index(loc.raw_excerpt)
                tiers[2].append((f"adjacent {loc.sheet_number} line {i + 1}",
                                 f"[near {loc.sheet_number}]\n" + "\n".join(lines[max(0, i - 2):i + 3])))
    for r in item.related_sheets:  # (4) other related-sheet excerpts
        tiers[3].append((f"sheet {r.sheet_number} ({r.why_included})", f"[sheet {r.sheet_number}]\n{r.text}"))
    mandatory = "\n\n".join(text for _, text in tiers[0])
    if estimate_tokens(mandatory) > budget:
        raise ContextBudgetExceeded(f"evidence needs {estimate_tokens(mandatory)} tokens, budget is {budget}")
    parts, included, omitted, seen = [mandatory], [label for label, _ in tiers[0]], [], set()
    for tier in tiers[1:]:
        for label, text in tier:
            if text in seen:
                continue
            seen.add(text)
            if estimate_tokens("\n\n".join(parts + [text])) <= budget:
                parts.append(text)
                included.append(label)
            else:
                omitted.append(label)
    context = "\n\n".join(parts)
    prompt = head + context + "\n"
    return PromptPackage(prompt=prompt, context_text=context, included=included, omitted=omitted,
                         prompt_tokens_est=estimate_tokens(prompt))


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# Build Guide: P2-C3
# Decision: a reply passes only if every line of its quote is word for word in the supplied context
def _whole_lines(quote: str, context_lines: set[str]) -> bool:
    """True when the quote is two or more whole context lines joined by ", " or "; " (each piece word for word)"""
    q = _squash(quote)
    cuts = [m.start() for m in re.finditer(r"[,;] ", q)]
    ok = {0}
    for end in sorted(cuts + [len(q)]):
        for st in sorted(ok):
            if st < end and q[st:end] in context_lines:
                if end == len(q):
                    return len(cuts) > 0
                ok.add(end + 2)
                break
    return False


def check_reply(reply: ModelReply, context_text: str) -> Optional[str]:
    if reply.verdict in ("real_error", "drafting_convention") and not (reply.supporting_quote or "").strip():
        return f"{reply.verdict} verdict with no supporting quote"
    if reply.verdict == "unresolved":
        lines = []  # an unresolved reply needs no quote, and its quote is never shown or used
    else:
        lines = [l for l in (reply.supporting_quote or "").splitlines() if l.strip()]
    context = _squash(context_text)
    whole = {_squash(l) for l in context_text.splitlines() if l.strip()}
    missing = [l for l in lines if _squash(l) not in context and not _whole_lines(l, whole)]
    if missing:
        return f"quote not found word for word in the supplied context: {missing[0][:80]!r}"
    if any(p in reply.reason.lower() for p in FORBIDDEN_PHRASES):  # P4-C1
        return "reason uses approve or reject language, which the agent never uses"
    return None


# Build Guide: P4-C1
# Decision: a convention needs an explicit NOTE or TYPICAL clause AND proof it covers this exact finding
def check_convention(reply: ModelReply, item: FindingWithContext) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (problem, applicability_quote, convention_sheet). Applicability is decided by code, not the model:
    the clause must sit on a sheet that itself shows the finding's entity."""
    f = item.finding
    clause = next((l for l in (reply.supporting_quote or "").splitlines()
                   if _squash(l).upper().startswith(("NOTE", "TYPICAL"))), None)
    if clause is None:
        return "drafting_convention without an explicit NOTE or TYPICAL clause in the quote", None, None
    if _squash(clause) not in {_squash(c) for c in convention_clauses(item)} and any(
            _squash(clause) == _squash(l) for r in item.related_sheets for l in r.text.splitlines()
            if r.sheet_number in _sheets_of(f)):
        return f"the quoted clause is not about the subject of {f.finding_id}", None, None
    home = next((r for r in item.related_sheets
                 if any(_squash(clause) == _squash(l) for l in r.text.splitlines())), None)
    if home is None:
        return "the convention clause is not on any sheet given to the classifier", None, None
    if home.sheet_number not in _sheets_of(f):
        return (f"the convention on {home.sheet_number} does not cover {f.affected_entity_key}: "
                f"that sheet does not show it", None, None)
    shown = [loc.raw_excerpt for e in f.evidence for loc in e.locations if loc.sheet_number == home.sheet_number]
    scope = [l for l in home.text.splitlines() if l.startswith("TYPICAL:")]
    return None, " / ".join(dict.fromkeys(shown + scope)), home.sheet_number


# Build Guide: P4-C1, P2-C5
# Decision: complete rule-appropriate evidence per rule, judged from the finding's own evidence records
def evidence_complete(finding: SuspectedFinding) -> bool:
    quotes = [e for e in finding.evidence if e.quotation]
    calc = [e for e in finding.evidence if e.role == "calculation" and e.formula]
    absence = [e for e in finding.evidence if e.role == "absence" and e.searched_scope]
    if finding.rule_id in ("R1", "R2", "R4"):
        return len(quotes) >= 2 or (len(quotes) >= 1 and bool(absence))
    if finding.rule_id == "R3":
        return bool(calc) and calc[0].computed_value is not None and bool(calc[0].locations)
    if finding.rule_id == "R5":
        return len(quotes) >= 2 and bool(calc)
    return False


# Build Guide: P5-C4
# Decision: one progress line per finding, and each result saved as it lands so Ctrl-C keeps what is done
def _report_progress(progress: Optional[Path], k: int, total: int, c: ClassifiedFinding, seconds: float) -> None:
    tries = f"{c.model_attempt_count} attempt" + ("" if c.model_attempt_count == 1 else "s")
    print(f"  [N7 {k}/{total}] {c.finding.finding_id}: {c.verdict} ({tries}, {seconds:.1f} s)")
    if progress is not None:
        progress.parent.mkdir(parents=True, exist_ok=True)
        with progress.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"n": k, "of": total, "finding_id": c.finding.finding_id, "verdict": c.verdict,
                                 "attempts": c.model_attempt_count, "reason": c.reason,
                                 "seconds": round(seconds, 2)}) + "\n")


# Build Guide: P0-C1, P0-C2, P2-C1, P2-C3, P4-C1, P4-C3, P5-C4
# Decision: N7 classify - the only model step; schema, quote and convention checks, one retry, then unresolved
# Reads:    findings_with_context, review_config
# Writes:   classified_findings
# Why:      a model that cannot point to the words behind its verdict is guessing
# May change: a vision model for scanned sets and geometry-based checks
# Wraps:    original
def n7_classify(state: ReviewState, client: ClassifierClient) -> dict:
    cfg = state.get("review_config") or ReviewConfig()
    out = []
    calls = failed = 0
    items = state["findings_with_context"]
    asks = sum(1 for i in items if not i.finding.candidate_reason.startswith(UNRESOLVED_INPUT))
    worst = asks * cfg.model_attempts
    print(f"  [N7 plan] {asks} findings for the model, at most {worst} calls one at a time, "  # P5-C4
          f"worst case {worst * cfg.model_timeout_seconds / 60:.0f} min; Ctrl-C stops and keeps the logs")
    progress = Path(state["output_folder_path"]) / "classify_progress.jsonl" if state.get("output_folder_path") else None
    for k, item in enumerate(items, start=1):
        f = item.finding
        t0 = time.monotonic()
        context = [r.sheet_number for r in item.related_sheets]
        if f.candidate_reason.startswith(UNRESOLVED_INPUT):
            out.append(ClassifiedFinding(finding=f, context_sheet_numbers=context, verdict="unresolved",
                                         reason=f.candidate_reason, model_attempt_count=0))
            _report_progress(progress, k, len(items), out[-1], time.monotonic() - t0)
            continue
        try:
            pkg = build_prompt(item, cfg)
        except ContextBudgetExceeded as exc:
            out.append(ClassifiedFinding(finding=f, context_sheet_numbers=context, verdict="unresolved",
                                         reason=f"{CONTEXT_BUDGET_EXCEEDED}: {exc}", model_attempt_count=0))
            _report_progress(progress, k, len(items), out[-1], time.monotonic() - t0)
            continue
        failures: list[str] = []
        attempts: list[dict] = []
        accepted: Optional[ModelReply] = None
        applies: tuple[Optional[str], Optional[str]] = (None, None)
        for attempt in range(1, cfg.model_attempts + 1):  # hard stop: at most two attempts (P2-C3)
            calls += 1
            started, raw = time.monotonic(), None
            try:
                raw = client.classify(item, pkg.prompt)
                reply = ModelReply.model_validate_json(raw)
                problem = check_reply(reply, pkg.context_text)
                if problem is None and reply.verdict not in allowed_verdicts(item):  # P4-C1, belt and braces
                    problem = f"{reply.verdict} is not an allowed verdict for this finding"
                if problem is None and reply.verdict == "drafting_convention":  # P4-C1
                    problem, *applies = check_convention(reply, item)
            except Exception as exc:  # timeout, connection error or unparseable reply: a failed attempt, never a stop
                reply, problem = None, f"{type(exc).__name__}: {str(exc)[:200]}"
            attempts.append({"attempt": attempt, "seconds": round(time.monotonic() - started, 3), "reply": raw,
                             "problem": problem, "usage": getattr(client, "last_usage", None)})
            if problem is None:
                accepted = reply
                break
            failures.append(f"attempt {attempt}: {problem}")
        common = dict(finding=f, context_sheet_numbers=context, model_attempt_count=len(failures) + (1 if accepted else 0),
                      attempt_failures=failures, context_included=pkg.included, context_omitted=pkg.omitted,
                      prompt_tokens_est=pkg.prompt_tokens_est, prompt_text=pkg.prompt, attempts=attempts)
        if accepted:
            out.append(ClassifiedFinding(verdict=accepted.verdict, supporting_quote=accepted.supporting_quote,
                                         reason=accepted.reason, applicability_quote=applies[0],
                                         convention_sheet=applies[1], **common))
        else:
            failed += 1
            out.append(ClassifiedFinding(verdict="unresolved", reason=f"model reply failed checks after "
                                         f"{len(failures)} attempts; last: {failures[-1]}", **common))
        _report_progress(progress, k, len(items), out[-1], time.monotonic() - t0)
    tally = {v: sum(c.verdict == v for c in out) for v in ("real_error", "drafting_convention", "unresolved")}
    print(f"[N7 classify] {calls} classifier calls via {client.name}: "
          + ", ".join(f"{k}={v}" for k, v in tally.items()) + (f", {failed} failed after retry" if failed else ""))
    return {"classified_findings": out}


# Build Guide: P4-C5
# Decision: evidence laid out per rule: sources side by side, absence as absence, R3 as counts and the exact ratio
def evidence_view(f: SuspectedFinding, cfg: ReviewConfig) -> list[str]:
    lines = []
    quotes = [e for e in f.evidence if e.quotation]
    if f.rule_id == "R3":
        calc = next((e for e in f.evidence if e.role == "calculation"), None)
        if calc and calc.numeric_inputs:
            cap, used, res = (calc.numeric_inputs.get(k, 0) for k in ("capacity", "used", "reserved"))
            where = ", ".join(_where(loc) for loc in calc.locations)
            lines.append(f"Installed {cap:g}, used {used:g}, reserved {res:g}, spare {cap - used - res:g}: "
                         f"{calc.formula} = {calc.computed_value} percent, limit {cfg.spare_io_threshold_pct:g} ({where})")
        return lines
    if quotes:
        lines.append("Side by side:" if len(quotes) > 1 else "Source:")
        lines += [f"  {', '.join(_where(loc) for loc in e.locations) or 'n/a'} | {e.quotation}" for e in quotes]
    for e in f.evidence:
        if e.role == "absence":
            lines.append(f"Absent: not found after searching {e.searched_scope}")
        elif e.role == "calculation" and f.rule_id == "R5" and e.numeric_inputs:
            lines.append(f"Lengths in feet: {e.numeric_inputs.get('min_ft')} and {e.numeric_inputs.get('max_ft')}; "
                         f"{e.formula} = {e.computed_value} percent, limit {cfg.cable_length_tolerance_pct:g}")
    return lines


# Build Guide: P4-C4
# Decision: blank reviewer columns in the CSV; marked files stay beside the run log and nothing reads them yet
# Future (P4-C4): analysis of marked reviews, per P5-C3.
REVIEWER_COLUMNS = ["reviewer_decision", "reviewer_note"]  # reviewer_decision: accepted, rejected or changed


FIX_TEMPLATES = {
    "R1": "Reconcile tag {entity} across the drawings, points list and sequence: {reason}.",
    "R2": "Make the IO assignment at {entity} match between the IO sheet and the points list ({reason}).",
    "R3": "Add capacity or release reserved points on {entity} to restore at least {spare:g} percent spare ({reason}).",
    "R4": "Make the drawing index and the sheet header for {entity} agree ({reason}).",
    "R5": "Confirm the length of {entity} and show the same value on every sheet ({reason}).",
}


# Build Guide: P0-C1, P0-C2, P4-C1, P4-C5
# Decision: N8 order - R1 to R5 then sheet; a real_error without complete evidence is held back (P4-C1)
# Reads:    classified_findings, review_config
# Writes:   ordered_comments, convention_findings, unresolved_findings
# Why:      suggested fixes come from a fixed template per rule, so a fix never says more than the evidence
# May change: priority ordering by discrepancy type and severity weighting once evidence supports weights
# Wraps:    original
def n8_order(state: ReviewState) -> dict:
    classified, cfg = state["classified_findings"], state.get("review_config") or ReviewConfig()
    gated = []
    for c in classified:  # P4-C1: never issue a comment without complete rule-appropriate evidence
        if c.verdict == "real_error" and not evidence_complete(c.finding):
            c = c.model_copy(update={"verdict": "unresolved", "reason": f"not issued: the {c.finding.rule_id} evidence "
                                     f"is incomplete, so this stays for a reviewer (model said: {c.reason})"})
        gated.append(c)
    classified = gated
    errors = [c for c in classified if c.verdict == "real_error"]
    errors.sort(key=lambda c: (c.finding.rule_id, (_sheets_of(c.finding) or ["~"])[0], c.finding.finding_id))
    comments = [ReviewComment(
        finding_id=c.finding.finding_id, rule_id=c.finding.rule_id, affected_entity_key=c.finding.affected_entity_key,
        cited_sheets=_sheets_of(c.finding), evidence_lines=evidence_view(c.finding, cfg),
        context_sheet_numbers=c.context_sheet_numbers, verdict=c.verdict, supporting_quote=c.supporting_quote,
        reason=c.reason, suggested_fix=FIX_TEMPLATES[c.finding.rule_id].format(
            entity=c.finding.affected_entity_key, reason=c.finding.candidate_reason, spare=cfg.spare_io_threshold_pct),
    ) for c in errors]
    conventions = [c for c in classified if c.verdict == "drafting_convention"]
    unresolved = [c for c in classified if c.verdict == "unresolved"]
    print(f"[N8 order] {len(comments)} comments, {len(conventions)} conventions, {len(unresolved)} unresolved")
    return {"ordered_comments": comments, "convention_findings": conventions, "unresolved_findings": unresolved}


def _other_block(n: int, c: ClassifiedFinding, cfg: ReviewConfig) -> list[str]:
    f = c.finding
    lines = [f"{n}. [{f.rule_id}] {f.finding_id}", f"   Entity: {f.affected_entity_key}",
             f"   Rule says: {f.candidate_reason}", "   Evidence:"]
    lines += [f"     {line}" for line in evidence_view(f, cfg)]
    lines += [f"   Sheets given to classifier: {', '.join(c.context_sheet_numbers)}",
              f"   Verdict: {c.verdict} - {c.reason}"]
    if c.supporting_quote:
        lines.append(f'   Supporting quote: "{c.supporting_quote}"')
    if c.applicability_quote:
        lines.append(f'   Applies here because {c.convention_sheet} shows: "{c.applicability_quote}"')
    return lines + [""]


# Build Guide: P0-C1, P0-C2, P2-C3, P3-C1, P4-C3, P4-C4, P4-C5
# Decision: N9 report - report, run log, classify log, and a normalization review of collisions and aliases
# Reads:    ordered_comments, convention_findings, unresolved_findings, run_metadata, output_folder_path,
#           classified_findings, cross_reference_table
# Writes:   review_outputs
# Why:      the reviewer reads a document after the run; dismissed findings stay visible so they can be overruled
# May change: a static HTML report with the cited sheets beside each comment
# Wraps:    original
def n9_report(state: ReviewState) -> dict:
    out_dir = Path(state["output_folder_path"])
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = state["run_metadata"]
    comments, conventions, unresolved = state["ordered_comments"], state["convention_findings"], state["unresolved_findings"]
    txt = ["CONTROLS SUBMITTAL REVIEW - RECOMMENDED COMMENTS", f"Run: {meta.run_id}", f"Input: {meta.input_folder}",
           "These are recommended comments for an engineer to review. The agent does not approve or reject submittals.",
           "Mark each row's reviewer_decision in review_report.csv as accepted, rejected or changed.",
           "", f"REAL ERRORS ({len(comments)})", ""]
    for n, c in enumerate(comments, start=1):
        txt += [f"{n}. [{c.rule_id}] {c.finding_id}", f"   Entity: {c.affected_entity_key}",
                f"   Cited sheets: {', '.join(c.cited_sheets) or 'non-drawing sources only'}", "   Evidence:"]
        txt += [f"     {line}" for line in c.evidence_lines]
        txt += [f"   Sheets given to classifier: {', '.join(c.context_sheet_numbers)}",
                f"   Verdict: {c.verdict} - {c.reason}"]
        if c.supporting_quote:
            txt.append(f'   Supporting quote: "{c.supporting_quote}"')
        txt += [f"   Suggested fix: {c.suggested_fix}", ""]
    txt += [f"DRAFTING CONVENTIONS ({len(conventions)})", ""]
    cfg = state.get("review_config") or ReviewConfig()
    for n, c in enumerate(conventions, start=1):
        txt += _other_block(n, c, cfg)
    txt += [f"UNRESOLVED ({len(unresolved)})", ""]
    for n, c in enumerate(unresolved, start=1):
        txt += _other_block(n, c, cfg)
    xref = state.get("cross_reference_table") or {}
    collisions = normalization_collisions(xref)
    alias_uses = [(k, e) for k, entries in xref.items() for e in entries if e.alias_of]
    txt += [f"NORMALIZATION REVIEW ({len(collisions)} collisions, {len(alias_uses)} alias uses)", ""]
    for key, entries in collisions.items():
        txt.append(f"   Collision: {key} is written " + ", ".join(sorted({f'{e.tag_raw!r}' for e in entries}))
                   + " (" + ", ".join(_where(e.location) for e in entries) + "). Check they are the same point.")
    for key, e in alias_uses:
        txt.append(f"   Alias: {e.alias_of} read as {key} at {_where(e.location)}, per an ALIAS line")
    txt.append("")
    report_txt = out_dir / "review_report.txt"
    report_txt.write_text("\n".join(txt) + "\n", encoding="utf-8")

    report_csv = out_dir / "review_report.csv"
    with report_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["section", "finding_id", "rule_id", "entity", "verdict", "cited_sheets",
                    "supporting_quote", "reason", "suggested_fix"] + REVIEWER_COLUMNS)
        for c in comments:
            w.writerow(["comment", c.finding_id, c.rule_id, c.affected_entity_key, c.verdict, " ".join(c.cited_sheets),
                        c.supporting_quote or "", c.reason, c.suggested_fix, "", ""])
        for section, items in (("convention", conventions), ("unresolved", unresolved)):
            for c in items:
                w.writerow([section, c.finding.finding_id, c.finding.rule_id, c.finding.affected_entity_key, c.verdict,
                            " ".join(_sheets_of(c.finding)), c.supporting_quote or "", c.reason, "", "", ""])

    run_log = out_dir / "run_log.txt"
    run_log.write_text("\n".join([f"{k}: {v}" for k, v in meta.model_dump().items()] + [
        f"comments: {len(comments)}", f"conventions: {len(conventions)}", f"unresolved: {len(unresolved)}",
        f"finished_at: {datetime.now().isoformat(timespec='seconds')}"]) + "\n", encoding="utf-8")
    classify_log = out_dir / "classify_log.jsonl"
    with classify_log.open("w", encoding="utf-8") as fh:
        for c in state["classified_findings"]:
            entry = {"finding_id": c.finding.finding_id, "verdict": c.verdict, "attempts": c.model_attempt_count,
                     "attempt_failures": c.attempt_failures, "context_included": c.context_included,
                     "context_omitted": c.context_omitted, "prompt_tokens_est": c.prompt_tokens_est,
                     "prompt_version": meta.prompt_version, "applicability_quote": c.applicability_quote,
                     "prompt_sha256": hashlib.sha256(c.prompt_text.encode("utf-8")).hexdigest() if c.prompt_text else None}
            if meta.full_text_logging:  # P4-C3 (I10): full text only for frozen synthetic datasets
                entry.update(prompt=c.prompt_text, attempt_records=c.attempts)
            else:
                entry.update(prompt="withheld: input is not a frozen synthetic dataset",
                             attempt_records=[{k: v for k, v in a.items() if k != "reply"} for a in c.attempts])
            fh.write(json.dumps(entry) + "\n")
    print(f"[N9 report] wrote {report_txt.name}, {report_csv.name}, {run_log.name}, {classify_log.name} to {out_dir}")
    return {"review_outputs": ReviewOutputs(report_txt_path=str(report_txt), report_csv_path=str(report_csv),
                                            run_log_path=str(run_log), classify_log_path=str(classify_log))}


# ---------------------------------------------------------------------------
# Graph and CLI
# ---------------------------------------------------------------------------

NODES = [
    ("N1_ingest", n1_ingest), ("N2_validate", n2_validate), ("N3_extract", n3_extract),
    ("N4_cross_reference", n4_cross_reference), ("N5_rule_checks", n5_rule_checks),
    ("N6_gather_context", n6_gather_context), ("N7_classify", None), ("N8_order", n8_order), ("N9_report", n9_report),
]


# Build Guide: P0-C1, P1-C2, P1-C4
# Decision: one agent, linear LangGraph graph N1 to N9; no branches, retries, planning or model-chosen tools
def build_graph(client: ClassifierClient):
    graph = StateGraph(ReviewState)
    previous = START
    for name, fn in NODES:
        graph.add_node(name, fn if fn else (lambda state: n7_classify(state, client)))
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    return graph.compile()


# Build Guide: P4-C3
# Decision: tie each run to the exact package, dataset and code that produced it
def run_identity(input_folder: Path) -> dict:
    sources = {}
    for name in REQUIRED_FILES.values():
        path = input_folder / name
        if path.is_file():
            st = path.stat()
            sources[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size_bytes": st.st_size,
                             "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}
    dataset, synthetic = "not a frozen synthetic dataset", False
    for manifest in (FROZEN_DATASETS, FROZEN_EVAL_SETS):
        if not manifest.is_file():
            continue
        frozen = json.loads(manifest.read_text(encoding="utf-8"))
        for name, info in frozen.get("datasets", {}).items():
            if sources and all(info["files"].get(k) == v["sha256"] for k, v in sources.items()):
                dataset, synthetic = f"{name} (generator {frozen.get('generator_version')}, frozen {frozen.get('frozen_on')})", True
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE, capture_output=True, text=True,
                                timeout=5).stdout.strip() or "not a git checkout"
    except (OSError, subprocess.SubprocessError):
        commit = "not a git checkout"
    code = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]
    return {"source_files": sources, "dataset": dataset, "full_text_logging": synthetic,
            "code_version": f"{commit}, submittal_review.py sha256 {code}"}


def _count(value) -> int:
    return len(value) if isinstance(value, (list, dict)) else 1


# Build Guide: P4-C6
# Decision: a run summary for each run, compared with the last run of the same package in the same output folder
def write_run_summary(state: dict, run_dir: Path, seconds: float) -> dict:
    classified = state.get("classified_findings", [])
    summary = {
        "run_id": run_dir.name, "source_hashes": {k: v["sha256"] for k, v in state["run_metadata"].source_files.items()},
        "sheets_read": len(state.get("sheet_records", [])), "tags_extracted": len(state.get("cross_reference_table", {})),
        "findings_per_rule": {r: sum(f.rule_id == r for f in state.get("suspected_findings", [])) for r in RULE_IDS},
        "verdicts": {"comments": len(state.get("ordered_comments", [])), "conventions": len(state.get("convention_findings", [])),
                     "unresolved": len(state.get("unresolved_findings", []))},
        "model_failed_attempts": sum(len(c.attempt_failures) for c in classified),
        "model_failed_findings": sum(1 for c in classified if c.attempt_failures and c.reason.startswith("model reply failed")),
        "run_seconds": round(seconds, 1), "changes_from_last_run": [], "compared_to": None,
    }
    earlier = sorted(p for p in run_dir.parent.glob("run_*/run_summary.json") if p.parent != run_dir)
    for prior_path in reversed(earlier):
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        if prior.get("source_hashes") != summary["source_hashes"]:
            continue
        summary["compared_to"] = prior["run_id"]
        for key in ("sheets_read", "tags_extracted"):
            if prior[key] != summary[key]:
                summary["changes_from_last_run"].append(f"{key} {prior[key]} -> {summary[key]} on the same package")
        if prior["verdicts"]["unresolved"] != summary["verdicts"]["unresolved"]:
            summary["changes_from_last_run"].append(
                f"unresolved {prior['verdicts']['unresolved']} -> {summary['verdicts']['unresolved']} on the same package")
        break
    (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    note = "; ".join(summary["changes_from_last_run"]) or "no change from the last run of this package"
    print(f"[monitor] {note}" if summary["compared_to"] else "[monitor] first run of this package in this output folder")
    return summary


# Build Guide: P1-C1, P1-C5, P4-C3, P4-C6
# Decision: single-shot run; the only memory is this run's state; every node, rule and stop is written to an audit log
# Future (P1-C5): a static HTML report with the cited sheets shown beside each comment.
def run_review(input_folder: Path, output_folder: Path, client: ClassifierClient,
               config: Optional[ReviewConfig] = None, config_file: str = "", config_sha256: str = "") -> ReviewState:
    input_folder, output_folder = Path(input_folder).resolve(), Path(output_folder).resolve()
    if output_folder == input_folder or input_folder in output_folder.parents:
        raise ValueError("The output folder must not be inside the input folder.")
    stamp = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    preflight = getattr(client, "preflight", None)
    if preflight:  # P2-C3: stop before any node runs if the model is not there
        preflight()
    run_dir, n = output_folder / stamp, 2
    while run_dir.exists():  # never overwrite an earlier run
        run_dir, n = output_folder / f"{stamp}_{n}", n + 1
    config = config or ReviewConfig()
    meta = RunMetadata(run_id=run_dir.name, started_at=datetime.now().isoformat(timespec="seconds"),
                       input_folder=str(input_folder), output_run_folder=str(run_dir), classifier_name=client.name,
                       config_file=config_file or "defaults", config_sha256=config_sha256 or "n/a",
                       config_values=config.model_dump_json(),
                       model_digest=getattr(client, "model_digest", "n/a"), **run_identity(input_folder))
    state: dict = {"submittal_folder_path": str(input_folder), "output_folder_path": str(run_dir),
                   "run_metadata": meta, "review_config": config}
    audit = [{"event": "run_start", "at": meta.started_at, **json.loads(meta.model_dump_json())}]
    started = last = time.monotonic()
    try:
        for update in build_graph(client).stream(dict(state), stream_mode="updates"):
            for node, output in update.items():
                now = time.monotonic()
                audit.append({"event": "node", "node": node, "seconds": round(now - last, 3),
                              "outputs": {k: _count(v) for k, v in (output or {}).items()}})
                last = now
                state.update(output or {})
                if node == "N5_rule_checks":
                    xref = state.get("cross_reference_table", {})
                    for f in output["suspected_findings"]:
                        audit.append({"event": "rule_fired", "finding_id": f.finding_id, "rule_id": f.rule_id,
                                      "entity": f.affected_entity_key, "reason": f.candidate_reason,
                                      "evidence": [json.loads(e.model_dump_json()) for e in f.evidence],
                                      "entity_spellings": sorted({(e.tag_raw, e.alias_of or "") for e in
                                                                  xref.get(f.affected_entity_key, [])})})
        audit.append({"event": "run_end", "seconds": round(time.monotonic() - started, 3)})
    except BaseException as exc:  # keep a partial audit log for any stop, including Ctrl-C
        audit.append({"event": "run_stopped", "seconds": round(time.monotonic() - started, 3),
                      "error": f"{type(exc).__name__}: {exc}"})
        raise
    finally:
        run_dir.mkdir(parents=True, exist_ok=True)
        with (run_dir / "audit_log.jsonl").open("w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(e, default=str) + "\n" for e in audit)
    write_run_summary(state, run_dir, time.monotonic() - started)
    return state


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="submittal_review", description="Controls Submittal Review Agent (Phase 5)")
    ap.add_argument("--input", required=True, help="submittal folder with drawings.pdf, points.xlsx, sequence.txt")
    ap.add_argument("--output", required=True, help="output folder; each run gets its own subfolder")
    ap.add_argument("--classifier", choices=("ollama", "recorded"), default="ollama",
                    help="ollama (default) or recorded replies for offline runs")
    ap.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL, help="local Ollama address (localhost only)")
    ap.add_argument("--responses", default=str(DEFAULT_RESPONSES), help="recorded replies for --classifier recorded")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), help="thresholds and limits (P1-C3)")
    args = ap.parse_args(argv)
    try:
        config_path = Path(args.config)
        config = load_config(config_path)
        config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
        print(f"[config] {config_path.name}: spare under {config.spare_io_threshold_pct:g} percent, "
              f"cable over {config.cable_length_tolerance_pct:g} percent, sha256 {config_sha[:12]}")
        client = (OllamaClient(config, args.ollama_url) if args.classifier == "ollama"
                  else RecordedResponseClient(Path(args.responses)))
        result = run_review(Path(args.input), Path(args.output), client, config, str(config_path.resolve()), config_sha)
    except (ModelUnavailableError, SizeLimitError, ValueError, FileNotFoundError) as exc:
        print(f"[stopped] {exc}")
        return 1
    except KeyboardInterrupt:  # P5-C4: cancellation keeps the partial audit log and classify progress
        print(f"[stopped] cancelled with Ctrl-C; partial logs kept in {Path(args.output).resolve()}")
        return 130
    print(f"[model] {client.name}, digest {getattr(client, 'model_digest', 'n/a')}, prompt {PROMPT_VERSION}")
    print(f"Done. Open {result['review_outputs'].report_txt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
