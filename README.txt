CONTROLS SUBMITTAL REVIEW AGENT - PHASE 5 (VALIDATION)
Addison Smith (addsmi1720) - AGENT PRO, ECPI University - MIT License

At a glance
-----------
What it does: reads a controls submittal (drawing set PDF, points list
spreadsheet, sequence of operation text), cross references the three, runs
five plain-code rule checks (R1 to R5), and has a small local model
(gemma3:4b through Ollama) sort each suspected finding into a real error, a
drafting convention, or unresolved. It drafts recommended comments with full
evidence for an engineer to review. It never approves or rejects a submittal
and never changes a source file. Everything runs on one Windows PC; nothing
leaves the machine.

Final results (2026-11-17, gemma3:4b, prompt p2-v4):
  Development sets (dev_a, dev_b, dev_c and the fixtures, with clean twins):
    20 of 20 seeded errors caught, 0 wrong comments, 0 comments on the
    clean twins (recall 1.0, precision 1.0).
  Holdout (holdout_1, pre-registered, never used for tuning, scored once):
    5 of 5 caught, 0 wrong comments, 0 comments on the clean twin.
  Rules-only baseline (every suspected finding issued, no model):
    20 of 20 caught on the development sets but 7 wrong comments
    (precision 0.741); 2 wrong comments on the holdout. The model step is
    what removes the wrong comments.
  Evidence: validation\results\validate_20261117_131754.json,
  validation\results\final_holdout_20261117_132843.json and
  benchmarks\baseline.json.

Limitation: every result above is on synthetic sets built by the project's
own generator in a deliberate test notation. The holdout is one set with 5
seeded errors. Real exported submittal packages have not been scored, and
extraction from real CAD exports is unproven.

Quick start on a fresh Windows PC
  1. Install Python 3.11 or newer (python.org) and Git for Windows.
  2. Install Ollama for Windows (ollama.com), leave it running, then:
       ollama pull gemma3:4b
  3. In PowerShell:
       git clone https://github.com/AddisonTech/controls-submittal-review-agent.git
       cd controls-submittal-review-agent
       py -m venv .venv
       .venv\Scripts\python.exe -m pip install -r requirements.txt
       .venv\Scripts\python.exe -m pytest -q
     The last line should read "161 passed" (the tests do not need Ollama).
  4. Run a review on the seeded example:
       .venv\Scripts\python.exe -m submittal_review --input tests\fixtures\seeded --output out
The full install, model and run notes follow below.

What this is
------------
A local agent that reads a controls submittal (drawing set PDF, points list
spreadsheet, sequence of operation text), lines the three documents up
against each other, runs five plain-code rule checks, and drafts recommended
comments for an engineer to review. It never approves or rejects a
submittal and never changes a source file.

Phase 0 built the walking skeleton: all nine nodes run in one linear
LangGraph graph, each node prints one line, and every node has a pytest case.

Phase 1 locks in the foundation decisions (P1-C1 to P1-C5):
  - No memory between runs. The same submittal in gives the same comments out.
  - A fixed pipeline. The model is used only at N7, one finding at a time.
  - Thresholds and limits live in review_config.json. A person edits that
    file, the agent never changes it, and every run logs what was in force.
    No severity weights: comments stay grouped R1 to R5, then by sheet.
  - One agent, nine nodes, one straight line. No sub-agents.
  - One command, one input folder, one output folder, no prompts mid-run.

Phase 2 puts the real model at N7 (P2-C1 to P2-C5):
  - A local model served by Ollama (gemma3:4b by default, set in the config),
    temperature 0, a fixed prompt version, no streaming, localhost only.
  - Every reply must parse as {verdict, supporting_quote, reason}, and the
    quote must appear word for word in the context the model was given.
    A failed reply is retried once; a second failure goes to unresolved
    and the run carries on. A timeout counts as a failed attempt.
  - The run stops before any node if Ollama or the model is missing, and
    stops at N2 or N5 if the package is over the page or finding cap.
  - Context is filled in a fixed priority order inside the token budget.
    Evidence is never cut; if it alone is too big, the finding is unresolved.
  - tools\eval_early.py scores a run against the labels (the agent never
    sees them).

Phase 3 settles how tags are matched and how the test data is kept (P3-C1 to P3-C3):
  - Exact keys only. T-101, T101 and T_101 are three different tags unless
    an ALIAS line on the index sheet says otherwise ("ALIAS: T101 = T-101").
    Every alias use is logged.
  - Two spellings that land on one key are flagged in the report's
    NORMALIZATION REVIEW section, never silently merged.
  - The fixture datasets are versioned and frozen by SHA-256 in
    tests\fixtures\datasets.json. A changed dataset fails the tests until
    the generator version is bumped and the sets are refrozen.

Phase 4 adds the safety and operations rules (P4-C1 to P4-C8):
  - The agent never approves or rejects. A reply with that language is a
    failed attempt, and a comment without complete evidence is never issued.
  - A convention needs an explicit NOTE or TYPICAL line AND must sit on a
    sheet that shows the finding itself. Code checks that, not the model.
    The report shows why each convention applies.
  - Every run writes audit_log.jsonl (each node with its time and counts,
    every rule that fired, any stop) and is tied to the source SHA-256s,
    the dataset, the code and the model digest. Full prompts and replies
    are kept only for the frozen synthetic datasets.
  - review_report.csv has blank reviewer_decision and reviewer_note columns.
  - run_summary.json is compared with the last run of the same package.
  - tools\benchmark.py refuses a new version that catches fewer seeded
    errors or issues more wrong comments than the baseline.
  - Nothing the agent runs changes the config. Thresholds change by hand.

Phase 5 decides whether it is ready to ship (P5-C1 to P5-C7):
  - tools\validate.py scores every rule on its own (caught, missed, wrong)
    on four development pairs, and scores a rules-only baseline from the
    same runs, so the report says what the model actually adds.
  - A clean twin with any comment fails. A seeded set with zero comments
    fails. A comment that does not trace to a rule_fired entry in the audit
    log fails, even when recall is high. The malformed set must stop loudly.
  - tools\make_eval_sets.py builds three development sets that vary panel
    count, controller type and typical conventions, plus one holdout. All
    are frozen by SHA-256 in eval_sets\datasets.json.
  - The holdout is pre-registered with the metric script's hash. Every
    tuning tool refuses it. tools\validate.py --final scores it once.
  - N7 prints its plan (findings, maximum calls, worst case time) and one
    line per finding. Ctrl-C stops the run and keeps every log written so far.
  - One model call at a time. N3 and N5 print the page and finding counts
    with their caps before any model call.
  - tools\ship_check.py runs the ship checklist: tests, benchmark, holdout
    untouched and unused, a fresh run that traces every comment, and the
    latest validation passed.
  - Prompt p2-v4: code decides whether a drafting convention is possible
    (a NOTE or TYPICAL line on a sheet that shows the finding, about the same
    subject), and the reply format only offers the verdicts code allows.

  N1 ingest -> N2 validate -> N3 extract -> N4 cross reference -> N5 rule checks
  -> N6 gather context -> N7 classify -> N8 order -> N9 report

Files
-----
  review_config.json           thresholds and limits (edit by hand)
  configs\qwen2.5-7b.json      the same config on a second local model
  submittal_review.py          the agent (graph, nodes, rules, CLI)
  tests/test_submittal_review.py   one test per node plus end-to-end tests
  tests/fixtures/seeded/       synthetic set with one seeded error per rule
  tests/fixtures/clean/        the clean twin (no seeded errors)
  tests/fixtures/malformed/    a page with no text layer, a missing column
  tests/fixtures/recorded_responses.json   recorded N7 replies
  tools/make_fixtures.py       regenerates every fixture (test tool only)
  tools/eval_early.py          early evaluation against the labels (P2-C5)
  tools/freeze_datasets.py     freezes the fixture datasets by SHA-256 (P3-C2)
  tools/benchmark.py           regression benchmark against the baseline (P4-C7)
  tools/make_eval_sets.py      builds and freezes the evaluation sets (P5-C2)
  tools/holdout.py             holdout registration and refusal (P5-C2)
  tools/validate.py            scoring, rules-only baseline, holdout final (P5-C1, P5-C2)
  tools/ship_check.py          ship checklist (P5-C6)
  eval_sets/                   dev_a, dev_b, dev_c, holdout_1, each with a clean twin
  eval_sets/holdout_registration.json   the sealed holdout and metric script hashes
  validation/results/          validation and final holdout results
  tests/oracle.py              test-only classifier that reads the labels (never used by the agent)
  benchmarks/                  benchmark results and the accepted baseline
  THIRD_PARTY_NOTICES.txt      licenses for every library and model (P4-C2)
  tests/fixtures/datasets.json the frozen versions and hashes
  tests/test_phase1.py to test_phase5.py   tests for each phase
  CHANGELOG.md                 what was built in each phase

Install (Windows 11)
--------------------
1. Install Python 3.11 or newer from python.org.
2. Open PowerShell in this folder and create a virtual environment:
     py -m venv .venv
3. Install the libraries:
     .venv\Scripts\python.exe -m pip install -r requirements.txt

PowerShell often blocks the Activate script, so these steps call the
virtual environment's python directly. No activation needed.

Local model (one time)
----------------------
1. Install Ollama for Windows from ollama.com and leave it running.
2. Pull the model in PowerShell:
     ollama pull gemma3:4b
If the machine can't run the 4B model well, pull a smaller one and set
model_name in review_config.json to match.
configs\qwen2.5-7b.json is the same config with model_name qwen2.5:7b, for
comparing models with --config configs\qwen2.5-7b.json (ollama pull qwen2.5:7b).

Run the agent
-------------
  .venv\Scripts\python.exe -m submittal_review --input tests\fixtures\seeded --output out

Offline, with the recorded replies instead of the model:
  .venv\Scripts\python.exe -m submittal_review --input tests\fixtures\seeded --output out --classifier recorded

Early evaluation (P2-C5), with Ollama running:
  .venv\Scripts\python.exe tools\eval_early.py --input tests\fixtures\seeded --output out_eval
  .venv\Scripts\python.exe tools\eval_early.py --input tests\fixtures\clean --output out_eval
Each prints PASS or FAIL per check and ends with EVAL PASS or EVAL FAIL.

Regression benchmark (P4-C7), with Ollama running:
  .venv\Scripts\python.exe tools\benchmark.py            compare with the baseline
  .venv\Scripts\python.exe tools\benchmark.py --accept   set this run as the baseline
--accept refuses a run that catches fewer seeded errors or issues more wrong
comments than the current baseline.

Validation (P5-C1), with Ollama running:
  .venv\Scripts\python.exe tools\validate.py
Prints each set, the per-rule counts for the agent and for rules only, the
conclusion, and ends with VALIDATION PASS or VALIDATION FAIL.

Ship check (P5-C6), after a baseline is accepted:
  .venv\Scripts\python.exe tools\ship_check.py
Ends with SHIP CHECK PASS or SHIP CHECK FAIL.

Final holdout (P5-C2), ONCE, only when every development check passes:
  .venv\Scripts\python.exe tools\validate.py --final
It refuses if validate.py or the holdout changed since registration, and it
refuses a second run. A later revision needs a newly generated holdout.

Real packages: keep them in real_packages\ (never committed). The audit log
withholds prompt and reply text for anything that is not a frozen synthetic set.

Each run writes to its own subfolder, out\run_YYYYMMDD_HHMMSS, holding:
  review_report.txt   recommended comments, then conventions, then unresolved
  review_report.csv   the same findings as a spreadsheet
  run_log.txt         run metadata, source hashes, dataset, code version, model digest, prompt version
  classify_log.jsonl  per finding: attempts, failures, context, applicability; full prompts for synthetic data
  audit_log.jsonl     every node with time and counts, every rule that fired, any stop
  run_summary.json    sheets, tags, findings per rule, verdicts, failures, run time, change from last run

The output folder must not be inside the input folder. Earlier runs are
never overwritten.

Config (review_config.json)
---------------------------
  spare_io_threshold_pct       R3 flags spare IO strictly under this (15)
  cable_length_tolerance_pct   R5 flags lengths that differ by more (10)
  model_name                   local model for N7 (gemma3:4b)
  temperature                  model temperature (0)
  model_timeout_seconds        per model attempt (120)
  model_attempts               attempts per finding, at most 2 (2)
  max_prompt_tokens            whole prompt (4096)
  max_context_tokens           evidence and context inside it (3000)
  max_pdf_pages                size cap for one package (250)
  max_suspected_findings       finding cap before N7 (150)

The size caps stop a run before N7 with a "split the package" message.
N3 and N5 print the counts against the caps.

Use a different file with --config path\to\file.json. A bad value stops the
run before any node runs. The run log records the file, its SHA-256 and the
values used.

Expected on the seeded set: 5 comments (one per rule), 1 drafting
convention (CBL-102 on typical T-201), 1 unresolved (AHU-01-OAT).
Expected on the clean set: 0 comments, the same convention and unresolved.

Run the tests
-------------
  .venv\Scripts\python.exe -m pytest -q

A pass is every test green. The last line reads "161 passed". The tests never
call a real model; they use recorded replies and a fake local Ollama server.

Regenerate the fixtures (only if the generator changes)
------------------------------------------------------
Bump GENERATOR_VERSION in tools\make_fixtures.py first, then:
  .venv\Scripts\python.exe tools\make_fixtures.py
  .venv\Scripts\python.exe tools\freeze_datasets.py
Note the version change in CHANGELOG.md. Never edit a frozen dataset by hand.

Input format (synthetic test notation)
--------------------------------------
The folder holds exactly drawings.pdf, points.xlsx and sequence.txt. Extra
files are ignored and listed by N1. Each PDF page carries labeled lines:
  SHEET: IO-101 | TITLE: Panel CP-01 IO
  INDEX: IO-101 | Panel CP-01 IO
  SCOPE: AHU-01-SAT | DOCS=DRAWINGS,POINTS,SEQUENCE
  ALIAS: T101 = T-101                  (optional, index sheet; P3-C1)
  TAG: AHU-01-SAT | PANEL: CP-01 | TYPE: AI | TERM: AI-01
  CABLE: CBL-001 | LENGTH_FT: 287      (or LENGTH_M)
  REF: IO-102
  BOM: CONTROLLER CP-01 | QTY: 1
  TYPICAL: APPLIES_TO=CP-01,CP-02
  CAPACITY: CP-01 | AI=8 | AO=4 | DI=8 | DO=4
  RESERVED: CP-01 | AI=2 | AO=0 | DI=0 | DO=0
points.xlsx has one worksheet named Points with the header row
tag, controller, terminal, point_type, description.
sequence.txt has one statement per line, for example
  SEQ: CP-01 controls AHU-01-SAT using AHU-01-CHWV
This is a deliberate test notation, not a claim about how real CAD exports
are laid out.
