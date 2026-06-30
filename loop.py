"""
Steps 2-4 of the loop: DISPATCH (optimise) -> SETTLE (imbalance) -> PnL.

The LP follows primer §6 (battery dispatch, why LP not MIP is the right first
cut). Settlement, imbalance accounting and the A/B/C decomposition follow
primer §7. The convention is energy-first: every cost is price [£/MWh] ×
energy [MWh per SP], so settle/energy_cost take MWh series directly. The one
exception is dispatch_lp, which keeps its decision variables as SP-averaged
powers in kW per primer §6.1 — the boundary conversion happens once per LP
call, via _kw_to_mwh, on the way into settle.

Scope: this layer is the SHORT-HORIZON end of primer §8's loop. Two layers are
deliberately out of scope and noted on the roadmap:
  * Long-horizon procurement / hedging (primer §5) — forward stack, PPAs,
    newsvendor sizing. Not implemented.
  * Non-commodity charges (primer §2.5) — TNUoS, DUoS Red bands, BSUoS, CM,
    levies. The price series here is wholesale + cash-out only.

DISPATCH: given the forecast net position and a battery, decide charge/discharge
per half-hour to minimise expected energy cost.

SETTLE: you trade day-ahead to your FORECAST net. Reality differs. The residual
(actual - forecast, after battery) settles at the IMBALANCE price. Better forecast
-> smaller residual -> smaller imbalance cost. That is the whole commercial point.

We compare three strategies (primer §7.2) to make the loop legible:
  A. perfect-foresight + battery   (theoretical floor on cost)
  B. forecast + battery            (what you'd actually run)
  C. forecast, no battery          (isolates the battery's value)
Naming gotcha: these are DISPATCH-LAYER strategies, distinct from the three
DECISION LAYERS of the README (procurement / PPA / dispatch).
"""
from __future__ import annotations
import pandas as pd
import pulp


def _kw_to_mwh(s: pd.Series, hours: float = 0.5) -> pd.Series:
    """SP-averaged power [kW] -> per-SP energy [MWh]. Δt defaults to 0.5h (GB SP).
    This is the single dimension-conversion helper in the loop — used exactly
    once per dispatch pass, at the LP -> settle boundary."""
    return s * hours / 1000.0


def dispatch_lp(net_kw: pd.Series, price: pd.Series,
                cap_kwh=500.0, rate_kw=250.0, eff=0.92, soc0_frac=0.5):
    """LP battery dispatch against a (forecast or actual) net position.

    The LP is the primer's §6.1 power-form formulation: decision variables are
    SP-averaged powers [kW] because battery rate limits and SoC capacity are
    physical specs of the asset, not energies per SP. ``net_kw`` is therefore
    expected as SP-averaged power [kW]; callers holding the energy form (MWh
    per SP) should multiply by 1000 / Δt_h before passing it in.

    Returns per-period grid draw and battery actions in kW, plus ``grid_mwh``
    — the per-SP grid energy that the settlement layer consumes."""
    T = len(net_kw)
    prob = pulp.LpProblem("dispatch", pulp.LpMinimize)
    c = [pulp.LpVariable(f"c{t}", 0, rate_kw) for t in range(T)]   # charge kW
    d = [pulp.LpVariable(f"d{t}", 0, rate_kw) for t in range(T)]   # discharge kW
    soc = [pulp.LpVariable(f"s{t}", 0, cap_kwh) for t in range(T)]
    grid = [pulp.LpVariable(f"g{t}") for t in range(T)]            # can be +/-
    pr = price.values
    net = net_kw.values
    # objective: cost of grid energy (the §6.1 Δt/1000 factor takes the kW
    # decision variable to MWh per SP so price [£/MWh] × energy [MWh] = £).
    prob += pulp.lpSum(pr[t] * grid[t] * 0.5 / 1000.0 for t in range(T))
    for t in range(T):
        prob += grid[t] == net[t] + c[t] - d[t]
        prev = soc0_frac * cap_kwh if t == 0 else soc[t - 1]
        prob += soc[t] == prev + (eff * c[t] - d[t] / eff) * 0.5   # 0.5h step
    # terminal SoC >= initial: stops the LP draining the (free) starting charge
    # by the horizon end, which would bias costs down and inflate battery value.
    prob += soc[T - 1] >= soc0_frac * cap_kwh
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    grid_kw = pd.Series([grid[t].value() for t in range(T)], index=net_kw.index)
    return pd.DataFrame({
        "net_kw": net,
        "charge_kw": [c[t].value() for t in range(T)],
        "discharge_kw": [d[t].value() for t in range(T)],
        "grid_kw": grid_kw,
        "grid_mwh": _kw_to_mwh(grid_kw),
        "soc_kwh": [soc[t].value() for t in range(T)],
    }, index=net_kw.index)


def energy_cost(energy_mwh: pd.Series, price: pd.Series) -> float:
    """Σ price [£/MWh] · energy [MWh] = £. Pure dot product, no unit conversion."""
    return float((energy_mwh * price).sum())


def settle(forecast_grid_mwh, actual_net_mwh, day_ahead, imbalance,
           charge_mwh=None, discharge_mwh=None):
    """Trade day-ahead to the FORECAST grid energy; settle the residual at
    imbalance price (primer §7.1).

    All energy inputs are MWh per SP. If ``charge_mwh``/``discharge_mwh`` are
    given, the actual grid energy applies the same (pre-committed) battery
    schedule to the ACTUAL net; otherwise actual_grid == actual_net (no battery).
    """
    if charge_mwh is not None:
        actual_grid_mwh = actual_net_mwh + charge_mwh - discharge_mwh
    else:
        actual_grid_mwh = actual_net_mwh
    da_cost = energy_cost(forecast_grid_mwh, day_ahead)            # bought ahead
    residual = actual_grid_mwh - forecast_grid_mwh                 # MWh per SP
    imb_cost = energy_cost(residual, imbalance)                    # settled at cashout
    return {"day_ahead_cost": da_cost, "imbalance_cost": imb_cost,
            "total_cost": da_cost + imb_cost,
            "abs_imbalance_mwh": float(residual.abs().sum())}


def run_loop(seed=0):
    import data, forecast
    p = data.build_portfolio(n_sites=5, days=21, seed=seed)
    net_mwh = forecast.portfolio_net_mwh(p)
    ctx = forecast.ctx_from_portfolio(p)
    fc, metrics = forecast.train_forecast(net_mwh, ctx=ctx, test_days=3)
    price = p["price"].reindex(fc.index)
    da, imb = price["day_ahead"], price["imbalance"]

    # fc carries MWh per SP; dispatch_lp wants SP-averaged power [kW] (§6.1)
    KW_PER_MWH_PER_SP = 1000.0 / 0.5
    actual_kw = fc["actual"] * KW_PER_MWH_PER_SP
    fcast_kw = fc["point"]  * KW_PER_MWH_PER_SP

    # B: forecast + battery -> commit battery schedule on the forecast
    disp_fc = dispatch_lp(fcast_kw, da)
    sB = settle(disp_fc["grid_mwh"], fc["actual"], da, imb,
                charge_mwh=_kw_to_mwh(disp_fc["charge_kw"]),
                discharge_mwh=_kw_to_mwh(disp_fc["discharge_kw"]))

    # C: forecast, no battery (forecast grid energy == forecast net energy)
    sC = settle(fc["point"], fc["actual"], da, imb)

    # A: perfect foresight + battery (cost floor; trade to actual, no imbalance)
    disp_pf = dispatch_lp(actual_kw, da)
    sA = {"total_cost": energy_cost(disp_pf["grid_mwh"], da),
          "imbalance_cost": 0.0, "abs_imbalance_mwh": 0.0}

    return metrics, {"A_perfect_battery": sA, "B_forecast_battery": sB,
                     "C_forecast_nobattery": sC}, fc, disp_fc


if __name__ == "__main__":
    m, scen, fc, disp = run_loop()
    print("=== Forecast quality ===")
    print(f"  MAE model {m['MAE_model_mwh']:.4f} MWh/SP vs naive "
          f"{m['MAE_naive_mwh']:.4f} MWh/SP "
          f"({m['improvement_vs_naive_%']}% better)\n")
    print("=== Loop economics over 3-day test window (GBP) ===")
    for name, s in scen.items():
        extra = (f"  imbalance={s['imbalance_cost']:8.2f}"
                 f"  |resid|={s.get('abs_imbalance_mwh', 0):7.3f} MWh")
        print(f"  {name:24s} total={s['total_cost']:9.2f}{extra}")
    b, c = scen["B_forecast_battery"], scen["C_forecast_nobattery"]
    print(f"\n  Battery saves: {c['total_cost']-b['total_cost']:.2f} GBP over 3 days")
    print(f"  Gap to perfect foresight: "
          f"{b['total_cost']-scen['A_perfect_battery']['total_cost']:.2f} GBP "
          f"(this is what better forecasting could still recover)")
