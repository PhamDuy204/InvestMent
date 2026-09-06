# V21 Cohort-Calibrated Risk Design

## Goal

Increase scientifically defensible paper-trade frequency toward the existing +$0.05 account realized net PnL/hour objective without reviving V19 one-leg abort leakage.

## Entry

V20's global venue/side post-fill calibration mixes low-capture shadow fills with rare large dislocations. V21 keeps the single-maker + conditional taker hedge execution model but calibrates causal terminal outcomes by pre-fill capture cohort: 0-5, 5-10, 10-20, and 20+ bps.

Only economically plausible shadow probes are prioritized: deterministic conditional pair value must be positive before calibration. Each causal fill records placement capture, post-fill EV, accept/reject, and reject unwind bps so the calibration can be audited rather than inferred from aggregates.

V21 uses a one-sided 90% Wilson lower bound instead of V20's 95% bound. The empirical/shrunk acceptance estimate must still be at least 90%, and expected attempt EV computed from the conservative lower bound must remain above the existing positive risk/objective floor. This is a risk tolerance change, not a profitability guarantee.

## Exit

V21 keeps route-relative mean reversion but reacts sooner to the extra admission risk: take profitable convergence sooner, protect positive PnL after two minutes if convergence stalls, arm divergence loss protection after three minutes with a smaller expansion allowance, use a 15-minute adaptive timeout, and cap holding at 30 minutes. Confirm divergence twice before acting and close divergence/max-hold immediately with executable taker depth instead of waiting for a passive exit timeout.

## Constraints

Paper/simulation only; public market data only; no credentials or authenticated trading endpoints. Fees, executable depth, funding, contract units, and one-leg abort losses remain in account-level economics. 20x/30x/40x remain paper leverage buckets; leverage cannot rescue negative EV. V20 production stays untouched until V21 tests and smoke validation pass.
