"""Controls Submittal Review Agent v2: spec compliance review.

Reads one v2 package (spec.txt, submittal_sequence.txt, submittal_points.csv,
drawing_list.csv), checks the submittal against the governing specification and
drafts recommended comments with exact quotes for an engineer to review. It
never approves or rejects a submittal and never changes a source file.

Six steps in one straight line, the same for every engine:
  V1 ingest -> V2 parse -> V3 table rules -> V4 build items -> V5 model check -> V6 report

V3 table rules are plain code with exact keys (trimmed, spaces collapsed, upper case, as v1 P3-C1):
  T1 point_missing          a points schedule row with no points list row of the same name
  T2 wrong_point_type       io_type differs between the schedule and the points list
  T3 unit_scaling_mismatch  units or range differ
  T4 alarm_wrong_or_missing alarm text differs
  T5 device_tag_mismatch    the points list and the drawing list name different devices for a point,
                            or a drawing list device names no points list point
  T6 ddc_hardware_mismatch  the points list and the drawing list name different DDC hardware for a point
Each difference goes to the model, one at a time, which answers real_error, not_an_error or unresolved.

V4 lines up each specification sequence section with the submittal section of the same number. The model lists
sequence_contradiction, setpoint_out_of_spec, alarm_wrong_or_missing and interlock_missing issues, each with
one exact quote from each side.

Code checks every reply, for every engine: it must parse into the reply schema, every quote must appear word for
word in the text the model was given (and a sequence quote must point at exactly one paragraph), the reason may
not use approve or reject language, at most two attempts, then unresolved.

Run:  .venv\\Scripts\\python.exe -m spec_review --input validation\\v2\\dev\\v2c01_ahu_mz\\seeded --output out
      [--engine gemma3:4b | claude-haiku | claude-sonnet]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

import submittal_review as sr

VERSION = "2.0.0"
PROMPT_VERSION_V2 = "v2-p2"
HERE = Path(__file__).resolve().parent
V2_DIR = HERE / "validation" / "v2"
INPUT_FILES = ("spec.txt", "submittal_sequence.txt", "submittal_points.csv", "drawing_list.csv")
TABLE_RULES = {"T1": "point_missing", "T2": "wrong_point_type", "T3": "unit_scaling_mismatch",
               "T4": "alarm_wrong_or_missing", "T5": "device_tag_mismatch", "T6": "ddc_hardware_mismatch"}
PROSE_TYPES = ("sequence_contradiction", "setpoint_out_of_spec", "alarm_wrong_or_missing", "interlock_missing")
PARA = re.compile(r"^(\d+(?:\.\d+)+[a-z]?) (.+)$")
SECTION = re.compile(r"^SECTION:\s*(\S+)\s*\|\s*(.+?)\s*$")


class HoldoutRefused(SystemExit):
    pass


# ---------------------------------------------------------------------------
# V1 ingest and V2 parse
# ---------------------------------------------------------------------------
@dataclass
class Section:
    num: str
    title: str
    paras: dict = field(default_factory=dict)  # paragraph number -> whole line as written


@dataclass
class Package:
    folder: Path
    general: list
    spec_sections: dict
    spec_points: dict  # name -> (row dict, line)
    spec_points_header: str
    sub_sections: dict
    points: dict
    points_header: str
    drawing: dict  # device tag -> (row dict, line)
    drawing_header: str
    hashes: dict


def _sections(lines: list[str], start: int = 0, stop: Optional[str] = None) -> dict:
    out, cur = {}, None
    for line in lines[start:]:
        if stop and line.startswith(stop):
            break
        m = SECTION.match(line)
        if m:
            cur = out[m.group(1)] = Section(m.group(1), m.group(2))
            continue
        p = PARA.match(line)
        if p and cur is not None:
            cur.paras[p.group(1)] = line
    return out


def _csv_rows(text: str) -> tuple[str, list[tuple[dict, str]]]:
    lines = [l for l in text.splitlines() if l.strip()]
    header = next(csv.reader([lines[0]]))
    rows = []
    for line in lines[1:]:
        vals = next(csv.reader([line]))
        rows.append((dict(zip(header, vals)), line))
    return lines[0], rows


def parse_package(folder: Path) -> Package:
    folder = Path(folder)
    missing = [n for n in INPUT_FILES if not (folder / n).is_file()]
    if missing:
        raise FileNotFoundError(f"{folder}: missing {', '.join(missing)} (a v2 package holds {', '.join(INPUT_FILES)})")
    raw = {n: (folder / n).read_bytes() for n in INPUT_FILES}
    text = {n: b.decode("utf-8") for n, b in raw.items()}
    spec = text["spec.txt"].splitlines()
    part3 = next((i for i, l in enumerate(spec) if l.startswith("PART 3")), 0)
    general = [l for l in spec[:part3] if PARA.match(l)]
    spec_sections = _sections(spec, part3, stop="POINTS SCHEDULE")
    sched = next((i for i, l in enumerate(spec) if l.startswith("POINTS SCHEDULE")), None)
    spec_points, sp_header = {}, ""
    if sched is not None:
        sp_header = spec[sched + 1]
        cols = [c.strip() for c in sp_header.split("|")]
        for line in spec[sched + 2:]:
            if not line.strip():
                continue
            vals = [v.strip() for v in line.split("|")]
            row = dict(zip(cols, vals))
            spec_points[norm(row["point_name"])] = (row, line)
    sub_sections = _sections(text["submittal_sequence.txt"].splitlines())
    p_header, p_rows = _csv_rows(text["submittal_points.csv"])
    d_header, d_rows = _csv_rows(text["drawing_list.csv"])
    return Package(folder, general, spec_sections, spec_points, sp_header, sub_sections,
                   {norm(r["point_name"]): (r, l) for r, l in p_rows}, p_header,
                   {norm(r["device_tag"]): (r, l) for r, l in d_rows}, d_header,
                   {n: hashlib.sha256(b).hexdigest() for n, b in raw.items()})


def norm(value: str) -> str:
    """Exact key per v1 P3-C1: trim, collapse spaces, upper case. Nothing else is merged."""
    return re.sub(r"\s+", " ", (value or "").strip()).upper()


# ---------------------------------------------------------------------------
# V3 table rules
# ---------------------------------------------------------------------------
class Candidate(BaseModel):
    cand_id: str
    rule: str
    error_type: str
    anchor: list  # [doc, key, field]
    summary: str
    context_lines: list


def _drawing_points(dev_row: dict) -> list[str]:
    return [norm(p) for p in (dev_row.get("connected_points") or "").split(";") if p.strip()]


def table_rules(pkg: Package) -> list[Candidate]:
    out: list[Candidate] = []
    listed_by = {}
    for tag, (row, line) in pkg.drawing.items():
        for p in _drawing_points(row):
            listed_by.setdefault(p, []).append(tag)

    def ctx(name: str, extra: list[str] = ()) -> list[str]:
        lines = [f"SPECIFICATION POINTS SCHEDULE columns: {pkg.spec_points_header}"]
        if name in pkg.spec_points:
            lines.append(pkg.spec_points[name][1])
        else:
            lines.append(f"Absent: no points schedule row named {name} in spec.txt")
        lines.append(f"SUBMITTAL POINTS LIST columns: {pkg.points_header}")
        if name in pkg.points:
            lines.append(pkg.points[name][1])
        else:
            lines.append(f"Absent: no row named {name} in submittal_points.csv ({len(pkg.points)} rows searched)")
        lines.append(f"DRAWING LIST columns: {pkg.drawing_header}")
        devs = list(dict.fromkeys(listed_by.get(name, []) + [t for t in extra if t in pkg.drawing]))
        lines += [pkg.drawing[t][1] for t in devs] or [f"Absent: no device in drawing_list.csv lists {name}"]
        return lines + [l for l in pkg.general]

    for name, (srow, _) in pkg.spec_points.items():
        if name not in pkg.points:
            out.append(Candidate(cand_id=f"T1:{name}:row", rule="T1", error_type=TABLE_RULES["T1"],
                                 anchor=["spec_points", srow["point_name"], "row"], context_lines=ctx(name),
                                 summary=f"the points schedule requires {srow['point_name']}; the points list has no row of that name"))
            continue
        prow = pkg.points[name][0]
        pairs = [("T2", "io_type", srow["io_type"], prow["io_type"]),
                 ("T3", "units_range", f"{srow['units']} | {srow['range']}", f"{prow['units']} | {prow['range']}"),
                 ("T4", "alarm", "" if srow["alarm"] == "-" else srow["alarm"], prow["alarm"])]
        for rule, fld, want, got in pairs:
            if norm(want) != norm(got):
                out.append(Candidate(cand_id=f"{rule}:{name}:{fld}", rule=rule, error_type=TABLE_RULES[rule],
                                     anchor=["points", prow["point_name"], fld], context_lines=ctx(name),
                                     summary=f"{prow['point_name']} {fld}: specification '{want or '(none)'}', submittal '{got or '(none)'}'"))
    for name, (prow, _) in pkg.points.items():
        dev = norm(prow.get("device_tag", ""))
        listed = listed_by.get(name, [])
        if (dev and dev not in pkg.drawing) or (listed and dev not in listed):
            out.append(Candidate(cand_id=f"T5:{name}:device_tag", rule="T5", error_type=TABLE_RULES["T5"],
                                 anchor=["points", prow["point_name"], "device_tag"], context_lines=ctx(name, [dev]),
                                 summary=f"{prow['point_name']}: points list device {prow.get('device_tag') or '(none)'}, drawing list "
                                         f"device {', '.join(listed) or '(none lists this point)'}"))
        drawing_dev = listed[0] if listed else (dev if dev in pkg.drawing else None)
        if drawing_dev:
            want = pkg.drawing[drawing_dev][0].get("ddc_hardware_id", "")
            if norm(want) != norm(prow.get("ddc_hardware_id", "")):
                out.append(Candidate(cand_id=f"T6:{name}:ddc_hardware_id", rule="T6", error_type=TABLE_RULES["T6"],
                                     anchor=["points", prow["point_name"], "ddc_hardware_id"], context_lines=ctx(name, [drawing_dev]),
                                     summary=f"{prow['point_name']}: points list DDC hardware {prow.get('ddc_hardware_id')}, "
                                             f"drawing list device {drawing_dev} on {want}"))
    for tag, (drow, dline) in pkg.drawing.items():
        names = _drawing_points(drow)
        unknown = [p for p in names if p not in pkg.points and p not in pkg.spec_points]
        if not names or unknown:
            lines = [f"DRAWING LIST columns: {pkg.drawing_header}", dline,
                     f"SUBMITTAL POINTS LIST columns: {pkg.points_header}",
                     f"Absent: submittal_points.csv has no row named {', '.join(unknown) if unknown else drow.get('connected_points', '')}"]
            out.append(Candidate(cand_id=f"T5:{tag}:connected_points", rule="T5", error_type=TABLE_RULES["T5"],
                                 anchor=["drawing", drow["device_tag"], "connected_points"], context_lines=lines + pkg.general,
                                 summary=f"drawing list device {drow['device_tag']} connects to "
                                         f"'{drow.get('connected_points', '')}', which is not a points list row"))
    order = {r: i for i, r in enumerate(TABLE_RULES)}
    return sorted(out, key=lambda c: order[c.rule])


# ---------------------------------------------------------------------------
# Prompts and reply schemas (the same for every engine)
# ---------------------------------------------------------------------------
FACTS = """Facts you may use
- Temperature: degC = (degF - 32) x 5 / 9. A temperature difference converts by 5 / 9 only.
- Pressure: 1 in. w.c. = 249.09 Pa. Water pressure: 1 psi = 6.895 kPa.
- Airflow: 1 cfm = 0.4719 L/s. Water flow: 1 gpm = 0.06309 L/s.
- Alarm levels: Level 1 is the most critical and Level 4 the least.
"""

TABLE_SYSTEM = """You check one difference that plain-code rules found between a building controls specification
and a contractor controls submittal. The rules compare the specification POINTS SCHEDULE with the submittal points
list (submittal_points.csv) and the contractor drawing device list (drawing_list.csv) by exact text, ignoring only
spaces and letter case. Some differences are real errors; others are the same requirement written another way.
Decide which this one is.

Verdicts
- real_error: the submittal does not meet the specification for this point or device. For example a point the
  schedule requires is not in the points list; the point type is a different kind (analog where binary is
  required, input where output is required); the units or range would read or scale the value wrongly; an alarm
  is missing or has a different level, limit or delay; the points list and the drawing list name different
  devices or different DDC hardware for the same point.
- not_an_error: both documents say the same thing in a different form, or the difference does not change what is
  built. For example a different unit symbol, unit spelling or abbreviation, range format or wording; an
  equivalent naming convention for point types; a value stated in other units that converts to the specified
  value within rounding; a drawing list device marked as needing no BAS connection.
- unresolved: the CONTEXT does not contain what you need to decide.

""" + FACTS + """- AI analog input, AO analog output, BI binary input, BO binary output. Some vendors write DI and DO for
  binary inputs and outputs.

Rules
- Use only the CONTEXT section. The FINDING section is what code found; never quote it.
- Point names, device tags and DDC hardware identifiers must match character for character, ignoring only spaces
  and letter case. Any other difference in one of them is a real_error.
- Judge only the field named in the FINDING. A difference in another column of the same row is checked on its
  own and is not a reason for this verdict.
- supporting_quote: copy ONE whole line exactly as it appears in the CONTEXT. For real_error quote the submittal
  line that is wrong, or the specification line that is not met when the submittal has no line. For not_an_error
  quote the submittal line that meets the specification. For unresolved write "".
- reason: one sentence in plain words. Never approve or reject the submittal and never ask for a resubmittal;
  only describe the difference.
Reply with JSON only: {"verdict": "...", "supporting_quote": "...", "reason": "..."}
"""

PROSE_SYSTEM = """You compare one section of a contractor sequence of operation with the same section of the
governing building controls specification, and list every place where the submittal does not meet the
specification. Paragraph numbers in the submittal follow the specification. A paragraph number with a letter
suffix (for example 3.1.3a) is a contractor addition with no matching specification paragraph.

Report an issue only of these types
- sequence_contradiction: a submittal step does something the specification forbids or does differently: a
  different mode, trigger, order, direction, controlled variable or action.
- setpoint_out_of_spec: a setpoint, limit, range, reset value, delay or interval differs from the specified value
  after unit conversion.
- alarm_wrong_or_missing: an alarm the specification requires is left out, or its level, condition or delay differs.
- interlock_missing: a safety or interlock the specification requires is left out or weakened, for example
  hardwired changed to software, manual reset changed to automatic reset, a required device or trigger left
  out, or a required paragraph left out.

These are not issues
- Different wording, sentence order or list order with the same meaning.
- A value in other units that converts to the specified value within rounding.
- A contractor addition that adds detail without changing a specified requirement.

""" + FACTS + """
Rules
- Use only the text you are given. Read every paragraph of both sections; an error can be anywhere, and one
  section can hold more than one.
- The SPECIFICATION REFERENCE shows the whole system. Read the section against it: a submittal that names the
  specific equipment, stages or cases of this system that a general specification phrase covers meets the
  specification. Quote only from the SPECIFICATION SECTION and the SUBMITTAL SECTION.
- submittal_quote: copy the words of ONE submittal paragraph exactly, from the SUBMITTAL SECTION. Write "" only
  when the submittal has no paragraph for the requirement at all.
- spec_quote: copy the words of ONE specification paragraph exactly, from the SPECIFICATION SECTION.
- reason: one sentence. Never approve or reject the submittal and never ask for a resubmittal.
- List only deviations. Never add an entry to say that a paragraph or a converted value matches.
- submittal_meets_spec: false for a real deviation. If your check of an entry finds that the submittal does meet
  the specification, set it true; code drops every entry marked true.
- If the section meets the specification, reply with an empty list.
Reply with JSON only: {"issues": [{"error_type": "...", "submittal_quote": "...", "spec_quote": "...", "reason": "...", "submittal_meets_spec": false}]}
"""

TableVerdict = Literal["real_error", "not_an_error", "unresolved"]


class TableReply(BaseModel):
    verdict: TableVerdict
    supporting_quote: str = ""
    reason: str = Field(min_length=1)


class ProseIssue(BaseModel):
    error_type: Literal["sequence_contradiction", "setpoint_out_of_spec", "alarm_wrong_or_missing", "interlock_missing"]
    submittal_quote: str = ""
    spec_quote: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    submittal_meets_spec: bool = False  # v2-p2: an entry the model itself found compliant is dropped by code


class ProseReply(BaseModel):
    issues: list[ProseIssue]


TABLE_SCHEMA = {"type": "object", "properties": {
    "verdict": {"type": "string", "enum": ["real_error", "not_an_error", "unresolved"]},
    "supporting_quote": {"type": "string"}, "reason": {"type": "string"}},
    "required": ["verdict", "supporting_quote", "reason"]}
PROSE_SCHEMA = {"type": "object", "properties": {"issues": {"type": "array", "items": {
    "type": "object", "properties": {
        "error_type": {"type": "string", "enum": list(PROSE_TYPES)},
        "submittal_quote": {"type": "string"}, "spec_quote": {"type": "string"}, "reason": {"type": "string"},
        "submittal_meets_spec": {"type": "boolean"}},
    "required": ["error_type", "submittal_quote", "spec_quote", "reason", "submittal_meets_spec"]}}}, "required": ["issues"]}


def table_user(c: Candidate) -> str:
    return (f"FINDING (do not quote)\nRULE: {c.rule} {c.error_type}\nCODE FOUND: {c.summary}\n\nCONTEXT:\n"
            + "\n".join(c.context_lines) + "\n")


def spec_reference(pkg: Package) -> str:
    """v2-p2: the whole specification for the system, the same for every section of a package (cached per package)."""
    out = ["SPECIFICATION REFERENCE (the whole specification for this system, for context; quote only from the",
           "SPECIFICATION SECTION and the SUBMITTAL SECTION further below)", "GENERAL REQUIREMENTS"] + pkg.general
    for num, sec in pkg.spec_sections.items():
        out += [f"SECTION {num} {sec.title}"] + list(sec.paras.values())
    out += ["POINTS SCHEDULE", pkg.spec_points_header] + [line for _, line in pkg.spec_points.values()]
    return "\n".join(out) + "\n\n"


def prose_user(pkg: Package, num: str) -> tuple[str, list[str], list[str]]:
    spec = pkg.spec_sections[num]
    sub = pkg.sub_sections.get(num)
    spec_lines = list(spec.paras.values())
    sub_lines = list(sub.paras.values()) if sub else []
    text = (f"SPECIFICATION SECTION {num} {spec.title}\n" + "\n".join(spec_lines) + "\n\n"
            f"SUBMITTAL SECTION {num} {spec.title}\n" + ("\n".join(sub_lines) if sub_lines else
                                                       "(the submittal has no section with this number)") + "\n")
    return text, spec_lines, sub_lines


# ---------------------------------------------------------------------------
# Code checks on every reply (the same for every engine)
# ---------------------------------------------------------------------------
def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().strip('"').strip()).strip()


def lines_containing(quote: str, lines: list[str]) -> list[str]:
    q = _squash(quote)
    return [l for l in lines if q and q in _squash(l)]


def para_of(line: str) -> str:
    m = PARA.match(line)
    return m.group(1) if m else ""


def check_table_reply(reply: TableReply, context_lines: list[str]) -> Optional[str]:
    if reply.verdict != "unresolved":
        if not reply.supporting_quote.strip():
            return f"{reply.verdict} verdict with no supporting quote"
        context = _squash("\n".join(context_lines))
        if _squash(reply.supporting_quote) not in context:
            return f"quote not found word for word in the supplied context: {reply.supporting_quote[:80]!r}"
    if any(p in reply.reason.lower() for p in sr.FORBIDDEN_PHRASES):
        return "reason uses approve or reject language, which the agent never uses"
    return None


def check_prose_issue(issue: ProseIssue, spec_lines: list[str], sub_lines: list[str]) -> tuple[Optional[str], str, str]:
    """Return (problem, submittal paragraph, specification paragraph). Each quote must point at exactly one paragraph."""
    spec_hit = lines_containing(issue.spec_quote, spec_lines)
    if len(spec_hit) != 1:
        return (f"spec_quote {'not found word for word' if not spec_hit else 'matches more than one paragraph'} "
                f"in the specification section: {issue.spec_quote[:80]!r}"), "", ""
    sub_para = ""
    if issue.submittal_quote.strip():
        sub_hit = lines_containing(issue.submittal_quote, sub_lines)
        if len(sub_hit) != 1:
            return (f"submittal_quote {'not found word for word' if not sub_hit else 'matches more than one paragraph'} "
                    f"in the submittal section: {issue.submittal_quote[:80]!r}"), "", ""
        sub_para = para_of(sub_hit[0])
    if any(p in issue.reason.lower() for p in sr.FORBIDDEN_PHRASES):
        return "reason uses approve or reject language, which the agent never uses", "", ""
    return None, sub_para, para_of(spec_hit[0])


# ---------------------------------------------------------------------------
# V5 model check and the whole run
# ---------------------------------------------------------------------------
def _call(engine, system: str, user: str, schema: dict, tag: str,
          prefix: Optional[str] = None) -> tuple[Optional[str], Optional[str], float, dict]:
    started = time.monotonic()
    engine.context = tag
    try:
        raw = engine.generate(system, user, schema, tag=tag, **({"prefix": prefix} if prefix else {}))
        problem = None
    except Exception as exc:  # timeout, connection error, refusal, cut-off reply: a failed attempt, never a stop
        from engines import BudgetExceeded
        if isinstance(exc, BudgetExceeded):
            raise
        raw, problem = None, f"{type(exc).__name__}: {str(exc)[:200]}"
    return raw, problem, time.monotonic() - started, dict(getattr(engine, "last_usage", None) or {})


def check_candidate(engine, c: Candidate, attempts: int, tag: str, log: list) -> dict:
    user = table_user(c)
    failures = []
    for attempt in range(1, attempts + 1):
        raw, problem, secs, usage = _call(engine, TABLE_SYSTEM, user, TABLE_SCHEMA, f"{tag}/{c.cand_id}")
        reply = None
        if problem is None:
            try:
                reply = TableReply.model_validate_json(raw)
                problem = check_table_reply(reply, c.context_lines)
            except Exception as exc:
                problem = f"{type(exc).__name__}: {str(exc)[:200]}"
        log.append({"item": c.cand_id, "kind": "table", "attempt": attempt, "seconds": round(secs, 3), "system": "TABLE_SYSTEM",
                    "user": user, "reply": raw, "problem": problem, "usage": usage})
        if problem is None:
            return {"verdict": reply.verdict, "quote": reply.supporting_quote, "reason": reply.reason,
                    "attempts": attempt, "failures": failures}
        failures.append(f"attempt {attempt}: {problem}")
    return {"verdict": "unresolved", "quote": "", "reason": f"model reply failed checks after {attempts} attempts; "
            f"last: {failures[-1]}", "attempts": attempts, "failures": failures}


def check_section(engine, pkg: Package, num: str, attempts: int, tag: str, log: list) -> dict:
    user, spec_lines, sub_lines = prose_user(pkg, num)
    prefix = spec_reference(pkg)
    failures, kept, bad, done = [], [], [], 0
    for attempt in range(1, attempts + 1):
        done = attempt
        raw, problem, secs, usage = _call(engine, PROSE_SYSTEM, user, PROSE_SCHEMA, f"{tag}/S{num}", prefix=prefix)
        kept, bad = [], []
        if problem is None:
            try:
                reply = ProseReply.model_validate_json(raw)
                for issue in [i for i in reply.issues if not i.submittal_meets_spec]:  # v2-p2: compliant entries dropped
                    p, sub_para, spec_para = check_prose_issue(issue, spec_lines, sub_lines)
                    (bad if p else kept).append((issue, p, sub_para, spec_para))
                if bad:
                    problem = f"{len(bad)} of {len(reply.issues)} issues failed checks; first: {bad[0][1]}"
            except Exception as exc:
                problem = f"{type(exc).__name__}: {str(exc)[:200]}"
        log.append({"item": f"S{num}", "kind": "prose", "attempt": attempt, "seconds": round(secs, 3), "system": "PROSE_SYSTEM",
                    "prefix_sha256": hashlib.sha256(prefix.encode("utf-8")).hexdigest(), "user": user, "reply": raw, "problem": problem, "usage": usage})
        if problem is None:
            break
        failures.append(f"attempt {attempt}: {problem}")
    issues, seen = [], set()
    for issue, _, sub_para, spec_para in kept:  # after the last attempt, issues that passed every check still stand
        anchor = ("sub", sub_para) if sub_para else ("spec", spec_para)
        if anchor in seen:
            continue
        seen.add(anchor)
        issues.append({"comment_id": f"P:{num}:{sub_para or '-'}:{spec_para}", "source": "prose", "rule": "P1",
                       "error_type": issue.error_type, "section": num, "sub_para": sub_para, "spec_para": spec_para,
                       "submittal_quote": issue.submittal_quote, "spec_quote": issue.spec_quote, "reason": issue.reason})
    unresolved = [{"item": f"S{num}", "reason": p, "error_type": i.error_type, "spec_quote": i.spec_quote,
                   "submittal_quote": i.submittal_quote} for i, p, _, _ in bad]
    if failures and len(failures) == attempts and not kept and not bad:
        unresolved.append({"item": f"S{num}", "reason": f"model reply failed checks after {attempts} attempts; last: {failures[-1]}"})
    return {"comments": issues, "unresolved": unresolved, "attempts": done, "failures": failures}


def holdout_v2_folder(folder: Path) -> bool:
    folder = Path(folder).resolve()
    if (V2_DIR / "holdout").resolve() in folder.parents:
        return True
    man = V2_DIR / "datasets_v2.json"
    if not man.is_file():
        return False
    hashes = {n: hashlib.sha256((folder / n).read_bytes()).hexdigest() for n in INPUT_FILES if (folder / n).is_file()}
    if len(hashes) != len(INPUT_FILES):
        return False
    for case in json.loads(man.read_text(encoding="utf-8"))["cases"].values():
        if case["split"] == "holdout" and any(all(case["files"].get(f"{t}/{n}") == h for n, h in hashes.items())
                                               for t in ("seeded", "clean")):
            return True
    return False


def refuse_holdout(folder: Path, tool: str) -> None:
    if holdout_v2_folder(folder):
        raise HoldoutRefused(f"{tool}: {Path(folder)} is part of the v2 holdout. It is scored once per engine with "
                             "tools\\validate_v2.py --holdout-final and never used for tuning.")


def run_spec_review(folder: Path, output: Path, engine, config: Optional[sr.ReviewConfig] = None, tag: str = "",
                    holdout_final: bool = False, write_files: bool = True) -> dict:
    """One package through V1 to V6. Returns the comments, dismissed differences, unresolved items and timing."""
    folder, output = Path(folder).resolve(), Path(output).resolve()
    if not holdout_final:
        refuse_holdout(folder, "spec_review")
    if output == folder or folder in output.parents:
        raise ValueError("The output folder must not be inside the input folder.")
    cfg = config or sr.ReviewConfig()
    started_at, t0 = datetime.now().isoformat(timespec="seconds"), time.monotonic()
    pkg = parse_package(folder)  # V1, V2
    candidates = table_rules(pkg)  # V3
    sections = list(pkg.spec_sections)  # V4
    print(f"[V3 table rules] {len(candidates)} differences; [V4 items] {len(sections)} sequence sections; "
          f"at most {(len(candidates) + len(sections)) * cfg.model_attempts} model calls via {engine.name}")
    log: list = []
    comments, dismissed, unresolved = [], [], []
    tag = tag or folder.name
    spent0 = _engine_spend(engine)
    for k, c in enumerate(candidates, 1):  # V5, table differences
        r = check_candidate(engine, c, cfg.model_attempts, tag, log)
        rec = {"comment_id": c.cand_id, "source": "table", "rule": c.rule, "error_type": c.error_type, "anchor": c.anchor,
               "summary": c.summary, "quote": r["quote"], "reason": r["reason"], "attempts": r["attempts"]}
        {"real_error": comments, "not_an_error": dismissed}.get(r["verdict"], unresolved).append(rec)
        print(f"  [V5 {k}/{len(candidates)}] {c.cand_id}: {r['verdict']} ({r['attempts']} attempt{'s' * (r['attempts'] > 1)})")
    for num in sections:  # V5, sequence sections
        r = check_section(engine, pkg, num, cfg.model_attempts, tag, log)
        comments += r["comments"]
        unresolved += r["unresolved"]
        print(f"  [V5 section {num}] {len(r['comments'])} issues" + (f", {len(r['unresolved'])} unresolved" if r["unresolved"] else ""))
    seconds = time.monotonic() - t0
    result = {"version": VERSION, "prompt_version": PROMPT_VERSION_V2, "folder": str(folder), "tag": tag,
              "engine": getattr(engine, "engine", engine.name), "engine_name": engine.name,
              "model_digest": getattr(engine, "model_digest", "n/a"), "started_at": started_at,
              "seconds": round(seconds, 2), "model_calls": len(log),
              "failed_attempts": sum(1 for l in log if l["problem"]), "cost_usd": round(_engine_spend(engine) - spent0, 6),
              "source_hashes": pkg.hashes, "candidates": [c.model_dump() for c in candidates],
              "comments": comments, "dismissed": dismissed, "unresolved": unresolved}
    if write_files:
        _write_outputs(output, result, log, public=_is_public(folder))
    print(f"[V6 report] {len(comments)} comments, {len(dismissed)} differences judged equivalent, "
          f"{len(unresolved)} unresolved, {seconds:.1f} s")
    return result


def _engine_spend(engine) -> float:
    guard = getattr(engine, "guard", None)
    if guard is None:
        return 0.0
    return guard.spent()


def _is_public(folder: Path) -> bool:
    from engines import frozen_public_set
    return frozen_public_set(folder)


REVIEWER_COLUMNS = sr.REVIEWER_COLUMNS


def _write_outputs(output: Path, result: dict, log: list, public: bool) -> Path:
    stamp = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir, n = output / stamp, 2
    while run_dir.exists():
        run_dir, n = output / f"{stamp}_{n}", n + 1
    run_dir.mkdir(parents=True)
    lines = [f"CONTROLS SUBMITTAL REVIEW AGENT v{VERSION}: SPECIFICATION COMPLIANCE REVIEW",
             f"Package: {result['folder']}", f"Engine: {result['engine_name']} ({result['model_digest']}), prompt {result['prompt_version']}",
             "These are recommended comments for an engineer to review. The agent does not approve or reject submittals.", "",
             f"RECOMMENDED COMMENTS ({len(result['comments'])})"]
    for i, c in enumerate(result["comments"], 1):
        if c["source"] == "table":
            lines += [f"{i}. [{c['rule']} {c['error_type']}] {c['summary']}", f"   Quote: {c['quote']}", f"   Why: {c['reason']}"]
        else:
            where = f"submittal {c['sub_para']}" if c["sub_para"] else "not in the submittal"
            lines += [f"{i}. [{c['error_type']}] section {c['section']}, {where}, specification {c['spec_para']}",
                      f"   Submittal: {c['submittal_quote'] or '(no paragraph)'}", f"   Specification: {c['spec_quote']}",
                      f"   Why: {c['reason']}"]
    lines += ["", f"DIFFERENCES JUDGED EQUIVALENT ({len(result['dismissed'])})"]
    lines += [f"- {d['summary']}: {d['reason']}" for d in result["dismissed"]]
    lines += ["", f"UNRESOLVED, FOR THE REVIEWER ({len(result['unresolved'])})"]
    lines += [f"- {u.get('comment_id', u.get('item'))}: {u['reason']}" for u in result["unresolved"]]
    (run_dir / "review_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (run_dir / "review_report.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["n", "comment_id", "error_type", "where", "submittal_quote", "spec_quote", "reason"] + REVIEWER_COLUMNS)
        for i, c in enumerate(result["comments"], 1):
            where = "/".join(c["anchor"]) if c["source"] == "table" else f"section {c['section']} submittal {c['sub_para'] or '-'}"
            w.writerow([i, c["comment_id"], c["error_type"], where, c.get("quote") or c.get("submittal_quote", ""),
                        c.get("spec_quote", ""), c["reason"], "", ""])
    with (run_dir / "check_log.jsonl").open("w", encoding="utf-8") as fh:
        for entry in log:
            if not public:  # full prompts and replies only for the frozen public and synthetic sets (v1 I10)
                entry = {**entry, "user": hashlib.sha256(entry["user"].encode("utf-8")).hexdigest(), "reply": None}
            fh.write(json.dumps(entry) + "\n")
    (run_dir / "run_summary.json").write_text(json.dumps({k: v for k, v in result.items() if k not in ("candidates",)},
                                                         indent=2) + "\n", encoding="utf-8")
    result["run_dir"] = str(run_dir)
    return run_dir


def main(argv: Optional[list[str]] = None) -> int:
    import engines as en
    ap = argparse.ArgumentParser(prog="spec_review", description=f"Controls Submittal Review Agent v{VERSION}: spec compliance review")
    ap.add_argument("--input", required=True, help=f"package folder with {', '.join(INPUT_FILES)}")
    ap.add_argument("--output", required=True, help="output folder; each run gets its own subfolder")
    ap.add_argument("--engine", choices=en.ENGINE_CHOICES, default=en.DEFAULT_ENGINE, help="review engine (default gemma3:4b, local)")
    ap.add_argument("--allow-cloud", action="store_true", help="let a Claude engine send a package that is not a frozen test set")
    ap.add_argument("--ollama-url", default=sr.DEFAULT_OLLAMA_URL)
    ap.add_argument("--config", default=str(sr.DEFAULT_CONFIG))
    args = ap.parse_args(argv)
    try:
        refuse_holdout(Path(args.input), "spec_review")
        cfg = sr.load_config(Path(args.config))
        en.check_cloud_allowed(args.engine, Path(args.input), args.allow_cloud)
        engine = en.make_engine(args.engine, cfg, args.ollama_url, run_label="spec_review_cli")
        engine.preflight()
        result = run_spec_review(Path(args.input), Path(args.output), engine, cfg)
    except HoldoutRefused as exc:
        print(f"[stopped] {exc}")
        return 2
    except (sr.ModelUnavailableError, en.BudgetExceeded, ValueError, FileNotFoundError) as exc:
        print(f"[stopped] {exc}")
        return 1
    except KeyboardInterrupt:
        print("[stopped] cancelled with Ctrl-C")
        return 130
    if result.get("cost_usd"):
        print(f"[cost] ${result['cost_usd']:.4f} for this package")
    print(f"Done. Open {Path(result['run_dir']) / 'review_report.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
