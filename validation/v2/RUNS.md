# v2 run log

Every v2 validation run, written by tools/validate_v2.py. Spend is Claude API spend priced from each call's usage.

| run | engine | split | pairs | recall | wrong rate | caught/planted | wrong/made | s per doc | spend USD | total spend USD | prompt | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dev_rules-only_20261126_181757 | rules-only | dev | 30 | 0.452 | 0.963 | 38/84 | 995/1033 | 0.0 | 0.0000 | 0.0000 | v2-p1 | rules-only baseline, no model |
| dev_gemma3-4b_20261126_182534 | gemma3:4b | dev | 1 | 0.500 | 0.900 | 1/2 | 9/10 | 48.9 | 0.0000 | 0.0000 | v2-p1 | smoke run, one pair, pipeline check |
| dev_claude-haiku_20261126_183044 | claude-haiku | dev | 5 | 1.000 | 0.312 | 11/11 | 5/16 | 16.0 | 0.0215 | 0.0215 | v2-p1 | cost check, first 5 dev pairs |
| dev_claude-haiku_20261126_183245 | claude-haiku | dev | 30 | 0.976 | 0.248 | 82/84 | 27/109 | 31.7 | 0.2675 | 0.2890 | v2-p1 | full dev run, prompt v2-p1 |
| dev_claude-sonnet_20261126_184135 | claude-sonnet | dev | 30 | 1.000 | 0.222 | 84/84 | 24/108 | 34.2 | 3.5421 | 3.8311 | v2-p1 | full dev run, prompt v2-p1 |
| dev_claude-haiku_20261126_185325 | claude-haiku | dev | 30 | 0.976 | 0.058 | 82/84 | 5/87 | 35.7 | 0.2714 | 4.1025 | v2-p2 | dev rerun, prompt v2-p2 |
| dev_claude-sonnet_20261126_190301 | claude-sonnet | dev | 30 | 1.000 | 0.012 | 84/84 | 1/85 | 34.9 | 3.6428 | 7.7453 | v2-p2 | dev rerun, prompt v2-p2 |
| dev_claude-haiku_20261126_191450 | claude-haiku | dev | 30 | 1.000 | 0.106 | 84/84 | 10/94 | 32.8 | 0.2742 | 8.0195 | v2-p3 | dev rerun, prompt v2-p3 |
| dev_claude-sonnet_20261126_192336 | claude-sonnet | dev | 30 | 1.000 | 0.012 | 84/84 | 1/85 | 36.5 | 3.6807 | 11.7001 | v2-p3 | dev rerun, prompt v2-p3 |
| dev_gemma3-4b_20261126_182733 | gemma3:4b | dev | 14 | 0.556 | 0.932 | 20/36 | 274/294 | 136.0 | 0.0000 | 11.7001 | v2-p1 | stopped by hand after 14 of 30 pairs: the prompt had moved to v2-p3 |
