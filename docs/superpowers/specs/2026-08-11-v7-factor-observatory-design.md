# V7 Factor Observatory and Research Council Design

Date: 2026-08-11
Branch: `v7-factor-observatory`
Base V6 head: `46212f4c9eef07001341a87dffea40cd223cfa84`
V6 frozen candidate hash: `be84d12f86df294fc7eaf30affe5cf6d89df99cb1092e7856f2dbfd016b3ec92`
Starting trial count: 857

## 1. Purpose and non-goals

V7 is a research/backtest/simulation cycle whose goal is to improve directional reliability enough to justify a later transition to paper trading under a strict untouched-forward gate. It does not add any live-order path, trading credential, OTP flow, withdrawal, transfer, or exchange-side leverage mutation.

The retained V6 H12 Ridge relative-return core remains the starting direction source. V7 must not modify V6 historical evidence or claim post-freeze V6 observations as fresh confirmation. The 2021-2023 confirmation and Aug 1-10, 2026 evidence remain locked and cannot be used for V7 retuning.

The central V7 problem is the dominant V6 `WRONG_SIDE` error class. V7 follows a simple-first escalation policy: test three tightly predeclared reliability hypotheses first, then use a factor observatory, nonlinear challenger, and scenario simulation only if the simple layer fails to provide enough incremental value.

The target verdict is `READY_FOR_PAPER_TRADING`, but the research process must return `NEEDS_MORE_RESEARCH` whenever the readiness gate is not fully satisfied.

## 2. Research principles

1. **Simple first.** A smaller causal rule that improves economic performance is preferred over a complex model with similar performance.
2. **One mechanism per primary hypothesis.** Threshold tweaks that do not change the mechanism are not treated as new scientific hypotheses.
3. **Causality before performance.** A candidate with future leakage is invalid regardless of backtest quality.
4. **Economic value after costs.** Promotion is based on after-cost incremental value, not raw classification accuracy.
5. **Forward evidence is immutable.** No V7 rule may be changed after the V7 freeze based on V7 forward results.
6. **Failures are first-class data.** Every failed experiment is recorded with the error class it targeted, the regime where it failed, and a `do_not_repeat` fingerprint.
7. **LLMs govern research, not trades.** Groq agents may retrieve evidence, propose hypotheses, audit methodology, and summarize results. They may not directly generate LONG/SHORT orders or bypass deterministic promotion code.
8. **No fabricated microstructure.** No synthetic L2 queue position, guaranteed maker fill, or unavailable market state is invented.
9. **No hidden alpha through risk changes.** Leverage, margin assumptions, reserve rules, and execution assumptions cannot be silently changed to make an alpha hypothesis look better.
10. **Trial accounting is monotonic.** Every inspected configuration that exposes performance counts toward the V7 research counter.

## 3. Architecture

The V7 trading/research path is:

`Frozen V6 H12 score -> H1 quarter-hour reliability veto -> H2 dispersion risk gate -> H3 weak-edge/cost veto -> inherited V6 portfolio/hysteresis/MARKET/1x -> enriched decision/error ledger -> deterministic promotion gate`

The V7 research path is separate:

`Factor specialists -> shared evidence ledger -> Error Scientist -> Methodology Auditor -> Research Judge -> deterministic experiment manifest -> approved backtest -> failure attribution -> research memory`

LLM outputs never sit directly in the execution path. Any model or rule proposed by an agent must first become a registered experiment and pass local deterministic validation.

## 4. First-line hypotheses

### 4.1 H1: quarter-hour conflict veto

The first hypothesis is motivated by recent research on periodic quarter-hour order imbalance in cryptocurrency futures. V7 uses only fully completed pre-decision windows.

For a decision at `T`, the latest usable quarter-hour opening window must end strictly before `T`. For example, a `04:00:00` decision may use the `03:45:00-03:45:09` opening window, never `04:00:00-04:00:09`.

Order imbalance is computed from causal trade data using aggressor-side semantics consistent with the source dataset. The implementation must include a regression test for `isBuyerMaker` sign mapping.

Define:

`strong_conflict = sign(QH_OI) != sign(H12_score) AND abs(QH_OI) > training_median(abs(QH_OI))`

When `strong_conflict=True`, V7 may veto a new ENTER or an exposure increase. H1 cannot flip direction, create a new LONG/SHORT signal, increase leverage, or force an EXIT.

The median threshold is fit only on the inner training fold. No threshold grid is permitted in the first-line H1 experiment.

### 4.2 H2: high-dispersion exposure gate

The second hypothesis treats cross-sectional dispersion as a reliability/risk state rather than a new direction source.

At each decision time, compute a causal cross-sectional dispersion statistic on the current causal top-liquidity universe. The default statistic is the IQR of trailing 12-hour returns.

Fit the high-dispersion threshold as the 80th percentile of that statistic in the inner training fold.

When `high_dispersion=True`, only new exposure increases are multiplied by `0.5`. HOLD, REDUCE, and EXIT remain available. H2 may not reverse direction or increase leverage in low-dispersion states.

H2 is rejected if it improves drawdown only by sacrificing too much after-cost return or if its benefit is concentrated in a single fold.

### 4.3 H3: weak-edge veto

The third hypothesis uses the inherited H12 score and avoids a new meta-model.

Within each inner training fold, compute the 20th percentile of `abs(H12_score)`. Evaluate the after-cost contribution of the weak-score bucket.

The veto is enabled for the evaluation fold only if the weak-score bucket has mean net contribution `<= 0` in the corresponding inner training fold.

When enabled, weak-score decisions may not ENTER or increase exposure. HOLD, REDUCE, and EXIT remain available.

No percentile grid, logistic regression, XGBoost, neural model, or LLM classifier is allowed in the first-line H3 experiment.

## 5. Primary experiment sequence and trial budget

The first-line sequence is fixed:

1. Replay the exact V6 baseline as V7 control, starting at trial 858.
2. Evaluate H1 alone.
3. Evaluate H2 alone.
4. Evaluate H3 alone.
5. Promote only hypotheses that clear the individual promotion gate.
6. If at least two hypotheses pass, evaluate exactly one combination containing the promoted hypotheses.
7. Run cost, delay, bootstrap, decision-error attribution, CSCV/PBO, DSR approximation, and liquidation/account stress on the final contenders.
8. Select one final V7 candidate or retain the V6 baseline.
9. Freeze the candidate before any V7 forward evaluation.

V7 first-line research is capped at 24 inspected/executed configurations and at most four alpha/reliability candidate specifications before final selection. Diagnostic configurations do not escape trial accounting if their performance is inspected.

If V7 escalates beyond H1-H3, the escalation phase is capped at an additional 36 inspected/executed performance configurations. Therefore the total V7 budget is at most 60 inspected/executed performance configurations after trial 857. Literature retrieval, factor coverage diagnostics, and unexecuted hypotheses may exceed this number, but no additional performance-bearing configuration may be inspected without a pre-freeze spec amendment. Exhausting the cap without a valid candidate ends V7 as `NEEDS_MORE_RESEARCH`; further mechanisms belong to V8.

The trial counter continues from 857 and is never reset.

## 6. Promotion gate inside discovery/evaluation

A hypothesis must improve after-cost performance at the inherited 10 bps round-trip assumption on evaluation folds relative to the frozen V6 control. It must also satisfy all of the following:

- the target error class or economic failure mode improves in the intended population;
- benefit is not explained only by an unrealistic turnover or exposure change;
- the candidate does not collapse at 20 bps costs;
- the candidate does not collapse under a +1 hour execution delay test;
- drawdown/tail risk does not increase disproportionately to incremental return;
- benefit is not isolated to a single fold;
- leakage and causal-schema tests pass;
- the complexity penalty is justified by incremental economic value.

A Sharpe improvement alone is insufficient if net return deteriorates materially.

## 7. Error-led research memory

V7 extends decision diagnostics into an append-only failure ledger. Each evaluated experiment produces a failure/success record with at least:

- `trial_number`
- `hypothesis_id`
- `target_error`
- `expected_mechanism`
- `actual_error_delta`
- `net_effect_bps`
- `turnover_effect`
- `drawdown_effect`
- `damaged_regime`
- `helped_regime`
- `assumption_status`
- `failure_reason`
- `do_not_repeat_fingerprint`
- `next_allowed_question`

The `do_not_repeat_fingerprint` is used by deterministic validation and the Error Scientist. A previously falsified mechanism may re-enter only when the new proposal supplies materially new independent evidence or a genuinely different mechanism; simple threshold nudges do not qualify.

Causal features and realized/oracle labels remain separated. Future labels are appended only after outcomes and are excluded from all pre-decision model/LLM contexts.

## 8. Factor Observatory

V7 may observe a broad factor space without automatically converting those observations into alpha. The observatory tracks factor families such as:

- price, momentum, and reversal;
- volume and trade activity;
- aggressor order flow and order imbalance;
- spread, liquidity, and available depth metrics;
- funding and futures basis;
- open interest and liquidation/crowding state;
- options volatility/skew when clean data are available;
- cross-sectional dispersion;
- cross-asset correlation and beta;
- size/liquidity structure;
- BTC/ETH leadership and crypto cross-asset state;
- equities, volatility indices, USD, rates, and commodities;
- scheduled macro events such as CPI, FOMC, and labor data;
- on-chain activity and token distribution;
- exchange inflow/outflow when source quality is sufficient;
- network activity;
- news and regulatory events;
- search/attention and social sentiment;
- hacks, listings, unlocks, and exchange events;
- transaction costs, slippage, funding stress, and liquidation risk.

For each factor family, the observatory records:

`coverage -> causal availability -> source quality -> stability -> target-error association -> incremental economic value`

Observation alone does not grant promotion into the strategy. Reverse-causality-prone features, especially simple sentiment indices, must be treated as context until they demonstrate out-of-sample incremental value.

## 9. Escalation path when simple hypotheses are insufficient

If H1-H3 do not sufficiently improve directional reliability, V7 may escalate in the following order only:

### Tier 1: factor-family challenge

A Factor Specialist may propose one factor family at a time using evidence from the observatory and literature. The hypothesis must identify the target error class, mechanism, exact causal inputs, and invalidation condition.

### Tier 2: nonlinear reliability challenger

Only factor families that demonstrated incremental information independently may enter a nonlinear challenger. The first nonlinear model should be small and interpretable enough for walk-forward testing, such as tree boosting or histogram gradient boosting.

Its preferred target is an H12 reliability probability or a no-trade/risk modifier, not a separate unbounded price-direction oracle.

Deep sequence models, Transformers, or more complex architectures are considered only if the smaller nonlinear challenger fails and there is a specific evidence-backed interaction that simple methods cannot capture.

### Tier 3: event/narrative scenario simulation

Scenario simulation may be used as a research/risk layer for discrete events and narrative propagation. It does not produce direct trading direction without separate causal event-study evidence.

Every escalation trial still consumes the common V7 trial counter and remains subject to the same multiple-testing and forward-freeze rules.

## 10. Multi-agent research council

V7 uses an event-driven research council. Logical roles may include:

- Market Microstructure Agent
- Derivatives Agent
- Macro/Cross-Asset Agent
- On-Chain Agent
- News/Event Agent
- Scenario Swarm Agent
- Error Scientist
- Methodology Auditor
- Research Judge/Synthesizer

Agents are invoked selectively based on the evidence gap; all agents are not called on every H12 decision or every research step.

Communication uses a shared append-only Research Blackboard. Agents exchange typed `EvidenceCard`-like objects rather than unconstrained long conversations. Each evidence card includes at least:

- `author_agent`
- `claim`
- `source_ids`
- `timestamp`
- `data_cutoff`
- `causal`
- `target_error`
- `expected_mechanism`
- `confidence`
- `supporting_evidence`
- `contradictory_evidence`
- `data_required`
- `recommended_action`

Dissent and contradictory evidence are preserved and cannot be deleted by the synthesizer.

The agent loop is:

`OBSERVE -> RETRIEVE -> HYPOTHESIZE -> RED-TEAM -> REGISTER -> EXPERIMENT -> ATTRIBUTE ERROR -> UPDATE MEMORY`

The loop is event-driven, triggered by a new evidence gap, a failed experiment, a meaningful change in an error bucket, or a new literature mechanism. It is not a continuously running self-modifying trader.

## 11. Agent tools and permissions

The council may receive narrow tools such as:

- `search_literature`
- `read_market_features`
- `query_factor_observatory`
- `query_error_ledger`
- `query_trial_registry`
- `query_do_not_repeat`
- `build_experiment_manifest`
- `validate_experiment`
- `run_approved_backtest`
- `compare_candidates`
- `run_scenario_simulation`

The following capabilities are explicitly absent:

- live order placement;
- exchange order cancellation;
- withdrawals or transfers;
- exchange-side leverage mutation;
- access to trading credentials or OTP flows.

`GROQ_API_KEY` is loaded only from an environment/secret store. Its value is never printed, logged, included in prompts, artifacts, diffs, or commits.

V7 reuses the existing Groq orchestration pattern instead of introducing an agent framework dependency unless an implementation requirement cannot be met with the existing code. Structured schema validation and deterministic local validators remain the authority even if an LLM returns valid JSON.

## 12. Local research skills

V7 defines local version-controlled skills rather than installing third-party trading skills directly into the research path. The initial local skills are:

- `skills/v7-research-scientist/SKILL.md`
- `skills/v7-methodology-auditor/SKILL.md`

The Research Scientist skill turns an evidence gap/failure ledger entry into one falsifiable hypothesis with fields including target error, observation, causal inputs, mechanism, single change, expected effect, cost risk, invalidation, and required test.

The Methodology Auditor skill checks causality, future leakage, duplicate/falsified mechanisms, parameter explosion, transaction-cost realism, execution realism, and whether the proposed experiment is genuinely incremental.

Third-party repositories may be used as literature/design references only. Their live-trading, copy-trading, credential-handling, or unreviewed skill files are not imported into the V7 execution path.

## 13. MiroFish/OASIS scenario role

The project referred to as "MicroFish" is treated as MiroFish unless later evidence identifies a different tool. MiroFish/OASIS is considered a social/swarm scenario simulator rather than a proven native financial time-series or order-book forecasting engine.

V7 therefore uses a MiroFish-inspired or isolated OASIS/MiroFish sidecar only for event/narrative research. A Scenario Swarm Agent may convert an event and causal context into a distribution of conceptual participant reactions, for example retail, momentum traders, leveraged perpetual traders, institutional risk managers, long-term holders, miners, and liquidity providers.

Permitted outputs include:

- scenario disagreement;
- consensus strength;
- tail-risk bucket;
- expected liquidity-stress bucket;
- narrative polarity;
- uncertainty/confidence.

A scenario simulator may not directly output an executable LONG/SHORT instruction. Its output can enter the strategy only if a causal historical event study shows incremental after-cost value and the module clears the normal promotion gate.

To minimize dependency and licensing risk, the default implementation is an isolated research adapter or sidecar rather than copying the entire external project into `crypto_research`.

## 14. Literature/evidence governance

V7 keeps a literature registry with source, access date, supported claim, affected hypothesis, source type, and evidence limitations. A paper citation does not authorize a feature unless the implementation matches the causal timing and available data semantics of the research question.

The Evidence Scout may browse public literature and documentation. It must distinguish peer-reviewed/preprint evidence, official API documentation, repository behavior, and informal blog opinions. Unsupported blog claims remain hypotheses, not evidence.

## 15. Artifact contract

V7 artifacts live under `artifacts/multi_asset_v7/` and include at least:

- `v7_protocol.json`
- `literature_registry.json`
- `hypothesis_registry.jsonl`
- `experiment_registry.csv`
- `agent_research_log.jsonl`
- `research_blackboard.jsonl`
- `factor_observatory.json`
- `failure_ledger.csv.gz`
- `do_not_repeat.json`
- `qh_imbalance_results.json`
- `dispersion_results.json`
- `weak_edge_results.json`
- `combination_results.json`
- `error_attribution.json`
- `stress_results.json`
- `dsr_results.json`
- `pbo_results.json`
- `final_candidate.json`
- `forward_freeze.json`
- `forward_observations.csv.gz`
- `readiness_gate.json`
- `final_report.md`

Escalation modules add their own artifacts without removing or overwriting first-line records.

## 16. Testing requirements

Implementation follows TDD for new nontrivial logic. Required regressions include:

1. quarter-hour features cannot consume trades at or after the decision timestamp;
2. `isBuyerMaker` sign mapping is explicitly tested;
3. the current quarter-hour opening cannot influence a simultaneous decision;
4. dispersion thresholds are fit only on the training fold;
5. weak-edge thresholds are fit only on the training fold;
6. future/forward/oracle fields are stripped from LLM contexts;
7. LLM hypotheses cannot directly create LONG/SHORT alpha;
8. trial numbers are monotonic from 857;
9. a falsified mechanism cannot silently re-enter under a small threshold change;
10. the exact V6 control replay remains unchanged apart from expected numerical-tolerance fixes already present in V6;
11. candidate/config/code mutation changes the freeze hash;
12. A1 readiness cannot pass before both 30 calendar days and 40 eligible H12 observations;
13. readiness cannot pass if 20 bps or +1 hour delay net performance is negative;
14. readiness cannot pass with liquidation, margin, exposure, or mutation violations;
15. no Binance live-order endpoint or trading credential path is introduced;
16. LLM secret values cannot appear in logs or artifacts;
17. scenario-simulator outputs cannot bypass experiment registration/promotion;
18. disagreement/dissent evidence cannot be silently discarded by synthesis.

Final verification includes full `pytest`, Ruff, compileall, leakage tests, secret scan, artifact-contract validation, trial-count consistency, and freeze-hash verification.

## 17. V7 freeze and A1 readiness gate

After discovery/evaluation selects the final candidate, V7 freezes the candidate configuration, relevant code identity, schema identity, and trial count into `forward_freeze.json` with a cryptographic hash.

No V7 tuning is permitted after that timestamp. Interim forward outcomes may be recorded but cannot alter the frozen V7 candidate. Any mechanism learned from forward failure belongs to V8 and the V7 forward period becomes locked evidence.

The A1 readiness gate requires both:

- at least 30 untouched calendar days after the V7 freeze; and
- at least 40 eligible untouched H12 observations.

All of the following must then pass simultaneously:

- net return at 10 bps > 0;
- Profit Factor > 1.10;
- Sharpe > 0.50;
- net return at 20 bps >= 0;
- net return with +1 hour execution delay >= 0;
- zero liquidations;
- zero exposure-cap violations;
- zero margin-rule violations;
- zero candidate-hash mutations;
- zero forward-driven retuning.

Only then may the verdict be `READY_FOR_PAPER_TRADING`.

If any hard gate fails, the V7 verdict is `NEEDS_MORE_RESEARCH`. Passing this gate authorizes only paper/simulated execution research, not live trading.

## 18. Independent-market scope

For V7 readiness, Binance USD-M untouched forward evidence is sufficient under A1. VN30 futures or another independent market remains a valuable external-generalization test but is not a hard requirement for the V7 `READY_FOR_PAPER_TRADING` verdict.

If an independent-market branch is tested, crypto-specific variables such as funding or liquidation state must not be forced into that market without a valid analogue and clean read-only market-data source.

## 19. Scope boundaries and YAGNI decisions

V7 deliberately does not:

- replace the H12 core before its reliability modifiers are tested;
- add RL;
- add a deep sequence model as the first nonlinear challenger;
- introduce LangGraph or another orchestration dependency when the existing Groq orchestration plus typed schemas is sufficient;
- call all agents on every market decision;
- allow free-form agent debate to select trades;
- import external live-trading skills;
- fabricate unavailable L2 state;
- optimize leverage for historical return;
- retune on Aug 1-10, 2026 or any V7 forward observation;
- claim MiroFish is a proven market forecaster without evidence.

## 20. Success criteria

V7 research is successful if it produces a causally valid, fully logged, reproducible final candidate with materially improved after-cost reliability and a trustworthy untouched-forward readiness process, even if the final verdict remains `NEEDS_MORE_RESEARCH`.

The stronger success state, `READY_FOR_PAPER_TRADING`, is awarded only by the deterministic A1 gate after the required untouched forward evidence exists.
