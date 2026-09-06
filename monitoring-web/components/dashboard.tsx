"use client";

import { useEffect, useMemo, useState } from "react";

import { LIVE_POLL_MS, buildEquitySeries, buildMarkedEquitySeries, getDisplayStatus, projectOpportunityScenario, projectPortfolioCapacity, projectPositionScenario, type MonitoringTelemetry, type OpportunityRadarRow } from "../lib/telemetry";
import { EquityChart } from "./equity-chart";


function money(value: number | null | undefined, digits = 4) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value < 0 ? "−" : ""}$${Math.abs(value).toFixed(digits)}`;
}

function percent(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function compactNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function duration(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function ageLabel(iso: string | undefined, now: number) {
  if (!iso) return "No telemetry yet";
  const age = Math.max(0, Math.floor((now - Date.parse(iso)) / 1000));
  if (age < 5) return "updated just now";
  if (age < 60) return `updated ${age}s ago`;
  return `updated ${Math.floor(age / 60)}m ${age % 60}s ago`;
}

function pnlTone(value: number | null | undefined) {
  if (!value) return "neutral";
  return value > 0 ? "positive" : "negative";
}

function asNumber(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function asText(value: unknown, fallback = "—") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function radarUnavailable(row: OpportunityRadarRow, sizing = false) {
  const warmup = row.signal_status === "WARMUP" || row.decision === "BASELINE_WARMUP";
  const label = warmup ? "WARMUP" : sizing ? "NOT SIZED" : "NOT MODELED";
  return <span className={`metric-state ${warmup ? "metric-warmup" : "metric-unavailable"}`}>{label}</span>;
}

function strategyName(strategyId: string) {
  return ({
    CONTROL_V14C: "V14-C control",
    ADAPTIVE_EXIT_SHADOW_V1: "Adaptive exit",
    SPREAD_CONTINUATION_SHADOW_V1: "Spread continuation",
    FUNDING_AWARE_SHADOW_V1: "Funding overlay",
  } as Record<string, string>)[strategyId] ?? strategyId;
}

function MiniSeriesChart({ values, label }: { values: number[]; label: string }) {
  if (values.length < 2) return <div className="mini-chart-empty">Collecting history…</div>;
  const width = 100;
  const height = 30;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1e-9);
  const points = values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : index / (values.length - 1) * width;
    const y = height - ((value - min) / span) * height;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  return (
    <svg className="mini-series" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label} preserveAspectRatio="none">
      <polyline points={points} fill="none" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function Dashboard() {
  const [telemetry, setTelemetry] = useState<MonitoringTelemetry | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [scenarioCapital, setScenarioCapital] = useState(100);
  const [scenarioLeverage, setScenarioLeverage] = useState(1);

  useEffect(() => {
    let alive = true;
    let inFlight = false;
    const load = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const response = await fetch(`/api/telemetry?t=${Date.now()}`, { cache: "no-store" });
        if (response.status === 404) {
          if (alive) setTelemetry(null);
          return;
        }
        if (!response.ok) throw new Error(`telemetry HTTP ${response.status}`);
        const data = (await response.json()) as MonitoringTelemetry;
        if (alive) {
          setTelemetry(data);
          setFetchError(null);
        }
      } catch (error) {
        if (alive) setFetchError(error instanceof Error ? error.message : "Telemetry unavailable");
      } finally {
        inFlight = false;
      }
    };
    void load();
    const poll = window.setInterval(load, LIVE_POLL_MS);
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      alive = false;
      window.clearInterval(poll);
      window.clearInterval(clock);
    };
  }, []);

  const status = getDisplayStatus(telemetry, now);
  const displaySchemaVersion = telemetry?.schema_version ?? "v21-monitoring-1";
  const isV16 = displaySchemaVersion === "v16-monitoring-1";
  const isV17 = displaySchemaVersion === "v17-monitoring-1";
  const isV19 = displaySchemaVersion === "v19-monitoring-1";
  const isV20 = displaySchemaVersion === "v20-monitoring-1";
  const isV21 = displaySchemaVersion === "v21-monitoring-1";
  const isExecutionAware = isV20 || isV21;
  const isV18 = displaySchemaVersion === "v18-monitoring-1" || isV19 || isExecutionAware;
  const websocketVersion = isV21 ? "V21" : isV20 ? "V20" : isV19 ? "V19" : "V18";
  const isMakerExecution = isV17 || isV18;
  const isRouteRelative = isV16 || isMakerExecution;
  const series = useMemo(() => (telemetry ? (isRouteRelative ? buildMarkedEquitySeries(telemetry) : buildEquitySeries(telemetry)) : []), [telemetry, isRouteRelative]);
  const metrics = telemetry?.metrics;
  const isV15 = displaySchemaVersion === "v15-monitoring-1";
  const isV14 = displaySchemaVersion === "v14-monitoring-1" || isV15 || isRouteRelative;
  const isV14C = telemetry?.portfolio_model === "CROSS_MARGIN_OPTIMIZER_V1";
  const accountLast = isRouteRelative && telemetry?.account_history?.length ? telemetry.account_history[telemetry.account_history.length - 1] : null;
  const strategyLab = telemetry?.strategy_lab ?? [];
  const carryResearch = telemetry?.funding_carry_research;
  const pnl = telemetry?.realized_pnl ?? 0;
  const enoughEvidence = (metrics?.closed_trade_count ?? 0) >= 2;
  const closed = telemetry?.closed_positions ?? [];
  const open = telemetry?.open_positions ?? [];
  const openMtm = open.reduce((sum, position) => {
    const value = asNumber(position.estimated_net_pnl_if_closed);
    return sum + (value ?? 0);
  }, 0);
  const hasLiveOpenMark = open.some((position) => position.mark_status === "LIVE");
  const radar = telemetry?.opportunity_radar ?? [];
  const scenarioPositionRows = open.flatMap((position) => {
    const projection = projectPositionScenario(position, telemetry?.equity ?? 0, scenarioCapital, scenarioLeverage);
    return projection ? [{ position, projection }] : [];
  });
  const scenarioPositions = scenarioPositionRows.map((row) => row.projection);
  const scenario = scenarioPositions.length > 0 ? scenarioPositions.reduce(
    (total, item) => ({
      long_notional: total.long_notional + item.long_notional,
      short_notional: total.short_notional + item.short_notional,
      gross_exposure: total.gross_exposure + item.gross_exposure,
      long_initial_margin: total.long_initial_margin + item.long_initial_margin,
      short_initial_margin: total.short_initial_margin + item.short_initial_margin,
      initial_margin: total.initial_margin + item.initial_margin,
      estimated_net_pnl_if_closed: total.estimated_net_pnl_if_closed + item.estimated_net_pnl_if_closed,
    }),
    {
      long_notional: 0,
      short_notional: 0,
      gross_exposure: 0,
      long_initial_margin: 0,
      short_initial_margin: 0,
      initial_margin: 0,
      estimated_net_pnl_if_closed: 0,
    },
  ) : null;
  const scenarioPnlPct = scenario ? scenario.estimated_net_pnl_if_closed / scenarioCapital * 100 : null;
  const capacity = projectPortfolioCapacity(scenarioCapital, scenarioLeverage, telemetry?.max_open_positions ?? 6);
  const scenarioOpportunityRows = scenarioPositionRows.length === 0
    ? radar.flatMap((row) => {
        const projection = projectOpportunityScenario(row, scenarioCapital, scenarioLeverage, telemetry?.max_open_positions ?? 6);
        return projection ? [projection] : [];
      }).slice(0, telemetry?.max_open_positions ?? 6)
    : [];
  const venueBalances = telemetry?.venue_balances ?? {};
  const venueMarginUsed = telemetry?.venue_margin_used ?? {};
  const venueAvailableMargin = telemetry?.venue_available_margin ?? {};
  const venueAccountEquity = telemetry?.venue_account_equity ?? {};
  const venueStress = telemetry?.venue_maintenance_stress ?? {};
  const venueMarginRatio = telemetry?.venue_margin_ratio ?? {};
  const venueMarginUtilization = telemetry?.venue_margin_utilization ?? {};
  const recentRows = [
    ...open.map((position) => ({ ...position, row_status: "OPEN" })),
    ...[...closed].reverse().map((position) => ({ ...position, row_status: "CLOSED" })),
  ].slice(0, 12);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="eyebrow"><span className="pulse" /> LIVE PAPER TELEMETRY</div>
          <h1>InvestMent <span>· {isV21 ? "V21 Cohort-Calibrated Risk Paper Monitor" : isV20 ? "V20 Execution-Aware Paper Monitor" : isV19 ? "V19 WebSocket Causal EV Paper Monitor" : isV18 ? "V18 WebSocket Causal EV Paper Monitor" : isV17 ? "V17 Maker-First EV Paper Monitor" : isV16 ? "V16 Route-Relative Paper Monitor" : isV15 ? "V15 Shadow Strategy Lab" : isV14C ? "V14-C Cross-Margin Paper Monitor" : isV14 ? "V14 Multi-Asset Paper Monitor" : "V21 Cohort-Calibrated Risk Paper Monitor"}</span></h1>
        </div>
        <div className="topbar-meta">
          <span className="readonly-badge">PUBLIC · READ ONLY</span>
          <span className={`status-chip status-${status.toLowerCase()}`}><i />{status}</span>
          <span className="updated">{ageLabel(telemetry?.updated_at_utc, now)}</span>
        </div>
      </header>

      {(fetchError || telemetry?.runner_error) && (
        <div className="alert" role="status">
          <strong>Monitoring notice</strong>
          <span>{telemetry?.runner_error ?? fetchError}</span>
        </div>
      )}

      <section className="hero-grid" aria-label="Primary performance metrics">
        <article className="kpi kpi-primary">
          <span className="kpi-label">{isRouteRelative ? "Marked equity" : "Current equity"}</span>
          <strong>{telemetry ? money(accountLast?.marked_equity ?? telemetry.equity, 4) : money(100, 4)}</strong>
          <small>{isRouteRelative ? `Realized ${money(telemetry?.equity, 4)} · started ${money(telemetry?.initial_equity, 2)}` : `Started at ${telemetry ? money(telemetry.initial_equity, 2) : money(100, 2)} virtual`}</small>
        </article>
        <article className={`kpi ${pnlTone(pnl)}`}>
          <span className="kpi-label">Realized PnL</span>
          <strong>{telemetry ? money(telemetry.realized_pnl, 4) : "—"}</strong>
          <small>{telemetry ? percent(telemetry.return_pct, 3) : "Waiting for telemetry"}</small>
        </article>
        <article className="kpi">
          <span className="kpi-label">Max drawdown</span>
          <strong>{metrics?.max_drawdown_pct === null || metrics?.max_drawdown_pct === undefined ? "—" : `${compactNumber(metrics.max_drawdown_pct, 2)}%`}</strong>
          <small>Realized equity path</small>
        </article>
        <article className="kpi">
          <span className="kpi-label">{isExecutionAware ? "Paired Win Rate" : "Win rate"}</span>
          <strong>{percent(metrics?.win_rate_pct)}</strong>
          <small>{metrics?.closed_trade_count ?? 0} closed paper trades</small>
        </article>
        <article className="kpi">
          <span className="kpi-label">Closed trades</span>
          <strong>{telemetry?.closed_position_count ?? 0}</strong>
          <small>{telemetry?.opened_position_count ?? 0} total opens</small>
        </article>
        <article className={`kpi ${hasLiveOpenMark ? pnlTone(openMtm) : ""}`}>
          <span className="kpi-label">Open positions</span>
          <strong>{telemetry?.open_position_count ?? 0}</strong>
          <small>{hasLiveOpenMark ? `Exit-now estimate ${money(openMtm, 4)}` : isV14 ? `${telemetry?.universe_size ?? 0} symbols · radar active` : "Duplicate suppression active"}</small>
        </article>
      </section>

      {isExecutionAware && telemetry && (
        <section className="panel v16-capital-panel" aria-label="V20 account-level execution performance">
          <div className="panel-head">
            <div>
              <span className="section-kicker">{isV21 ? "V21 · 90% COHORT POLICY · ACCOUNT OBJECTIVE" : "V20 · ACCOUNT-LEVEL REALIZED OBJECTIVE"}</span>
              <h2>Execution truth</h2>
            </div>
            <span className="model-badge">TARGET ≥ +{money(telemetry.target_realized_pnl_per_hour ?? 0.05, 2)} / HOUR</span>
          </div>
          <div className="risk-metrics v16-capital-grid">
            <div><span>Account Realized PnL</span><strong className={pnlTone(telemetry.realized_pnl)}>{money(telemetry.realized_pnl, 4)}</strong><small>all equity-mutating paper events</small></div>
            <div><span>Paired Realized PnL</span><strong className={pnlTone(telemetry.paired_realized_pnl)}>{money(telemetry.paired_realized_pnl, 4)}</strong><small>successful paired closes only</small></div>
            <div><span>Non-Paired Execution PnL</span><strong className={pnlTone(telemetry.non_paired_execution_pnl)}>{money(telemetry.non_paired_execution_pnl, 4)}</strong><small>aborts and other realized execution paths</small></div>
            <div><span>Account PnL/hour</span><strong className={pnlTone(telemetry.account_pnl_per_hour)}>{money(telemetry.account_pnl_per_hour, 4)}</strong><small>target +{money(telemetry.target_realized_pnl_per_hour ?? 0.05, 4)}/h</small></div>
            <div><span>Paired PnL/hour</span><strong className={pnlTone(telemetry.paired_pnl_per_hour)}>{money(telemetry.paired_pnl_per_hour, 4)}</strong><small>{compactNumber(telemetry.paired_trades_per_hour, 3)} paired trades/h</small></div>
            <div><span>Abort net</span><strong className={pnlTone(telemetry.abort_net_pnl)}>{money(telemetry.abort_net_pnl, 4)}</strong><small>{telemetry.abort_count ?? 0} aborts · {money(telemetry.abort_fees, 4)} fees</small></div>
            <div><span>Realized Funding PnL</span><strong className={pnlTone(telemetry.realized_funding_pnl)}>{money(telemetry.realized_funding_pnl, 4)}</strong><small>{money(telemetry.funding_pnl_per_hour, 4)} / hour</small></div>
            <div><span>Total fee drag</span><strong>{money(telemetry.total_fee_drag, 4)}</strong><small>paired {money(telemetry.paired_fee_drag, 4)} · non-paired {money(telemetry.non_paired_fee_drag, 4)}</small></div>
            <div><span>Rolling 1h / 3h / 6h</span><strong className={pnlTone(telemetry.rolling_1h_pnl)}>{money(telemetry.rolling_1h_pnl, 4)}</strong><small>{money(telemetry.rolling_3h_pnl, 4)} · {money(telemetry.rolling_6h_pnl, 4)}</small></div>
            <div><span>Median entry gap</span><strong>{duration(telemetry.median_entry_gap_seconds)}</strong><small>p95 {duration(telemetry.p95_entry_gap_seconds)}</small></div>
            <div><span>PnL reconciliation</span><strong className={Math.abs(telemetry.account_pnl_reconciliation_error ?? 0) < 1e-8 ? "positive-text" : "negative-text"}>{money(telemetry.account_pnl_reconciliation_error, 8)}</strong><small>account − paired − non-paired</small></div>
          </div>
          <p className="risk-boundary">Paired Win Rate is intentionally separate from account profitability. {isV21 ? "V21 uses a 90% confidence lower bound on matching-cohort post-fill acceptance inside conservative after-cost attempt EV; it does not require a 90% empirical accept rate, and it is not a guaranteed final trade win rate." : "V20 admission prices the causal maker-fill accept/reject tree and its unwind loss before allocating paper leverage."}</p>
        </section>
      )}

      {isRouteRelative && telemetry && (
        <section className="panel v16-capital-panel" aria-label={`${isV18 ? websocketVersion : isV17 ? "V17" : "V16"} realtime capital and PnL`}>
          <div className="panel-head">
            <div><span className="section-kicker">{isV18 ? `${websocketVersion} · WEBSOCKET CAUSAL EXECUTABLE ACCOUNT` : isV17 ? "V17 · MAKER-FIRST EXECUTABLE ACCOUNT" : "V16 · EXECUTABLE EXIT-NOW ACCOUNT"}</span><h2>Capital & PnL flow</h2></div>
            <span className="model-badge">$100 PAPER START</span>
          </div>
          <div className="risk-metrics v16-capital-grid">
            <div><span>Realized equity</span><strong>{money(telemetry.equity, 4)}</strong><small>changes only on simulated CLOSE</small></div>
            <div><span>Marked equity</span><strong className={pnlTone((accountLast?.marked_equity ?? telemetry.equity) - telemetry.initial_equity)}>{money(accountLast?.marked_equity ?? telemetry.equity, 4)}</strong><small>realized + close-now net</small></div>
            <div><span>Estimated net if exited now</span><strong className={pnlTone(accountLast?.unrealized_net_pnl ?? openMtm)}>{money(accountLast?.unrealized_net_pnl ?? openMtm, 4)}</strong><small>includes modeled exit fees</small></div>
            <div><span>Modeled fee drag</span><strong>{money(accountLast?.modeled_fee_drag ?? metrics?.fee_drag, 4)}</strong><small>realized + open if closed now</small></div>
            <div><span>Gross exposure</span><strong>{money(accountLast?.gross_exposure ?? telemetry.gross_exposure, 2)}</strong><small>{compactNumber(telemetry.gross_leverage_used, 2)}× account gross</small></div>
            <div><span>Initial margin</span><strong>{money(accountLast?.margin_used ?? telemetry.initial_margin_used, 2)}</strong><small>{money(telemetry.available_margin, 2)} venue headroom</small></div>
          </div>
          <p className="risk-boundary">Marked equity is not a forecast: it is the current public-book executable close estimate for every open paper route. Realized equity remains unchanged until a simulated close.</p>
        </section>
      )}

      {isMakerExecution && telemetry && (
        <section className="panel maker-observatory" aria-label={`${isV18 ? websocketVersion : "V17"} maker execution observatory`}>
          <div className="panel-head risk-head">
            <div>
              <span className="section-kicker">{isV18 ? `${websocketVersion} · WEBSOCKET + POST-FILL EV` : "V17 · CAUSAL MAKER EXECUTION"}</span>
              <h2>{isV18 ? "Causal Execution Observatory" : "Maker Execution Observatory"}</h2>
            </div>
            <span className="model-badge">Paper only · EV gated</span>
          </div>
          <div className="risk-metrics maker-metrics-grid">
            <div><span>Pending entries</span><strong>{telemetry.pending_entry_count ?? 0}</strong><small>resting passive pairs</small></div>
            <div><span>Pending exits</span><strong>{telemetry.pending_exit_count ?? 0}</strong><small>maker-first close attempts</small></div>
            <div><span>Passive probes</span><strong>{telemetry.maker_probe_count ?? 0}</strong><small>shadow fill-learning attempts</small></div>
            <div><span>Later-book observations</span><strong>{telemetry.maker_fill_observation_count ?? 0}</strong><small>fill-model evidence, not fills</small></div>
            <div><span>No-fill cancels</span><strong>{telemetry.maker_entry_cancel_count ?? 0}</strong><small>zero fee / zero equity mutation</small></div>
            <div><span>One-leg hedges</span><strong>{telemetry.one_leg_hedge_count ?? 0}</strong><small>missing leg taker-hedged</small></div>
            <div><span>Exit fallbacks</span><strong>{telemetry.maker_exit_fallback_count ?? 0}</strong><small>maker timeout → taker close</small></div>
            <div><span>Hedge failures</span><strong className={(telemetry.maker_hedge_failure_count ?? 0) === 0 ? "positive-text" : "negative-text"}>{telemetry.maker_hedge_failure_count ?? 0}</strong><small>depth / public-book guard</small></div>
          </div>
          {isV18 && (
            <div className="risk-metrics maker-metrics-grid v18-stream-grid">
              <div><span>WebSocket venues</span><strong>{telemetry.connected_venue_count ?? 0} / {telemetry.expected_venue_count ?? "—"}</strong><small>{telemetry.ws_reconnect_count ?? 0} stream retry attempts since restart</small></div>
              {isV21 && <div><span>Stream errors · last minute</span><strong>{Object.values(telemetry.stream_errors_last_60s_by_venue ?? {}).reduce((sum, count) => sum + count, 0)}</strong><small>{Object.entries(telemetry.stream_errors_last_60s_by_venue ?? {}).map(([venue, count]) => `${venue} ${count}`).join(" · ") || "No recent errors"}</small></div>}
              {isV21 && <div><span>Funding refresh age</span><strong>{telemetry.funding_refresh_age_seconds == null ? "—" : `${compactNumber(telemetry.funding_refresh_age_seconds, 0)} s`}</strong><small>full public REST refresh · 180 s limit</small></div>}
              <div><span>Median book age</span><strong>{telemetry.book_age_ms_median == null ? "—" : `${compactNumber(telemetry.book_age_ms_median, 0)} ms`}</strong><small>local receive clock</small></div>
              <div><span>Max book age</span><strong>{telemetry.book_age_ms_max == null ? "—" : `${compactNumber(telemetry.book_age_ms_max, 0)} ms`}</strong><small>{telemetry.stale_book_count ?? 0} stale / skew-rejected</small></div>
              <div><span>Book updates</span><strong>{telemetry.book_update_count ?? 0}</strong><small>{telemetry.book_cache_entry_count ?? 0} bounded latest books</small></div>
              {isV21 && <div><span>Public trade prints</span><strong>{telemetry.public_trade_update_count ?? 0}</strong><small>OKX {telemetry.public_trade_update_counts_by_venue?.okx ?? 0} · Gate {telemetry.public_trade_update_counts_by_venue?.gate ?? 0} causal queue evidence</small></div>}
              <div><span>{isV21 ? "Shadow post-fill accepted" : "Post-fill accepted"}</span><strong>{isV21 ? telemetry.v21_shadow_accept_count ?? 0 : telemetry.post_fill_accept_count ?? 0}</strong><small>{isV21 ? "causal calibration outcomes" : "EV revalidated after fill"}</small></div>
              <div><span>{isV21 ? "Shadow post-fill rejected" : "Post-fill rejected"}</span><strong>{isV21 ? telemetry.v21_shadow_reject_count ?? 0 : telemetry.post_fill_reject_count ?? 0}</strong><small>{isV21 ? "causal calibration outcomes" : "stale edge not opened"}</small></div>
              <div><span>One-leg aborts</span><strong>{telemetry.one_leg_abort_count ?? 0}</strong><small>{money(telemetry.one_leg_abort_pnl, 4)} realized unwind</small></div>
              <div><span>Runner RSS</span><strong>{compactNumber((telemetry.process_rss_bytes ?? 0) / 1024 / 1024, 0)} MB</strong><small>{telemetry.memory_prune_count ?? 0} cache prunes</small></div>
            </div>
          )}
          {(telemetry.pending_entries?.length ?? 0) > 0 && (
            <div className="table-scroll maker-pending-table">
              <table>
                <thead><tr><th>State</th><th>Symbol</th><th>Route</th><th>Maker limits</th><th>Qty</th><th>Capture</th><th>Expected EV</th><th>Min EV</th><th>P(open)</th><th>Lev</th></tr></thead>
                <tbody>{telemetry.pending_entries?.map((pending) => (
                  <tr key={pending.pending_id ?? `${pending.symbol}-${pending.placed_at_utc}`}>
                    <td><span className="decision-chip">{asText(pending.status)}</span></td>
                    <td className="mono strong">{asText(pending.symbol)}</td>
                    <td><span className="route-long">L {asText(pending.long_exchange)}</span><span className="route-arrow">↔</span><span className="route-short">S {asText(pending.short_exchange)}</span></td>
                    <td className="mono two-line"><span>{compactNumber(pending.long_limit_price, 5)}</span><span>{compactNumber(pending.short_limit_price, 5)}</span></td>
                    <td className="mono">{compactNumber(pending.quantity, 6)}</td>
                    <td className="mono">{pending.capture_bps === undefined ? "—" : `${compactNumber(pending.capture_bps, 2)} bps`}</td>
                    <td className={`mono ${pnlTone(pending.expected_value_bps)}`}>{pending.expected_value_bps === undefined ? "—" : `${compactNumber(pending.expected_value_bps, 2)} bps`}</td>
                    <td className="mono">{pending.minimum_required_ev_bps === undefined ? "—" : `${compactNumber(pending.minimum_required_ev_bps, 2)} bps`}</td>
                    <td className="mono">{pending.p_open === undefined ? "—" : percent(pending.p_open * 100, 1)}</td>
                    <td className="mono">{pending.leverage === undefined ? "—" : `${compactNumber(pending.leverage, 0)}×`}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <p className="risk-boundary">PENDING does not mean filled. {isV21 ? "V21 exposes one causal maker leg, calibrates post-fill outcomes within the matching capture cohort, then requires positive after-cost EV before hedging." : isV20 ? "V20 exposes one causal maker leg, immediately prices the taker hedge after fill, and rejects the attempt when calibrated account-level terminal EV is not positive enough." : isV18 ? `${websocketVersion} requires a fresh post-placement WebSocket book and revalidates EV at the actual maker/taker entry prices; a rejected one-leg fill is immediately unwound in paper.` : "V17 recognizes a passive maker fill only on a later public order book that touches or trades through the resting limit; a one-leg fill uses the executable public book to hedge the missing leg."}</p>
        </section>
      )}

      {isV21 && carryResearch && (
        <section className="panel" aria-label="Funding carry research">
          <div className="panel-head">
            <div><span className="section-kicker">V22 · OBSERVATION ONLY</span>
              <h2>Funding carry research</h2>
              <p>{carryResearch.fresh_quote_count} fresh quotes · {carryResearch.positive_after_fee_quote_count} routes above the fee hurdle</p>
            </div>
          </div>
          <div className="table-scroll">
            <table>
              <thead><tr><th>Symbol</th><th>Long → Short</th><th>Funding quote</th><th>Round-trip fees</th><th>After fees</th><th>Settlement UTC</th></tr></thead>
              <tbody>{carryResearch.rows.map((row) => (
                <tr key={`${row.symbol}-${row.long_venue}-${row.short_venue}`}>
                  <td>{row.symbol}</td><td>{row.long_venue} → {row.short_venue}</td>
                  <td className="mono">{row.quoted_funding_bps.toFixed(2)} bps</td>
                  <td className="mono">{row.round_trip_fee_bps.toFixed(2)} bps</td>
                  <td className={`mono ${pnlTone(row.after_fee_quote_bps)}`}>{row.after_fee_quote_bps.toFixed(2)} bps</td>
                  <td className="mono">{new Date(row.settlement_at_ms).toISOString().slice(11, 16)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <p className="risk-boundary">Next shared settlement only; quotes can change. Spread, depth, basis movement and margin risk still need execution evidence. No capital is allocated and no research quote is counted as account PnL.</p>
        </section>
      )}

      {isV15 && strategyLab.length > 0 && (
        <section className="panel strategy-lab-panel" aria-label="V15 shadow strategy lab">
          <div className="panel-head strategy-lab-head">
            <div>
              <span className="section-kicker">V15 · CONTROL + SHADOW</span>
              <h2>Strategy Lab</h2>
              <p>Control PnL stays primary. Shadow results are isolated experiments and never place live orders.</p>
            </div>
            <span className="model-badge">PAPER ONLY</span>
          </div>
          <div className="strategy-lab-grid">
            {strategyLab.map((strategy) => {
              const observationOnly = strategy.mode === "OBSERVATION_ONLY";
              const isControl = strategy.mode === "CONTROL";
              return (
                <article className="strategy-card" key={strategy.strategy_id}>
                  <div className="strategy-card-head">
                    <div><span>{isControl ? "CONTROL" : observationOnly ? "OVERLAY" : "SHADOW"}</span><strong>{strategyName(strategy.strategy_id)}</strong></div>
                    <span className={`strategy-mode ${isControl ? "control" : "shadow"}`}>{strategy.mode ?? "—"}</span>
                  </div>
                  {observationOnly ? (
                    <div className="strategy-primary"><span>Funding routes observed</span><strong>{strategy.observed_route_count ?? 0}</strong></div>
                  ) : (
                    <div className={`strategy-primary ${pnlTone(strategy.realized_pnl)}`}><span>Realized {isControl ? "control" : "shadow"} PnL</span><strong>{money(strategy.realized_pnl, 4)}</strong></div>
                  )}
                  <dl>
                    {!observationOnly && <><div><dt>Open</dt><dd>{strategy.open_position_count ?? 0}</dd></div><div><dt>Closed</dt><dd>{strategy.closed_trade_count ?? 0}</dd></div></>}
                    {!isControl && !observationOnly && <><div><dt>Win rate</dt><dd>{percent(strategy.win_rate_pct)}</dd></div><div><dt>Profit factor</dt><dd>{compactNumber(strategy.profit_factor)}</dd></div></>}
                  </dl>
                </article>
              );
            })}
          </div>
          <p className="strategy-boundary">V15 shadow evidence does not mutate V14-C equity, margin, or order decisions. Promotion requires a materially larger out-of-sample paper sample.</p>
        </section>
      )}

      {isV14 && telemetry && (
        <section className="portfolio-observatory" aria-label="V14 modeled portfolio risk">
          <article className="panel risk-panel">
            <div className="panel-head risk-head">
              <div>
                <span className="section-kicker">MODELED PAPER RISK</span>
                <h2>{isV18 ? "WebSocket post-fill EV allocator" : isV17 ? "Maker-first EV allocator" : isV16 ? "Route-relative multi-strategy allocator" : isV14C ? "Cross-margin portfolio optimizer" : "Isolated portfolio budget"}</h2>
              </div>
              <span className="model-badge">{telemetry.margin_model === "CROSS_MARGIN_PAPER_V1" ? "Cross-margin simulation" : telemetry.margin_model === "ISOLATED_PAPER_V1" ? "Isolated-margin simulation" : "Paper margin model"}</span>
            </div>
            <div className="risk-metrics">
              <div><span>{isRouteRelative ? "Max position leverage" : "Exchange leverage"}</span><strong>{compactNumber(telemetry.exchange_leverage, 1)}×</strong><small>{isV18 ? "positions choose 20×–40×" : isRouteRelative ? "actual positions choose 1×–3×" : "actual V14 paper model"}</small></div>
              <div><span>Gross leverage</span><strong>{compactNumber(telemetry.gross_leverage_used, 2)}× / {compactNumber(telemetry.gross_leverage_cap, 1)}×</strong><small>{money(telemetry.gross_exposure, 2)} gross open</small></div>
              <div><span>Initial margin used</span><strong>{money(telemetry.initial_margin_used, 2)}</strong><small>{money(telemetry.available_margin, 2)} cross-margin headroom</small></div>
              <div><span>Stress maintenance</span><strong>{money(telemetry.maintenance_stress_used, 2)}</strong><small>min ratio {compactNumber(telemetry.min_stress_margin_ratio, 2)}×</small></div>
              <div><span>Position slots</span><strong>{telemetry.open_position_count} / {telemetry.max_open_positions ?? 6}</strong><small>{telemetry.universe_size ?? 0} symbols · {isRouteRelative ? "unique routes" : "one pair each"}</small></div>
              <div><span>Invariant failures</span><strong className={(telemetry.invariant_failure_count ?? 0) === 0 ? "positive-text" : "negative-text"}>{telemetry.invariant_failure_count ?? 0}</strong><small>accounting / margin guard</small></div>
            </div>
            <div className="venue-budget-grid">
              {Object.keys(venueBalances).sort().map((venue) => (
                <div className="venue-budget" key={venue}>
                  <div className="venue-budget-head"><strong>{venue.toUpperCase()}</strong><span>{isV14C || isRouteRelative ? "shared cross-margin" : "paper collateral"}</span></div>
                  <dl>
                    <div><dt>Balance</dt><dd>{money(venueBalances[venue], 4)}</dd></div>
                    <div><dt>Account equity</dt><dd className={pnlTone((venueAccountEquity[venue] ?? venueBalances[venue]) - venueBalances[venue])}>{money(venueAccountEquity[venue] ?? venueBalances[venue], 4)}</dd></div>
                    <div><dt>IM used</dt><dd>{money(venueMarginUsed[venue], 4)} · {percent((venueMarginUtilization[venue] ?? 0) * 100, 1)}</dd></div>
                    <div><dt>Headroom</dt><dd>{money(venueAvailableMargin[venue], 4)}</dd></div>
                    <div><dt>Stress maint.</dt><dd>{money(venueStress[venue], 4)}</dd></div>
                    <div><dt>Stress ratio</dt><dd>{venueMarginRatio[venue] === undefined ? "—" : `${compactNumber(venueMarginRatio[venue], 2)}×`}</dd></div>
                  </dl>
                </div>
              ))}
            </div>
            <p className="risk-boundary">{isV18 ? `${websocketVersion} allocates only after causal post-fill EV revalidation using 20×–40× paper leverage. Books are receive-time fresh and cross-venue skew bounded; exact exchange liquidation is intentionally not modeled.` : isV17 ? `V17 allocates per exact route using maker-first expected value, causal fill probabilities, and 1×–3× paper leverage. Cross margin remains venue-local; exact exchange liquidation is still unavailable until symbol/tier rules are modeled.` : isV16 ? `V16 allocates per exact route and chooses 1×–3× paper leverage from route-relative edge and observed volatility. Cross margin remains venue-local; exact exchange liquidation is still unavailable until symbol/tier rules are modeled.` : isV14C ? `Cross margin is shared only inside each venue. Maintenance uses a ${(telemetry.maintenance_stress_rate ?? 0) * 100}% paper stress rate with ${(telemetry.margin_utilization_cap ?? 0) * 100}% IM utilization cap; exact exchange liquidation remains unavailable until symbol/tier rules are modeled.` : "Maintenance margin and liquidation remain unavailable until venue-specific tiers are modeled."}</p>
          </article>

          <article className="panel radar-panel">
            <div className="panel-head radar-head">
              <div>
                <span className="section-kicker">{isV21 ? "V21 COHORT EV RADAR" : isV18 ? "POST-FILL EV RADAR" : isV17 ? "MAKER EV RADAR" : isV16 ? "ROUTE-RELATIVE RADAR" : "OPPORTUNITY RADAR"}</span>
                <h2>{isV21 ? "Route dislocation vs cohort-calibrated attempt EV" : isV18 ? "Route dislocation vs causal executable EV" : isV17 ? "Route dislocation vs expected execution value" : isV16 ? "Raw spread vs structural route basis" : "Why the scanner trades — or waits"}</h2>
              </div>
              <span className="radar-count">{telemetry.last_cycle_signal_count ?? 0} signals now · {telemetry.last_cycle_tradeable_count ?? 0} tradeable · {telemetry.observed_signal_count ?? 0} observed</span>
            </div>
            {radar.length === 0 ? (
              <div className="radar-empty">{isV21 ? "Streaming public books while collecting matching-cohort causal maker-fill evidence." : isV18 ? "Streaming fresh public books and learning causal route/fill evidence." : isV17 ? "Learning route baselines and causal maker-fill probabilities from public books." : isV16 ? "Collecting route baselines from public executable books." : "Waiting for the next V14 scan diagnostics."}</div>
            ) : (
              <div className="table-scroll radar-scroll">
                {isV21 ? (
                  <>
                    <div className="radar-legend" aria-label="V21 radar definitions">
                      <span><strong>P(fill)</strong> causal maker-fill estimate</span>
                      <span><strong>P(accept)</strong> cohort post-fill point estimate</span>
                      <span><strong>Accept LB</strong> conservative 90% lower bound</span>
                      <span><strong>Cal G/L</strong> cohort fills: global / venue-side</span>
                    </div>
                    <table className="radar-table radar-table-v21">
                      <thead><tr><th>Symbol</th><th>Route</th><th title="Selected maker side and venue">Maker</th><th>Gross</th><th>Base 60m</th><th>Base 15m</th><th>Capture</th><th title="After-cost paired value conditional on an accepted maker fill">Pair value</th><th title="Conservative unwind value when a maker fill is rejected post-fill">Abort value</th><th title="Account-level EV per maker attempt, including fills, accepts and aborts">Attempt EV</th><th>Min EV</th><th title="Causal probability that the selected maker attempt fills">P(fill)</th><th title="Point estimate of post-fill acceptance in the matching V21 capture cohort">P(accept)</th><th title="One-sided 90% conservative lower bound for post-fill acceptance">Accept LB</th><th title="Matching-cohort fill samples: global / selected venue-side">Cal G/L</th><th>Vol</th><th>Lev</th><th>Signal</th><th>Decision</th></tr></thead>
                      <tbody>
                        {radar.slice(0, 20).map((row, index) => (
                          <tr key={`${row.symbol ?? "radar"}-${index}`} className={row.signal_status === "WARMUP" ? "radar-row-warmup" : undefined}>
                            <td className="mono strong">{asText(row.symbol)}</td>
                            <td>{row.buy_venue && row.sell_venue ? <><span className="route-long">L {row.buy_venue}</span><span className="route-arrow">↔</span><span className="route-short">S {row.sell_venue}</span></> : radarUnavailable(row)}</td>
                            <td className="mono">{row.maker_side && row.maker_venue ? `${row.maker_side === "LONG" ? "L" : "S"} ${row.maker_venue}` : radarUnavailable(row)}</td>
                            <td className="mono">{row.gross_edge_bps === undefined ? radarUnavailable(row) : `${compactNumber(row.gross_edge_bps, 2)} bps`}</td>
                            <td className="mono">{row.baseline_60m_bps === undefined ? radarUnavailable(row) : `${compactNumber(row.baseline_60m_bps, 2)} bps`}</td>
                            <td className="mono">{row.baseline_15m_bps === undefined ? radarUnavailable(row) : `${compactNumber(row.baseline_15m_bps, 2)} bps`}</td>
                            <td className={`mono ${pnlTone(row.capture_bps)}`}>{row.capture_bps === undefined ? radarUnavailable(row) : `${compactNumber(row.capture_bps, 2)} bps`}</td>
                            <td className={`mono ${pnlTone(row.conditional_pair_value_bps)}`}>{row.conditional_pair_value_bps === undefined ? radarUnavailable(row) : `${compactNumber(row.conditional_pair_value_bps, 2)} bps`}</td>
                            <td className={`mono ${pnlTone(row.reject_net_bps)}`}>{row.reject_net_bps === undefined ? radarUnavailable(row) : `${compactNumber(row.reject_net_bps, 2)} bps`}</td>
                            <td className={`mono ${pnlTone(row.expected_attempt_ev_bps)}`}>{row.expected_attempt_ev_bps === undefined ? radarUnavailable(row) : `${compactNumber(row.expected_attempt_ev_bps, 2)} bps`}</td>
                            <td className="mono">{row.minimum_required_ev_bps === undefined ? radarUnavailable(row) : `${compactNumber(row.minimum_required_ev_bps, 2)} bps`}</td>
                            <td className="mono">{row.p_open === undefined ? radarUnavailable(row) : percent(row.p_open * 100, 0)}</td>
                            <td className="mono">{row.estimated_accept_probability === undefined ? radarUnavailable(row) : percent(row.estimated_accept_probability * 100, 0)}</td>
                            <td className="mono">{row.post_fill_accept_probability === undefined ? radarUnavailable(row) : percent(row.post_fill_accept_probability * 100, 0)}</td>
                            <td className="mono">{row.execution_calibration_global_fills === undefined || row.execution_calibration_local_fills === undefined ? radarUnavailable(row) : `${row.execution_calibration_global_fills} / ${row.execution_calibration_local_fills}`}</td>
                            <td className="mono">{row.price_volatility_bps === undefined ? radarUnavailable(row) : `${compactNumber(row.price_volatility_bps, 1)} bps`}</td>
                            <td className="mono">{row.proposed_leverage === undefined ? radarUnavailable(row, true) : `${compactNumber(row.proposed_leverage, 0)}×`}</td>
                            <td><span className={`signal-chip signal-${asText(row.signal_status, "watch").toLowerCase()}`}>{asText(row.signal_status, "WATCH")}</span></td>
                            <td><span className={`decision-chip decision-${asText(row.decision, "unknown").toLowerCase().replaceAll("_", "-")}`}>{asText(row.decision)}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </>
                ) : isMakerExecution ? (
                  <table className="radar-table radar-table-v16">
                    <thead><tr><th>Symbol</th><th>Route</th><th>Gross</th><th>Base 60m</th><th>Base 15m</th><th>Capture</th><th>Maker RT</th><th>4-taker RT</th><th>EV</th><th>Min EV</th><th>P(open)</th><th>P long</th><th>P short</th><th>Vol</th><th>Lev</th><th>Signal</th><th>Decision</th></tr></thead>
                    <tbody>
                      {radar.slice(0, 20).map((row, index) => (
                        <tr key={`${row.symbol ?? "radar"}-${index}`}>
                          <td className="mono strong">{asText(row.symbol)}</td>
                          <td>{row.buy_venue && row.sell_venue ? <><span className="route-long">L {row.buy_venue}</span><span className="route-arrow">↔</span><span className="route-short">S {row.sell_venue}</span></> : "—"}</td>
                          <td className="mono">{row.gross_edge_bps === undefined ? "—" : `${compactNumber(row.gross_edge_bps, 2)} bps`}</td>
                          <td className="mono">{row.baseline_60m_bps === undefined ? "—" : `${compactNumber(row.baseline_60m_bps, 2)} bps`}</td>
                          <td className="mono">{row.baseline_15m_bps === undefined ? "—" : `${compactNumber(row.baseline_15m_bps, 2)} bps`}</td>
                          <td className={`mono ${pnlTone(row.capture_bps)}`}>{row.capture_bps === undefined ? "—" : `${compactNumber(row.capture_bps, 2)} bps`}</td>
                          <td className="mono">{row.maker_round_trip_hurdle_bps === undefined ? "—" : `${compactNumber(row.maker_round_trip_hurdle_bps, 2)} bps`}</td>
                          <td className="mono">{row.four_taker_hurdle_bps === undefined ? "—" : `${compactNumber(row.four_taker_hurdle_bps, 2)} bps`}</td>
                          <td className={`mono ${pnlTone(row.expected_value_bps)}`}>{row.expected_value_bps === undefined ? "—" : `${compactNumber(row.expected_value_bps, 2)} bps`}</td>
                          <td className="mono">{row.minimum_required_ev_bps === undefined ? "—" : `${compactNumber(row.minimum_required_ev_bps, 2)} bps`}</td>
                          <td className="mono">{row.p_open === undefined ? "—" : percent(row.p_open * 100, 0)}</td>
                          <td className="mono">{row.long_fill_probability === undefined ? "—" : percent(row.long_fill_probability * 100, 0)}</td>
                          <td className="mono">{row.short_fill_probability === undefined ? "—" : percent(row.short_fill_probability * 100, 0)}</td>
                          <td className="mono">{row.price_volatility_bps === undefined ? "—" : `${compactNumber(row.price_volatility_bps, 1)} bps`}</td>
                          <td className="mono">{row.proposed_leverage === undefined ? "—" : `${compactNumber(row.proposed_leverage, 0)}×`}</td>
                          <td><span className={`signal-chip signal-${asText(row.signal_status, "watch").toLowerCase()}`}>{asText(row.signal_status, "WATCH")}</span></td>
                          <td><span className={`decision-chip decision-${asText(row.decision, "unknown").toLowerCase().replaceAll("_", "-")}`}>{asText(row.decision)}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                <table className={isV16 ? "radar-table radar-table-v16" : "radar-table"}>
                  <thead><tr><th>Symbol</th><th>Venues</th><th>Best route</th><th>Gross edge</th><th>4-leg fees</th><th>{isV16 ? "Raw net" : "Net edge"}</th>{isV16 && <><th>Baseline</th><th>Excess</th><th>Fee hurdle</th><th>After cost</th><th>Z</th><th>5m slope</th><th>Vol</th><th>Lev</th></>}{isV15 && <><th>30m history</th><th>Slope</th><th>Funding</th></>}<th>{isV16 ? "Score" : "C score"}</th><th>Rank</th><th>Signal</th><th>Decision</th></tr></thead>
                  <tbody>
                    {radar.slice(0, 20).map((row, index) => (
                      <tr key={`${row.symbol ?? "radar"}-${index}`}>
                        <td className="mono strong">{asText(row.symbol)}</td>
                        <td>{row.available_venues?.map((venue) => venue.toUpperCase()).join(" · ") || "—"}</td>
                        <td>{row.buy_venue && row.sell_venue ? <><span className="route-long">L {row.buy_venue}</span><span className="route-arrow">↔</span><span className="route-short">S {row.sell_venue}</span></> : "—"}</td>
                        <td className="mono">{row.gross_edge_bps === undefined ? "—" : `${compactNumber(row.gross_edge_bps, 2)} bps`}</td>
                        <td className="mono">{row.total_fee_bps === undefined ? "—" : `${compactNumber(row.total_fee_bps, 2)} bps`}</td>
                        <td className={`mono ${pnlTone(row.best_net_edge_bps)}`}>{row.best_net_edge_bps === undefined ? "—" : `${compactNumber(row.best_net_edge_bps, 2)} bps`}</td>
                        {isV16 && <><td className="mono">{row.baseline_bps === undefined ? "—" : `${compactNumber(row.baseline_bps, 2)} bps`}</td><td className={`mono ${pnlTone(row.excess_spread_bps)}`}>{row.excess_spread_bps === undefined ? "—" : `${compactNumber(row.excess_spread_bps, 2)} bps`}</td><td className="mono">{row.fee_hurdle_bps === undefined ? "—" : `${compactNumber(row.fee_hurdle_bps, 2)} bps`}</td><td className={`mono ${pnlTone(row.excess_after_cost_bps)}`}>{row.excess_after_cost_bps === undefined ? "—" : `${compactNumber(row.excess_after_cost_bps, 2)} bps`}</td><td className="mono">{compactNumber(row.z_score, 2)}</td><td className={`mono ${pnlTone(row.short_slope_bps_per_min)}`}>{row.short_slope_bps_per_min === undefined ? "—" : `${compactNumber(row.short_slope_bps_per_min, 2)} bps/m`}</td><td className="mono">{row.price_volatility_bps === undefined ? "—" : `${compactNumber(row.price_volatility_bps, 1)} bps`}</td><td className="mono">{row.proposed_leverage === undefined ? "—" : `${compactNumber(row.proposed_leverage, 0)}×`}</td></>}
                        {isV15 && <><td className="mono">{row.persistence_seconds === undefined ? "—" : `${compactNumber(row.persistence_seconds / 60, 0)}m · ${row.persistence_sample_count ?? 0}x`}</td><td className={`mono ${pnlTone(row.spread_slope_bps_per_min)}`}>{row.spread_slope_bps_per_min === undefined ? "—" : `${compactNumber(row.spread_slope_bps_per_min, 2)} bps/m`}</td><td className={`mono ${pnlTone(row.funding_edge_bps)}`}>{row.funding_status === "AVAILABLE" && row.funding_edge_bps !== undefined ? `${compactNumber(row.funding_edge_bps, 2)} bps` : row.funding_status ?? "—"}</td></>}
                        <td className="mono">{row.optimizer_score_bps === undefined ? "—" : `${compactNumber(row.optimizer_score_bps, 2)} bps`}</td>
                        <td className="mono">{row.optimizer_rank ?? "—"}</td>
                        <td><span className={`signal-chip signal-${asText(row.signal_status, "rejected").toLowerCase()}`}>{asText(row.signal_status, "REJECTED")}</span>{row.edge_to_trade_bps !== undefined && row.edge_to_trade_bps > 0 ? <small className="edge-gap">{compactNumber(row.edge_to_trade_bps, 2)} bps short</small> : null}</td>
                        <td><span className={`decision-chip decision-${asText(row.decision, "unknown").toLowerCase().replaceAll("_", "-")}`}>{asText(row.decision)}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                )}
              </div>
            )}
          </article>
        </section>
      )}

      {open.length > 0 && (
        <section className="open-positions" aria-label="Live open paper positions">
          <div className="open-section-head">
            <div><span className="section-kicker">LIVE RISK</span><h2>Open paper positions</h2></div>
            <span>Executable close VWAP · public order books · ~2s marks</span>
          </div>
          <div className="open-card-stack">
            {open.map((position) => {
              const net = asNumber(position.estimated_net_pnl_if_closed);
              const gross = asNumber(position.gross_unrealized_pnl);
              const live = position.mark_status === "LIVE";
              const positionId = asText(position.position_id, position.symbol ?? "open");
              const positionHistory = isRouteRelative ? (telemetry?.position_history?.[positionId] ?? []) : [];
              return (
                <article className="panel open-card" key={positionId}>
                  <div className="open-card-head">
                    <div>
                      <div className="position-title-line">
                        <h3>{asText(position.symbol)}</h3>
                        <span className={`mark-chip ${live ? "live" : "unavailable"}`}>{live ? "LIVE MARK" : "MARK UNAVAILABLE"}</span>
                      </div>
                      <p>Opened {duration(asNumber(position.held_seconds))} ago · {isV18 ? "post-fill EV" : isV17 ? "entry expected EV" : isV16 ? "entry excess after costs" : "initial net edge"} {compactNumber(asNumber(position.initial_net_edge_bps), 2)} bps</p>
                    </div>
                    <div className={`open-net ${pnlTone(net)}`}>
                      <span>Est. net if closed now</span>
                      <strong>{live ? money(net, 4) : "—"}</strong>
                    </div>
                  </div>

                  <div className="legs-grid">
                    <div className="leg leg-long">
                      <div className="leg-head"><span>LONG</span><strong>{asText(position.long_exchange).toUpperCase()}</strong></div>
                      <dl>
                        <div><dt>Entry VWAP</dt><dd>{compactNumber(asNumber(position.long_entry_vwap), 4)}</dd></div>
                        <div><dt>Close-now VWAP</dt><dd>{compactNumber(asNumber(position.long_current_vwap), 4)}</dd></div>
                        <div><dt>Leg PnL</dt><dd className={pnlTone(asNumber(position.long_unrealized_pnl))}>{money(asNumber(position.long_unrealized_pnl), 4)}</dd></div>
                        <div><dt>Entry notional</dt><dd>{money(asNumber(position.long_entry_notional), 4)}</dd></div>
                        <div><dt>Fee assumption</dt><dd>{compactNumber(asNumber(position.long_fee_bps), 2)} bps</dd></div>
                      </dl>
                    </div>
                    <div className="leg leg-short">
                      <div className="leg-head"><span>SHORT</span><strong>{asText(position.short_exchange).toUpperCase()}</strong></div>
                      <dl>
                        <div><dt>Entry VWAP</dt><dd>{compactNumber(asNumber(position.short_entry_vwap), 4)}</dd></div>
                        <div><dt>Cover-now VWAP</dt><dd>{compactNumber(asNumber(position.short_current_vwap), 4)}</dd></div>
                        <div><dt>Leg PnL</dt><dd className={pnlTone(asNumber(position.short_unrealized_pnl))}>{money(asNumber(position.short_unrealized_pnl), 4)}</dd></div>
                        <div><dt>Entry notional</dt><dd>{money(asNumber(position.short_entry_notional), 4)}</dd></div>
                        <div><dt>Fee assumption</dt><dd>{compactNumber(asNumber(position.short_fee_bps), 2)} bps</dd></div>
                      </dl>
                    </div>
                  </div>

                  <div className="position-summary">
                    <div><span>Gross unrealized</span><strong className={pnlTone(gross)}>{live ? money(gross, 4) : "—"}</strong></div>
                    <div><span>Current spread</span><strong>{live ? `${compactNumber(asNumber(position.current_spread_bps), 2)} bps` : "—"}</strong></div>
                    <div><span>Entry + est. exit fees</span><strong>{money((asNumber(position.entry_fees) ?? 0) + (asNumber(position.estimated_exit_fees) ?? 0), 4)}</strong></div>
                    <div><span>Gross exposure</span><strong>{money(asNumber(position.entry_gross_exposure), 4)}</strong></div>
                    <div><span>Exposure / equity</span><strong>{percent(asNumber(position.exposure_pct_of_equity), 1)}</strong></div>
                    <div className="margin-summary"><span>Margin / leverage</span><strong>{position.margin_model === "CROSS_MARGIN_PAPER_V1" || position.margin_model === "ISOLATED_PAPER_V1" ? `${money(asNumber(position.initial_margin), 4)} @ ${compactNumber(asNumber(position.leverage), 1)}×` : "Not modeled in V13"}</strong></div>
                  </div>
                  {isRouteRelative && (
                    <>
                      <div className="v16-route-stats">
                        {isMakerExecution ? <>
                          <div><span>Entry execution</span><strong>{asText(position.entry_execution_mode)}</strong></div>
                          <div><span>Leg liquidity</span><strong>{asText(position.long_entry_liquidity)} / {asText(position.short_entry_liquidity)}</strong></div>
                          <div><span>Expected EV</span><strong className={pnlTone(position.entry_expected_value_bps)}>{compactNumber(position.entry_expected_value_bps, 2)} bps</strong></div>
                          <div><span>Min EV</span><strong>{compactNumber(position.entry_minimum_ev_bps, 2)} bps</strong></div>
                          <div><span>Capture</span><strong>{compactNumber(position.entry_capture_bps, 2)} bps</strong></div>
                          <div><span>P(open) at entry</span><strong>{position.entry_fill_probability === undefined ? "—" : percent(position.entry_fill_probability * 100, 1)}</strong></div>
                          <div><span>60m / 15m baseline</span><strong>{compactNumber(position.entry_baseline_bps, 2)} / {compactNumber(position.entry_baseline_15m_bps, 2)} bps</strong></div>
                          <div><span>Route volatility</span><strong>{compactNumber(position.entry_price_volatility_bps, 1)} bps</strong></div>
                          {isV18 && <><div><span>Post-fill decision</span><strong>{asText(position.post_fill_decision)}</strong></div><div><span>Actual capture</span><strong>{compactNumber(position.actual_capture_bps, 2)} bps</strong></div><div><span>Hedge latency</span><strong>{compactNumber(position.entry_hedge_delay_ms, 0)} ms</strong></div></>}
                        </> : <>
                          <div><span>Route baseline</span><strong>{compactNumber(position.entry_baseline_bps, 2)} bps</strong></div>
                          <div><span>Entry excess</span><strong>{compactNumber(position.entry_excess_spread_bps, 2)} bps</strong></div>
                          <div><span>Fee hurdle</span><strong>{compactNumber(position.entry_fee_hurdle_bps, 2)} bps</strong></div>
                          <div><span>Z-score</span><strong>{compactNumber(position.entry_z_score, 2)}</strong></div>
                          <div><span>5m slope at entry</span><strong>{compactNumber(position.entry_short_slope_bps_per_min, 2)} bps/m</strong></div>
                          <div><span>Route volatility</span><strong>{compactNumber(position.entry_price_volatility_bps, 1)} bps</strong></div>
                        </>}
                      </div>
                      <div className="position-history-grid">
                        <div className="position-history-card"><div><span>Estimated exit-net history</span><strong className={pnlTone(positionHistory.at(-1)?.net_pnl)}>{money(positionHistory.at(-1)?.net_pnl, 4)}</strong></div><MiniSeriesChart values={positionHistory.map((point) => point.net_pnl)} label={`${asText(position.symbol)} estimated exit-net history`} /></div>
                        <div className="position-history-card"><div><span>Spread history</span><strong>{positionHistory.length ? `${compactNumber(positionHistory.at(-1)?.spread_bps, 2)} bps` : "—"}</strong></div><MiniSeriesChart values={positionHistory.map((point) => point.spread_bps)} label={`${asText(position.symbol)} spread history`} /></div>
                      </div>
                    </>
                  )}
                  <div className="model-note">{isV18 ? `${websocketVersion} streams bounded public books, recognizes fills only from post-placement snapshots, and revalidates EV before opening a hedged position. Exit-now marks are executable taker estimates, not forecasts.` : isV17 ? "V17 enters with causal maker-first execution: passive fills are recognized only on later public-book touch/trade-through; missing legs are taker-hedged. Close-now marks remain executable taker estimates, not forecasts." : isV16 ? "V16 trades the dislocation relative to this exact route’s causal baseline, not raw spread-to-zero. Position leverage is chosen dynamically from route-relative edge and volatility; exact liquidation remains unavailable." : position.margin_model === "CROSS_MARGIN_PAPER_V1" ? "V14-C shares collateral across positions on the same venue. The displayed position IM is its contribution to venue cross margin; exact venue liquidation remains unavailable." : position.margin_model === "ISOLATED_PAPER_V1" ? "V14-B reserves isolated initial margin per leg." : "V13 sizes by paper notional, but does not simulate leverage, margin or liquidation."}</div>
                </article>
              );
            })}
          </div>
        </section>
      )}

      <section className="panel scenario-panel" aria-label="Capital and leverage what-if simulator">
        <div className="scenario-head">
          <div>
            <span className="section-kicker">WHAT-IF ORDERS · READ ONLY</span>
            <h2>$20 / $50 / $100 × leverage</h2>
            <p>Re-size the current executable paper positions. Changing these controls never changes the actual runner.</p>
          </div>
          <div className="scenario-control-grid">
            <fieldset>
              <legend>Total capital</legend>
              <div className="scenario-buttons">
                {[20, 50, 100].map((capital) => (
                  <button key={capital} type="button" className={scenarioCapital === capital ? "active" : ""} aria-pressed={scenarioCapital === capital} onClick={() => setScenarioCapital(capital)}>${capital}</button>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend>Hypothetical leverage</legend>
              <div className="scenario-buttons">
                {[1, 2, 3, 5].map((leverage) => (
                  <button key={leverage} type="button" className={scenarioLeverage === leverage ? "active" : ""} aria-pressed={scenarioLeverage === leverage} onClick={() => setScenarioLeverage(leverage)}>{leverage}×</button>
                ))}
              </div>
            </fieldset>
          </div>
        </div>
        {capacity && (
          <div className="scenario-metrics">
            <div><span>Gross capacity</span><strong>{money(capacity.gross_capacity, 2)}</strong><small>{scenarioLeverage}× selected capital</small></div>
            <div><span>Gross / equal slot</span><strong>{money(capacity.pair_gross_capacity, 2)}</strong><small>{capacity.max_positions} slots</small></div>
            <div><span>Notional / leg</span><strong>{money(capacity.leg_notional_capacity, 2)}</strong><small>flat-book fallback</small></div>
            <div><span>Initial margin / slot</span><strong>{money(capacity.pair_initial_margin_capacity, 2)}</strong><small>gross ÷ leverage</small></div>
            <div><span>Projected open gross</span><strong>{scenario ? money(scenario.gross_exposure, 2) : "—"}</strong><small>{scenarioPositionRows.length ? `${scenarioPositionRows.length} marked positions` : "no LIVE open mark"}</small></div>
            <div className={scenario ? pnlTone(scenario.estimated_net_pnl_if_closed) : ""}><span>Projected close-now PnL</span><strong>{scenario ? money(scenario.estimated_net_pnl_if_closed, 4) : "—"}</strong><small>{scenario ? `${percent(scenarioPnlPct, 2)} on $${scenarioCapital}` : "requires LIVE open marks"}</small></div>
          </div>
        )}

        <div className="scenario-orders">
          <div className="scenario-orders-head"><strong>Scenario orders</strong><span>${scenarioCapital} · {scenarioLeverage}× · hypothetical only</span></div>
          {scenarioPositionRows.length > 0 ? (
            <div className="table-scroll">
              <table className="scenario-order-table">
                <thead><tr><th>Source</th><th>Symbol</th><th>Route</th><th>LONG notional</th><th>SHORT notional</th><th>Gross</th><th>Initial margin</th><th>Estimated net if exited now</th><th>PnL / capital</th></tr></thead>
                <tbody>{scenarioPositionRows.map(({ position, projection }) => (
                  <tr key={`scenario-${asText(position.position_id, position.symbol ?? "open")}`}>
                    <td><span className="scenario-source live">LIVE MARK</span></td>
                    <td className="mono strong">{asText(position.symbol)}</td>
                    <td><span className="route-long">L {asText(position.long_exchange)}</span><span className="route-arrow">↔</span><span className="route-short">S {asText(position.short_exchange)}</span></td>
                    <td className="mono">{money(projection.long_notional, 4)}</td>
                    <td className="mono">{money(projection.short_notional, 4)}</td>
                    <td className="mono">{money(projection.gross_exposure, 4)}</td>
                    <td className="mono">{money(projection.initial_margin, 4)} @ {scenarioLeverage}×</td>
                    <td className={`mono ${pnlTone(projection.estimated_net_pnl_if_closed)}`}>{money(projection.estimated_net_pnl_if_closed, 4)}</td>
                    <td className={`mono ${pnlTone(projection.pnl_pct_of_capital)}`}>{percent(projection.pnl_pct_of_capital, 3)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          ) : scenarioOpportunityRows.length > 0 ? (
            <div className="table-scroll">
              <table className="scenario-order-table">
                <thead><tr><th>Source</th><th>Symbol</th><th>Route</th><th>LONG notional</th><th>SHORT notional</th><th>Gross</th><th>Initial margin</th><th>Current net edge</th></tr></thead>
                <tbody>{scenarioOpportunityRows.map((row) => (
                  <tr key={`scenario-opportunity-${row.symbol}`}>
                    <td><span className="scenario-source hypothetical">TRADEABLE NOW</span></td>
                    <td className="mono strong">{row.symbol}</td>
                    <td><span className="route-long">L {row.long_exchange}</span><span className="route-arrow">↔</span><span className="route-short">S {row.short_exchange}</span></td>
                    <td className="mono">{money(row.long_notional, 4)}</td>
                    <td className="mono">{money(row.short_notional, 4)}</td>
                    <td className="mono">{money(row.gross_exposure, 4)}</td>
                    <td className="mono">{money(row.initial_margin, 4)} @ {row.leverage}×</td>
                    <td className="mono positive">{compactNumber(row.best_net_edge_bps, 2)} bps</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          ) : (
            <div className="scenario-unavailable">No LIVE open mark or currently TRADEABLE radar row. Capacity changes above are still valid, but no order/PnL row is fabricated.</div>
          )}
        </div>
        <p className="scenario-note">Open-position PnL is a linearized what-if from the latest executable close mark and the selected capital/leverage. It is not a forecast. When flat, TRADEABLE rows show hypothetical sizing only; no future PnL is invented.</p>
      </section>

      <section className="content-grid">
        <article className="panel chart-panel">
          <div className="panel-head">
            <div><span className="section-kicker">{isRouteRelative ? "EXECUTABLE ACCOUNT" : "REALIZED ACCOUNT"}</span><h2>{isRouteRelative ? "Marked equity timeline" : "Equity curve"}</h2></div>
            <div className={`delta ${pnlTone(isRouteRelative ? (accountLast?.marked_equity ?? telemetry?.equity ?? 0) - (telemetry?.initial_equity ?? 0) : pnl)}`}>{telemetry ? (isRouteRelative ? money((accountLast?.marked_equity ?? telemetry.equity) - telemetry.initial_equity, 4) : percent(telemetry.return_pct, 3)) : "—"}</div>
          </div>
          <EquityChart points={series} />
        </article>

        <aside className="panel effectiveness">
          <div className="panel-head"><div><span className="section-kicker">QUALITY OF EDGE</span><h2>Effectiveness</h2></div></div>
          {!enoughEvidence && (
            <div className="evidence-note"><span>LOW SAMPLE</span> Not enough closed trades for stable effectiveness estimates.</div>
          )}
          <dl className="metric-list">
            <div><dt>Profit factor</dt><dd>{compactNumber(metrics?.profit_factor)}</dd></div>
            <div><dt>Avg win</dt><dd className="positive-text">{money(metrics?.avg_win)}</dd></div>
            <div><dt>Avg loss</dt><dd className="negative-text">{money(metrics?.avg_loss)}</dd></div>
            <div><dt>Fee drag</dt><dd>{money(metrics?.fee_drag)}</dd></div>
            <div><dt>Avg hold</dt><dd>{duration(metrics?.avg_holding_seconds)}</dd></div>
            <div><dt>Scans</dt><dd>{telemetry?.scan_count?.toLocaleString() ?? "—"}</dd></div>
          </dl>
          <div className="boundary-note"><strong>Paper only.</strong> No live money, order placement, or private exchange credentials are connected to this dashboard.</div>
        </aside>
      </section>

      <section className="panel positions-panel">
        <div className="panel-head positions-head">
          <div><span className="section-kicker">EXECUTION LEDGER</span><h2>Recent positions</h2></div>
          <span className="ledger-meta">OPEN = estimated close-now · CLOSED = realized</span>
        </div>
        {recentRows.length === 0 ? (
          <div className="table-empty"><strong>No paper positions yet.</strong><span>The scanner is running; a trade appears only when net edge clears costs and safety filters.</span></div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>Status</th><th>Symbol</th><th>Route</th><th>Qty</th><th>Entry</th><th>Exit</th><th>Fees</th><th>Hold</th><th>Reason</th><th>Net PnL</th></tr></thead>
              <tbody>
                {recentRows.map((row, index) => {
                  const net = row.row_status === "OPEN"
                    ? asNumber(row.estimated_net_pnl_if_closed)
                    : asNumber(row.realized_net_pnl);
                  return (
                    <tr key={`${asText(row.position_id, "row")}-${index}`}>
                      <td><span className={`row-status ${row.row_status === "OPEN" ? "open" : "closed"}`}>{row.row_status}</span></td>
                      <td className="mono strong">{asText(row.symbol)}</td>
                      <td><span className="route-long">L {asText(row.long_exchange)}</span><span className="route-arrow">↔</span><span className="route-short">S {asText(row.short_exchange)}</span></td>
                      <td className="mono">{compactNumber(asNumber(row.quantity), 6)}</td>
                      <td className="mono two-line"><span>{compactNumber(asNumber(row.long_entry_vwap), 4)}</span><span>{compactNumber(asNumber(row.short_entry_vwap), 4)}</span></td>
                      <td className="mono two-line"><span>{compactNumber(asNumber(row.long_exit_vwap ?? row.long_current_vwap), 4)}</span><span>{compactNumber(asNumber(row.short_exit_vwap ?? row.short_current_vwap), 4)}</span></td>
                      <td className="mono">{money(
                        (asNumber(row.entry_fees) ?? 0) +
                        (asNumber(row.row_status === "OPEN" ? row.estimated_exit_fees : row.exit_fees) ?? 0),
                        4,
                      )}</td>
                      <td>{duration(asNumber(row.held_seconds))}</td>
                      <td>{asText(row.close_reason, row.row_status === "OPEN" ? "Active" : "—")}</td>
                      <td className={`mono ${pnlTone(net)}`}>
                        <span className="pnl-kind">{row.row_status === "OPEN" ? "EST" : "REAL"}</span>
                        {net === null ? "—" : money(net, 4)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <footer>
        <span>{isV21 ? "V21 cohort-calibrated cross-exchange paper research" : isV20 ? "V20 execution-aware cross-exchange paper research" : isV19 ? "V19 causal execution cross-exchange paper research" : displaySchemaVersion === "v18-monitoring-1" ? "V18 post-fill EV cross-exchange paper research" : isV17 ? "V17 maker-first EV cross-exchange paper research" : isV16 ? "V16 route-relative cross-exchange paper research" : isV15 ? "V15 control + shadow cross-exchange paper research" : "V21 cohort-calibrated cross-exchange paper research"}</span>
        <span className="footer-dot">•</span>
        <span>Accounting changes only on simulated CLOSE</span>
        <span className="footer-spacer" />
        <span>Auto-refresh 2s</span>
      </footer>
    </main>
  );
}
