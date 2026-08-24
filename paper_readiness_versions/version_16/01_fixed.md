# Fixed / Proven through V16

1. H12 loses before costs; ALPHA failure remains dominant.
2. Rank-only and existing-feature rescue paths remain rejected from V12/V13.
3. Binance historical `bookDepth` remains rejected by V15's predeclared cross-fold integrity gate.
4. **V16 closes the alternative-historical-source branch:** no existing local archive was found and Binance public bulk top-of-book/L2 does not provide the required old-fold coverage.
5. Tardis is a technically credible historical source, but adopting paid/API full-history access would add cost/pipeline complexity solely to rescue already-failed H12. It is therefore not adopted at this checkpoint.
6. The already-running local L2 recorder is the smaller, provenance-clean path: forward-only research with first-seen timestamps.
7. No strategy code, dependency, performance replay, prospective outcome or trial was touched.
8. Trial 871 remains untouched; `LIVE_NOT_AUTHORIZED` remains invariant.
