Regression benchmark (P4-C7)

results\   one JSON per benchmark run, kept in version control
baseline.json   the accepted benchmark a new version must not lose ground to
runs\      the agent's run folders from benchmark runs (ignored by git)

A new version replaces the current one only if seeded errors caught does not
drop and wrong comments do not rise. tools\benchmark.py --accept refuses to set
a baseline that loses ground.
