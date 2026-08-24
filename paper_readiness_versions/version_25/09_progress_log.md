# Progress Log

## V25 raw H21-C economic rejection — 2026-08-24 Asia/Ho_Chi_Minh

- Used exact V4 `in_universe_15`, frozen optimizer/overlay, decision geometry and V11 70/30 replay semantics.
- Confirmed each fold has one final 12h-grid timestamp intentionally not replayed because its holding horizon would cross the outer-test boundary; no fabricated cross-fold label was added.
- Raw H21-C net `-7.02798%` vs baseline `-3.52864%`; turnover `315.22` vs `50.51`; wrong-side damage `2.69184` vs `1.21854`.
- Rejected raw directional replacement. No scale or threshold search performed.
- Next action is a separately predeclared minimal reliability mapping using existing helpers.
- Trial 871 remains untouched; `LIVE_NOT_AUTHORIZED`.
