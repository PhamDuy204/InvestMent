# Methods / Math — V20

For decision timestamp `t`, define `m(t)` as the latest archive observation satisfying:

`create_time < t` and `t - create_time <= 15 minutes`.

No observation at or after `t` is admissible. If no such observation exists or the requested field is null, that metric is unavailable.

For open interest:

`oi_change_1h(t) = log(OI(m(t)) / OI(m(t-1h)))`,

where both endpoints independently satisfy the same strict causal rule.
