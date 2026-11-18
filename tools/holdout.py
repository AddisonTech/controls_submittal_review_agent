"""Holdout guard for the Controls Submittal Review Agent (P5-C2).

The holdout is pre-registered in eval_sets/holdout_registration.json before any
final test: the holdout cases, the SHA-256 of their inputs and sealed labels, and
the SHA-256 of the metric script (tools/validate.py). Tuning tools call refuse()
so a holdout folder can never be used for tuning, and tools/validate.py --final
scores it exactly once.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRATION = ROOT / "eval_sets" / "holdout_registration.json"
METRIC_SCRIPT = ROOT / "tools" / "validate.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def registration() -> dict:
    return json.loads(REGISTRATION.read_text(encoding="utf-8")) if REGISTRATION.is_file() else {}


# Build Guide: P5-C2
# Decision: a holdout folder is recognized by name or by its registered input hashes
def is_holdout(folder: Path) -> bool:
    reg = registration()
    folder = Path(folder)
    for case in reg.get("cases", {}).values():
        files = case["inputs"]
        if folder.name == case["folder"] or (
                all((folder / n).is_file() for n in files) and all(sha256(folder / n) == h for n, h in files.items())):
            return True
    return False


def refuse(folder: Path, tool: str) -> None:
    """Stop a tuning tool from touching the holdout (P5-C2)."""
    if is_holdout(folder):
        raise SystemExit(f"{tool}: {Path(folder).name} is a registered holdout. It is scored once, with "
                         "tools\\validate.py --final, and never used for tuning.")


# Build Guide: P5-C2
# Decision: the holdout has not been touched when its inputs, sealed labels and the metric script match registration
def untouched() -> list[str]:
    reg, problems = registration(), []
    if not reg:
        return ["no holdout is registered (run tools\\validate.py --register)"]
    for name, case in reg["cases"].items():
        folder = ROOT / "eval_sets" / case["folder"]
        for fname, h in {**case["inputs"], **case["labels"]}.items():
            if not (folder / fname).is_file() or sha256(folder / fname) != h:
                problems.append(f"{name}: {fname} changed since registration")
    if sha256(METRIC_SCRIPT) != reg["metric_script_sha256"]:
        problems.append("tools\\validate.py changed since the holdout was registered")
    return problems
