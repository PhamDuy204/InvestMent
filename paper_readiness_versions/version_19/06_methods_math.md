# Methods / Math — V19

## Exact replay reconciliation

For each inherited outer fold:

1. fit Ridge or fixed HistGB on the same causal price features;
2. use the inherited frozen V4 optimizer and no-trade/funding overlay;
3. build the same decision log with target weights and H12 holding/funding labels;
4. split each fold 70/30 exactly as V10/V11;
5. replay the evaluation partition with portfolio drift, transaction cost, funding and final unwind.

Ridge reproduction is accepted only because keys, target weights, scores and labels match the inherited decision log to floating-point precision.

## HistGB rejection

Relative to corrected Ridge:

- aggregate net delta: `-0.035537747938`;
- Sharpe delta: `-0.853859281160`;
- wrong-side count delta: `-2` (negligible count improvement);
- wrong-side economic-damage delta: `+0.363076241579` (materially worse);
- fold net improvement count: `1/3`;
- fold damage improvement count: `1/3`.

Count alone is not enough: two fewer wrong-side events accompanied by materially larger economic damage is a rejection.

## Candidate metrics causal rule

A future hourly metric at decision time `t` may only use archive rows with `create_time < t`. Any aggregation window must be fixed before inspecting H12 outcomes.
