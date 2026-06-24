# C&I Solar + Battery: thin end-to-end prototype

A minimal, runnable version of the **forecast → dispatch → settle → PnL** loop for a
small commercial & industrial solar+battery portfolio. Built to grow understanding,
not to be production code.

## Portfolio vs system — the modelling distinction

Two things are modelled and they are **not the same thing**:

- **Portfolio** = the customer's grid-facing position = `site load − site rooftop solar`.
  This is what we forecast, hedge and dispatch the battery against. On the customer
  side, the **only self-supply source is solar** (plus battery storage from
  `loop.py`). The customer does not own a CCGT.
- **System mix** = national GB generation by fuel (wind, nuclear, CCGT, coal,
  biomass, hydro, interconnectors, national solar). This enters the prototype only
  as **price-formation context**: it drives wholesale + imbalance prices and feeds
  the forecaster as features. National wind is *never* added to the portfolio net.

## The loop (what each file does)

| Step | File | What it does |
|------|------|--------------|
| Data | `data.py` | Real-shaped **synthetic** solar, load, price *and* the GB **generation mix**. Plus **real**-data fetchers (Elexon FUELHH, PV Live) you can switch on locally. |
| 1. Forecast | `forecast.py` | Predicts half-hourly **portfolio net** (load − rooftop solar). Point + **quantile** forecasts, with price + mix features. Benchmarked vs naive baseline. |
| 2. Dispatch | `loop.py` `dispatch_lp` | **LP** battery schedule (PuLP/CBC) minimising energy cost s.t. SoC / rate / capacity constraints. |
| 3. Settle | `loop.py` `settle` | Trade day-ahead to the **forecast**; residual (actual − forecast) settles at the **imbalance** price. |
| 4. PnL | `loop.py` `run_loop` | Three strategies isolate where money comes from. |

## Run it

Uses [`uv`](https://docs.astral.sh/uv/) for env + deps (lockfile committed):

```bash
uv sync                       # install everything into .venv
uv run python loop.py         # end-to-end forecast → dispatch → settle → PnL
uv run python forecast.py     # just the forecast quality summary
uv run jupyter lab explore.ipynb   # data / forecast / dispatch / risk-band plots
```

## The synthetic GB generation mix (system context)

Built in `data.py::synth_generation_mix` (MW, half-hourly, ~30 GW typical demand):

| Fuel | Function | Intended shape |
|------|----------|----------------|
| Solar (national) | `synth_solar_national` | Bell-shaped diurnal, seasonal amplitude, cloud noise. ~15 GW peak capacity. |
| Wind | `synth_wind_national` | AR(1) weather-driven CF, no diurnal cycle, mild seasonal (windier winter). ~30 GW capacity. |
| Nuclear | `synth_nuclear_national` | Near-flat ~5.5 GW baseload, 4 fictitious units with rare on/off outage steps. |
| CCGT | inside `synth_generation_mix` | Flexible marginal plant, **follows the entire residual** demand after weather + baseload + interconnectors. (GB is **coal-free** since 30 Sep 2024 — no coal stack; winter-peak spikes come from a scarcity term in the price model.) |
| Biomass | `synth_biomass_national` | Steady ~2.5 GW baseload (Drax-like). |
| Hydro + PS | `synth_hydro_national` | Small (~0.3–1.5 GW), peaker shape around evening demand. |
| Interconnectors | `synth_interconnectors` | Net imports swing with a diurnal pattern + noise (proxy for cross-border spread). |

The mix is then fed to `synth_price`, which forms a CCGT-marginal price pulled DOWN
by renewables share and pushed UP by system tightness, with a convex **scarcity**
adder as residual demand nears the gas-fleet headroom (`FLEX_GAS_REF_MW`). So
windy/sunny periods can clear cheap (sometimes negative); tight winter-peak periods
leaning on pricey peaking gas / imports produce spikes. The imbalance price adds a
Student-t spread whose scale grows with tightness.

The forecaster (`forecast.py::ctx_from_portfolio`) consumes the mix and prices as
features (day-ahead price, lagged imbalance, lagged renewables share, lagged
residual demand, lagged national wind/solar) — strictly respecting what would be
known ahead of delivery in a real settlement timeline.

## The key idea the numbers show

Three strategies are compared so each effect is legible:

- **A — perfect foresight + battery**: theoretical cost floor (no imbalance).
- **B — forecast + battery**: what you'd actually run.
- **C — forecast, no battery**: same forecast, battery removed.

`C − B` = **the battery's value**. `B − A` = **the cost of forecast error** — the
money better forecasting can still recover. That second gap is the entire economic
case for the data-science role, made measurable.

> Note: on synthetic data the forecast is *easy* (≈90% better than naive, tiny
> residual), so the forecast-error gap looks small. On real Elexon/PV Live data the
> series is far noisier, the gap widens, and the value of forecasting grows — which
> is exactly the point to demonstrate next.

## Switching to real data (run locally — sandbox can't reach these domains)

All sources are public and **need no API key**. The quickest path is the toggle in
`explore.ipynb` (`USE_REAL_DATA = True`), or in code:

```python
p = data.build_portfolio(n_sites=5, real=True,
                         date_from="2025-01-06", date_to="2025-01-27")
```

This calls `data.real_context`, which assembles the real GB mix + prices into the
**same canonical schema** as the synthetic path (so forecast/dispatch/settle work
unchanged). Underneath:

- **Elexon BMRS** `FUELHH` (half-hourly per-fuel generation — solar, wind, nuclear,
  CCGT, biomass, hydro, interconnectors; the COAL column is now ~0), `INDO`/`ITSDO`
  (demand), `NDF` (national demand forecast = a real benchmark),
  `balancing/settlement/system-prices/{date}` (imbalance / cash-out price), and
  `MID` (Market Index Data — a within-day wholesale price used as a day-ahead proxy).
  See `real_elexon_fuelhh_wide`, `real_elexon_system_price`, `real_elexon_mid` and
  the assembler `real_context` in `data.py`. (Verify dataset field names on first
  run — they drift occasionally.) Docs: https://developer.data.elexon.co.uk/
- **PV Live** (Sheffield Solar): `pip install pvlive-api` -> national PV, 30-min.
  Scale to a site by capacity ratio. See `real_pvlive_national`.
- **Octopus Agile**: real half-hourly retail prices (regional) if you want a retail
  signal instead of wholesale.
- **Open-Meteo**: free historical irradiance/temperature for features.

Keep **customer load synthetic** — no open per-site C&I data exists. That gap *is*
Volter's proprietary moat, so simulating it is the honest design.

## Natural next steps (in rough order)

1. Swap synthetic prices+solar for real Elexon+PV Live; re-run and watch the
   forecast-error gap grow.
2. Add a **no simultaneous charge/discharge** binary -> turns the LP into a **MIP**.
3. Use the **quantile** forecast in dispatch (e.g. hedge to q50 but hold battery
   headroom sized by q10–q90) -> uncertainty-aware optimisation.
4. Add **error attribution** (which sites / periods drive residual cost?) -> the
   feedback arrow that closes the loop back to model improvement.
5. Move from 1-day to intraday re-forecasting as new actuals arrive.
