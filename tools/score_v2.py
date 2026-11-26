"""Scoring for test set v2. Pinned by SHA-256 in validation/v2/HOLDOUT_V2.md; the holdout final refuses to run
if this file changes after registration. The rules are the ones written in CHANGELOG.md under "v2 (unreleased)".

Unit of scoring: one planted error (labels.json in the seeded twin). The clean twin has none.

A comment is anchored where it points:
  table comment     the anchor code gave it: [doc, key, field], for example ["points", "AHU-1-SAT", "units_range"]
  sequence comment  ["sub", paragraph, ""] when it quotes a submittal paragraph, otherwise ["spec", paragraph, ""]
A comment matches a planted error when its anchor is one of the error's anchors. A sequence comment that quotes
a submittal paragraph also matches an error of kind "absent" (a requirement left out of the submittal) through
the specification paragraph it quotes.

Each planted error is caught at most once. Per twin, comments are taken in report order:
  caught     the first comment that matches a planted error not yet caught
  duplicate  a comment that only matches an error already caught (reported, not a wrong comment, not counted
             in comments made)
  wrong      every other comment, which includes every comment on a clean twin

  recall              = caught / planted
  wrong comment rate  = wrong / comments made, where comments made = caught + wrong (0 when nothing was said)
  pass                = recall >= 0.90 and wrong comment rate <= 0.05
Counts are summed across cases before any rate is taken; rates are never averaged.
"""

from __future__ import annotations

ERROR_TYPES = ("point_missing", "wrong_point_type", "sequence_contradiction", "setpoint_out_of_spec",
               "alarm_wrong_or_missing", "interlock_missing", "unit_scaling_mismatch", "device_tag_mismatch",
               "ddc_hardware_mismatch")
RECALL_BAR = 0.90
WRONG_RATE_BAR = 0.05


def comment_anchors(c: dict) -> tuple[list, list]:
    """(primary anchors, anchors that may only match an absent error)."""
    if c["source"] == "table":
        return [list(c["anchor"])], []
    if c.get("sub_para"):
        return [["sub", c["sub_para"], ""]], [["spec", c["spec_para"], ""]]
    return [["spec", c["spec_para"], ""]], []


def _matches(c: dict, err: dict) -> bool:
    primary, absent_only = comment_anchors(c)
    anchors = [list(a) for a in err["anchors"]]
    if any(a in anchors for a in primary):
        return True
    return err.get("kind") == "absent" and any(a in anchors for a in absent_only)


def score_twin(comments: list[dict], errors: list[dict]) -> dict:
    caught: dict[str, dict] = {}
    wrong, dups = [], []
    for c in comments:
        hit = next((e for e in errors if e["error_id"] not in caught and _matches(c, e)), None)
        if hit is not None:
            caught[hit["error_id"]] = c
        elif any(_matches(c, e) for e in errors):
            dups.append(c)
        else:
            wrong.append(c)
    return {"caught": caught, "missed": [e for e in errors if e["error_id"] not in caught], "wrong": wrong, "duplicates": dups}


def _blank() -> dict:
    return {"planted": 0, "caught": 0, "wrong": 0}


def aggregate(pairs: list[dict]) -> dict:
    """pairs: [{"case", "errors", "seeded_comments", "clean_comments"}]. Returns totals, per type, per hard flag."""
    tot = {"planted": 0, "caught": 0, "wrong": 0, "duplicates": 0, "wrong_on_clean": 0, "wrong_on_seeded": 0}
    per_type = {t: _blank() for t in ERROR_TYPES}
    per_hard: dict[str, dict] = {}
    misses, wrongs = [], []
    for p in pairs:
        s = score_twin(p["seeded_comments"], p["errors"])
        c = score_twin(p["clean_comments"], [])
        tot["planted"] += len(p["errors"])
        tot["caught"] += len(s["caught"])
        tot["wrong_on_seeded"] += len(s["wrong"])
        tot["wrong_on_clean"] += len(c["wrong"])
        tot["duplicates"] += len(s["duplicates"])
        for e in p["errors"]:
            per_type[e["type"]]["planted"] += 1
            per_type[e["type"]]["caught"] += e["error_id"] in s["caught"]
            for h in e.get("hard", []):
                ph = per_hard.setdefault(h, _blank())
                ph["planted"] += 1
                ph["caught"] += e["error_id"] in s["caught"]
        for w in s["wrong"] + c["wrong"]:
            per_type.setdefault(w["error_type"], _blank())["wrong"] += 1
        misses += [{"case": p["case"], **e} for e in s["missed"]]
        wrongs += [{"case": p["case"], "twin": "seeded", **w} for w in s["wrong"]] + \
                  [{"case": p["case"], "twin": "clean", **w} for w in c["wrong"]]
    tot["wrong"] = tot["wrong_on_seeded"] + tot["wrong_on_clean"]
    tot["comments_made"] = tot["caught"] + tot["wrong"]
    tot["recall"] = round(tot["caught"] / tot["planted"], 4) if tot["planted"] else 0.0
    tot["wrong_rate"] = round(tot["wrong"] / tot["comments_made"], 4) if tot["comments_made"] else 0.0
    tot["passes"] = tot["recall"] >= RECALL_BAR and tot["wrong_rate"] <= WRONG_RATE_BAR
    for d in list(per_type.values()) + list(per_hard.values()):
        d["recall"] = round(d["caught"] / d["planted"], 4) if d["planted"] else None
    return {"totals": tot, "per_type": per_type, "per_hard": per_hard, "misses": misses, "wrong_comments": wrongs,
            "bar": {"recall_at_least": RECALL_BAR, "wrong_rate_at_most": WRONG_RATE_BAR}}


def rules_only_comments(result: dict) -> list[dict]:
    """The rules-only baseline from the same run: every table difference issued as a comment, no model step."""
    return [{"comment_id": c["cand_id"], "source": "table", "rule": c["rule"], "error_type": c["error_type"],
             "anchor": c["anchor"]} for c in result["candidates"]]
