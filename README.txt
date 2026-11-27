CONTROLS SUBMITTAL REVIEW AGENT - v2
Addison Smith (addsmi1720) - AGENT PRO, ECPI University - MIT License

At a glance
-----------
What it does: reads a controls submittal, checks it against the
specification and against itself, and drafts recommended comments with full
evidence for an engineer to review. It never approves or rejects a
submittal and never changes a source file.

Two reviews:
  submittal_review (v1): drawing set PDF, points list spreadsheet and
    sequence of operation text cross referenced by five plain-code rules
    (R1 to R5); a model sorts each suspected finding into a real error, a
    drafting convention or unresolved.
  spec_review (v2): a specification (sequences and points schedule) against
    the submittal's sequence, points list and drawing device list. Six
    plain-code table rules (T1 to T6) find every difference and the model
    judges each one; the model reads each sequence section against the
    specification section of the same number. Code checks every quote word
    for word.

Engines: gemma3:4b through Ollama is the default, runs on the PC, and
nothing leaves the machine. v2 adds Claude as an optional engine behind a
flag (--engine claude-haiku or --engine claude-sonnet). A Claude engine
sends the prompts to the Anthropic API, so it refuses any package that is
not a frozen public or synthetic test set unless --allow-cloud is given.

v2 results (2026-11-26, prompt v2-p3)
-------------------------------------
Test set v2: 40 spec compliance pairs (a seeded twin with planted errors and
a clean twin with none) in six systems: multizone and single zone VAV air
handlers, VAV reheat terminals, fan coil units, and chilled water and hot
water plants. 113 planted errors in 9 types: point missing, wrong point
type, sequence contradicts spec, setpoint or range out of spec, wrong or
missing alarm, interlock or safety missing, unit or scaling mismatch, device
tag mismatch between the drawing list and the points list, and DDC hardware
identifier mismatch. Hard cases: long documents (up to 16 terminals and 80
points), two errors in one section, and correct look-alikes in every pair
(SI or dual units, DI and DO for BI and BO, reworded alarms, contractor
added paragraphs, local devices with no BAS point). Split before any run:
30 dev pairs (84 errors) and 10 holdout pairs (29 errors), the holdout
pinned by SHA-256 in validation\v2\HOLDOUT_V2.md and scored once per
engine.

Sources (validation\v2\SOURCES.md has URLs and terms): UFGS 23 09 00,
UFGS 23 09 23.02 and UFGS 25 10 10 (US Government works), VA Section
23 09 23 (US Government work), and the sequence logic of the Modelica
Buildings Library G36 package (BSD 3-clause style license). Everything was
paraphrased into new synthetic text; ASHRAE Guideline 36 itself was skipped
because it has no reuse grant.

Scoring (pre-registered in CHANGELOG.md before any engine ran): recall =
planted errors caught / planted. A wrong comment is any comment that matches
no planted error, including every comment on a clean twin. Wrong comment
rate = wrong / comments made. Pass bar: recall 0.90 or higher AND wrong
comment rate 0.05 or lower.

  engine          split    recall          wrong comments      s/doc   USD/doc   bar
  gemma3:4b       dev      0.524 (44/84)   674/718 (0.939)     159.8   0         FAIL
  gemma3:4b       holdout  0.586 (17/29)   203/220 (0.923)     140.7   0         FAIL
  Claude Haiku    dev      1.000 (84/84)   10/94 (0.106)       32.8    0.0046    FAIL
  Claude Haiku    holdout  1.000 (29/29)   1/30 (0.033)        28.6    0.0039    pass
  Claude Sonnet   dev      1.000 (84/84)   1/85 (0.012)        36.5    0.0613    PASS
  Claude Sonnet   holdout  0.966 (28/29)   0/28 (0.000)        32.5    0.0531    PASS
  rules only      dev      0.452 (38/84)   995/1033 (0.963)    0       0         FAIL
  rules only      holdout  0.345 (10/29)   283/293 (0.966)     0       0         FAIL

  Claude Haiku is Claude Haiku 5.5 (claude-haiku-5-5) and Claude Sonnet is
  Claude Sonnet 5.5 (claude-sonnet-5-5), both at effort medium. A document is
  one twin. Time is wall time per document with one document at a time.

The call:
  Claude Sonnet 5.5 PASSES the bar on dev and on the holdout. It is the
    only engine that does.
  Claude Haiku 5.5 is NOT a pass. It clears the bar on the holdout but fails
    it on dev (wrong comment rate 0.106 against 0.05). Its dev wrong
    comments went from 5 at v2-p2 to 10 at v2-p3 although v2-p3 changed only
    the missing point check, so the count varies from run to run. One good
    holdout does not outweigh that.
  gemma3:4b FAILS by a wide margin on both splits. It catches about half
    the errors and most of its comments are wrong; 65 percent of its replies
    failed the code checks. It stays the default only because it is the
    local, nothing-leaves-the-machine engine.

Where the engines struggled (per type tables in validation\v2\results\):
  gemma3:4b: unit or scaling mismatch (0 of 6 on dev), wrong point type
    (1 of 6), sequence contradictions and interlocks (6 of 16, 3 of 8), and
    look-alikes: 369 wrong table verdicts called a correct SI value, a DI
    for BI name or a reworded alarm a real error.
  Claude Haiku 5.5: no missed errors on dev at v2-p3; every wrong comment
    sat on three correct paraphrases in sequence sections (AHU "stage 2
    and stage 3" for "stage 2 or higher", a single zone AHU naming its
    chilled water valve, a valve order).
  Claude Sonnet 5.5: one holdout miss, a unit or scaling mismatch on a
    chilled water differential pressure point, where its verdict
    contradicted its own reason.

Claude API spend for v2: $12.84 of the $50.00 budget, every call priced from
its usage in validation\v2\spend_ledger.jsonl (run by run in
validation\v2\RUNS.md).

Limitation: every v2 package is built from public and synthetic material in
a fixed layout (SECTION lines, numbered paragraphs, CSV lists). One author
wrote the generator, the prompts and the scorer, and the holdout comes from
the same generator, so it tests unseen combinations, not unseen kinds of
error. The holdout is small (29 errors), so one miss moves recall by 0.034.
Real exported submittals are longer, messier and laid out differently; no
score here carries over to them without a test on real packages.

v1 results (2026-11-17, gemma3:4b, prompt p2-v4, submittal_review)
------------------------------------------------------------------
  Development sets (dev_a, dev_b, dev_c and the fixtures, with clean twins):
    20 of 20 seeded errors caught, 0 wrong comments, 0 comments on the
    clean twins (recall 1.0, precision 1.0).
  Holdout (holdout_1, pre-registered, never used for tuning, scored once,
    now spent and not rescored in v2):
    5 of 5 caught, 0 wrong comments, 0 comments on the clean twin.
  Rules-only baseline (every suspected finding issued, no model):
    20 of 20 caught on the development sets but 7 wrong comments
    (precision 0.741); 2 wrong comments on the holdout. The model step is
    what removes the wrong comments.
  Evidence: validation\results\validate_20261117_131754.json,
  validation\results\final_holdout_20261117_132843.json and
  benchmarks\baseline.json.
  Limitation: synthetic sets built by the project's own generator in a
  deliberate test notation; the holdout is one set with 5 seeded errors.

Quick start on a fresh Windows PC
  1. Install Python 3.11 or newer (python.org) and Git for Windows.
  2. Install Ollama for Windows (ollama.com), leave it running, then:
       ollama pull gemma3:4b
  3. In PowerShell:
       git clone https://github.com/AddisonTech/controls_submittal_review_agent.git
       cd controls_submittal_review_agent
       py -m venv .venv
       .venv\Scripts\python.exe -m pip install -r requirements.txt
       .venv\Scripts\python.exe -m pytest -q
     The last line should read "191 passed" (the tests need neither Ollama
     nor an API key; the Claude API is mocked).
  4. Run a review on the seeded example:
       .venv\Scripts\python.exe -m submittal_review --input tests\fixtures\seeded --output out
       .venv\Scripts\python.exe spec_review.py --input validation\v2\dev\v2c01_ahu_mz\seeded --output out
  5. Optional, Claude engines: set ANTHROPIC_API_KEY as a user environment
     variable (never in a file in this folder), then add
     --engine claude-haiku or --engine claude-sonnet to either command.
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

v2 adds a second review and a choice of engine:
  - spec_review.py checks a submittal against its specification: V1 read
    the package, V2 parse the sections and lists, V3 table rules T1 to T6,
    V4 pair each specification sequence section with the submittal section
    of the same number, V5 model judgments, V6 report. T1 missing point,
    T2 point type, T3 range and units, T4 alarm, T5 drawing list device
    tag, T6 DDC hardware identifier. Exact keys as P3-C1.
  - Every sequence check carries the whole specification as a reference
    block; quotes must come from the section under review. An entry the
    model itself marks as meeting the spec is dropped by code.
  - engines.py: --engine gemma3:4b (default), claude-haiku or
    claude-sonnet, for both reviews. Every engine gets the same prompts,
    schemas and code checks. Claude calls use structured outputs, cached
    instructions and effort medium; the key comes only from
    ANTHROPIC_API_KEY and is never printed or logged.
  - Every Claude call is priced from its usage and written to
    validation\v2\spend_ledger.jsonl. SpendGuard reserves each call's
    worst case and stops the run before the $50.00 cap could be passed.
  - A Claude engine refuses a package that is not a frozen public or
    synthetic test set unless --allow-cloud is given.

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
  CHANGELOG.md                 what was built in each phase and in v2
  engines.py                   v2 engine switch, Claude engine, spend guard and ledger
  spec_review.py               v2 specification compliance review (T1 to T6, sequence checks)
  tools/v2_templates.py        v2 system templates and error types
  tools/make_v2_sets.py        builds and freezes test set v2 (--check verifies it)
  tools/score_v2.py            v2 scorer (pinned in HOLDOUT_V2.md)
  tools/validate_v2.py         v2 dev runs, rules-only baseline, holdout final
  tests/test_v2.py             v2 tests, Claude API mocked
  validation/v2/dev, holdout/  30 dev and 10 holdout pairs, each seeded and clean
  validation/v2/SOURCES.md     sources, URLs and licenses for test set v2
  validation/v2/HOLDOUT_V2.md  the pinned holdout and scorer hashes
  validation/v2/RUNS.md        every v2 run with its scores and spend
  validation/v2/results/       one JSON result per v2 run
  validation/v2/spend_ledger.jsonl   every Claude call with its usage and cost

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

v2 specification review on one package:
  .venv\Scripts\python.exe spec_review.py --input validation\v2\dev\v2c01_ahu_mz\seeded --output out
  add --engine claude-haiku or --engine claude-sonnet for a Claude engine
The folder holds spec.txt, submittal_sequence.txt, submittal_points.csv
and drawing_list.csv. A holdout folder is refused.

v2 validation (dev only unless --holdout-final):
  .venv\Scripts\python.exe tools\validate_v2.py --rules-only
  .venv\Scripts\python.exe tools\validate_v2.py --engine gemma3:4b
  .venv\Scripts\python.exe tools\validate_v2.py --engine claude-haiku --workers 4
  .venv\Scripts\python.exe tools\validate_v2.py --engine claude-sonnet --limit 5
Each run prints recall, wrong comments, the bar, a per type table, time
and spend, writes validation\v2\results\<run>.json and adds a line to
validation\v2\RUNS.md. --holdout-final scores the v2 holdout once per
engine; all three engines have used theirs. Rebuild or check the set with
  .venv\Scripts\python.exe tools\make_v2_sets.py --check

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

A pass is every test green. The last line reads "191 passed". The tests never
call a real model; they use recorded replies, a fake local Ollama server and a
mocked Claude client, and need no API key.

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
