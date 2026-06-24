"""
Data layer for the C&I solar + battery prototype.

Two modes:
  - SYNTHETIC (default, runs anywhere): real-shaped solar, price, load and the GB
    national generation mix, all generated from documented patterns.
  - REAL (run locally): pulls genuine half-hourly data from public, key-free APIs.

Modelling distinction — important, kept explicit in the code:
  * PORTFOLIO  = a C&I site's grid-facing net = (site load) - (site rooftop solar).
                 Self-supply on the customer side is SOLAR ONLY (plus battery storage
                 from loop.py). This is what we forecast / hedge / dispatch.
  * SYSTEM MIX = national GB generation by fuel (wind, nuclear, CCGT, coal, biomass,
                 hydro, interconnectors, solar). The customer does not own any of
                 these other than rooftop solar; they enter the prototype only as
                 PRICE-FORMATION CONTEXT (drive wholesale + imbalance prices) and
                 as features for the forecaster. NEVER add national wind/nuclear/etc
                 to the portfolio net.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

HH_PER_DAY = 48

# ----------------------------------------------------------------------------
# SYNTHETIC GENERATORS  (real-shaped; seeded by documented GB patterns)
# ----------------------------------------------------------------------------

def _hh_index(days: int, start="2026-01-06"):
    periods = days * HH_PER_DAY
    return pd.date_range(start=start, periods=periods, freq="30min")

# ---- portfolio-side (customer): solar + load -------------------------------

def synth_solar(days: int, capacity_kw: float = 250.0, seed=0) -> pd.Series:
    """Half-hourly solar generation (kW) for one C&I rooftop.
    Bell-shaped daily curve, seasonal amplitude, cloud noise. Zero at night."""
    rng = np.random.default_rng(seed)
    idx = _hh_index(days)
    hh = idx.hour + idx.minute / 60.0
    doy = idx.dayofyear
    seasonal = 0.55 + 0.45 * np.sin((doy - 80) / 365 * 2 * np.pi)   # winter low
    daylen = 6.5 + 2.5 * seasonal                                   # half-width hours
    bell = np.clip(1 - ((hh - 12.5) / daylen) ** 2, 0, None)
    clearsky = capacity_kw * seasonal * bell
    clouds = np.clip(rng.beta(6, 2, len(idx)), 0, 1)                # mostly clear-ish
    gen = clearsky * clouds
    return pd.Series(gen, index=idx, name="solar_kw")

def synth_site_load(days: int, base_kw: float = 180.0, seed=1) -> pd.Series:
    """Half-hourly C&I demand (kW): weekday business profile, lower weekends/nights."""
    rng = np.random.default_rng(seed)
    idx = _hh_index(days)
    hh = idx.hour + idx.minute / 60.0
    occ = 1 / (1 + np.exp(-(hh - 7.5))) - 1 / (1 + np.exp(-(hh - 18.5)))
    occ = np.clip(occ, 0.08, 1)                                     # nonzero base load
    weekend = np.where(idx.dayofweek >= 5, 0.45, 1.0)               # quieter weekends
    noise = rng.normal(1, 0.06, len(idx))
    load = base_kw * (0.25 + 0.75 * occ) * weekend * noise
    return pd.Series(np.clip(load, 0, None), index=idx, name="load_kw")

# ---- system-side (national context): GB generation mix in MW ---------------

def synth_national_demand(days: int, seed=10) -> pd.Series:
    """GB national electricity demand (MW). Winter > summer, evening peak,
    weekend dip. ~22-45 GW envelope, roughly matching NESO INDO/ITSDO scale."""
    rng = np.random.default_rng(seed)
    idx = _hh_index(days)
    hh = idx.hour + idx.minute / 60.0
    doy = idx.dayofyear
    seasonal = 0.85 + 0.30 * np.cos((doy - 15) / 365 * 2 * np.pi)   # peak around Jan
    evening = 1.0 + 0.35 * np.exp(-((hh - 18.5) ** 2) / 6)
    morning = 1.0 + 0.18 * np.exp(-((hh - 8) ** 2) / 4)
    daily = (evening + morning) / 2.0
    weekend = np.where(idx.dayofweek >= 5, 0.92, 1.0)
    noise = rng.normal(1, 0.02, len(idx))
    demand = 30000 * seasonal * daily * weekend * noise
    return pd.Series(demand, index=idx, name="demand_mw")

def synth_wind_national(days: int, seed=11) -> pd.Series:
    """GB wind (MW). AR(1) weather-driven capacity factor, no diurnal cycle,
    mild seasonal (windier winter). Capacity ~30 GW."""
    rng = np.random.default_rng(seed)
    idx = _hh_index(days)
    n = len(idx)
    seasonal_cf = 0.38 + 0.12 * np.cos((idx.dayofyear - 15) / 365 * 2 * np.pi)
    cf = np.empty(n)
    cf[0] = seasonal_cf[0]
    rho, sigma = 0.96, 0.06
    for t in range(1, n):
        cf[t] = rho * cf[t - 1] + (1 - rho) * seasonal_cf[t] + rng.normal(0, sigma)
    cf = np.clip(cf, 0.02, 0.95)
    return pd.Series(30000 * cf, index=idx, name="wind_mw")

def synth_nuclear_national(days: int, seed=12) -> pd.Series:
    """GB nuclear (MW). Near-flat baseload (~5.5 GW), 4 fictitious units each
    ~1.4 GW with rare on/off step changes (~monthly outages)."""
    rng = np.random.default_rng(seed)
    idx = _hh_index(days)
    n = len(idx)
    n_units, unit_mw = 4, 1400.0
    p_switch = 1.0 / (HH_PER_DAY * 25)
    states = np.ones((n_units, n))
    for u in range(n_units):
        s = 1
        for t in range(n):
            if rng.random() < p_switch:
                s = 1 - s
            states[u, t] = s
    nuclear = states.sum(axis=0) * unit_mw + rng.normal(0, 30, n)
    return pd.Series(np.clip(nuclear, 0, None), index=idx, name="nuclear_mw")

def synth_biomass_national(days: int, seed=13) -> pd.Series:
    """GB biomass (MW). Steady ~2.5 GW baseload, small noise (Drax-like)."""
    rng = np.random.default_rng(seed)
    idx = _hh_index(days)
    base = 2500 + rng.normal(0, 80, len(idx))
    return pd.Series(np.clip(base, 0, None), index=idx, name="biomass_mw")

def synth_hydro_national(days: int, seed=14) -> pd.Series:
    """GB hydro + pumped storage net (MW). Small (~0.3-1.5 GW), peaks with the
    evening demand peak (peaker behaviour)."""
    rng = np.random.default_rng(seed)
    idx = _hh_index(days)
    hh = idx.hour + idx.minute / 60.0
    peak = 0.3 + 0.7 * np.exp(-((hh - 18) ** 2) / 5)
    base = 1000 * peak + rng.normal(0, 60, len(idx))
    return pd.Series(np.clip(base, 50, None), index=idx, name="hydro_mw")

def synth_solar_national(days: int, seed=15) -> pd.Series:
    """GB national PV (MW). Same bell shape as rooftop, scaled to ~15 GW peak."""
    return (synth_solar(days, capacity_kw=15_000 * 1000, seed=seed) / 1000.0
            ).rename("solar_mw")

def synth_interconnectors(days: int, seed=16) -> pd.Series:
    """Net interconnector imports (MW), positive = importing. Simple diurnal
    swing (importing into the GB demand peak), large noise. In a real model
    this would close the loop on cross-border price spreads — here it's an
    exogenous signal."""
    rng = np.random.default_rng(seed)
    idx = _hh_index(days)
    hh = idx.hour + idx.minute / 60.0
    base = 2500 * np.sin((hh - 6) / 24 * 2 * np.pi)                 # peak-time imports
    base += rng.normal(0, 800, len(idx))
    return pd.Series(np.clip(base, -6000, 8000), index=idx,
                     name="interconnector_mw")

def synth_generation_mix(days: int, seed: int = 20) -> pd.DataFrame:
    """Assemble the national GB generation mix (MW, half-hourly).

    Inflexible / weather-driven / baseload stacks are generated first
    (wind, nuclear, biomass, hydro, solar, interconnectors). CCGT then fills
    the RESIDUAL demand as a flexible mid-merit follower; coal only switches
    on when the residual exceeds the CCGT comfort band (winter peak tightness).

    Returns one wide DataFrame with one column per fuel plus a few derived
    columns (renewables share, residual demand) that are convenient for both
    the price model and the forecaster's features.
    """
    demand = synth_national_demand(days, seed=seed)
    wind = synth_wind_national(days, seed=seed + 1)
    nuclear = synth_nuclear_national(days, seed=seed + 2)
    biomass = synth_biomass_national(days, seed=seed + 3)
    hydro = synth_hydro_national(days, seed=seed + 4)
    solar = synth_solar_national(days, seed=seed + 5)
    interc = synth_interconnectors(days, seed=seed + 6)

    non_thermal = wind + nuclear + biomass + hydro + solar + interc
    residual = (demand - non_thermal).clip(lower=0)
    # coal stays at zero unless residual blows past CCGT comfort (~25 GW)
    coal_threshold = 25000
    coal = ((residual - coal_threshold).clip(lower=0) * 0.45).clip(upper=2000)
    ccgt = (residual - coal).clip(lower=0, upper=28000)

    mix = pd.concat({
        "demand_mw": demand, "wind_mw": wind, "nuclear_mw": nuclear,
        "biomass_mw": biomass, "hydro_mw": hydro, "solar_mw": solar,
        "interconnector_mw": interc, "ccgt_mw": ccgt, "coal_mw": coal,
    }, axis=1)
    mix["renewables_mw"] = mix["wind_mw"] + mix["solar_mw"]
    mix["renewables_share"] = (mix["renewables_mw"] / mix["demand_mw"]).clip(0, 2)
    mix["residual_demand_mw"] = (mix["demand_mw"]
                                 - mix["renewables_mw"] - mix["nuclear_mw"]
                                 - mix["biomass_mw"] - mix["hydro_mw"]
                                 - mix["interconnector_mw"])
    return mix

# ---- prices: now mix-aware -------------------------------------------------

def synth_price(days: int, mix: pd.DataFrame | None = None, seed=2) -> pd.DataFrame:
    """Half-hourly prices (GBP/MWh): a day-ahead reference and a fatter-tailed
    imbalance / cash-out price.

    Merit-order flavour: CCGT-marginal base, pulled DOWN by renewables share
    and pushed UP by system tightness and by coal being on (a tell that the
    stack is deep into expensive plant). Imbalance = day-ahead + a Student-t
    spread whose scale grows with tightness.
    """
    rng = np.random.default_rng(seed)
    if mix is None:
        mix = synth_generation_mix(days, seed=seed + 1000)
    idx = mix.index
    renew_share = mix["renewables_share"].values
    coal_on = (mix["coal_mw"].values > 200).astype(float)
    tightness = (mix["residual_demand_mw"].values / 28000)           # 1 ≈ CCGT cap
    base = (75
            + 80 * np.clip(tightness, -1.0, 1.2)                     # tight -> up
            + 100 * coal_on                                          # coal -> spike
            - 60 * np.clip(renew_share, 0, 1.5))                     # renewables -> down
    day_ahead = base + rng.normal(0, 5, len(idx))
    day_ahead = np.clip(day_ahead, -75, 600)
    spread_scale = 10 + 30 * np.clip(tightness, 0, 1.2)
    spread = rng.standard_t(3, len(idx)) * spread_scale
    imbalance = np.clip(day_ahead + spread, -100, 900)
    return pd.DataFrame({"day_ahead": day_ahead, "imbalance": imbalance}, index=idx)


def build_portfolio(n_sites: int = 5, days: int = 14, seed: int = 0):
    """Assemble a synthetic C&I portfolio + the surrounding GB system context.

    The customer portfolio is just the per-site (load, rooftop solar). The GB
    generation mix is built alongside and used to drive the price model and to
    feed the forecaster features — it is NOT added to the portfolio's physical
    net. Sites share a weather/cloud factor so forecast errors don't fully
    cancel (the whole point of portfolio-level modelling).
    """
    rng = np.random.default_rng(seed)
    mix = synth_generation_mix(days, seed=seed + 200)
    price = synth_price(days, mix=mix, seed=seed + 100)
    idx = price.index
    shared_cloud = np.clip(rng.beta(6, 2, len(idx)), 0, 1)
    sites = {}
    for s in range(n_sites):
        cap = rng.uniform(120, 400)
        base = rng.uniform(120, 300)
        solar = synth_solar(days, capacity_kw=cap, seed=seed + s)
        solar = solar * (0.4 + 0.6 * pd.Series(shared_cloud, index=idx) /
                         np.clip(pd.Series(shared_cloud, index=idx).mean(), 1e-6, None)).clip(0, 1.5)
        load = synth_site_load(days, base_kw=base, seed=seed + 50 + s)
        sites[f"site_{s}"] = pd.DataFrame({"solar_kw": solar, "load_kw": load})
    return {"sites": sites, "price": price, "mix": mix, "index": idx}


# ----------------------------------------------------------------------------
# REAL DATA FETCHERS  (run locally; sandbox cannot reach these domains)
# ----------------------------------------------------------------------------

def real_elexon_fuelhh(date_from: str, date_to: str) -> "pd.DataFrame":
    """Half-hourly generation outturn by fuel type (incl. SOLAR), from Elexon BMRS.
    Public, no API key. Docs: https://developer.data.elexon.co.uk/  (dataset FUELHH).

    Returns the raw long-format response (one row per settlement period x fuel).
    For the full fuel-type breakdown in one row per HH, use ``real_elexon_fuelhh_wide``.
    """
    import requests
    url = "https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH"
    params = {"publishDateTimeFrom": date_from, "publishDateTimeTo": date_to,
              "format": "json"}
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    return pd.json_normalize(r.json()["data"])

def real_elexon_fuelhh_wide(date_from: str, date_to: str) -> "pd.DataFrame":
    """FUELHH pivoted to one column per fuel type (MW), HH index. Columns
    typically include: CCGT, OCGT, OIL, COAL, NUCLEAR, WIND, PS, NPSHYD,
    BIOMASS, OTHER, SOLAR, plus interconnectors (INTFR, INTIRL, INTNED,
    INTEW, INTNEM, INTELEC, INTIFA2, INTNSL, INTVKL).
    """
    df = real_elexon_fuelhh(date_from, date_to)
    return (df.pivot_table(index="startTime", columns="fuelType",
                           values="generation", aggfunc="sum")
              .sort_index())

def real_elexon_system_price(settlement_date: str) -> "pd.DataFrame":
    """Half-hourly system (imbalance / cash-out) price for a settlement date.
    Public, no API key. This is the price your forecast error is charged at.
    """
    import requests
    url = f"https://data.elexon.co.uk/bmrs/api/v1/balancing/settlement/system-prices/{settlement_date}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return pd.json_normalize(r.json()["data"])

def real_pvlive_national(start: str, end: str) -> "pd.DataFrame":
    """National PV generation, 30-min, from Sheffield Solar PV_Live.
    `pip install pvlive-api`. Scale to a site by (site_capacity / national_capacity).
    """
    from pvlive_api import PVLive
    pv = PVLive()
    return pv.between(start=pd.Timestamp(start, tz="UTC"),
                      end=pd.Timestamp(end, tz="UTC"), dataframe=True)


if __name__ == "__main__":
    p = build_portfolio(n_sites=5, days=14, seed=0)
    agg = sum(s["load_kw"] for s in p["sites"].values()) - \
          sum(s["solar_kw"] for s in p["sites"].values())
    print("Portfolio net (load - rooftop solar) kW — describe:")
    print(agg.describe().round(1).to_string())
    print("\nPrice GBP/MWh — describe:")
    print(p["price"].describe().round(1).to_string())
    print("\nGB generation mix MW — describe (cols subset):")
    cols = ["demand_mw", "wind_mw", "nuclear_mw", "ccgt_mw", "coal_mw",
            "solar_mw", "renewables_share", "residual_demand_mw"]
    print(p["mix"][cols].describe().round(1).to_string())
