# Open Problems — V31

## P0 — Accumulate the predeclared DEVELOPMENT block

Keep the existing recorder healthy. The development clock starts at `2026-08-24T06:00:00Z` and reaches eligibility only after seven contiguous days satisfying the fixed V17 coverage rules.

If a common outage >15 minutes occurs, record it and reset the development start to the next clean common restart; do not bridge the gap.

## P1 — Development diagnostic after eligibility

Only after P0 passes may the fixed `top_of_book_imbalance` be evaluated against H12 outcomes. Use one hourly decision timestamp, chronological halves, and no threshold search. Do not treat ~7-second snapshots as independent samples.

## P2 — Untouched block

Keep `2026-08-31T18:00:00Z` onward unread during development analysis. If the development clock resets, the purge/untouched boundary must be prospectively moved before opening outcomes and recorded in a new checkpoint.

## P3 — Candidate freeze / trial 871 / paper

Still blocked. No candidate freeze, no trial 871, no A1.
