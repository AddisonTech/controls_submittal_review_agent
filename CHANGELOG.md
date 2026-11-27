# Changelog

## Phase 0 - Walking skeleton

- P0-C1 - implemented, VERIFIED 2026-11-17: nine nodes N1 to N9 in one linear LangGraph graph with no branches or retries; R1 to R5 in plain code per the operational definitions (R3 flags under 15 percent, R5 flags over 10 percent, both computed as written); Windows paths via pathlib; each node prints one progress line; student runs: .venv\Scripts\python.exe -m submittal_review --input tests\fixtures\seeded --output out
- P0-C2 - implemented, VERIFIED 2026-11-17: one ReviewState TypedDict whose fields come from the node contracts, each with exactly one writer; Pydantic records at every node boundary (SourceLocation, SheetRecord, PointRecord, Evidence, SuspectedFinding, ClassifiedFinding and the rest); finding IDs built from rule, entity and kind so they are stable run to run; student runs: .venv\Scripts\python.exe -m pytest -q
- P0-C3 - implemented, VERIFIED 2026-11-17: seeded set (one error per rule plus one convention and one unresolved candidate), clean twin and malformed set from tools/make_fixtures.py, with extraction_truth.json and error_labels.json the agent never reads; recorded N7 replies; one test per node, end-to-end tests on both sets, ground truth, normalization, evidence schema, stable IDs, zero capacity and unknown cable unit tests; student runs: .venv\Scripts\python.exe -m pytest -q (pass is "37 passed")
- P0-C1 - conflict flagged and resolved by student 2026-11-12: R1 said document applicability is "declared in fixture truth", but the agent never loads the answer files during a review. Applicability now comes from SCOPE lines on the index sheet, which are part of the input. A tag with no SCOPE line becomes an R1 candidate for N7, which is how the unresolved path is exercised.
- P0-C2 - extended contract: SheetRecord carries scope_declarations, capacity_lines and reserved_lines beyond the I5 field list, because the P0-C1 input grammar (SCOPE, CAPACITY, RESERVED) has to land somewhere R1 and R3 can read it. No new state fields were added.
- P0-C1 - scoped down: N7 uses RecordedResponseClient, a local stand-in that returns recorded replies by finding ID. The Ollama client, quote check and retries belong to P2-C1 and P2-C3. N7 already takes an injected client so the real one drops in without changing the graph.
- P0-C1 - design note: when a rule cannot compute (zero or unknown capacity, unknown cable unit), N5 marks the candidate UNRESOLVED_INPUT and N7 records it as unresolved without a model call. This is inside the node, not a graph branch.
- Dependencies beyond the Python standard library: pdfplumber (PDF text, named in P2-C2), openpyxl (points list, named in P2-C2), reportlab (fixture generator only, never imported by the agent).

### Rule 9 checklist for the student
- [ ] .venv\Scripts\python.exe -m submittal_review --input tests\fixtures\seeded --output out runs to "Done." and prints all nine node lines
- [ ] .venv\Scripts\python.exe -m pytest -q shows every test passing

## Phase 1 - Foundation

- P1-C1 - implemented, VERIFIED 2026-11-17: no memory between runs; each run starts from only what the CLI sets (input, output, run metadata, config) and writes its own run folder; test proves the same submittal gives the same report with an unrelated run in between; student runs: .venv\Scripts\python.exe -m pytest -q
- P1-C2 - implemented, VERIFIED 2026-11-17: fixed pipeline with no planning or model-chosen tools; a counting client proves N1 to N6 make zero classifier calls and N7 makes one per computable finding; student runs: .venv\Scripts\python.exe -m pytest -q
- P1-C3 - implemented, VERIFIED 2026-11-17: review_config.json holds the I9 config scope (spare_io_threshold_pct 15, cable_length_tolerance_pct 10, model_name, temperature 0, model_timeout_seconds 120, model_attempts 2, max_prompt_tokens 4096, max_context_tokens 3000, max_pdf_pages 250, max_suspected_findings 150); Pydantic ReviewConfig rejects out-of-range values, more than two attempts, context larger than the prompt, and unknown keys; R3, R5 and the R3 suggested fix read the thresholds; the run log records the config file, its SHA-256 and every value; no severity weights or ordering are configurable; student runs: .venv\Scripts\python.exe -m submittal_review --input tests\fixtures\seeded --output out
- P1-C3 - scoped down: model_name, temperature, timeout, attempts, token budgets and the page and finding caps are accepted, validated and logged in Phase 1 only. N7 starts using them in P2-C1 and P2-C3, and the caps are enforced per P2-C3 and P5-C7 (Rule 1, one phase at a time).
- P1-C3 - design change carried from the instructor revision: the student draft put the severity order in the config file; the accepted revision says version one has no severity ranking or weights. N8 keeps the fixed R1 to R5 then sheet order from P0-C2, and a test confirms no config value can reorder comments.
- P1-C4 - implemented, VERIFIED 2026-11-17: one agent, nine nodes, one straight line; test reads the compiled LangGraph and confirms the node names, the START to END chain and no conditional edges; student runs: .venv\Scripts\python.exe -m pytest -q
- P1-C5 - implemented, VERIFIED 2026-11-17: one command, one input folder, one output folder, no prompts; tests run the CLI with stdin closed, confirm it finishes with "Done. Open ...", and confirm a bad config exits non-zero before N1 and writes no output; student runs: .venv\Scripts\python.exe -m pytest -q (pass is "59 passed")

## Phase 2 - Core agent

- P2-C1 - implemented, VERIFIED 2026-11-17: N7 calls a local model through OllamaClient; model_name and temperature come from review_config.json (gemma3:4b, temperature 0); fixed prompt version p2-v1; the run log records the model name, the digest Ollama reports and the prompt version; no multimodal input, N2 still refuses pages without a text layer; student runs: .venv\Scripts\python.exe tools\eval_early.py --input tests\fixtures\seeded --output out_eval (pass ends with "EVAL PASS")
- P2-C2 - implemented, VERIFIED 2026-11-17: no network beyond localhost (OllamaClient refuses any non-local address); HTTP uses the Python standard library, so no new dependency; sources are opened read only and a test confirms their SHA-256 hashes are unchanged after a run; student runs: .venv\Scripts\python.exe -m pytest -q
- P2-C3 - implemented, VERIFIED 2026-11-17: every reply must parse into ModelReply (verdict, supporting_quote, reason) and the quote must appear word for word in the supplied context (spacing differences allowed); real_error and drafting_convention need a quote; a failed reply, a timeout or a connection error is a failed attempt; at most two attempts, then unresolved with the reason, and the run continues; Ollama and the model are checked before any node runs; the 250-page cap stops the run at N2 and the 150-finding cap at N5, both before N7, with a "split the package" message; context is filled in the I6 priority order (rule evidence, typical clause, adjacent text, other related sheets), evidence is never cut, and evidence over the budget is unresolved as context_budget_exceeded with no model call; included and omitted excerpts go to classify_log.jsonl; student runs: .venv\Scripts\python.exe -m pytest -q
- P2-C3 - design note: token counts use UTF-8 bytes as a conservative stand-in, since this version does not call a tokenizer. Bytes never undercount a byte-level tokenizer, so the budget fails safe as I6 asks. The 120-second limit is enforced as wall clock with a worker thread.
- P2-C3 - extended existing P1-C3 implementation: model_name, temperature, model_timeout_seconds, model_attempts, max_prompt_tokens, max_context_tokens, max_pdf_pages and max_suspected_findings, accepted and logged in Phase 1, are now used.
- P2-C4 - implemented, VERIFIED 2026-11-17: not conversational; every request sends stream false; a test confirms exactly one progress line per node, N1 to N9 in order; student runs: .venv\Scripts\python.exe -m pytest -q
- P2-C5 - implemented, VERIFIED 2026-11-17: tools\eval_early.py runs the agent and scores it against error_labels.json, which the agent never reads: at least 4 of 5 seeded errors caught with complete evidence, wrong comments at or under 20 percent, every comment's evidence complete, labeled conventions kept as conventions, no forbidden phrases (approve, reject, resubmit and the like); pytest covers the harness with recorded replies, and the live command is the eval case for the model's behavior; student runs: .venv\Scripts\python.exe tools\eval_early.py --input tests\fixtures\seeded --output out_eval and the same with --input tests\fixtures\clean
- P0-C1 - extended for P2-C3: the classifier interface now takes the prompt and returns the reply as text, so N7 can check it; the Phase 0 test fake was updated to match. N2, N5 and N9 gained the caps and the classify log inside the nodes; the graph shape is unchanged.
- P1-C5 - extended: the CLI now uses the local model by default (--classifier recorded runs offline) and prints [stopped] with the reason instead of a traceback when Ollama, the model or the size caps stop a run; the Phase 1 CLI test now passes --classifier recorded.
- P2-C5 - first live eval, 2026-11-17, gemma3:4b with prompt p2-v1: seeded set 2 of 5 caught, 0 wrong comments, the CBL-102 convention missed; clean twin convention missed. The classify log showed three causes: the model quoted the rule's own sentence instead of drawing text, joined two real lines into one quote, and called unrelated typical notes conventions. Changed to prompt p2-v2 (quote one line from CONTEXT only, the finding marked do-not-quote, a convention must explain this exact kind of difference) and the quote check now accepts a quote of several lines only when every line is word for word in the context. Tuned on the development fixtures only; no holdout exists yet, so none was touched (P5-C2).
- P2-C5 - second live eval, 2026-11-17, gemma3:4b with prompt p2-v2: every finding came out drafting_convention (0 of 5 caught). The worked cable example in the prompt pulled the small model toward that verdict, which is the waved-through failure P4-C1 warns about. Changed to prompt p2-v3: no worked example, and a fixed order of questions in which a convention is only allowed when a NOTE or TYPICAL line covers the same subject as the finding. Added configs\qwen2.5-7b.json so the same eval can run on a second local model (Apache 2.0, fits the 6 GB GPU) per P2-C1 and P4-C2; review_config.json still names gemma3:4b.
- P2-C5 - third live eval, 2026-11-17, prompt p2-v3: gemma3:4b passed both sets (seeded 4 of 5 caught, 0 wrong comments, CBL-102 kept as a convention; clean twin 0 comments). qwen2.5:7b failed the seeded set (1 of 5 caught, 6 findings called conventions). gemma3:4b stays the default model.

## Phase 3 - Knowledge

- P3-C1 - extended existing P0-C1 implementation: normalize_key already follows the I2 policy (trim, collapse spaces, uppercase, tidy spacing around a kept hyphen; hyphens, underscores, periods and leading zeros are never removed); new tests prove T-101, T101, T_101, T.101 and AI-01 versus AI-1 stay distinct, and that the same terminal on two controllers stays two points.
- P3-C1 - implemented, VERIFIED 2026-11-17: tag equivalence only through an explicit ALIAS line in the input ("ALIAS: T101 = T-101"); N4 maps the alias, marks each entry it touched (alias_of), and prints the alias-use count; SCOPE lines follow the alias so R1 sees one tag; conflicting or chained aliases stop the run; two raw spellings that land on one key are flagged as a normalization collision, never silently merged, and R1 still treats them as one tag per I3; N9 adds a NORMALIZATION REVIEW section listing every collision and every alias use with its source; student runs: .venv\Scripts\python.exe -m pytest -q
- P3-C1 - design note: the alias map lives in the input as ALIAS lines on the index sheet, for the same reason as the SCOPE lines in Phase 0: the agent never reads the answer files and the input folder holds exactly three files. Contract extension: SheetRecord.alias_declarations and XrefEntry.alias_of; N9 now also reads cross_reference_table and classified_findings. No new state field.
- P3-C2 - implemented, VERIFIED 2026-11-17: the generator records FIXTURE_SCHEMA_VERSION 1 and a seed note (it is deterministic and uses no random numbers); tools\freeze_datasets.py writes tests\fixtures\datasets.json with the versions and the SHA-256 of every file in the seeded, clean and malformed sets; tests fail if a frozen dataset changes without a refreeze, check the versions against the generator and the labels, and prove the agent never reads the answer files (the report is identical with them deleted); the generator output did not change, so it stays at 0.1.0; student runs: .venv\Scripts\python.exe -m pytest -q
- P3-C2 - scoped down: an engineer reviewing a sample of generated sheets for plausibility is a person's task and is still open. Freezing generated evaluation sets and the blind holdout belong to P5-C2.
- P3-C3 - extended existing P1-C1 implementation: static by design; each run reads one exported package and nothing carries between runs; the P1-C1 reproducibility test is the check.

## Phase 4 - Safety and operations

- P4-C1 - implemented, VERIFIED 2026-11-17: a model reason with approve, reject, resubmit or similar wording is a failed attempt; N8 holds back any real_error whose evidence is not complete for its rule (it goes to unresolved with the reason); a drafting_convention must quote an explicit NOTE or TYPICAL clause, and code then checks that the clause sits on a sheet that itself shows the finding's entity, records that as the applicability quote and sheet, and otherwise treats the reply as a failed attempt, so a convention that cannot be shown to apply ends unresolved; student runs: .venv\Scripts\python.exe -m pytest -q
- P4-C1 - design note: applicability is decided by code rather than asked of the model, because the second live eval showed gemma3:4b excusing AHU-02-SAT with a cable note from a sheet that does not show that tag. A test reproduces that exact case and proves it now ends unresolved.
- P4-C1 - extended existing P2-C5 implementation: evidence_complete and the forbidden phrase list moved into the agent; tools\eval_early.py now uses the agent's copies, so there is one definition of each.
- P4-C2 - implemented, VERIFIED 2026-11-17: THIRD_PARTY_NOTICES.txt lists every requirement and model with its license (Gemma 3 terms recorded as not open source; reportlab is BSD and used only by the fixture generator); .gitignore keeps out\, out_*, benchmarks\runs and real_packages\ out of the repository; tests fail if a dependency or configured model is missing from the notices; student runs: .venv\Scripts\python.exe -m pytest -q
- P4-C3 - implemented, VERIFIED 2026-11-17: every run writes audit_log.jsonl (run start with metadata, each node with its time and output counts, every rule that fired with its evidence and the entity's raw spellings, run end, or run_stopped with the error for any stop including Ctrl-C); the run log adds the SHA-256, size and modified time of each source, the frozen dataset and generator version when the input matches one, the git commit when available and the script's SHA-256; the classify log adds per-attempt time, reply, failure and token counts; full prompts and replies are written only for frozen synthetic datasets, and for anything else they are withheld and only the prompt SHA-256 is kept (I10); student runs: .venv\Scripts\python.exe -m submittal_review --input tests\fixtures\seeded --output out
- P4-C3 - extended existing P1-C1 implementation: run_review now streams the graph node by node to time and log each one; the graph shape is unchanged.
- P4-C4 - implemented, VERIFIED 2026-11-17: review_report.csv ends with blank reviewer_decision and reviewer_note columns on every row, and the report tells the reviewer to mark them; nothing reads them in version one; student runs: .venv\Scripts\python.exe -m pytest -q
- P4-C5 - implemented, VERIFIED 2026-11-17: evidence is laid out per rule (R1, R2, R4 and R5 sources side by side with locations, absence written as "Absent: not found after searching ...", R3 as installed, used, reserved and spare counts with the exact ratio and limit, R5 with both lengths in feet and the limit); conventions show the line that makes them apply; student runs: .venv\Scripts\python.exe -m pytest -q
- P4-C6 - implemented, VERIFIED 2026-11-17: run_summary.json records sheets read, tags extracted, findings per rule, verdict counts, model failures and run time, and is compared with the last run of the same package (same source hashes) in the same output folder; a change in sheets, tags or the unresolved count is listed and printed as a [monitor] line; student runs: .venv\Scripts\python.exe -m pytest -q
- P4-C7 - implemented, VERIFIED 2026-11-17: tools\benchmark.py runs every frozen benchmark pair (seeded and clean twin), records caught, missed, wrong comments, precision, recall, clean-set comments, unresolved and run time with the dataset, source hashes, model and digest, prompt version and config, writes benchmarks\results\, and compares with benchmarks\baseline.json; a version passes only if caught does not drop and wrong comments do not rise, and --accept refuses a baseline that loses ground; student runs: .venv\Scripts\python.exe tools\benchmark.py --accept
- P4-C8 - extended existing P1-C3 implementation: manual updates only; a test runs the agent and the benchmark and proves review_config.json is unchanged; no code path writes the config.
- P4-C7 - first live baseline, 2026-11-17: gemma3:4b, prompt p2-v3, caught 4 of 5, 0 wrong comments, 0 clean-set comments, precision 1.0, recall 0.8, 45 s (benchmarks\results\bench_20261117_122907.json).

## Phase 5 - Validation

- P5-C1 - implemented, VERIFIED 2026-11-17: tools\validate.py scores per rule with the I8 spec (TP is a comment that matches a seeded label with complete evidence, FN is a seeded label with no such comment, FP is any other comment; recall and precision from summed counts, never averaged percentages); a rules-only baseline is scored from the same runs by treating every suspected finding as a comment; the record lists each finding as caught, missed, wrong comment, held as convention or unresolved; a clean twin with any comment fails, a seeded set with zero comments fails, a comment with no rule_fired entry in the audit log fails even when TP is high, and the malformed set must stop loudly; pass needs recall and precision of at least 0.80 overall and zero clean-twin comments; results go to validation\results\ with the model, digest, prompt version and limitations; student runs: .venv\Scripts\python.exe tools\validate.py (pass ends with "VALIDATION PASS")
- P5-C1 - offline check with the recorded replies, 2026-11-17: rules only scores recall 1.0 and precision 0.741 on the development pairs (20 caught, 7 wrong comments: 4 network points and 3 typical cable notes). The recorded replies cover only the fixtures, so the offline validate fails on the dev sets as expected; the live run is the real result.
- P5-C2 - implemented, VERIFIED 2026-11-17: tools\make_eval_sets.py (generator 1.0.0, deterministic, seed per set) builds dev_a (3 panels, ECY-600, typical), dev_b (4 panels, ECY-S1000, no typical), dev_c (2 panels, PLC-1769, typical) and holdout_1 (5 panels, ECY-600, typical), each with a clean twin, frozen in eval_sets\datasets.json; tools\validate.py --register seals the holdout inputs, labels and the metric script's SHA-256 in eval_sets\holdout_registration.json; eval_early, benchmark and validate refuse the holdout by folder name or by input hashes; --final runs once, refuses if anything changed since registration, and records the date and result file; student runs: .venv\Scripts\python.exe -m pytest -q
- P5-C2 - disclosure: while building the generator, the rule checks (N1 to N5, no model, no prompt) were run once on holdout_1 to confirm each seeded error is detectable. Nothing was tuned from it: no prompt, threshold or code changed afterward, and the model has never seen it. Registration came after the last code change to tools\validate.py.
- P5-C3 - skipped: feedback into iteration (reading reviewer_decision and reviewer_note back into the agent) is out of scope for version one. The columns exist from P4-C4 and nothing reads them.
- P5-C4 - implemented, VERIFIED 2026-11-17: N7 prints its plan (findings, maximum calls, worst case at the timeout) and one line per finding with its verdict, attempts and time; each finding is appended to classify_progress.jsonl as it finishes; Ctrl-C stops the run with exit code 130, audit_log.jsonl ends with run_stopped, and the partial logs stay; student runs: .venv\Scripts\python.exe -m submittal_review --input tests\fixtures\seeded --output out
- P5-C5 - extended existing P2-C1 implementation: N7 already calls the model one finding at a time; a test confirms no two calls overlap.
- P5-C6 - implemented, VERIFIED 2026-11-17: tools\ship_check.py checks the tests pass, the benchmark loses no ground against the accepted baseline, the holdout is unchanged and no tuning run read it, and a fresh run traces every comment to the audit log; it prints the latest model versus rules-only conclusion; student runs: .venv\Scripts\python.exe tools\ship_check.py (pass ends with "SHIP CHECK PASS")
- P5-C7 - extended existing P2-C3 implementation: the caps were already enforced; N3 now prints the page count with the 250-page cap and N5 the finding count with the 150-finding cap, both before any model call.
- P4-C7 - extended: the benchmark now runs the fixtures pair plus dev_a, dev_b and dev_c, records which sets it ran, and treats a change of sets as a new baseline rather than a comparison. The Phase 4 baseline was taken on the fixtures pair only, so a new baseline is needed: .venv\Scripts\python.exe tools\benchmark.py --accept. Fixed the "No baseline yet" line that printed while --accept was setting one. The Phase 4 benchmark test now pins the fixtures pair, since the recorded replies cover only the fixtures.

- P5-C1 - first live validation, 2026-11-17, gemma3:4b, prompt p2-v3: VALIDATION FAIL. Agent caught 11 of 20 seeded errors with 0 wrong comments and 0 clean-twin comments (recall 0.55, precision 1.0); rules only caught 20 of 20 with 7 wrong comments (recall 1.0, precision 0.741), so neither variant passed. Every one of the 9 misses went to the reviewer as unresolved, none was issued wrongly. The classify logs showed three causes: (a) 5 replies called a plain difference a drafting_convention with no NOTE or TYPICAL line about it (refused twice by the P4-C1 check, then unresolved); (b) 3 R1 missing-from-sequence findings answered unresolved because the model did not read the SCOPE line as settling which documents must list the tag; (c) 1 R5 reply joined two real context lines with a comma, which the quote check refused. Run results: validation\results\validate_20261117_124706.json.
- P4-C1, P2-C3 - extended for p2-v4 (tuned on the fixtures and dev_a, dev_b, dev_c only; the holdout and tools\validate.py are unchanged since registration): code now decides whether a convention is possible at all, using the same sheet test as check_convention plus a subject test (the line names the entity or uses the rule's subject words: R1 sequence, points, scope; R2 type, term; R3 spare, reserved, capacity; R4 title, index; R5 length); when none qualifies, the prompt says so and the reply format sent to Ollama offers only real_error and unresolved, and code refuses any other verdict; check_convention also refuses a NOTE about another subject (the G-002 BACnet trunk note no longer qualifies to excuse a cable length); R1 prompts state the SCOPE line code found for the tag, or that there is none; the reply format always asks for the quote field; a quote of two or more whole context lines joined by a comma or semicolon passes, each piece checked word for word; an unresolved reply's quote is not checked, since it is never used. Prompt version p2-v4.
- P5-C6 - extended: the ship check now fails unless the latest development validation passed (check 5). On 2026-11-17 the first run passed checks 1 to 4 while validation had failed, which a ship check must not allow.
- P4-C7 - the benchmark baseline accepted 2026-11-17 on the four pairs (bench_20261117_125020.json, prompt p2-v3, caught 11 of 20, 0 wrong) is the floor p2-v4 is compared against.

### Rule 9 checklist for the student
- [ ] .venv\Scripts\python.exe -m pytest -q shows "161 passed"
- [ ] .venv\Scripts\python.exe tools\validate.py ends with VALIDATION PASS
- [ ] .venv\Scripts\python.exe tools\benchmark.py --accept sets the new baseline
- [ ] .venv\Scripts\python.exe tools\ship_check.py ends with SHIP CHECK PASS
- [ ] .venv\Scripts\python.exe tools\validate.py --final, once, after everything above passes

- P5-C1 - second live validation, 2026-11-17, gemma3:4b, prompt p2-v4: VALIDATION PASS on the four development pairs. Agent 20 of 20 caught, 0 wrong comments, 0 clean-twin comments (recall 1.0, precision 1.0); rules only 20 of 20 with 7 wrong comments (precision 0.741). Benchmark baseline set to bench_20261117_132056.json (20 of 20, 0 wrong). Ship check 5 of 5 PASS. Result: validation\results\validate_20261117_131754.json
- P5-C2 - final holdout, 2026-11-17, scored once with tools\validate.py --final: holdout_1 (5 panels, ECY-600, typical; never seen by the model or used for tuning) 5 of 5 caught, 0 wrong comments, 0 clean-twin comments, CBL-105 kept as a drafting convention (recall 1.0, precision 1.0); rules only 5 of 5 with 2 wrong comments (precision 0.714). The registration records the run, so a later revision needs a newly generated holdout. Result: validation\results\final_holdout_20261117_132843.json
- P5-C2 - limitation: every result above is on synthetic sets in the P0-C1 notation. The holdout is one set with 5 seeded errors, which shows the model generalizes to an unseen layout but is a small sample. Real exported packages have not been scored.
- P5-C2 - test updated 2026-11-17, after the final holdout run: test_the_shipped_registration_matches_the_holdout_and_metric_script required final_run to be empty, which was only true before validate.py --final ran, so it failed once the registration recorded the run (160 passed, 1 failed). It now accepts final_run as empty, or as naming a result file in validation\results\ that records the holdout as passed (5 of 5 caught, 0 wrong comments). The holdout.untouched() check is unchanged, the holdout was not rerun, and no agent logic changed.

## v2 (unreleased)

### Scoring rules and readings (pre-registered)

Written and committed before any engine has run on a v2 case and before any Claude API call. The only v2 run
before this commit is the rules-only baseline on the dev cases, which uses no model. Code: tools\score_v2.py,
pinned by SHA-256 in validation\v2\HOLDOUT_V2.md.

- Test set v2: validation\v2, 40 spec compliance pairs built by tools\make_v2_sets.py from public and synthetic
  material (sources and terms in validation\v2\SOURCES.md). Each pair is a seeded twin with planted errors and a
  clean twin with none; both carry the same correct look-alikes. Split now and fixed: 30 dev pairs and 10 holdout
  pairs (cases 4, 8, ..., 40). 113 planted errors in 9 types (84 dev, 29 holdout).
- Unit of scoring: one planted error, as listed in the seeded twin's labels.json, which the agent never reads.
- Recall: planted errors caught, out of planted. Counts are summed across pairs before the rate is taken; rates
  are never averaged.
- Wrong comments: flags on correct content, including every comment on a clean twin. A comment is wrong when it
  matches no planted error in its twin. Wrong comment rate = wrong comments / comments made, where comments made =
  caught + wrong.
- Matching: a table comment carries the anchor code gave it (document, key, field); a sequence comment is anchored
  at the submittal paragraph it quotes, or at the specification paragraph when it quotes no submittal paragraph. A
  comment catches a planted error when its anchor is one of the error's anchors. For an error of kind "absent"
  (a requirement left out of the submittal) a comment also matches through the specification paragraph it quotes.
  Each error is caught once; a second comment on an error already caught is a duplicate, reported but not counted
  as wrong or as a comment made.
- An item whose reply fails the code checks twice is unresolved: it is never a comment and never a catch.
- Pass bar for an engine: recall 0.90 or higher with wrong comments at 5 percent or less of comments made (wrong
  comment rate 0.05 or lower). Both must hold.
- Reported for every engine (gemma3:4b, Claude Haiku 5.5, Claude Sonnet 5.5) against the bar: recall, wrong
  comments and rate, clean twin comments, time per document, cost per document, and a per error type table
  (planted, caught, recall, wrong comments by the type the engine gave them), plus the hard case slices (long
  documents, two errors in one section) and the rules-only baseline from the same runs.
- Tuning: prompts and code-side rules may change on dev results only. Every dev run and rerun is logged with its
  cost in validation\v2\RUNS.md and validation\v2\results\. When dev is final, each engine scores the v2 holdout
  exactly once with tools\validate_v2.py --holdout-final, and tuning stops. The v1 holdout (holdout_1) was scored
  once in Phase 5 and stays spent; it is not rescored.
- Budget: $50.00 of Claude API spend for this task, a hard stop in code (engines.py SpendGuard reserves each call's
  worst case and refuses any call that could pass the cap). Cost check first: Claude Haiku on 5 dev pairs; if the
  projected cost of both full dev runs plus both holdout runs is over $44, stop and report.
- Engine settings, the same prompts, schemas and code checks for all three: gemma3:4b through Ollama, temperature 0,
  num_ctx 8192 for v2 prompts. Claude Haiku 5.5 (claude-haiku-5-5) and Claude Sonnet 5.5 (claude-sonnet-5-5):
  effort medium set explicitly, adaptive thinking (the model default), max_tokens 8000, no temperature (both models
  refuse non-default sampling parameters), the instructions in a cached system block, the reply schema through
  structured outputs. Server-side refusal fallbacks are left off: a fallback would answer with a different model in
  the middle of a measurement, so a refusal counts as a failed attempt instead.

### Built

- v2 engines - implemented: engines.py adds --engine gemma3:4b (default, local), --engine claude-haiku and --engine
  claude-sonnet to submittal_review (N7) and spec_review; the API key comes only from ANTHROPIC_API_KEY and is never
  printed or logged; every Claude call is priced from its usage and appended to validation\v2\spend_ledger.jsonl;
  a budget stop ends a run cleanly rather than counting as a failed reply; one Claude validation run at a time.
- v2 privacy - design change from P2-C2: v1 never sent anything off the machine. That stays the default. A Claude
  engine sends prompts to the Anthropic API, so it refuses any package that is not a frozen public or synthetic
  test set unless --allow-cloud is passed. THIRD_PARTY_NOTICES.txt lists the SDK and the hosted models.
- v2 spec compliance review - implemented: spec_review.py reads spec.txt, submittal_sequence.txt,
  submittal_points.csv and drawing_list.csv; six table rules T1 to T6 (exact keys, as P3-C1) find every difference
  between the points schedule, the points list and the drawing list and the model judges each one real_error,
  not_an_error or unresolved; each specification sequence section is paired with the submittal section of the
  same number and the model lists issues, each with one exact quote per side; code checks every quote (word for
  word, one paragraph only), the reply schema, the forbidden phrases and the two attempt limit for every engine.
  Prompt version v2-p1.
- v2 test set - implemented: tools\make_v2_sets.py and tools\v2_templates.py (generator 2.0.0, deterministic), six
  systems (multizone and single zone VAV AHUs, VAV reheat terminals, fan coil units, chilled water and hot water
  plants); hard cases: long documents (up to 16 terminals and 80 points), two errors in one section, and look-alikes
  in every pair (SI or dual units, DI and DO for BI and BO, reworded alarms, contractor added paragraphs, local
  devices with no BAS point). Frozen in validation\v2\datasets_v2.json; holdout pinned in validation\v2\HOLDOUT_V2.md.
- v2 holdout - implemented: spec_review and tools\validate_v2.py refuse a holdout folder, by path or by file hashes,
  unless validate_v2 runs with --holdout-final; the final run checks all 100 pinned files and the scorer, records
  the engine before its first call, and refuses a second final for the same engine.
- Disclosure: one author wrote the generator, the prompts and the scorer. The prompts state standard reviewer
  knowledge written before any run (unit conversions, DI and DO as names for binary points, Level 1 most critical),
  and that knowledge also covers look-alikes the generator plants. The holdout comes from the same generator, so it
  tests unseen combinations of systems, values, look-alikes and errors, not unseen kinds of error.
- Rules-only baseline on dev (no model, run before this commit): recall 0.452 (38 of 84; the rules see only the
  points and drawing lists, never the sequences) with 995 wrong comments of 1033 (rate 0.963). The model step is
  what has to remove the look-alikes and find the sequence errors.

### Dev runs and tuning log (dev results only; the v2 holdout is untouched)

- 2026-11-26, rules-only baseline on dev (no model): recall 0.452, wrong 995 of 1033 (rate 0.963), $0.
- 2026-11-26, gemma3:4b smoke run on one dev pair, prompt v2-p1: pipeline check only (recall 0.500, wrong 9 of 10).
- 2026-11-26, cost check, Claude Haiku 5.5 on the first 5 dev pairs, prompt v2-p1: $0.0215 actual ($0.0022 per
  document; 1,105 to 1,208 cached system tokens read per call). Projected from the measured tokens per call and the
  dev call counts (1,033 table differences, 294 sequence sections): Haiku dev $0.22 and holdout $0.07, Sonnet dev
  $4.20 to $6.62 and holdout $1.40 to $2.21, total $5.90 to $9.13, under the $44 stop line, so the runs went ahead.
- 2026-11-26, Claude Haiku 5.5 on all dev pairs, prompt v2-p1: recall 0.976 (82 of 84), wrong 27 of 109 (rate
  0.248), FAIL, $0.2675. 26 of the 27 wrong comments sat on two paraphrases in the generator that are correct only
  in the context of the whole system (AHU 3.3.2 "stage 2 and stage 3" for "stage 2 or higher" where the sequence
  has three stages; single zone AHU 3.3.3 and 3.5.4 naming the chilled water valve where the unit's only cooling is
  a chilled water coil); the model saw only the section under review. Misses: a device tag with two letters swapped
  (TT-6-AS for TT-6-SA), which the "different spelling" wording in the table prompt invited it to excuse, and one
  terminal minimum airflow in a 14 terminal section.
- 2026-11-26, Claude Sonnet 5.5 on all dev pairs, prompt v2-p1: recall 1.000 (84 of 84), wrong 24 of 108 (rate
  0.222), FAIL, $3.5421. 16 wrong comments were entries whose own reason says the paragraph matches ("55 °F converts
  to 12.8 °C, so this matches"); 8 were table verdicts that judged a different column of the row than the one code
  flagged (a correct unit range called wrong because the same row carried a planted device tag error).
- Prompt v2-p2 (spec_review.py), from those dev results only: (1) every sequence section check now carries the
  whole specification (all sections and the points schedule) as a reference block before the section, sent to
  Claude as its own cached block and to gemma3:4b as the same text, with quotes still limited to the section; (2)
  the sequence prompt says to read a general specification phrase against the system the specification describes;
  (3) each sequence issue carries submittal_meets_spec, and code drops every entry the model marks true, for every
  engine; (4) the table prompt says point names, device tags and DDC hardware identifiers must match character for
  character (the P3-C1 exact key policy) and drops "different spelling" from the not_an_error examples; (5) the
  table prompt says to judge only the field code flagged. No test set file, label, threshold or scoring rule changed.
- 2026-11-26, Claude Haiku 5.5 on all dev pairs, prompt v2-p2: recall 0.976 (82 of 84), wrong 5 of 87 (rate 0.058),
  FAIL by 0.008, $0.2714. Both misses were T1 missing points answered unresolved because "the points list rows
  searched are not shown"; 3 wrong comments were still on the AHU 3.3.2 stage wording.
- 2026-11-26, Claude Sonnet 5.5 on all dev pairs, prompt v2-p2: recall 1.000 (84 of 84), wrong 1 of 85 (rate 0.012),
  PASS, $3.6428.
- Prompt v2-p3 (spec_review.py), from the Haiku v2-p2 misses only: a T1 missing point check now lists every point
  name and description in the submittal points list, so the model can see what code searched. Nothing else changed.
- 2026-11-26, gemma3:4b on dev, prompt v2-p1: stopped by hand after 14 of 30 pairs once the prompt had moved to
  v2-p3; partial score of the completed pairs: recall 0.556 (20 of 36), wrong 274 of 294 (rate 0.932), 136 s per
  document (validation\v2\results\dev_gemma3-4b_20261126_182733_partial.json).
- 2026-11-26, Claude Haiku 5.5 on all dev pairs, prompt v2-p3: recall 1.000 (84 of 84), wrong 10 of 94 (rate 0.106),
  FAIL, $0.2742. Every wrong comment was on one of three paraphrases the generator wrote as correct (AHU 3.3.2
  "stage 2 and stage 3", single zone AHU 3.5.4 "the heating and chilled water valves", AHU 3.2.6 valve order); the
  count moves between runs (5 at v2-p2, 10 at v2-p3), since these models take no temperature setting.
- 2026-11-26, Claude Sonnet 5.5 on all dev pairs, prompt v2-p3: recall 1.000 (84 of 84), wrong 1 of 85 (rate 0.012),
  PASS, $3.6807.
- Dev final, 2026-11-26: prompt v2-p3 is frozen and tuning stops. The remaining Haiku wrong comments sit on three
  sentences of this generator; a prompt aimed at them would teach to the test, not improve the reviewer. Next:
  gemma3:4b on dev with v2-p3, then each engine on the v2 holdout once with --holdout-final.
