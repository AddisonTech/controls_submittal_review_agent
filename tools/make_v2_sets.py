"""Build test set v2: 40 spec compliance document pairs (seeded and clean twin).

Deterministic: no random numbers, the same code writes the same bytes. Each
case is one HVAC system from tools/v2_templates.py rendered as four files:

  spec.txt                 governing specification excerpt (sequence and points schedule)
  submittal_sequence.txt   contractor sequence of operation, paragraph numbers follow the spec
  submittal_points.csv     contractor points list (UFGS 23 09 00 paragraph 3.3.10 columns)
  drawing_list.csv         device list from the contractor drawings
  labels.json              planted errors and look-alikes (scoring only; the reviewer never reads it)

The seeded twin carries the planted errors; the clean twin is the same package
with none. Both carry the same correct look-alikes (units in other systems,
DI for BI, reworded alarms, added contractor paragraphs, local devices with no
BAS point), which a reviewer should not flag.

The split is fixed here: cases 4, 8, ..., 40 are the v2 holdout, the rest are dev.

  .venv\\Scripts\\python.exe tools\\make_v2_sets.py            build, freeze and pin
  .venv\\Scripts\\python.exe tools\\make_v2_sets.py --check    confirm the files on disk match the generator
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import v2_templates as T  # noqa: E402

GENERATOR_VERSION = "2.0.0"
V2 = ROOT / "validation" / "v2"
FILES = ("spec.txt", "submittal_sequence.txt", "submittal_points.csv", "drawing_list.csv", "labels.json")
INPUT_FILES = FILES[:4]
POINT_COLUMNS = ["point_name", "description", "ddc_hardware_id", "io_type", "units", "range", "settings", "alarm", "device_tag"]
DRAWING_COLUMNS = ["device_tag", "description", "ddc_hardware_id", "sheet", "connected_points"]
SPEC_POINT_COLUMNS = ["point_name", "description", "io_type", "units", "range", "alarm"]
SHORT = {"contra": "sequence_contradiction", "setpt": "setpoint_out_of_spec", "alarm": "alarm_wrong_or_missing",
         "interlock": "interlock_missing", "missing": "point_missing", "iotype": "wrong_point_type",
         "unit": "unit_scaling_mismatch", "talarm": "alarm_wrong_or_missing", "tag": "device_tag_mismatch",
         "ddc": "ddc_hardware_mismatch"}

# case: (template, number, variant, size, style, look-alikes, planted errors)
#   style: ip (inch-pound, as the spec), si (submittal in SI only) or dual (SI with inch-pound in brackets)
#   look-alikes: deg (degree sign and hyphen ranges), di (DI and DO for BI and BO), alarm_words (reworded
#   alarms), extra (added contractor paragraphs), local (local devices with no BAS point)
#   errors: (kind, target, mode) with kind from SHORT; prose targets are paragraph numbers, table targets point names
CASES = [
    ("ahu_mz", 1, 0, 0, "ip", ("extra", "local"), [("setpt", "3.1.3", ""), ("iotype", "AHU-1-SF-S", "")]),
    ("vav_rh", 2, 0, 8, "ip", ("alarm_words", "local"), [("setpt", "3.2.6", ""), ("tag", "VAV-203-FLOW", "points"), ("iotype", "VAV-206-DMP", "")]),
    ("fcu", 3, 0, 0, "dual", ("di", "extra"), [("contra", "3.2.3", ""), ("missing", "FCU-3-COS", "")]),
    ("chw_plant", 1, 0, 2, "ip", ("local", "alarm_words"), [("setpt", "3.3.2", ""), ("interlock", "3.6.3", "")]),
    ("hw_plant", 1, 0, 2, "ip", ("deg", "local"), [("contra", "3.2.1", ""), ("unit", "HWP-1-HW-DP", "span")]),
    ("ahu_sz", 4, 0, 0, "ip", ("di", "local"), [("alarm", "3.5.1", ""), ("talarm", "RTU-4-SAT", "value")]),
    ("ahu_mz", 2, 1, 0, "si", ("extra",), [("contra", "3.1.5", ""), ("setpt", "3.2.3", ""), ("ddc", "AHU-2-FZ", "points")]),
    ("vav_rh", 3, 1, 12, "ip", ("extra", "local"), [("setpt", "3.2.8", ""), ("alarm", "3.4.1", "")]),
    ("ahu_mz", 3, 2, 0, "ip", ("deg", "alarm_words"), [("interlock", "3.5.1", ""), ("interlock", "3.5.4", ""), ("missing", "AHU-3-OAF", "")]),
    ("chw_plant", 2, 1, 3, "dual", ("di",), [("contra", "3.3.2", ""), ("tag", "CHWP-2-CHWST", "points"), ("ddc", "CHWP-2-CWST", "points")]),
    ("fcu", 4, 1, 0, "ip", ("alarm_words", "local"), [("interlock", "3.4.1", ""), ("alarm", "3.4.2", ""), ("iotype", "FCU-4-CHWV", "")]),
    ("hw_plant", 2, 1, 3, "si", ("extra",), [("setpt", "3.5.2", ""), ("interlock", "3.5.3", ""), ("missing", "HWP-2-HWRT", "")]),
    ("ahu_sz", 5, 1, 0, "dual", ("extra",), [("contra", "3.1.3", ""), ("setpt", "3.4.3", ""), ("tag", "RTU-5-MAT", "points")]),
    ("vav_rh", 4, 2, 16, "si", ("alarm_words",), [("contra", "3.3.1", ""), ("setpt", "3.2.11", ""), ("talarm", "VAV-409-DAT", "blank")]),
    ("ahu_mz", 4, 3, 0, "ip", ("local", "di"), [("setpt", "3.4.1", ""), ("contra", "3.4.3", ""), ("iotype", "AHU-4-DSP", "")]),
    ("chw_plant", 3, 2, 2, "ip", ("deg", "extra"), [("interlock", "3.2.1", ""), ("missing", "CHWP-3-CHW-FS2", ""), ("unit", "CHWP-3-CHW-FLOW", "span")]),
    ("fcu", 5, 2, 0, "si", ("alarm_words",), [("setpt", "3.2.2", ""), ("ddc", "FCU-5-ZT", "points")]),
    ("hw_plant", 3, 2, 2, "dual", ("di", "local"), [("interlock", "3.3.1", ""), ("talarm", "HWP-3-B1-S", "delay")]),
    ("ahu_sz", 6, 2, 0, "ip", ("alarm_words", "extra"), [("interlock", "3.5.3", ""), ("unit", "RTU-6-FLT", "span"), ("missing", "RTU-6-OAT", "")]),
    ("vav_rh", 5, 0, 10, "dual", ("extra", "local"), [("alarm", "3.4.3", ""), ("interlock", "3.5.1", ""), ("tag", "VAV-504-DAT", "points")]),
    ("ahu_mz", 5, 4, 0, "dual", ("alarm_words",), [("alarm", "3.4.2", ""), ("alarm", "3.5.2", ""), ("unit", "AHU-5-SAT", "label")]),
    ("chw_plant", 4, 0, 3, "si", ("extra",), [("setpt", "3.4.1", ""), ("contra", "3.4.2", ""), ("iotype", "CHWP-4-CH2-S", "")]),
    ("fcu", 6, 0, 0, "ip", ("local", "deg"), [("setpt", "3.1.2", ""), ("tag", "FCU-6-SAT", "points"), ("unit", "FCU-6-ZT", "label")]),
    ("hw_plant", 4, 0, 2, "ip", ("alarm_words",), [("setpt", "3.2.1", ""), ("alarm", "3.4.2", ""), ("ddc", "HWP-4-HW-DP", "points")]),
    ("ahu_sz", 7, 0, 0, "si", ("di",), [("setpt", "3.1.1", ""), ("contra", "3.4.2", ""), ("missing", "RTU-7-FZ", "")]),
    ("vav_rh", 6, 1, 14, "ip", ("deg",), [("contra", "3.3.3", ""), ("setpt", "3.2.13", ""), ("missing", "VAV-607-FLOW", "")]),
    ("ahu_mz", 6, 5, 0, "ip", ("extra", "di"), [("contra", "3.3.4", ""), ("setpt", "3.3.3", ""), ("talarm", "AHU-6-DSP", "level")]),
    ("chw_plant", 5, 1, 2, "dual", ("local",), [("interlock", "3.6.1", ""), ("alarm", "3.6.2", ""), ("unit", "CHWP-5-CHW-DP", "span")]),
    ("fcu", 7, 1, 0, "ip", ("extra",), [("contra", "3.1.1", ""), ("ddc", "FCU-7-HWV", "points"), ("iotype", "FCU-7-FAN-S", "")]),
    ("hw_plant", 5, 1, 3, "ip", ("local", "di"), [("contra", "3.3.2", ""), ("interlock", "3.5.1", ""), ("tag", "HWP-5-HWRT", "points")]),
    ("ahu_mz", 7, 6, 0, "si", ("local",), [("interlock", "3.4.4", ""), ("setpt", "3.5.3", ""), ("ddc", "AHU-7-SD-RA", "points")]),
    ("vav_rh", 7, 2, 9, "ip", ("alarm_words", "extra"), [("alarm", "3.4.2", ""), ("contra", "3.3.4", ""), ("iotype", "VAV-705-HWV", "")]),
    ("ahu_sz", 8, 1, 0, "ip", ("deg", "local"), [("setpt", "3.3.3", ""), ("talarm", "RTU-8-ZT", "delay"), ("unit", "RTU-8-SAT", "label")]),
    ("chw_plant", 6, 2, 3, "ip", ("alarm_words", "local"), [("contra", "3.5.2", ""), ("setpt", "3.5.1", ""), ("tag", "CHWP-6-RM", "points")]),
    ("fcu", 8, 2, 0, "dual", ("local",), [("setpt", "3.3.1", ""), ("missing", "FCU-8-SAT", ""), ("talarm", "FCU-8-COS", "blank")]),
    ("hw_plant", 6, 2, 2, "ip", ("extra", "deg"), [("contra", "3.3.2", ""), ("interlock", "3.5.2", ""), ("iotype", "HWP-6-HW-FS", "")]),
    ("ahu_mz", 8, 7, 0, "ip", ("alarm_words", "extra", "local"), [("contra", "3.2.2", ""), ("contra", "3.2.6", ""), ("unit", "AHU-8-OAF", "span")]),
    ("vav_rh", 8, 0, 12, "si", ("local",), [("setpt", "3.1.2", ""), ("ddc", "VAV-806-DMP", "points"), ("talarm", "VAV-803-FLOW", "value")]),
    ("ahu_sz", 9, 2, 0, "dual", ("alarm_words", "di"), [("interlock", "3.5.2", ""), ("setpt", "3.2.4", ""), ("missing", "RTU-9-ZT", "")]),
    ("ahu_mz", 9, 8, 0, "ip", ("di", "deg", "local"), [("alarm", "3.4.3", ""), ("setpt", "3.1.6", ""), ("tag", "AHU-9-SD-SA", "points"), ("ddc", "AHU-9-FLT", "points")]),
]
HOLDOUT_CASES = {i for i in range(4, 41, 4)}  # 1-based case numbers, fixed before any engine run
LONG_PARAGRAPHS, LONG_POINTS = 30, 40  # a package this size or larger counts as a long document


def case_id(i: int) -> str:
    return f"v2c{i:02d}_{CASES[i - 1][0]}"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _num(x: float, nd: int) -> str:
    s = f"{x:.{nd}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def render(text: str, p: dict, style: str) -> str:
    def rep(m: re.Match) -> str:
        kind, key = m.group(1), m.group(2)
        v = p[key]
        if kind is None:
            return str(v)
        ip = {"T": f"{_num(v, 1)} °F", "dT": f"{_num(v, 1)} °F", "P": f"{_num(v, 2)} in. w.c.", "F": f"{_num(v, 0)} cfm",
              "W": f"{_num(v, 0)} gpm", "D": f"{_num(v, 1)} psi"}[kind]
        si = {"T": f"{T.c(v):.1f} °C", "dT": f"{v * 5 / 9:.1f} °C", "P": f"{v * 249.09:.0f} Pa", "F": f"{v * 0.4719:.0f} L/s",
              "W": f"{v * 0.06309:.1f} L/s", "D": f"{v * 6.895:.0f} kPa"}[kind]
        return {"ip": ip, "si": si, "dual": f"{si} ({ip})"}[style]
    return re.sub(r"\{(?:(T|dT|P|F|W|D):)?([a-z_0-9]+)\}", rep, text)


IP_UNITS = {"temp": "degF", "press": "in. w.c.", "flow": "cfm", "pct": "%", "bin": "-", "wflow": "gpm", "wdp": "psi", "ppm": "ppm"}
SI_UNITS = {"temp": "degC", "press": "Pa", "flow": "L/s", "pct": "%", "bin": "-", "wflow": "L/s", "wdp": "kPa", "ppm": "ppm"}


def convert(kind: str, x: float, delta: bool = False) -> float:
    if kind == "temp":
        return x * 5 / 9 if delta else T.c(x)
    return x * {"press": 249.09, "flow": 0.4719, "wflow": 0.06309, "wdp": 6.895}.get(kind, 1.0)


def _fmt_si(kind: str, x: float) -> str:
    return _num(x, {"temp": 1, "press": 0, "flow": 0, "wflow": 1, "wdp": 0}.get(kind, 2))


def point_units(pt: T.Point, si: bool, deg: bool) -> str:
    u = (SI_UNITS if si else IP_UNITS)[pt.kind]
    if deg and u == "degF":
        u = "°F"
    return u


def point_range(pt: T.Point, si: bool, deg: bool, span: float = 1.0) -> str:
    lo, hi = pt.rng
    if pt.kind == "bin":
        return f"{lo}/{hi}"
    hi = hi * span
    if si:
        lo, hi = _fmt_si(pt.kind, convert(pt.kind, lo)), _fmt_si(pt.kind, convert(pt.kind, hi))
    else:
        lo, hi = _num(lo, 2), _num(hi, 2)
    return f"{lo}-{hi}" if deg else f"{lo} to {hi}"


def alarm_text(al: T.Alarm | None, pt: T.Point, si: bool, deg: bool, words: bool) -> str:
    if al is None:
        return ""
    u = point_units(pt, si, deg)
    val = ""
    if al.value is not None:
        if al.kind == "belowpct":
            val = _num(al.value, 1)
        elif si:
            val = _fmt_si(pt.kind, convert(pt.kind, al.value, delta=al.kind == "dev"))
        else:
            val = _num(al.value, 2)
    L, d = al.level, al.delay
    if not words:
        return {"above": f"Level {L}: above {val} {u} for {d} min", "below": f"Level {L}: below {val} {u} for {d} min",
                "dev": f"Level {L}: {val} {u} from setpoint for {d} min", "trip": f"Level {L}: on trip",
                "mismatch": f"Level {L}: status differs from command for {d} s",
                "belowpct": f"Level {L}: below {val} percent of setpoint for {d} min"}[al.kind]
    return {"above": f"L{L} high alarm at {val} {u}, {d} min delay", "below": f"L{L} low alarm at {val} {u}, {d} min delay",
            "dev": f"L{L} deviation alarm, +/- {val} {u} from setpoint, {d} min delay", "trip": f"L{L} alarm when tripped",
            "mismatch": f"L{L} command/status mismatch alarm, {d} s delay",
            "belowpct": f"L{L} low alarm under {val}% of setpoint, {d} min delay"}[al.kind]


def near_miss(tag: str) -> str:
    """A plausible mistyped device tag: change the last digit, or swap the last two letters."""
    if tag[-1].isdigit():
        return tag[:-1] + str((int(tag[-1]) + 5) % 10)
    head, last = tag.rsplit("-", 1)
    if len(last) >= 2:
        return f"{head}-{last[:-2]}{last[-1]}{last[-2]}"
    return tag + "1"


def other_ddc(ddc: str, all_ddc: list[str]) -> str:
    others = [d for d in dict.fromkeys(all_ddc) if d != ddc]
    if others:
        return others[0]
    head, last = ddc.rsplit("-", 1)
    return f"{head}-{int(last) + 1}" if last.isdigit() else ddc + "-2"


def _csv(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerows(rows)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# One case
# ---------------------------------------------------------------------------
def build_case(i: int) -> dict[str, dict[str, str]]:
    key, n, v, size, style, looks, errors = CASES[i - 1]
    fn = T.TEMPLATES[key]
    system, p = fn(n, v, size) if key in ("vav_rh", "chw_plant", "hw_plant") else fn(n, v)
    cid = case_id(i)
    twins = {}
    for twin in ("clean", "seeded"):
        twins[twin] = _render_twin(cid, system, p, style, set(looks), errors if twin == "seeded" else [], twin)
    return twins


def _render_twin(cid: str, system: T.System, p: dict, style: str, looks: set, errors: list, twin: str) -> dict[str, str]:
    si = style in ("si", "dual") and True
    deg = "deg" in looks and not si
    di = "di" in looks
    words = "alarm_words" in looks
    prose = {t: (k, mode) for k, t, mode in errors if k in T.PROSE_KEYS}
    table = [(k, t, mode) for k, t, mode in errors if k not in T.PROSE_KEYS]
    labels = []

    # ---- spec
    spec = [f"SPECIFICATION EXCERPT (synthetic test document, case {cid})",
            "SECTION 23 09 93 SEQUENCES OF OPERATION FOR HVAC CONTROLS",
            f"SYSTEM: {system.title}",
            "",
            "PART 1 GENERAL",
            "1.1 Provide a points schedule in tabular form for each HVAC system, with each row representing a hardware point, network point or configuration point.",
            "1.2 Alarm generation is the monitoring of a value, comparison of the value to alarm conditions and the creation of an alarm when the conditions set for the alarm are met.",
            "1.3 Values in this section are stated in inch-pound units. A submittal may state values in SI units when they convert to the specified value.",
            "1.4 The sequences below are the minimum required behavior. Do not change a specified value without approval.",
            "",
            "PART 3 EXECUTION, SEQUENCE OF OPERATION"]
    for s in system.sections:
        spec.append(f"SECTION: {s.num} | {s.title}")
        spec += [f"{pa.num} {render(pa.spec, p, 'ip')}" for pa in s.paras]
        spec.append("")
    spec.append(f"POINTS SCHEDULE: {system.eq}")
    spec.append(" | ".join(SPEC_POINT_COLUMNS))
    for pt in system.points:
        spec.append(" | ".join([pt.name, pt.desc, pt.io, point_units(pt, False, False), point_range(pt, False, False),
                                alarm_text(pt.alarm, pt, False, False, False) or "-"]))
    spec_text = "\n".join(spec) + "\n"

    # ---- submittal sequence
    seq = [f"CONTRACTOR SUBMITTAL: SEQUENCE OF OPERATION (synthetic test document, case {cid})",
           f"SUBMITTAL FOR: SECTION 23 09 93, {system.title}",
           "Paragraph numbers follow the specification. Paragraphs with a letter suffix are contractor additions.",
           ""]
    n_paras = 0
    for s in system.sections:
        seq.append(f"SECTION: {s.num} | {s.title}")
        for pa in s.paras:
            text = pa.sub
            if pa.num in prose:
                k, _ = prose[pa.num]
                text = pa.errs[k]
                same = [o for o, (kk, _) in prose.items() if o != pa.num and o.rsplit(".", 1)[0] == s.num]
                labels.append({"type": T.PROSE_KEYS[k], "kind": "absent" if text is T.ABSENT else "present",
                               "anchors": ([["spec", pa.num, ""]] if text is T.ABSENT else [["sub", pa.num, ""], ["spec", pa.num, ""]]),
                               "section": s.num, "same_section": bool(same),
                               "description": f"{pa.num}: " + ("paragraph left out of the submittal" if text is T.ABSENT else
                                                               f"{k} variant planted: {render(text, p, style)}")})
            if text is not T.ABSENT:
                seq.append(f"{pa.num} {render(text, p, style)}")
                n_paras += 1
            if "extra" in looks and pa.num in system.extras:
                num, extra = system.extras[pa.num]
                seq.append(f"{num} {render(extra, p, style)}")
        seq.append("")
    seq_text = "\n".join(seq).rstrip("\n") + "\n"

    # ---- submittal points list and drawing list
    rows = {}
    for pt in system.points:
        io_t = pt.io
        rows[pt.name] = {"point_name": pt.name, "description": pt.desc, "ddc_hardware_id": pt.ddc, "io_type": io_t,
                         "units": point_units(pt, si, deg), "range": point_range(pt, si, deg), "settings": "",
                         "alarm": alarm_text(pt.alarm, pt, si, deg, words), "device_tag": pt.device}
    devices = deepcopy(system.devices)
    by_name = {pt.name: pt for pt in system.points}
    all_ddc = [pt.ddc for pt in system.points]
    for k, target, mode in table:
        pt = by_name[target]
        row = rows[target]
        lab = {"type": SHORT[k], "kind": "present", "section": "points", "same_section": False}
        if k == "missing":
            del rows[target]
            for d in devices:
                if target in d.points:
                    d.points.remove(target)
            devices = [d for d in devices if d.points]
            lab.update(kind="absent", anchors=[["spec_points", target, "row"]],
                       description=f"{target} left out of the points list and the drawing list")
        elif k == "iotype":
            row["io_type"] = pt.bad_io
            lab.update(anchors=[["points", target, "io_type"]], description=f"{target} type {pt.io} listed as {pt.bad_io}")
        elif k == "unit":
            if mode == "span":
                row["range"] = point_range(pt, si, deg, span=2.0)
                lab["description"] = f"{target} range scaled to twice the specified span: {row['range']}"
            else:  # label: units of the other system with unconverted numbers
                row["units"] = "degF" if si else "degC"
                lab["description"] = f"{target} units {row['units']} with the range numbers left as {row['range']}"
            lab["anchors"] = [["points", target, "units_range"]]
        elif k == "talarm":
            al = deepcopy(pt.alarm)
            if mode == "blank":
                row["alarm"] = ""
            else:
                if mode == "level":
                    al.level = al.level + 2 if al.level <= 2 else al.level - 2
                elif mode == "value":
                    al.value = al.value * 2 if al.kind != "belowpct" else al.value - 30
                elif mode == "delay":
                    al.delay = al.delay * 6
                row["alarm"] = alarm_text(al, pt, si, deg, words)
            lab.update(anchors=[["points", target, "alarm"]],
                       description=f"{target} alarm {mode}: '{row['alarm']}' against the specified alarm")
        elif k == "tag":
            row["device_tag"] = near_miss(pt.device)
            lab.update(anchors=[["points", target, "device_tag"], ["drawing", pt.device, "connected_points"]],
                       description=f"{target} device tag {row['device_tag']} on the points list, {pt.device} on the drawing list")
        elif k == "ddc":
            row["ddc_hardware_id"] = other_ddc(pt.ddc, all_ddc)
            lab.update(anchors=[["points", target, "ddc_hardware_id"]],
                       description=f"{target} DDC hardware {row['ddc_hardware_id']} on the points list, {pt.ddc} on the drawing list")
        labels.append(lab)
    if di:
        for row in rows.values():
            row["io_type"] = {"BI": "DI", "BO": "DO"}.get(row["io_type"], row["io_type"])
    points_csv = _csv([POINT_COLUMNS] + [[r[c] for c in POINT_COLUMNS] for r in rows.values()])
    if "local" in looks:
        devices += deepcopy(system.local_devices)
    drawing_csv = _csv([DRAWING_COLUMNS] + [[d.tag, d.desc, d.ddc, d.sheet, "; ".join(d.points) or d.note] for d in devices])

    long_doc = n_paras >= LONG_PARAGRAPHS or len(rows) >= LONG_POINTS
    for j, lab in enumerate(labels, start=1):
        lab["error_id"] = f"{cid}-E{j}"
        lab["hard"] = sorted([h for h, on in (("long_document", long_doc), ("two_in_one_section", lab.pop("same_section")),
                                              ("lookalikes_nearby", bool(looks))) if on])
    lookalikes = sorted(looks | ({"units_" + style} if style != "ip" else set()))
    label_doc = {"case": cid, "twin": twin, "system": system.title, "style": style, "lookalikes": lookalikes,
                 "long_document": long_doc, "paragraphs": n_paras, "points": len(rows),
                 "errors": [{k: lab[k] for k in ("error_id", "type", "kind", "anchors", "section", "hard", "description")}
                            for lab in labels]}
    for f in (spec_text, seq_text, points_csv, drawing_csv):
        assert chr(0x2013) not in f and chr(0x2014) not in f, "no en or em dashes in generated text"
    return {"spec.txt": spec_text, "submittal_sequence.txt": seq_text, "submittal_points.csv": points_csv,
            "drawing_list.csv": drawing_csv, "labels.json": json.dumps(label_doc, indent=2) + "\n"}


# ---------------------------------------------------------------------------
# Build, freeze and pin
# ---------------------------------------------------------------------------
def folder_for(i: int) -> Path:
    return V2 / ("holdout" if i in HOLDOUT_CASES else "dev") / case_id(i)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build_all() -> dict[Path, bytes]:
    out = {}
    for i in range(1, len(CASES) + 1):
        for twin, files in build_case(i).items():
            for name, text in files.items():
                out[folder_for(i) / twin / name] = text.encode("utf-8")
    return out


def manifest(files: dict[Path, bytes]) -> dict:
    cases = {}
    for i in range(1, len(CASES) + 1):
        cid, base = case_id(i), folder_for(i)
        cases[cid] = {"split": "holdout" if i in HOLDOUT_CASES else "dev", "folder": base.relative_to(ROOT).as_posix(),
                      "files": {f"{twin}/{n}": sha256_bytes(files[base / twin / n]) for twin in ("seeded", "clean") for n in FILES}}
    return {"generator_version": GENERATOR_VERSION, "cases": cases}


def holdout_markdown(man: dict, scorer_sha: str) -> str:
    lines = ["# Test set v2 holdout (pinned)", "",
             "These 10 cases are the v2 holdout. They were split off when the set was generated, before any",
             "engine ran on any v2 case. Every v2 tool refuses a holdout folder unless it is run as",
             "`tools\\validate_v2.py --holdout-final`, which scores each engine on the holdout exactly once.",
             "", "The files are pinned by SHA-256. A file that does not match its pin stops the final run.", "",
             f"Generator: tools/make_v2_sets.py {man['generator_version']}", "",
             f"Scorer: tools/score_v2.py sha256 `{scorer_sha}`", "",
             "| case | file | sha256 |", "|---|---|---|"]
    for cid, info in man["cases"].items():
        if info["split"] != "holdout":
            continue
        for f, h in info["files"].items():
            lines.append(f"| {cid} | {info['folder']}/{f} | `{h}` |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build test set v2")
    ap.add_argument("--check", action="store_true", help="confirm the files on disk match the generator")
    args = ap.parse_args(argv)
    files = build_all()
    man = manifest(files)
    if args.check:
        bad = [p for p, b in files.items() if not p.is_file() or p.read_bytes() != b]
        print(f"{len(files) - len(bad)} of {len(files)} files match the generator")
        return 1 if bad else 0
    for path, data in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (V2 / "datasets_v2.json").write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    scorer = ROOT / "tools" / "score_v2.py"
    scorer_sha = sha256_bytes(scorer.read_bytes()) if scorer.is_file() else "not written yet"
    (V2 / "HOLDOUT_V2.md").write_text(holdout_markdown(man, scorer_sha), encoding="utf-8")
    counts: dict[str, dict[str, int]] = {}
    for p, b in files.items():
        if p.name == "labels.json" and p.parent.name == "seeded":
            split = p.parent.parent.parent.name
            for e in json.loads(b)["errors"]:
                counts.setdefault(e["type"], {"dev": 0, "holdout": 0})[split] += 1
    print(f"wrote {len(files)} files for {len(CASES)} cases ({len(HOLDOUT_CASES)} holdout)")
    for t in T.ERROR_TYPES:
        print(f"  {t:24s} dev {counts.get(t, {}).get('dev', 0):3d}  holdout {counts.get(t, {}).get('holdout', 0):3d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
