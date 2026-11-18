"""Test-only stand-in for a model that answers every development finding correctly.

It reads the development labels (never the holdout) and quotes a real line from the
prompt's CONTEXT, so every reply passes the agent's own checks. It exists only to test
the validation, benchmark and ship tools; the agent never sees labels.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABEL_FILES = [ROOT / "tests" / "fixtures" / n / "error_labels.json" for n in ("seeded", "clean")] + [
    ROOT / "eval_sets" / n / "error_labels.json" for n in ("dev_a", "dev_a_clean", "dev_b", "dev_b_clean", "dev_c", "dev_c_clean")]


def answers() -> dict:
    out = {}
    for path in LABEL_FILES:
        labels = json.loads(path.read_text(encoding="utf-8"))
        out.update({e["finding_id"]: "real_error" for e in labels["seeded_errors"]})
        out.update({e["finding_id"]: e["verdict"] for e in labels["expected_other_verdicts"]})
    return out


class OracleClient:
    name = "oracle"

    def __init__(self, everything_is_an_error: bool = False):
        self.answers, self.everything = answers(), everything_is_an_error

    def classify(self, item, prompt=""):
        fid = item.finding.finding_id
        verdict = "real_error" if self.everything else self.answers.get(fid, "unresolved")
        lines = [l for l in prompt.split("CONTEXT:\n", 1)[1].splitlines() if l and not l.startswith("[")]
        if verdict == "drafting_convention":
            quote = next(l for l in lines if l.startswith("NOTE: CABLE LENGTHS"))
        else:
            keys = [k for k in item.finding.affected_entity_key.split(":") if k]
            quote = next((l for l in lines if any(k in l for k in keys)), lines[0])
        return json.dumps({"verdict": verdict, "supporting_quote": quote if verdict != "unresolved" else None,
                           "reason": "Oracle answer for testing the validation tools."})
