"""Freeze the fixture datasets by SHA-256 (P3-C2).

Writes tests/fixtures/datasets.json: for each dataset folder, the generator
version, fixture schema version, seed note, freeze date and the SHA-256 of
every file. The tests refuse any dataset whose files no longer match.

Policy (P3-C2): a frozen dataset is never edited in place. A generator fix
means bumping GENERATOR_VERSION in tools/make_fixtures.py, regenerating, and
freezing again, so the change is visible in this file and in the changelog.
Keep the old datasets.json in version control for comparison.

Run from the repo root:  python tools/freeze_datasets.py
"""

# Future (P3-C2): a sanitized real submittal, with all customer and site names removed, frozen the same way.

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import make_fixtures as gen  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
MANIFEST = FIXTURES / "datasets.json"
DATASETS = ("seeded", "clean", "malformed")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Build Guide: P3-C2
# Decision: one manifest records version, seed note and every file hash for each dataset
def snapshot() -> dict:
    return {
        "generator_version": gen.GENERATOR_VERSION,
        "fixture_schema_version": gen.FIXTURE_SCHEMA_VERSION,
        "seed": gen.GENERATOR_SEED,
        "datasets": {name: {"files": {p.name: sha256(p) for p in sorted((FIXTURES / name).iterdir()) if p.is_file()}}
                     for name in DATASETS},
        "shared_files": {"recorded_responses.json": sha256(FIXTURES / "recorded_responses.json")},
    }


def main() -> None:
    data = snapshot()
    data["frozen_on"] = date.today().isoformat()
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Froze {len(DATASETS)} datasets at generator {data['generator_version']} to {MANIFEST}")


if __name__ == "__main__":
    main()
