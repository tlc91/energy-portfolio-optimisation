"""
Step 1 of the loop: FORECAST the portfolio net position (demand - rooftop solar).

See primer §4 for the conceptual frame (information set, leakage discipline,
pinball loss, naive-baseline yardstick). The unit convention follows §1:
n_t = L_t - S_t is the per-SP energy in MWh — the same quantity contracts,
settlement, and §7 imbalance accounting use — so this layer trains, evaluates
and emits forecasts in MWh per SP, not in SP-averaged power.

The portfolio is the customer's grid-facing net: site load minus on-site solar.
No other generation source contributes to portfolio self-supply. The national
mix (wind, nuclear, CCGT, ...) enters here only as price/system-state FEATURES.

Mirrors the real job:
  - build features (calendar, lag, price, mix) -> predict half-hourly net
  - produce a POINT forecast AND quantiles (uncertainty) -> the quantiles feed
    the optimiser and let us reason about imbalance risk
  - always compare against a NAIVE baseline (yesterday-same-period). The job is
    "beat the baseline", same as beating NESO's published demand forecast.

Deliberately simple models (the point is the end-to-end wiring, not SOTA).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

HH = 48

def portfolio_net_mwh(p) -> pd.Series:
    """Portfolio net energy per SP [MWh] = Σ site load_mwh − Σ site solar_mwh.
    This is n_t in primer §1 — the quantity contracts/settlement act on."""
    load = sum(s["load_mwh"] for s in p["sites"].values())
    solar = sum(s["solar_mwh"] for s in p["sites"].values())
    return (load - solar).rename("net_mwh")

def portfolio_net(p) -> pd.Series:
    """Portfolio net as SP-averaged power [kW] — the form dispatch_lp wants
    (primer §6.1, the deliberate power-form exception). Energy form is
    portfolio_net_mwh; this is a thin wrapper for the LP boundary."""
    load = sum(s["load_kw"] for s in p["sites"].values())
    solar = sum(s["solar_kw"] for s in p["sites"].values())
    return (load - solar).rename("net_kw")

def ctx_from_portfolio(p) -> pd.DataFrame:
    """Forecaster context features built from the system mix + prices.

    Units: da_price / imb_price_lag in £/MWh; vre_share_lag dimensionless;
    resid_demand_lag, nat_wind_lag, nat_solar_lag in MW (national mix scale —
    these are predictors of price, not of the customer's MWh per SP net).

    Leakage rules applied here (primer §4.1, "knowable at decision time"):
      - day_ahead price: cleared the day before delivery -> available as a
        same-period feature.
      - imbalance price: only settled after the fact -> lag(1) only.
      - mix state (VRE share, residual demand): a real model would use
        a system forecast; here we use lag(1) of the actual as a stand-in
        (an honest placeholder, primer §9.2 #7).
    """
    mix, price = p["mix"], p["price"]
    return pd.DataFrame({
        "da_price": price["day_ahead"],
        "imb_price_lag": price["imbalance"].shift(1),
        "vre_share_lag": mix["vre_share"].shift(1),
        "resid_demand_lag": mix["residual_demand_mw"].shift(1),
        "nat_wind_lag": mix["wind_mw"].shift(1),
        "nat_solar_lag": mix["solar_mw"].shift(1),
    }, index=mix.index)

def make_features(net: pd.Series, ctx: pd.DataFrame | None = None) -> pd.DataFrame:
    idx = net.index
    df = pd.DataFrame(index=idx)
    df["sp"] = (idx.hour * 2 + idx.minute // 30)        # settlement period 0..47
    df["dow"] = idx.dayofweek
    df["weekend"] = (idx.dayofweek >= 5).astype(int)
    df["sin_sp"] = np.sin(2 * np.pi * df["sp"] / HH)
    df["cos_sp"] = np.cos(2 * np.pi * df["sp"] / HH)
    df["lag_1d"] = net.shift(HH)                         # same period yesterday
    df["lag_1w"] = net.shift(HH * 7)                     # same period last week
    df["roll_1d"] = net.shift(HH).rolling(HH).mean()     # trailing daily mean
    if ctx is not None:
        for col in ctx.columns:
            df[col] = ctx[col].reindex(idx).values
    df["y"] = net.values
    return df.dropna()

def naive_baseline(net: pd.Series) -> pd.Series:
    """Yesterday's same settlement period — the persistence baseline of primer §4.4.
    Cheap, surprisingly strong intraday; "beat the baseline" is the operational test."""
    return net.shift(HH).rename("naive")

def pinball(y, q_pred, q):
    """Quantile (pinball) loss — primer §4.3 / Koenker & Bassett 1978.
    Minimising E[ρ_q(y, ŷ)] yields the true conditional q-quantile;
    averaging across quantiles approximates CRPS, a proper scoring rule."""
    d = y - q_pred
    return np.mean(np.maximum(q * d, (q - 1) * d))

def train_forecast(net_mwh: pd.Series, ctx: pd.DataFrame | None = None,
                   test_days: int = 3):
    """Train point + q10/q50/q90 forecasts of the portfolio net.

    ``net_mwh`` is expected in MWh per SP (primer §1). All loss/metric values
    returned (MAE, RMSE, pinball) inherit that unit.
    """
    feat = make_features(net_mwh, ctx=ctx)
    split = feat.index.max() - pd.Timedelta(days=test_days)
    tr, te = feat[feat.index <= split], feat[feat.index > split]
    Xcols = [c for c in feat.columns if c != "y"]
    Xtr, ytr, Xte, yte = tr[Xcols], tr["y"], te[Xcols], te["y"]

    # point forecast (random_state fixed -> reproducible runs)
    point = GradientBoostingRegressor(n_estimators=200, max_depth=3,
                                      learning_rate=0.05, subsample=0.8,
                                      random_state=0)
    point.fit(Xtr, ytr)
    p_hat = pd.Series(point.predict(Xte), index=te.index, name="point")

    # quantile forecasts (uncertainty band) at 10/50/90
    quants = {}
    for q in (0.1, 0.5, 0.9):
        m = GradientBoostingRegressor(loss="quantile", alpha=q, n_estimators=200,
                                      max_depth=3, learning_rate=0.05, subsample=0.8,
                                      random_state=0)
        m.fit(Xtr, ytr)
        quants[q] = pd.Series(m.predict(Xte), index=te.index)

    # independently-fitted quantiles can cross; enforce q10 <= q50 <= q90 by
    # sorting each row (monotone, coherent bands for downstream risk sizing).
    qsorted = np.sort(np.column_stack([quants[0.1], quants[0.5], quants[0.9]]), axis=1)
    quants[0.1] = pd.Series(qsorted[:, 0], index=te.index)
    quants[0.5] = pd.Series(qsorted[:, 1], index=te.index)
    quants[0.9] = pd.Series(qsorted[:, 2], index=te.index)

    naive = naive_baseline(net_mwh).reindex(te.index)
    metrics = {
        "MAE_model_mwh": float(np.mean(np.abs(yte - p_hat))),
        "MAE_naive_mwh": float(np.mean(np.abs(yte - naive))),
        "RMSE_model_mwh": float(np.sqrt(np.mean((yte - p_hat) ** 2))),
        "pinball_q10_mwh": float(pinball(yte.values, quants[0.1].values, 0.1)),
        "pinball_q90_mwh": float(pinball(yte.values, quants[0.9].values, 0.9)),
    }
    metrics["improvement_vs_naive_%"] = round(
        100 * (1 - metrics["MAE_model_mwh"] / metrics["MAE_naive_mwh"]), 1)
    out = pd.DataFrame({"actual": yte, "point": p_hat,
                        "q10": quants[0.1], "q50": quants[0.5], "q90": quants[0.9],
                        "naive": naive})
    return out, metrics


if __name__ == "__main__":
    import data
    p = data.build_portfolio(n_sites=5, days=21, seed=0)
    net = portfolio_net_mwh(p)
    ctx = ctx_from_portfolio(p)
    out, m = train_forecast(net, ctx=ctx, test_days=3)
    print("Forecast vs naive baseline (test window) — units MWh per SP:")
    for k, v in m.items():
        print(f"  {k:24s} {v}")
    print("\nHead of forecast frame (MWh per SP):")
    print(out.head(6).round(4).to_string())
