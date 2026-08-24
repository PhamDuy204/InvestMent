# Methods / Math — V22

H21-A used `A=-log(global_long_short_account_ratio)` and failed the fixed gate because aggregate IC was negative and only one fold had positive mean IC.

H21-B is fixed as:

`B = log(top_trader_position_long_short_ratio) - log(global_long_short_account_ratio)`.

The same timestamp-wise Spearman and fixed top2-bottom2 spread diagnostics apply. No outcome-derived sign or threshold is allowed.
