# State — Version 22

V22 records the first predeclared positioning-mechanism result.

- H21-A `crowd_short_contrarian = -log(count_long_short_ratio)` was tested exactly once on DEVELOPMENT after its V21 predeclaration was committed/pushed.
- Fixed gate result: **REJECT**.
- Mean timestamp IC by fold: `+0.000114`, `-0.034643`, `-0.016561`; only `1/3` folds positive.
- Aggregate mean timestamp IC: `-0.017030`, violating the fixed positive aggregate-IC requirement.
- Top2-minus-bottom2 mean return spread was positive in `3/3` folds, but this does not override the failed rank-stability gate.
- No sign flip, reciprocal transform, threshold search, or economic replay was attempted after seeing the result.
- Per the committed ladder, H21-B is now the only authorized next mechanism.
- Trial 871 remains unauthorized/unconsumed; `READY_TO_START_PAPER=false`; `LIVE_NOT_AUTHORIZED`.
