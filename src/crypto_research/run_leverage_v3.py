from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_research.leverage_v3 import simulate_weight_schedule

ANNUAL_12H = 365.0 * 2.0


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0 or not math.isfinite(denominator):
        return None
    return float(numerator / denominator)


def summarize_account_result(result: dict[str, object]) -> dict[str, object]:
    path = result["account_path"]
    if not isinstance(path, pd.DataFrame) or path.empty:
        period_returns = pd.Series(dtype=float)
        daily_returns = pd.Series(dtype=float)
        weekly_returns = pd.Series(dtype=float)
        max_drawdown = 1.0 if result.get("liquidated") else 0.0
    else:
        work = path[["timestamp", "equity"]].copy()
        work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
        equity = work.drop_duplicates("timestamp", keep="last").set_index("timestamp")["equity"].astype(float).sort_index()
        origin = equity.index[0]
        period_equity = equity.resample("12h", origin=origin).last().dropna()
        period_returns = period_equity.pct_change(fill_method=None).dropna()
        daily_returns = equity.resample("24h", origin=origin).last().dropna().pct_change(fill_method=None).dropna()
        weekly_returns = equity.resample("168h", origin=origin).last().dropna().pct_change(fill_method=None).dropna()
        running_max = equity.cummax().replace(0.0, np.nan)
        max_drawdown = float((1.0 - equity / running_max).max()) if len(equity) else 0.0
        if result.get("liquidated"):
            max_drawdown = max(max_drawdown, 1.0 - float(result["final_equity"]) / float(result["initial_equity"]))

    mean = float(period_returns.mean()) if len(period_returns) else 0.0
    std = float(period_returns.std(ddof=1)) if len(period_returns) > 1 else 0.0
    downside = period_returns[period_returns < 0]
    downside_std = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    positive = float(period_returns[period_returns > 0].sum())
    negative = float(-period_returns[period_returns < 0].sum())
    var_95 = float(period_returns.quantile(0.05)) if len(period_returns) else 0.0
    tail = period_returns[period_returns <= var_95]
    cvar_95 = float(tail.mean()) if len(tail) else var_95
    final_equity = float(result["final_equity"])
    initial_equity = float(result["initial_equity"])
    n_periods = max(len(period_returns), 1)
    annualized_return = -1.0 if final_equity <= 0 else float((final_equity / initial_equity) ** (ANNUAL_12H / n_periods) - 1.0)
    annualized_volatility = std * math.sqrt(ANNUAL_12H)
    sharpe = mean / std * math.sqrt(ANNUAL_12H) if std > 0 else 0.0
    sortino = mean / downside_std * math.sqrt(ANNUAL_12H) if downside_std > 0 else 0.0
    return {
        "net_return": float(result["net_return"]),
        "annualized_return": annualized_return,
        "volatility": annualized_volatility,
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": float(max_drawdown),
        "calmar": _safe_ratio(annualized_return, max_drawdown),
        "profit_factor": _safe_ratio(positive, negative),
        "win_rate": float((period_returns > 0).mean()) if len(period_returns) else 0.0,
        "expectancy": mean,
        "period_count": int(len(period_returns)),
        "turnover_notional_over_initial_equity": float(result["turnover_notional"]) / initial_equity,
        "funding_return": float(result["funding_cashflow"]) / initial_equity,
        "transaction_cost": (float(result["execution_cost"]) + float(result["slippage_cost"])) / initial_equity,
        "execution_cost": float(result["execution_cost"]) / initial_equity,
        "slippage_cost": float(result["slippage_cost"]) / initial_equity,
        "liquidation_count": int(result["liquidation_count"]),
        "liquidated": bool(result["liquidated"]),
        "liquidation_timestamp": result.get("liquidation_timestamp"),
        "minimum_margin_ratio": float(result["minimum_margin_ratio"]),
        "max_effective_leverage": float(result["max_effective_leverage"]),
        "margin_infeasible": bool(result["margin_infeasible"]),
        "worst_trade": float(period_returns.min()) if len(period_returns) else 0.0,
        "worst_day": float(daily_returns.min()) if len(daily_returns) else 0.0,
        "worst_week": float(weekly_returns.min()) if len(weekly_returns) else 0.0,
        "var_95": var_95,
        "cvar_95": cvar_95,
    }


def load_market(periods: pd.DataFrame, *, root: Path) -> pd.DataFrame:
    symbols: set[str] = set()
    for text in periods["weights_json"]:
        symbols.update(json.loads(text))
    start = pd.to_datetime(periods["entry_timestamp"], utc=True).min()
    end = pd.to_datetime(periods["exit_timestamp"], utc=True).max()
    raw = pd.read_csv(
        root / "data/binance_futures_v2/raw_1h.csv.gz",
        usecols=["timestamp", "symbol", "open", "high", "low", "close"],
    )
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
    raw = raw.loc[raw["symbol"].isin(symbols) & raw["timestamp"].between(start, end)].copy()
    panel = pd.read_pickle(root / "data/binance_futures_v2/panel_core.pkl")
    funding = panel.loc[
        panel["symbol"].isin(symbols) & pd.to_datetime(panel["timestamp"], utc=True).between(start, end),
        ["timestamp", "symbol", "funding_event_rate"],
    ].copy()
    funding["timestamp"] = pd.to_datetime(funding["timestamp"], utc=True)
    return raw.merge(funding, on=["timestamp", "symbol"], how="left", validate="one_to_one").fillna({"funding_event_rate": 0.0})


def run_grid(
    periods: pd.DataFrame,
    market: pd.DataFrame,
    *,
    leverages=(1, 2, 3, 5, 10, 20),
    maintenance_margin_rate: float = 0.01,
    round_trip_cost_bps: float = 10.0,
    slippage_bps: float = 0.0,
    funding_multiplier: float = 1.0,
) -> dict[str, object]:
    work = market.copy()
    work["funding_event_rate"] = work["funding_event_rate"].astype(float) * float(funding_multiplier)
    output = {}
    for leverage in leverages:
        result = simulate_weight_schedule(
            periods=periods,
            market=work,
            initial_equity=1.0,
            leverage_multiplier=float(leverage),
            exchange_leverage_setting=20.0,
            maintenance_margin_rate=maintenance_margin_rate,
            round_trip_cost_bps=round_trip_cost_bps,
            slippage_bps=slippage_bps,
            liquidation_fee_rate=0.005,
        )
        summary = summarize_account_result(result)
        summary["leverage_multiplier"] = leverage
        summary["maintenance_margin_rate"] = maintenance_margin_rate
        summary["round_trip_cost_bps"] = round_trip_cost_bps
        summary["slippage_bps_one_way"] = slippage_bps
        summary["funding_multiplier"] = funding_multiplier
        output[str(leverage)] = summary
    return output


def shock_grid(periods: pd.DataFrame, *, leverages=(1, 2, 3, 5, 10, 20), maintenance_margin_rate=0.01) -> dict[str, object]:
    gross = periods["gross_exposure"].astype(float)
    output = {}
    for shock in (0.05, 0.10, 0.15):
        rows = {}
        for leverage in leverages:
            effective = gross * float(leverage)
            equity_factor = 1.0 - effective * shock
            maintenance = effective * (1.0 + shock) * maintenance_margin_rate
            margin_ratio = equity_factor / maintenance.replace(0.0, np.nan)
            rows[str(leverage)] = {
                "shock": shock,
                "minimum_equity_factor": float(equity_factor.min()),
                "minimum_margin_ratio": float(margin_ratio.min()),
                "liquidation_condition_count": int((equity_factor <= maintenance).sum()),
                "risk_of_ruin_count": int((equity_factor <= 0.0).sum()),
            }
        output[str(shock)] = rows
    return output


def main() -> None:
    root = Path(".")
    out = root / "artifacts/multi_asset_v3"
    periods = pd.read_csv(out / "cost_aware_periods.csv.gz")
    market = load_market(periods, root=root)
    base = run_grid(periods, market)
    payload = {
        "price_source": "Binance USD-M contract 1h OHLC proxy; intrabar low for longs/high for shorts used conservatively for liquidation because historical mark-price archive was not available in the local cache",
        "maintenance_margin_assumption": "fixed 1% base; historical per-contract leverage brackets are not reconstructed",
        "exchange_leverage_setting": 20.0,
        "base": base,
    }
    (out / "leverage_1x_20x_results.json").write_text(json.dumps(payload, indent=2, default=str))
    stress = {
        "cost_x1_5": run_grid(periods, market, round_trip_cost_bps=15.0),
        "cost_x2": run_grid(periods, market, round_trip_cost_bps=20.0),
        "slippage_2_5bps_one_way": run_grid(periods, market, slippage_bps=2.5),
        "slippage_5bps_one_way": run_grid(periods, market, slippage_bps=5.0),
        "maintenance_2pct": run_grid(periods, market, maintenance_margin_rate=0.02),
        "maintenance_5pct": run_grid(periods, market, maintenance_margin_rate=0.05),
        "funding_x2": run_grid(periods, market, funding_multiplier=2.0),
        "funding_x3": run_grid(periods, market, funding_multiplier=3.0),
        "instant_adverse_correlation_one": shock_grid(periods),
    }
    (out / "liquidation_stress_results.json").write_text(json.dumps(stress, indent=2, default=str))
    print(json.dumps(base, default=str))


if __name__ == "__main__":
    main()
