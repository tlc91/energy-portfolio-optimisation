"""
Steps 2-4 of the loop: DISPATCH (optimise) -> SETTLE (imbalance) -> PnL.

DISPATCH: given the forecast net position and a battery, decide charge/discharge
per half-hour to minimise expected energy cost. This is the LP from the primer:
  minimise  sum_t price_t * grid_t
  s.t.      SoC balance, capacity limits, rate limits, grid = net + charge - discharge
We solve it as a pure LP (continuous). A no-simultaneous-charge/discharge binary
would make it a MIP; the LP relaxation almost never charges & discharges at once
when prices are positive, so LP is the right pragmatic first cut.

SETTLE: you trade day-ahead to your FORECAST net. Reality differs. The residual
(actual - forecast, after battery) settles at the IMBALANCE price. Better forecast
-> smaller residual -> smaller imbalance cost. That is the whole commercial point.

We compare three strategies to make the loop legible:
  A. perfect-foresight + battery   (theoretical floor on cost)
  B. forecast + battery            (what you'd actually run)
  C. forecast, no battery          (isolates the battery's value)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import pulp

MWH = 1000.0  # kW -> MW conversion for pricing (price is GBP/MWh, 0.5h periods)

def dispatch_lp(net_kw: pd.Series, price: pd.Series,
                cap_kwh=500.0, rate_kw=250.0, eff=0.92, soc0_frac=0.5):
    """LP battery dispatch against a (forecast or actual) net position.
    Returns per-period grid draw and battery actions (kW). Positive grid = import."""
    T = len(net_kw)
    prob = pulp.LpProblem("dispatch", pulp.LpMinimize)
    c = [pulp.LpVariable(f"c{t}", 0, rate_kw) for t in range(T)]   # charge kW
    d = [pulp.LpVariable(f"d{t}", 0, rate_kw) for t in range(T)]   # discharge kW
    soc = [pulp.LpVariable(f"s{t}", 0, cap_kwh) for t in range(T)]
    grid = [pulp.LpVariable(f"g{t}") for t in range(T)]            # can be +/-
    pr = price.values
    net = net_kw.values
    # objective: cost of grid energy (0.5h => kW*0.5/1000 MWh)
    prob += pulp.lpSum(pr[t] * grid[t] * 0.5 / MWH for t in range(T))
    for t in range(T):
        prob += grid[t] == net[t] + c[t] - d[t]
        prev = soc0_frac * cap_kwh if t == 0 else soc[t - 1]
        prob += soc[t] == prev + (eff * c[t] - d[t] / eff) * 0.5   # 0.5h step
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    res = pd.DataFrame({
        "net_kw": net,
        "charge_kw": [c[t].value() for t in range(T)],
        "discharge_kw": [d[t].value() for t in range(T)],
        "grid_kw": [grid[t].value() for t in range(T)],
        "soc_kwh": [soc[t].value() for t in range(T)],
    }, index=net_kw.index)
    return res

def energy_cost(grid_kw: pd.Series, price: pd.Series) -> float:
    return float((grid_kw * price * 0.5 / MWH).sum())

def settle(forecast_grid_kw, actual_net_kw, day_ahead, imbalance,
           battery_actions=None):
    """Trade day-ahead to the FORECAST grid position; settle the residual at
    imbalance price. If battery_actions given, the actual grid uses the same
    (pre-committed) battery schedule applied to the ACTUAL net."""
    if battery_actions is not None:
        actual_grid = (actual_net_kw
                       + battery_actions["charge_kw"]
                       - battery_actions["discharge_kw"])
    else:
        actual_grid = actual_net_kw
    da_cost = energy_cost(forecast_grid_kw, day_ahead)            # bought ahead
    residual = actual_grid - forecast_grid_kw                     # kW per period
    imb_cost = float((residual * imbalance * 0.5 / MWH).sum())    # settled at cashout
    return {"day_ahead_cost": da_cost, "imbalance_cost": imb_cost,
            "total_cost": da_cost + imb_cost,
            "abs_imbalance_kwh": float((residual.abs() * 0.5).sum())}


def run_loop(seed=0):
    import data, forecast
    p = data.build_portfolio(n_sites=5, days=21, seed=seed)
    net = forecast.portfolio_net(p)
    ctx = forecast.ctx_from_portfolio(p)
    fc, metrics = forecast.train_forecast(net, ctx=ctx, test_days=3)
    price = p["price"].reindex(fc.index)
    da, imb = price["day_ahead"], price["imbalance"]

    actual_net = fc["actual"]
    fcast_net = fc["point"]

    # B: forecast + battery -> commit battery schedule on the forecast
    disp_fc = dispatch_lp(fcast_net, da)
    sB = settle(disp_fc["grid_kw"], actual_net, da, imb, battery_actions=disp_fc)

    # C: forecast, no battery
    sC = settle(fcast_net, actual_net, da, imb, battery_actions=None)

    # A: perfect foresight + battery (cost floor; trade to actual, no imbalance)
    disp_pf = dispatch_lp(actual_net, da)
    sA = {"total_cost": energy_cost(disp_pf["grid_kw"], da),
          "imbalance_cost": 0.0, "abs_imbalance_kwh": 0.0}

    return metrics, {"A_perfect_battery": sA, "B_forecast_battery": sB,
                     "C_forecast_nobattery": sC}, fc, disp_fc


if __name__ == "__main__":
    m, scen, fc, disp = run_loop()
    print("=== Forecast quality ===")
    print(f"  MAE model {m['MAE_model']:.1f} kW vs naive {m['MAE_naive']:.1f} kW "
          f"({m['improvement_vs_naive_%']}% better)\n")
    print("=== Loop economics over 3-day test window (GBP) ===")
    for name, s in scen.items():
        extra = f"  imbalance={s['imbalance_cost']:8.2f}  |resid|={s.get('abs_imbalance_kwh',0):7.1f} kWh"
        print(f"  {name:24s} total={s['total_cost']:9.2f}{extra}")
    b, c = scen["B_forecast_battery"], scen["C_forecast_nobattery"]
    print(f"\n  Battery saves: {c['total_cost']-b['total_cost']:.2f} GBP over 3 days")
    print(f"  Gap to perfect foresight: "
          f"{b['total_cost']-scen['A_perfect_battery']['total_cost']:.2f} GBP "
          f"(this is what better forecasting could still recover)")
