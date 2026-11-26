# v2 run log

Every v2 validation run, written by tools/validate_v2.py. Spend is Claude API spend priced from each call's usage.

| run | engine | split | pairs | recall | wrong rate | caught/planted | wrong/made | s per doc | spend USD | total spend USD | prompt | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dev_rules-only_20261126_181757 | rules-only | dev | 30 | 0.452 | 0.963 | 38/84 | 995/1033 | 0.0 | 0.0000 | 0.0000 | v2-p1 | rules-only baseline, no model |
