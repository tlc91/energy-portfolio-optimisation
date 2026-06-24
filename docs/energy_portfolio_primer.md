# Optimising the Energy Portfolio of a Commercial & Industrial Customer in Great Britain

### A primer linking market structure, forecasting, hedging and short-term dispatch — and a critical review of the accompanying prototype

*Working paper — written as a learning foundation and a basis for future research.*

---

## Abstract

A commercial and industrial (**C&I** — non-domestic, sub-transmission-connected) energy
customer with on-site generation and storage faces a layered decision problem. Months
ahead it must **hedge** an uncertain future volume by buying energy forward. Day-ahead it
must refine that position against the latest forecast. Within the hour it must **dispatch**
flexible assets (here, a battery) and accept that whatever it got wrong is **settled at the
imbalance (cash-out) price**. Each layer has a different information set, a different
decision variable, and a different source of risk. This paper builds the conceptual and
mathematical scaffolding for that problem in the Great Britain (**GB**) market, in enough
depth to (a) understand *why* the accompanying code is structured the way it is, (b) see
clearly what it simplifies, and (c) plan rigorous extensions. It closes with a critical
review of the prototype, including several concrete logic issues, and a research roadmap.

We use the convention throughout that **cost is positive** (money leaving the customer) and
**revenue is negative**. Energy quantities are in kilowatt-hours (**kWh**) or megawatt-hours
(**MWh**); power in **kW**/**MW**; prices in pounds per MWh (**£/MWh**). One GB
**settlement period** (**SP**) is 30 minutes, so there are 48 per day and power $p$ kW
sustained over one SP delivers $0.5p/1000$ MWh.

---

## 1. The problem, stated once, cleanly

Let the portfolio's **grid-facing net position** in settlement period $t$ be

$$
n_t \;=\; \underbrace{L_t}_{\text{site load}} \;-\; \underbrace{S_t}_{\text{on-site solar}} \quad [\text{kW}],
$$

aggregated over all sites in the portfolio. When $n_t>0$ the portfolio is a net *importer*
(it must buy energy); when $n_t<0$ it is a net *exporter*. This single quantity — **not**
load and generation separately — is what is hedged, forecast, and dispatched against.
On-site solar is the *only* self-supply on the customer side; a battery adds **temporal
shifting** of that net but creates no new energy.

The customer's total cost over a horizon $\mathcal{T}$, decomposed by the decision layer that
incurs it, is

$$
\boxed{\;C \;=\; \underbrace{C_{\text{fwd}}}_{\text{forward/hedge}} \;+\; \underbrace{C_{\text{DA}}}_{\text{day-ahead}} \;+\; \underbrace{C_{\text{ID}}}_{\text{within-day}} \;+\; \underbrace{C_{\text{imb}}}_{\text{imbalance / cash-out}} \;+\; \underbrace{C_{\text{non-comm}}}_{\text{networks, levies, capacity}}\;}
$$

Every term but the last is a *trading* decision taken under uncertainty about $n_t$ and
about prices. The art is that **each term is decided at a different time, against a
different forecast**, and the residual uncertainty cascades down to the cash-out term, which
is the most expensive and least controllable. The entire economic case for a forecasting and
optimisation function is: *push risk up the timeline, where it is cheap to manage, and out of
the cash-out term, where it is dear.*

---

## 2. The GB electricity market: institutions, timeline, prices

### 2.1 Who is who

- **NESO** — the **National Energy System Operator** (publicly owned since October 2024;
  formerly National Grid ESO). It balances the system second-by-second and publishes the
  national demand forecast.
- **Elexon** — administers the **Balancing and Settlement Code** (**BSC**) and runs
  **imbalance settlement**: it measures every party's metered volume against its
  contracted/notified volume and charges the difference at the cash-out price.
- **Ofgem** — the regulator (Office of Gas and Electricity Markets).
- **Suppliers / shippers / traders** — the licensed parties that actually transact. A C&I
  customer typically sits *behind* a licensed supplier or a route-to-market partner; "running
  the portfolio" means optimising the position that is ultimately settled in that party's name.

Historically the **Pool** (1990–2001) was replaced by **NETA** (New Electricity Trading
Arrangements, 2001) and then **BETTA** (British Electricity Trading and Transmission
Arrangements, 2005), which extended a single GB market to Scotland. The defining feature of
NETA/BETTA versus the old Pool is that it is a **bilateral, self-dispatch** market: parties
contract freely and are responsible for balancing their own positions, with the system
operator and cash-out as the backstop. This is *why* a private portfolio optimisation
function exists at all — the customer, not a central dispatcher, owns its imbalance.

### 2.2 The trading timeline (the spine of the whole problem)

```
   months/years ahead        day ahead        within-day        gate closure (T−1h)     after the fact
  ┌───────────────────┐   ┌─────────────┐   ┌──────────────┐   ┌──────────────────┐   ┌───────────────┐
  │  FORWARD / FUTURES │ → │  DAY-AHEAD  │ → │  INTRADAY /  │ → │  BALANCING MECH. │ → │   SETTLEMENT  │
  │ seasons,quarters,  │   │  auction +  │   │  CONTINUOUS  │   │ (NESO dispatches │   │  (Elexon:     │
  │ months (baseload/  │   │  hourly/HH  │   │   trading    │   │  bids & offers)  │   │  cash-out the │
  │ peak blocks)       │   │  EPEX/N2EX  │   │              │   │                  │   │   imbalance)  │
  └───────────────────┘   └─────────────┘   └──────────────┘   └──────────────────┘   └───────────────┘
   shrink volume risk      price discovery    fine-tune the      physical balancing      you pay/are paid
   with crude volume       at fixed Δt        position as the    by the SO; sets the     for actual − final
   knowledge               horizon            forecast sharpens  cash-out price          notified position
```

- **Forward / futures market.** Standardised **baseload** (24×7) and **peak** (working-day
  daytime) blocks for months, quarters and seasons, traded over-the-counter via brokers and
  on exchanges (ICE). This is where the *bulk* of a C&I volume is bought, far enough ahead
  that only a crude volume forecast exists. The decision variable is *how much* to lock in.
- **Day-ahead (DA) market.** A blind auction (EPEX SPOT and Nord Pool/N2EX in GB) clearing
  one price per delivery hour (and increasingly per half-hour) for the next day. This is the
  reference "spot" price most analyses use, and the one the prototype calls `day_ahead`.
- **Intraday / continuous market.** Trading right up to **gate closure**, which in GB is
  **one hour before the start of the settlement period**. As delivery approaches and the
  forecast sharpens, parties trim their position here.
- **Balancing Mechanism (BM).** After gate closure, **NESO** is the only actor: it accepts
  **Offers** (to generate more / demand less) and **Bids** (the reverse) submitted by
  **Balancing Mechanism Units** to keep the system in real-time balance. The prices of the
  accepted actions feed the cash-out price.
- **Settlement.** Elexon compares each party's *metered* volume to its *final notified*
  contractual position and charges the difference — the **imbalance** — at the cash-out price
  (next section).

### 2.3 How the wholesale price forms: merit order and marginal pricing

GB, like most liberalised markets, clears at the **system marginal price**: generators are
stacked cheapest-first (the **merit order**), and the price is set by the *most expensive
unit needed* to meet demand. With near-zero-marginal-cost renewables at the bottom of the
stack, the marginal unit is usually a gas plant (**CCGT** — Combined Cycle Gas Turbine), so a
useful reduced-form is

$$
\pi^{\text{DA}}_t \;\approx\; \underbrace{\text{SRMC}^{\text{CCGT}}_t}_{\text{fuel}\,/\,\eta\,+\,\text{carbon}} \;+\; \beta_{\text{tight}}\,\text{tightness}_t \;-\; \beta_{\text{ren}}\,\text{renewables-share}_t \;+\; \varepsilon_t,
$$

where **SRMC** is short-run marginal cost. The two structural levers are visible directly:

- **Renewables share** $r_t = (\text{wind}_t+\text{solar}_t)/\text{demand}_t$ pushes price
  *down* — a windy, sunny half-hour can clear at or below zero (negative prices occur when it
  is cheaper to pay to offload than to curtail inflexible plant).
- **System tightness** — residual demand relative to available flexible capacity — pushes
  price *up*, with scarcity spikes when the stack runs into expensive peaking gas and
  imports. (Note GB has been **coal-free** since its last coal station, Ratcliffe-on-Soar,
  closed on **30 September 2024**; the marginal unit is now almost always gas. The prototype
  reflects this — it carries no coal stack and models peak spikes via a convex scarcity term.)

This is exactly the structure the prototype's `synth_price` encodes (§9). The key intuition
for a portfolio manager: **price and your own net position are both driven by weather and
demand**, so they are *correlated*, and that correlation is where both risk and opportunity
live (you are most likely to be short exactly when the system is tight and prices spike).

### 2.4 Cash-out (the imbalance price): the term that disciplines everything

Let a party's final notified (contracted) position in SP $t$ be $q^{\text{contract}}_t$ and
its metered outturn $q^{\text{actual}}_t$. Its **imbalance volume** is

$$
\Delta_t \;=\; q^{\text{actual}}_t - q^{\text{contract}}_t .
$$

Under the GB **single imbalance price** regime (introduced through BSC modification **P305**,
phased in from 2015), *both* directions settle at one price $\pi^{\text{imb}}_t$ per SP — you
no longer face a separate, worse price for being short than for being long. That price is
built from the most expensive balancing actions NESO actually took, averaged over the
**Price Average Reference** (**PAR**) volume (reduced to **1 MWh** in 2018 to make the price
reflect genuinely marginal actions), plus reserve-scarcity adders. The settlement cash flow
to the customer is

$$
C^{\text{imb}}_t \;=\; -\,\Delta_t \,\pi^{\text{imb}}_t \cdot \tfrac{1}{2}\big/1000 \quad [\pounds],
$$

with the sign convention that being short ($\Delta_t<0$, used less or generated more than
contracted) and being long are penalised/rewarded symmetrically *at that period's price*.

Two facts matter for strategy:

1. **Cash-out is volatile and fat-tailed.** It is set by marginal balancing actions in a
   tight real-time system, so its variance is largest exactly when tightness is highest. The
   prototype models this with a Student-$t$ spread whose scale grows with tightness — a
   faithful qualitative choice (§9).
2. **Single pricing does not make imbalance "free."** Even though long and short settle at
   the same price, imbalance is risky because $\pi^{\text{imb}}_t$ is uncertain *and*
   correlated with your error: a cold, still evening makes you short *and* makes cash-out
   spike. So the expected cost of imbalance is not $\mathbb{E}[\Delta]\,\mathbb{E}[\pi]$ but
   $\mathbb{E}[\Delta\,\pi]=\mathbb{E}[\Delta]\mathbb{E}[\pi]+\operatorname{Cov}(\Delta,\pi)$,
   and the covariance term is the silent killer. **This is the single most important reason to
   forecast well.**

### 2.5 The non-commodity stack (why C&I is special)

A C&I bill is *not* just energy. A large fraction is **non-commodity** charges that a real
portfolio optimiser also targets:

- **TNUoS / DUoS** — Transmission and Distribution Network Use of System charges. DUoS has
  time-banded ("red/amber/green") unit rates; shifting load out of the red band is real money.
- **Triad** (historical) — TNUoS demand charges were once levied on a site's demand during
  the three highest national-demand half-hours each winter; "Triad avoidance" was a major
  battery/flexibility use case until **Ofgem's Targeted Charging Review** largely removed the
  benefit for demand from April 2023. Mentioned because much existing literature assumes it.
- **Capacity Market (CM)**, **BSUoS** (Balancing Services Use of System, now largely fixed
  and socialised to demand), and policy levies (RO, CfD, FiT).
- **Ancillary / flexibility revenues** — frequency response products (e.g. Dynamic
  Containment) and BM participation, which a battery can "stack" on top of arbitrage.

The prototype models *only* wholesale arbitrage + imbalance. That is the right first cut, but
**value stacking is where a real C&I battery earns its keep**, and it is the largest gap
between this model and reality (see roadmap, §10).

---

## 3. The portfolio-vs-system distinction (and why the code is religious about it)

Two quantities are modelled and they are categorically different:

| | **Portfolio (customer)** | **System (national)** |
|---|---|---|
| What | $\sum_i (L^i_t - S^i_t)$ | GB generation mix by fuel, national demand |
| Role | hedged, forecast, dispatched | *price-formation context* + forecaster features |
| In the net? | **yes** | **never** added to portfolio net |

National wind, nuclear, CCGT etc. influence the *price* the portfolio pays and are useful
*predictors* of that price, but they are not the customer's energy. Conflating the two — e.g.
"netting off national wind" — is the classic beginner error, and the code's comments and
structure are deliberately built to prevent it. Mathematically the system mix enters only
through the price model $\pi(\cdot)$ and the forecaster's feature vector $x_t$, never through
$n_t$.

---

## 4. Forecasting the net position

### 4.1 What we are forecasting, and the information set

We want the conditional distribution of $n_t$ given everything *knowable at decision time*
$\tau$:

$$
F_{n_t\mid \mathcal{I}_\tau}(\cdot), \qquad \mathcal{I}_\tau = \{\text{calendar},\, \text{lagged } n,\, \text{known prices},\, \text{weather forecast},\, \text{system-state forecast}\}.
$$

The phrase "knowable at $\tau$" is doing enormous work. **Leakage** — letting a feature carry
information that would not in fact be available when the decision is made — is the most common
and most dangerous error in energy forecasting, because backtests look brilliant and live
performance collapses. The accompanying code is unusually disciplined here:

- **Day-ahead price** is cleared the *day before* delivery → usable as a same-period feature.
- **Imbalance price** is only known *after* settlement → usable only at **lag 1** (or more).
- **System mix state** (renewables share, residual demand) would, in production, come from a
  *system forecast*; the prototype uses **lag-1 actuals** as an honest stand-in placeholder.

A clean way to state the rule: a feature $x_t$ is admissible for a forecast made at $\tau$
iff $x_t \in \sigma(\mathcal{I}_\tau)$ — it is measurable with respect to information available
at $\tau$.

### 4.2 Point forecasts and why they are not enough

A point forecast $\hat n_t = \mathbb{E}[n_t\mid\mathcal{I}_\tau]$ minimises mean squared error
but tells you nothing about *risk*. Because cash-out is convex and fat-tailed in your error,
the optimal hedge and the optimal battery headroom depend on the **whole predictive
distribution**, not its mean. Hence we forecast **quantiles**.

### 4.3 Quantile forecasts, pinball loss, and proper scoring

The $q$-quantile $\hat n_t^{(q)}$ is estimated by minimising the **pinball (quantile) loss**
(Koenker & Bassett, 1978):

$$
\rho_q(y,\hat y) \;=\; \begin{cases} q\,(y-\hat y) & y \ge \hat y\\ (q-1)\,(y-\hat y) & y < \hat y \end{cases}
\;=\; \max\!\big(q(y-\hat y),\,(q-1)(y-\hat y)\big).
$$

Minimising $\mathbb{E}[\rho_q]$ yields the true conditional quantile; it is the exact loss
implemented in the prototype's `pinball`. Averaging pinball loss across many quantiles
approximates the **Continuous Ranked Probability Score** (**CRPS**), a *proper* scoring rule
(Gneiting & Raftery, 2007) — "proper" meaning it is optimised by reporting your true beliefs,
so it cannot be gamed by over- or under-confident bands. **Calibration** is the operational
test: the realised value should fall below $\hat n^{(q)}$ a fraction $q$ of the time. The
notebook's "reading the band" guidance is exactly a calibration check.

> **Caveat the prototype inherits:** independently fitted quantile models can **cross**
> ($\hat n^{(0.1)} > \hat n^{(0.9)}$ for some $t$), which is incoherent. Production systems
> enforce monotonicity (sorting, isotonic regression, or jointly trained models). See §9.

### 4.4 Baselines: you have not forecast until you have beaten one

A forecast is only meaningful relative to a baseline. The natural ones are:

- **Persistence / naive** — "same settlement period yesterday," $\hat n_t = n_{t-48}$. Cheap,
  surprisingly strong intraday, and the prototype's benchmark.
- **NESO's published demand forecast** (NDF) — the real-world bar at system level; "beat
  NESO" is the genuine job at the national scale.

Skill is reported as $1 - \text{MAE}_{\text{model}}/\text{MAE}_{\text{naive}}$. There are two
*different* gaps that beginners routinely conflate, and the prototype makes the distinction
vividly:

- **Forecast-skill gap** (model vs naive): on the synthetic data the model beats persistence
  by ~90% (the structured intraday shape is highly learnable, while lag-1 naive carries
  yesterday's noise). This gap is *large*.
- **Economic forecast-error gap** ($B-A$, §7.2): the *absolute* residual is tiny in kW because
  the synthetic net is smooth, so the money left on the table is small even though skill is
  high.

So the README's "the forecast is easy" refers to the **small absolute residual**, not to a
strong naive baseline. On *real, noisy* data both the residual and the economic gap widen,
which is when forecasting value becomes measurable in pounds. **The economic value of a
forecaster is set by the irreducible noise it removes from the cash-out term, not by its
headline skill over a baseline.**

### 4.5 Where the weather comes in

Both legs of $n_t = L_t - S_t$ are weather-driven, on different horizons:

- **Solar $S_t$.** Physically, $S_t \approx \eta_{\text{PV}}\,A\,\text{GHI}_t\,(1-\text{cloud}_t)$
  where **GHI** is Global Horizontal Irradiance. A robust pipeline separates the deterministic
  **clear-sky** envelope (a closed-form function of solar geometry — date, time, latitude) from
  the stochastic **cloud** attenuation. Forecasting then targets the clear-sky index
  $k_t = S_t/S^{\text{clear}}_t \in [0,1]$, which is far more stationary than $S_t$ itself.
- **Load $L_t$.** Temperature drives heating and cooling, classically captured by **HDD/CDD**
  (Heating/Cooling Degree Days), $\text{HDD}=\max(0,T_{\text{base}}-T)$, with strong
  calendar (occupancy) structure for C&I sites.

The forecast horizon dictates the weather source:

| Horizon | Dominant weather signal | Method |
|---|---|---|
| 0–2 h (next half-hours) | **persistence** of cloud/irradiance; satellite & sky-camera nowcasting | statistical, fast-updating |
| 2 h – 2 days | **Numerical Weather Prediction** (NWP) | NWP-driven regression / ML |
| > 2 days | NWP ensembles, climatology | probabilistic, wide bands |

**NWP** is Numerical Weather Prediction — the physics-based atmospheric models run by centres
such as the **ECMWF** (European Centre for Medium-Range Weather Forecasts) and the Met Office.
Their **ensemble** runs (many perturbed simulations) are the natural source of *probabilistic*
weather inputs, which map directly to the quantile forecasts of §4.3: weather uncertainty is
the principal driver of $n_t$ uncertainty, so a well-built forecaster ingests NWP ensemble
spread rather than just the deterministic run. The prototype's `Open-Meteo` integration note
is the hook for exactly this. The crucial practical point: **a same-hour forecast and a
day-ahead forecast are different models with different feature sets** — persistence dominates
the former, NWP the latter — and conflating them (using only lags for day-ahead, or only NWP
for nowcasting) leaves skill on the table.

---

## 5. Hedging and forward procurement (the long-horizon layer)

### 5.1 The decision

Far ahead, you know your *expected* volume and its *uncertainty* but little about the realised
shape. You choose a forward quantity $h$ (per block) to buy at price $\pi^{\text{fwd}}$. Buy
too little and you must top up later at an uncertain — possibly spiked — spot/cash-out price;
buy too much and you must sell the surplus back, possibly at a loss. This is structurally a
**newsvendor problem**.

### 5.2 The newsvendor / critical-fractile result

Let underage (being short, must buy more) cost $c_u$ per unit and overage (being long, must
sell back) cost $c_o$ per unit, relative to the forward price. If demand $D$ (your volume) has
distribution $F_D$, the cost-minimising hedge is the **critical fractile**:

$$
h^\star \;=\; F_D^{-1}\!\left(\frac{c_u}{c_u + c_o}\right).
$$

Read this directly: if being short is *more* painful than being long ($c_u>c_o$ — typically
true, because cash-out spikes hurt) you hedge *above* the median forecast, i.e. you buy to a
**high quantile** of your volume distribution. This is precisely where the quantile forecasts
of §4.3 become a decision tool rather than a diagnostic: **the optimal hedge volume is a
quantile of the predictive distribution, with the quantile level set by the cost asymmetry.**

A subtlety worth stating, given §2.4: under the GB *single* imbalance price the per-unit
penalty for being short and long is the *same* number ex post, so $c_u$ and $c_o$ are **not**
asymmetric because of dual pricing. The asymmetry that pushes $h^\star$ above the median comes
from the **covariance** term of §2.4 — you tend to be short exactly when cash-out spikes — so
$c_u$ is the *expected* short-side cost conditional on being short, which exceeds the
long-side cost. The newsvendor is the reduced form; the covariance is the mechanism.
The prototype's roadmap item "hedge to q50 but hold battery headroom sized by q10–q90" is a
practical, layered version of this idea.

### 5.3 Beyond the single newsvendor

Real hedging is multi-period and path-dependent (you re-hedge as the horizon shrinks and
information arrives), which generalises to **multistage stochastic programming** and to
risk-aware objectives such as minimising **Conditional Value-at-Risk** (**CVaR**) rather than
expected cost:

$$
\min_{h}\; \mathbb{E}[C(h)] + \lambda\,\text{CVaR}_\alpha[C(h)],
$$

trading expected cost against tail risk via $\lambda$. This is the natural home for the
quantile/scenario outputs of the forecaster and the obvious bridge between §4 and §6.

---

## 6. Short-term optimisation: battery dispatch as a linear program

### 6.1 The deterministic LP

Given a (forecast or actual) net path $\{n_t\}$, a price path $\{\pi_t\}$, and a battery, we
choose per-period charge $c_t\ge 0$, discharge $d_t\ge 0$, state of charge $\text{SoC}_t$, and
grid draw $g_t$ to minimise energy cost. With round-trip efficiency split as charge/discharge
efficiency $\eta$, capacity $\bar E$ (kWh), power rating $\bar P$ (kW) and step
$\Delta t = 0.5$ h:

$$
\begin{aligned}
\min_{c,d,\text{SoC},g}\quad & \sum_{t} \pi_t\, g_t\, \frac{\Delta t}{1000} \\
\text{s.t.}\quad
& g_t = n_t + c_t - d_t && \text{(grid = net + charge − discharge)}\\
& \text{SoC}_t = \text{SoC}_{t-1} + \big(\eta\,c_t - d_t/\eta\big)\,\Delta t && \text{(storage dynamics)}\\
& 0 \le \text{SoC}_t \le \bar E,\quad 0 \le c_t,d_t \le \bar P && \text{(capacity, rate limits)}\\
& \text{SoC}_0 = \sigma_0 \bar E && \text{(initial fill)}
\end{aligned}
$$

This is exactly the `dispatch_lp` formulation. The objective is linear, the constraints are
linear, so it is a **linear program** solved here by **CBC** (Coin-or Branch and Cut) via
PuLP. The double application of $\eta$ — multiply on charge, divide on discharge — encodes a
**round-trip efficiency** of $\eta^2$ (here $0.92^2 \approx 0.85$), a defensible convention
(an alternative splits losses as $\sqrt{\eta_{\text{rt}}}$ each way).

### 6.2 Why LP (not MIP) is the right first cut

Physically, charging and discharging at once is meaningless, which would call for a binary
$z_t\in\{0,1\}$ and the no-simultaneity constraints $c_t\le \bar P z_t$,
$d_t\le \bar P(1-z_t)$ — turning the LP into a **Mixed-Integer Program** (**MIP**). But with
strictly positive prices and $\eta<1$, simultaneous charge/discharge is always cost-increasing,
so the **LP relaxation** almost never does it. Solving the easy LP and checking the solution is
the pragmatic first cut; promote to MIP only when prices can go negative (then the relaxation
*can* cheat) or when no-simultaneity must be guaranteed. The roadmap names exactly this.

### 6.3 The deterministic-optimisation trap (and the fix)

The LP above is solved against a *single* net path. Committed against the **forecast**, the
battery is optimal for a future that will not occur; the deviation flows to cash-out. The
principled responses, in increasing sophistication:

1. **Stochastic / scenario LP** — optimise expected cost over scenarios $\{n_t^{(s)}\}$ drawn
   from the predictive distribution, with the battery schedule as a *here-and-now* decision
   common to all scenarios.
2. **Robust optimisation** — optimise against the worst case within an uncertainty set
   (e.g. the q10–q90 band), trading cost for guarantees.
3. **Model Predictive Control (MPC)** — re-solve every period as new actuals arrive, applying
   only the first action (the roadmap's "intraday re-forecasting"). This is how such systems
   actually run in production.

The notebook's risk-band exercise (settling the *one committed* schedule against q10/q50/q90
realisations) is a lightweight, honest precursor to (1)–(2): it *measures* the cost band the
uncertainty implies before investing in solving the harder stochastic program.

### 6.4 What the simple LP omits

- **Degradation.** Cycling ages a battery. A throughput cost $\kappa\sum_t (c_t+d_t)\Delta t$
  in the objective (or a cycle-count constraint) prevents the optimiser from trading tiny
  price spreads that do not cover wear.
- **Terminal SoC.** With no constraint tying the final SoC to the initial, the LP will
  **drain the battery to empty by the horizon end**, booking the initial stored energy as free
  revenue (see §9 — this is a genuine bug). A constraint $\text{SoC}_{T}\ge \sigma_0\bar E$
  fixes it.
- **Grid limits, export constraints, and the non-commodity stack** (§2.5) — all absent.

---

## 7. Settlement and the value decomposition

### 7.1 How settlement is modelled

You **trade day-ahead to your forecast** grid position $g^{\text{f}}_t$ (the LP's `grid_kw`
computed on the forecast). Reality delivers actual net $n^{\text{a}}_t$; applying the
*pre-committed* battery schedule to the actual net gives the actual grid
$g^{\text{a}}_t = n^{\text{a}}_t + c_t - d_t$. The residual is settled at cash-out:

$$
C \;=\; \underbrace{\sum_t \pi^{\text{DA}}_t\, g^{\text{f}}_t\,\tfrac{\Delta t}{1000}}_{\text{bought ahead}} \;+\; \underbrace{\sum_t \pi^{\text{imb}}_t\, \big(g^{\text{a}}_t - g^{\text{f}}_t\big)\,\tfrac{\Delta t}{1000}}_{\text{imbalance}}.
$$

Because the battery schedule appears in *both* $g^{\text{a}}$ and $g^{\text{f}}$, it cancels
in the residual: $g^{\text{a}}_t - g^{\text{f}}_t = n^{\text{a}}_t - n^{\text{f}}_t$. So **the
imbalance is exactly the forecast error priced at cash-out** — a clean, correct result that is
the conceptual heart of the prototype.

### 7.2 The three-strategy decomposition

| Strategy | Trades to | Battery? | Isolates |
|---|---|---|---|
| **A** perfect foresight | actual net | yes | theoretical cost floor (no imbalance) |
| **B** forecast | forecast net | yes | what you would actually run |
| **C** forecast | forecast net | **no** | — |

- $C - B$ = **the battery's value** (the only difference is the battery).
- $B - A$ = **the cost of forecast error** — the money better forecasting could still recover.

This is the measurable business case for the data-science role: $B-A$ quantifies, in pounds,
the prize for a better model. *A is "perfect foresight valued at the day-ahead price" — it
hardcodes zero imbalance — not a true lower bound on achievable cost (intraday or cash-out
could occasionally beat day-ahead). Read it as a clean reference point, not a hard floor.* *Caveat* (§9): on easy synthetic data $B-A$ is tiny and can even
be negative (forecast error lands in a period where cash-out happened to pay you), so the
decomposition is most informative on real, noisy data.

---

## 8. Putting the loop together

```
        WEATHER (NWP ensembles)            SYSTEM MIX (national, by fuel)
                 │                                   │  features + price formation
                 ▼                                   ▼
   ┌──────────────────────────┐         ┌───────────────────────────┐
   │ FORECAST  n_t  (point +   │◄────────┤  PRICE  π_DA , π_imb      │
   │ q10/q50/q90)              │         └───────────────────────────┘
   └──────────┬───────────────┘
              │ predictive distribution
   ┌──────────▼───────────────┐   hedge to a quantile (newsvendor, §5)
   │ HEDGE / FORWARD BUY       │
   └──────────┬───────────────┘
   ┌──────────▼───────────────┐   LP/MIP/stochastic (§6); commit on forecast
   │ DISPATCH  battery         │
   └──────────┬───────────────┘
   ┌──────────▼───────────────┐   trade DA to forecast; residual → cash-out (§7)
   │ SETTLE  +  PnL  (A/B/C)   │
   └──────────┬───────────────┘
              │  error attribution  ───────────────►  feedback to FORECAST model
              ▼
        money + diagnostics
```

The dashed feedback arrow — *which sites/periods drove residual cost?* — closes the loop from
settlement back to model improvement, and is the roadmap's item 4.

---

## 9. Critical review of the prototype

The code is clean, runs end-to-end (`uv run python loop.py`), and is conceptually honest:
the portfolio/system separation, the leakage discipline in `ctx_from_portfolio`, the
battery-cancels-in-residual identity, and the A/B/C decomposition are all correct and
well-motivated. The issues below are about *modelling fidelity and edge cases*, ordered by
importance.

> **Status (kept for the learning record).** The HIGH and MED items below — terminal SoC
> (9.1.1), non-reproducibility (9.1.2b), quantile crossing (9.2.3) and the convoluted solar
> cloud (9.2.5) — **have since been fixed** in the code, and the coal stack (9.2 / §2.3) has
> been removed to reflect GB going coal-free. The diagnoses are left intact because
> *recognising* these failure modes is the transferable skill; the resolutions are noted inline.

### 9.1 Logic bugs

1. **No terminal state-of-charge constraint (`loop.py::dispatch_lp`).** SoC starts at
   $\sigma_0\bar E = 250$ kWh but nothing prevents the LP from ending at zero. The optimiser
   therefore **sells the initial stored energy for free**, biasing every strategy's cost
   *downward* and inflating apparent battery value. Because A dispatches on actual and B on
   forecast over *different* windows, the bias does not cleanly cancel. **Fix (applied):**
   `prob += soc[T-1] >= soc0_frac * cap_kwh`. This was the most material bug; with it in
   place the battery's measured value drops appreciably (the free end-of-horizon drain is
   gone), which is the correct, more conservative number.

2. **"Cost of forecast error" ($B-A$) can be negative and mixes three effects.** In a typical
   run $B-A$ is a few pounds while B's imbalance term is *negative* (a profit) — but the exact
   figures vary from run to run (see bug 2b) and should not be quoted as precise. Three things
   muddy the metric: (i) on smooth synthetic data, forecast errors land in
   cash-out-favourable periods about as often as not, so the sign is noise; (ii) $B-A$ also
   includes the difference in *day-ahead volume* (A trades to actual, B to forecast), not just
   imbalance, so it is not a pure "forecast error cost"; (iii) **crucially, A and B both
   inherit the terminal-SoC bug (#1) but on *different* net paths** (actual vs forecast), so
   each books a *different* amount of free end-of-horizon energy — this contaminates $B-A$
   directly. Bug 1 and this interpretation problem are, at root, the same defect seen twice.
   For a cleaner metric, report the imbalance term directly and/or the *absolute* imbalance
   volume `abs_imbalance_kwh` (already computed) — and fix bug 1 first.

2b. **Non-reproducible results (`forecast.py::train_forecast`).** The point and quantile
   `GradientBoostingRegressor`s are created with `subsample=0.8` but **no `random_state`**, so
   every run draws different subsamples and every headline number (MAE, $B-A$, imbalance)
   changes between runs. An independent re-run of this prototype produced materially different
   pounds figures from the same code. **Fix (applied):** `random_state=0` on every estimator,
   making runs reproducible. (Exact pounds figures are still kept out of this paper, since they
   depend on data settings; the prototype's own output is the source of truth.)

### 9.2 Modelling simplifications worth flagging

3. **Quantile crossing.** `train_forecast` fits q10/q50/q90 as independent
   `GradientBoostingRegressor(loss="quantile")` models; nothing enforces
   $\hat n^{(0.1)}\le\hat n^{(0.5)}\le\hat n^{(0.9)}$. **Fix (applied):** a post-hoc row-wise
   `np.sort` across the three columns makes the band monotone; isotonic calibration is the
   heavier-duty alternative if crossing is severe.

4. **Cash-out lacks real-world asymmetry.** `synth_price` builds imbalance as day-ahead plus a
   *symmetric* Student-$t$ spread. Real cash-out, even under single pricing, is shaped by the
   *direction* the system is short and exhibits skew and reserve-scarcity adders; a symmetric
   spread lets a naive strategy "profit from imbalance" too easily (see bug 2). Consider a
   skewed/tightness-conditioned shift, not just a tightness-scaled *scale*.

5. **Double-counted, convoluted solar cloud (`data.py::build_portfolio`).**
   Each site's `synth_solar` already applied an independent `beta(6,2)` cloud; the portfolio
   builder then multiplied by a *shared* cloud factor normalised by its own mean. The intent —
   correlated weather so site errors do not fully diversify away — is right and important, but
   the construction was hard to read and the independent per-site cloud partly defeated it.
   **Fix (applied):** `synth_solar` now takes an explicit `cloud` argument, and the builder
   forms each site's cloud as a convex blend `CLOUD_CORR·shared + (1−CLOUD_CORR)·idiosyncratic`
   (in $[0,1]$, no double cloud, one readable correlation knob).
   Suggest generating one shared cloud field and per-site idiosyncratic noise *explicitly*,
   with a documented correlation parameter.

6. **`renewables_share` excludes nuclear/biomass from "low-carbon."** It is wind+solar only.
   Defensible (it targets the *price-suppressing variable* renewables), but the name invites
   confusion with the carbon intensity story; a comment or rename (`vre_share` for variable
   renewables) would help.

7. **Lag-1 actuals stand in for a system forecast.** Honest and clearly documented, but lag-1
   leaks *less-noisy-than-reality* information about mix state into the forecaster, flattering
   skill. The roadmap's move to real Elexon data and a genuine system forecast will close this.

8. **Single 3-day holdout, no walk-forward.** Fine for a prototype; for any quantitative claim
   about skill, a rolling-origin (walk-forward) evaluation with multiple folds is needed, since
   a single split can be lucky.

### 9.3 Minor

- `synth_solar_national` reuses the rooftop bell shape scaled to 15 GW; real national PV has a
  smoother, geographically-smeared profile (less cloud variance per MW). Low priority.
- No grid import/export power limit in dispatch; the battery can drive arbitrarily large
  export. Add a `grid` bound if modelling a constrained connection.
- `MWH = 1000.0` and the repeated `*0.5/1000` factor are correct but un-named; a single
  `MWH_PER_KW_SP = 0.5/1000` constant would reduce the chance of a unit slip later.

**Overall:** an unusually well-conceived teaching prototype. Fixing the terminal-SoC
constraint (bug 1) and tempering the $B-A$ interpretation (bug 2) are the two changes I would
make before drawing any quantitative conclusion from it.

---

## 10. Research roadmap

Ordered to maximise learning-per-unit-effort, building on the README's own list:

1. **Real data.** Swap synthetic price/solar for Elexon BMRS (FUELHH, system prices) and PV
   Live; re-run and watch the forecast-error gap ($B-A$) grow as the series gets noisier — the
   point at which forecasting value becomes measurable.
2. **Fix the LP** (terminal SoC, degradation cost, grid limits) so cost numbers are trustworthy.
3. **Genuine system forecast** to replace lag-1 mix features; ingest **NWP ensembles**
   (Open-Meteo / ECMWF) for solar and load, with separate nowcast vs day-ahead models (§4.5).
4. **Uncertainty-aware dispatch.** Move from the deterministic LP to a scenario/stochastic LP
   or robust formulation that consumes the quantile band (§6.3), then to **MPC** with intraday
   re-forecasting.
5. **Hedge optimisation as newsvendor / CVaR** (§5) — turn the quantile forecast into an actual
   forward-buy quantile decision, with a tunable risk aversion $\lambda$.
6. **Error attribution** — decompose residual cash-out cost by site/period to close the
   feedback loop to model improvement (§8).
7. **Value stacking** — add DUoS red-band avoidance, Capacity Market, and frequency-response
   revenues to the battery objective (§2.5); this is where real C&I economics live.
8. **Calibration as a first-class metric** — track reliability diagrams and CRPS, not just MAE,
   so the quantiles that drive §4–§6 are trustworthy.

---

## Glossary of acronyms

BETTA — British Electricity Trading and Transmission Arrangements · BM — Balancing Mechanism ·
BMU — Balancing Mechanism Unit · BSC — Balancing and Settlement Code · BSUoS — Balancing
Services Use of System · C&I — Commercial & Industrial · CBC — Coin-or Branch and Cut ·
CCGT — Combined Cycle Gas Turbine · CDD/HDD — Cooling/Heating Degree Days · CM — Capacity
Market · CRPS — Continuous Ranked Probability Score · CVaR — Conditional Value-at-Risk ·
DA — Day-Ahead · DUoS/TNUoS — Distribution/Transmission Network Use of System · ECMWF —
European Centre for Medium-Range Weather Forecasts · GB — Great Britain · GHI — Global
Horizontal Irradiance · LP — Linear Program · MAE — Mean Absolute Error · MIP — Mixed-Integer
Program · MPC — Model Predictive Control · MWh/kWh — Mega/kilowatt-hour · NESO — National
Energy System Operator · NETA — New Electricity Trading Arrangements · NWP — Numerical Weather
Prediction · PAR — Price Average Reference · SoC — State of Charge · SP — Settlement Period ·
SRMC — Short-Run Marginal Cost · VRE — Variable Renewable Energy.

---

## References

Cited sparingly — only foundational sources.

1. **Elexon.** *The Balancing and Settlement Code (BSC)* and BSC modification **P305**
   (single imbalance price). The authoritative description of GB imbalance settlement and
   cash-out. https://www.elexon.co.uk/ and https://bscdocs.elexon.co.uk/
2. **NESO (National Energy System Operator).** Balancing Mechanism, demand forecasting and
   system operation. https://www.neso.energy/
3. **Ofgem.** *Targeted Charging Review: Decision* (2019) and electricity market arrangements.
   https://www.ofgem.gov.uk/
4. **Koenker, R., & Bassett, G. (1978).** "Regression Quantiles." *Econometrica*, 46(1),
   33–50. — The foundation of quantile regression / pinball loss.
5. **Gneiting, T., & Raftery, A. E. (2007).** "Strictly Proper Scoring Rules, Prediction, and
   Estimation." *Journal of the American Statistical Association*, 102(477), 359–378. — Proper
   scoring, CRPS; the basis for evaluating probabilistic forecasts.
6. **Hong, T., & Fan, S. (2016).** "Probabilistic electric load forecasting: A tutorial
   review." *International Journal of Forecasting*, 32(3), 914–938. — The standard entry point
   to probabilistic energy forecasting.
7. **Morales, J. M., Conejo, A. J., Madsen, H., Pinson, P., & Zugno, M. (2014).**
   *Integrating Renewables in Electricity Markets: Operational Problems.* Springer. — The
   reference text linking forecasting, market timeline, and stochastic optimisation.
8. **Birge, J. R., & Louveaux, F. (2011).** *Introduction to Stochastic Programming* (2nd ed.).
   Springer. — Newsvendor, multistage stochastic programming, the math under §5–§6.
