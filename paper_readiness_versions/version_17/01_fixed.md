# Fixed / Proven through V17

1. H12 loses before costs; ALPHA failure remains dominant.
2. Rank-only and existing-feature rescue paths remain rejected from V12/V13.
3. Historical microstructure rescue remains closed from V15/V16.
4. V17 resolves the forward-L2 schema question without new code: the recorder already persists `top_of_book_imbalance`, microprice, spread and depth fields with causal timestamps.
5. Raw record count is no longer treated as independent evidence. The 180,180 stored rows hide a ~68.3h common outage; current evidence is two short contiguous segments.
6. The first forward feature is fixed to existing `top_of_book_imbalance`; no threshold grid, new downloader, reconstruction framework or dependency is justified.
7. A time-only sample sufficiency/boundary rule is predeclared before outcome inspection; current data fails it.
8. No prospective outcome, performance replay or trial was opened. Trial 871 remains untouched; `LIVE_NOT_AUTHORIZED` remains invariant.
