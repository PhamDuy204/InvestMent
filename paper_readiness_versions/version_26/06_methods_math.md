# Methods / Math — V26

Let baseline target be `w*_t`, current drifted weight be `w_t`, H12 score `s_t`, and H21-C state `c_t`.

Conflict:

`conflict = sign(c_t) != sign(s_t)`, with both signs non-zero.

If conflict and `|w*_t| > |w_t|` in the same direction, proposed target becomes current `w_t`. If the base target flips direction, proposed target becomes zero. Otherwise target is unchanged.

Thus H26 can only veto exposure increases; it cannot reverse H12 or boost exposure.
