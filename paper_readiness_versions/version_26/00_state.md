# State — Version 26

V26 predeclares one minimal use of the predictively admitted H21-C feature as H12 reliability state rather than standalone direction.

### H26 — zero-threshold H21-C/H12 conflict veto

At each corrected V11 replay decision:

- base target remains the inherited H12 target;
- define `h21c = sign(ret_4) * oi_log_change_1h`;
- if `sign(h21c)` and `sign(H12 effective_score)` are both non-zero and disagree, then veto **only a new/increased H12 exposure** using the existing V7 `_veto_increase` semantics;
- reductions, exits, same-or-smaller exposure and non-conflict decisions pass unchanged;
- never create the opposite direction; never increase leverage/exposure above H12;
- conflict magnitude threshold is fixed at exactly `0.0`, so there is no fitted threshold.

Implementation for the diagnostic will reuse existing V7 H1 logic by mapping `h21c` to the H1 conflict input and setting `qh_abs_threshold=0.0`. No strategy source change is required for this DEVELOPMENT test.
