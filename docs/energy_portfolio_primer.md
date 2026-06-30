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
**revenue is negative**. Prices are in pounds per MWh (**£/MWh**). One GB **settlement
period** (**SP**) is 30 minutes, so there are 48 per day.

**Energies vs powers — and why we keep them separate.** Settlement, contracts, and the
conservation law that ties them together are statements about **energy** integrated over
the SP. We therefore write every per-SP volume — net position $n_t$, contracts $q^x_t$,
metered outturn, imbalance $\Delta_t$ — in **MWh per SP** unless explicitly marked as a
power. Instantaneous physical signals (load and solar metered traces, battery rate limits,
the LP's charge/discharge decision variables) are naturally **powers** in kW or MW; we
convert via $E = P \cdot \Delta t$ where $\Delta t = 0.5$ h is the current SP length.

The reason for the discipline is that **the energy formulation is invariant under changes
of $\Delta t$** — the EU's 15-minute imbalance settlement period (ISP) reform, the
aggregation of many SPs into a forward block, or any future sub-half-hour ancillary product
— whereas the power formulation requires rescaling every $\Delta t$ that appears. The
prototype code carries some signals in kW for implementation convenience (load curves,
battery rates); this paper labels each quantity with its dimension so a reader can audit
the unit story without having to trust that everything has the same $\Delta t$.

---

## 1. The problem, stated once, cleanly

Let the portfolio's **grid-facing net position** in settlement period $t$ be

$$
n_t \;=\; \underbrace{L_t}_{\text{site load}} \;-\; \underbrace{S_t}_{\text{on-site solar}} \quad [\text{MWh per SP}],
$$

aggregated over all sites in the portfolio. $L_t$ and $S_t$ are the **energies** consumed
and generated in SP $t$ — the integrals of the instantaneous load and solar powers $P^L,
P^S$ over the half-hour. Meters report the underlying power trace; settlement and contracts
care only about its integral $n_t$, which is the quantity hedged, forecast, and dispatched
against. When $n_t>0$ the portfolio is a net *importer*; when $n_t<0$ it is a net
*exporter*. On-site solar is the *only* self-supply on the customer side; a battery adds
**temporal shifting** of that net but creates no new energy.

The customer's total cost over a horizon $\mathcal{T}$, decomposed by the decision layer that
incurs it, is

$$
\boxed{\;C \;=\; \underbrace{C_{\text{fwd}}}_{\text{forward/hedge}} \;+\; \underbrace{C_{\text{DA}}}_{\text{day-ahead}} \;+\; \underbrace{C_{\text{ID}}}_{\text{within-day}} \;+\; \underbrace{C_{\text{imb}}}_{\text{imbalance / cash-out}} \;+\; \underbrace{C_{\text{non-comm}}}_{\text{networks, levies, capacity}}\;}
$$

**Each commodity term has the same shape — price × energy — at its own decision layer.**
With prices in [£/MWh] and contracted/imbalance energies in [MWh], each cost in £ is just
the dot product of the two:

$$
\begin{aligned}
C_{\text{fwd}} &= \sum_{B\in\mathcal{B}} \pi^{\text{fwd}}_B \cdot E^{\text{fwd}}_B && [\pounds] \\
C_{\text{DA}}  &= \sum_t \pi^{\text{DA}}_t  \cdot q^{\text{DA}}_t  && [\pounds] \\
C_{\text{ID}}  &= \sum_t \pi^{\text{ID}}_t  \cdot q^{\text{ID}}_t  && [\pounds] \\
C_{\text{imb}} &= \sum_t \pi^{\text{imb}}_t \cdot \Delta_t          && [\pounds]
\end{aligned}
$$

where:

- $\pi^x_t$ — clearing price in market $x$ for SP $t$ [£/MWh];
- $q^x_t$ — **energy** bought ($q>0$) or sold ($q<0$) at layer $x$ for SP $t$ [MWh]. No $\Delta t$ factor appears — that is the point of carrying contracts as energies in the first place;
- $E^{\text{fwd}}_B$ — total energy of forward **block** $B$ [MWh]. Blocks (months, quarters, seasons) are quoted as a flat **power** $P^{\text{fwd}}_B$ [MW] held over the block's covered SPs (every SP for baseload, peak SPs only for peak blocks); the contracted energy is $E^{\text{fwd}}_B = P^{\text{fwd}}_B \cdot H_B$ with $H_B$ the block's covered duration in hours;
- $\pi^{\text{ID}}_t$ in $C_{\text{ID}}$ is a volume-weighted average of the continuous-market trades that settled into SP $t$ (the intraday market clears continuously up to gate closure, not at a single auction);
- $\Delta_t = q^{\text{actual}}_t - q^{\text{contract}}_t$ [MWh] is the **imbalance energy** — the residual after every prior layer (defined formally in §2.4).

The energies physically clear at every SP — this is a conservation law:

$$
\underbrace{q^{\text{fwd}}_t + q^{\text{DA}}_t + q^{\text{ID}}_t}_{q^{\text{contract}}_t} \;+\; \Delta_t \;=\; q^{\text{actual}}_t \;=\; n_t \quad [\text{MWh per SP}],
$$

i.e. **every MWh consumed in SP $t$ came from *some* layer**, and whatever prior trading
didn't cover is closed by the imbalance residual. **This is why $C_{\text{imb}}$ is the
residual term: it prices the energy your forecasts and trades failed to secure earlier.**
The identity is fundamentally an *energy* balance; the prototype's code happens to carry
the same equation in kW (SP-averaged power), which is equivalent only because every term on
every line has the same $\Delta t$. The equivalence breaks the moment time grids differ —
forward blocks span thousands of SPs, intraday is moving toward 15 min, ancillary services
already run on sub-second windows — which is why the doc writes it in energy.

The final $C_{\text{non-comm}}$ — networks, levies, capacity — is the regulated charge
stack (§2.5) and is not a price × traded-energy term in the same sense; it depends on
metered consumption against published tariffs.

Every commodity term but the last is a *trading* decision taken under uncertainty about
$n_t$ and about prices. The art is that **each term is decided at a different time, against
a different forecast**, and the residual uncertainty cascades down to the cash-out term,
which is the most expensive and least controllable. The entire economic case for a
forecasting and optimisation function is: *push risk up the timeline, where it is cheap to
manage, and out of the cash-out term, where it is dear.*

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
\pi^{\text{DA}}_t \;\approx\; \underbrace{\text{SRMC}^{\text{CCGT}}_t}_{\text{fuel}\,/\,\eta_{\text{th}}\,+\,\text{carbon}} \;+\; \beta_{\text{tight}}\,\text{tightness}_t \;-\; \beta_{\text{ren}}\,\text{renewables-share}_t \;+\; \varepsilon_t,
$$

where, term by term:

- $\pi^{\text{DA}}_t$ — the **day-ahead wholesale clearing price** in SP $t$ (£/MWh); the prototype's `day_ahead` series and the reference "spot" price most analyses use.
- $\text{SRMC}^{\text{CCGT}}_t$ — the **short-run marginal cost** of the marginal CCGT unit, decomposed in the underbrace as:
  - $\text{fuel}/\eta_{\text{th}}$ — the gas spot price (£/MWh of *gas*) divided by the plant's **thermal efficiency** $\eta_{\text{th}}$ (typically $\approx 0.5$–$0.6$ for a modern CCGT), giving £ per MWh of *electricity*. The division reflects that you must burn more than 1 MWh of gas to get 1 MWh of power out. (This $\eta_{\text{th}}$ is unrelated to the battery round-trip efficiency $\eta$ in §6.)
  - $\text{carbon}$ — the **carbon cost** per MWh of electricity = UK/EU ETS allowance price (£/tCO₂) × the plant's emissions intensity (tCO₂/MWh, $\approx 0.35$ for CCGT).
- $\text{tightness}_t$ — **residual demand relative to available flexible capacity** (dimensionless; the prototype normalises residual demand by `FLEX_GAS_REF_MW`, so $\text{tightness} \approx 1$ means the system is running tight).
- $\text{renewables-share}_t = (\text{wind}_t + \text{solar}_t)/\text{demand}_t$ — the share of demand met by variable renewables.
- $\beta_{\text{tight}}, \beta_{\text{ren}} > 0$ — reduced-form sensitivities **[£/MWh]** (since tightness and renewables-share are dimensionless ratios, the betas carry the same units as price). They quantify how many £/MWh of price-lift a one-unit increase in tightness adds, and how many £/MWh a one-unit increase in renewables share takes away. Estimated empirically (e.g. by regression on historical Elexon data).
- $\varepsilon_t$ — a mean-zero residual capturing everything the reduced form omits: unit outages, gas-price shocks, intraday demand surprises, balancing actions feeding back into prompt prices, and pure sentiment.

A stylised picture of the stack ordered cheapest → costliest makes the levers
visible at a glance:

```
£/MWh ↑
      │                                                ┌─ peaking / imports ─┐
      │                                                │   (£200+, scarcity)  │
      │                              ┌──── CCGT ──────┤                      │
      │                              │   (£75–110)    │                      │
      │            ┌── biomass ─────┤                 │                      │
      │            │   + hydro       │                 │                      │
      │   ┌── nuclear (baseload) ───┤                 │                      │
      │   │                          │                 │                      │
      │   │  wind + solar (≈ £0)     │                 │                      │
      └───┴──────────────────────────┴─────────────────┴──────────────────────┴─► MW cumulative
          ↑                          ↑                 ↑                      ↑
        windy night             normal afternoon  cool evening          winter peak
        clears in VRE           clears in CCGT    clears in CCGT        clears in peaking
        (≤ £0 possible)         (≈ £80)           (≈ £100)              (≥ £200, scarcity)
```

Stack blocks ordered low-to-high SRMC, width ∝ available MW. The system clears
at the £/MWh of the most expensive block needed; the demand intercept slides
right as the system tightens. The two structural levers are visible directly:

- **Renewables share** $r_t = (\text{wind}_t+\text{solar}_t)/\text{demand}_t$ pushes price
  *down* — a windy, sunny half-hour can clear at or below zero (negative prices occur when it
  is cheaper to pay to offload than to curtail inflexible plant).
- **System tightness** — residual demand relative to available flexible capacity — pushes
  price *up*, with scarcity spikes when the stack runs into expensive peaking gas and
  imports. (Note GB has been **coal-free** since its last coal station, Ratcliffe-on-Soar,
  closed on **30 September 2024**; the marginal unit is now almost always gas. The prototype
  reflects this — it carries no coal stack and models peak spikes via a convex scarcity term.)

This is exactly the structure the prototype's `synth_price` (in `data.py`)
encodes — CCGT-marginal base, VRE-share suppression, convex scarcity adder near
the flexible-gas headroom; see §9 for caveats. The key intuition for a portfolio
manager: **price and your own net position are both driven by weather and
demand**, so they are *correlated*, and that correlation is where both risk and
opportunity live (you are most likely to be short exactly when the system is
tight and prices spike).

### 2.3.1 Intraday: same fundamentals, refreshed information

The intraday (ID) market trades the same physical commodity as DA — same merit
order (§2.3), same marginal CCGT, same VRE supply, same demand. So ID is
**anchored to DA** and decomposes into a reduced form of the same shape, plus
two ID-specific terms:

$$
\pi^{\text{ID}}_t \;\approx\; \pi^{\text{DA}}_t \;+\;
\underbrace{\beta_r\,\Delta r_t \;+\; \beta_T\,\Delta\text{tightness}_t \;+\; \beta_O\,\Delta\text{outages}_t}_{\text{news between DA gate closure and ID trade time}}
\;+\; \underbrace{\beta_L\,\text{gate-closure pressure}_t}_{\text{liquidity / forced flow}}
\;+\; \varepsilon^{\text{ID}}_t,
$$

where the $\Delta$ terms are the **revisions** in expected VRE share, system
tightness and unit outages between DA gate closure (~noon the previous day)
and the time of the ID trade. Three structural differences from DA matter for
the modeller:

1. **Continuous market, not an auction.** Trades clear bilaterally over time
   right up to **gate closure** (T-1h in GB). What we call "the ID price for
   SP $t$" is a *volume-weighted average* of trades that settled into that SP,
   not a single clearing — exactly the form §1 already writes.
2. **Updated information set.** ID prices incorporate later NWP runs, fresher
   demand actuals, real-time outage news, and BM signals leaking back into
   prompt prices. ID is sharper than DA on the same fundamentals.
3. **Liquidity asymmetry near gate closure.** Order books thin as gate
   approaches; parties with mismatched positions become forced sellers/buyers,
   creating one-sided flow that can dislocate ID from fundamentals briefly.
   This is the $\beta_L$ term above, and has no analogue in DA.

Empirically, the ID-DA spread mean-reverts to ~0 on long samples (no consistent
arbitrage), but has substantial variance — particularly in stressed periods,
where forecast revisions move ID materially. The dominant predictor of the
spread is the **forecast revision** itself: if NWP at H-6 raises expected wind
by 4 GW relative to DA, ID prices compress vs DA in roughly that direction.

**The economic role of ID, in one sentence.** ID is where you trade off the
*update* to your forecast against the *committed* DA position: you bought DA
assuming forecast $\hat n^{\text{DA}}$, intervening news refines it to
$\hat n^{\text{ID}}$, and you re-trade $(\hat n^{\text{ID}} - \hat n^{\text{DA}})$
in ID — paying $\pi^{\text{ID}}_t$ — to shrink the residual that would otherwise
flow to the (more expensive) imbalance settlement at cash-out. This is the
"push risk up the timeline" idea of §1 applied at finer granularity: ID is to
DA what gate closure is to imbalance.

The prototype does not model ID — it trades DA-to-forecast and lets the rest
flow to imbalance (§7.1). Adding an ID layer is a natural extension once
intraday re-forecasting (roadmap #4, §6.3 MPC) is in place: the ID layer
*consumes* the re-forecast and *defends* the DA position against it.

### 2.4 Cash-out (the imbalance price): the term that disciplines everything

Let a party's final notified (contracted) position in SP $t$ be $q^{\text{contract}}_t$
**[MWh per SP]** and its metered outturn $q^{\text{actual}}_t$ **[MWh per SP]** — both are
*energies*, integrals of the corresponding instantaneous powers over the half-hour, exactly
as real BSC settlement files report them. Its **imbalance energy** is

$$
\Delta_t \;=\; q^{\text{actual}}_t - q^{\text{contract}}_t \quad [\text{MWh per SP}].
$$

(The prototype's code carries the same identity in kW (SP-averaged power) for
implementation convenience; that is equivalent only under uniform $\Delta t = 0.5$ h, and
the doc keeps energy as the primary unit so the formulas survive a future change in SP
length — see the abstract.)

Under the GB **single imbalance price** regime (introduced through BSC modification **P305**,
phased in from 2015), *both* directions settle at one price $\pi^{\text{imb}}_t$ per SP — you
no longer face a separate, worse price for being short than for being long. That price is
built from the most expensive balancing actions NESO actually took, averaged over the
**Price Average Reference** (**PAR**) volume (reduced to **1 MWh** in 2018 to make the price
reflect genuinely marginal actions), plus reserve-scarcity adders. The settlement cash flow
to the customer is

$$
C^{\text{imb}}_t \;=\; -\,\Delta_t \,\pi^{\text{imb}}_t \quad [\pounds],
$$

i.e. imbalance energy [MWh] × cash-out price [£/MWh] gives £ directly, with no conversion
factor because $\Delta_t$ is already an energy. Summing over $t$ recovers the
$C_{\text{imb}}$ of §1. The sign convention is that being short ($\Delta_t<0$, used less or
generated more than contracted) and being long are penalised/rewarded symmetrically *at
that period's price*.

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

A delivered C&I price in 2025/26 is roughly **40% commodity + 60% non-commodity**; the
latter is a stack of regulated and policy-driven charges that a real portfolio optimiser
also targets — and that the prototype does *not* model. The components below collectively
explain why a C&I energy function spends more time on tariffs and timing than on wholesale
trading.

#### 2.5.1 Network use of system (regional, time-banded)

- **TNUoS** — **T**ransmission **N**etwork **U**se of **S**ystem. Recovers the cost of the
  GB transmission grid. After the **Targeted Charging Review** (April 2023) the demand
  side has two parts:
  - **Locational demand tariff** in **£/kW** of agreed peak capacity, levied annually
    across 14 GSP zones. Northern Scotland sits near or below zero (a *credit*, reflecting
    that southward flows are expensive); the South West is highest. The spread is on the
    order of **£40–£50/kW/yr** between extremes — a 1 MW peak-coincident site sees that
    much annual difference between siting in Glasgow vs Exeter.
  - **Demand residual** — a fixed standing charge banded by capacity. Total residual
    recovery rose ~60% between 2025/26 and 2026/27 (~£3.8bn → ~£6.4bn).
- **Triad** (historical). Until **April 2023**, the TNUoS demand element was levied on a
  site's three highest national-demand half-hours each winter. "Triad avoidance" was *the*
  C&I flexibility use case for a decade. The TCR replaced it with the fixed
  capacity-based charges above; most pre-2023 literature about C&I storage value still
  assumes Triad exists.
- **DUoS** — **D**istribution **N**etwork **U**se of **S**ystem. Recovers the cost of the
  local distribution network across 14 DNO regions. Two components:
  - **Time-banded unit rate** in p/kWh: **Red / Amber / Green**. Red typically covers
    weekday 16:00–19:00 in winter and is **5–25 p/kWh** depending on region — *several
    times* the Green rate. Shifting load out of Red is the single largest behind-the-meter
    optimisation lever the prototype's `dispatch_lp` could be extended to target.
  - **Capacity charge** in p/kVA/day on Agreed Supply Capacity (**ASC**), restructured
    under Ofgem's **Access SCR** in April 2025: standing charges fell sharply, capacity
    charges roughly doubled. **Right-sizing ASC** is now a procurement decision in its
    own right — over-sized ASC bleeds £/yr regardless of consumption.

#### 2.5.2 Balancing and capacity (national, fixed-ahead)

- **BSUoS** — **B**alancing **S**ervices **U**se of **S**ystem. Recovers NESO's balancing
  cost. Reformed in 2023: now levied as a *fixed-ahead* £/MWh on demand only (suppliers
  fully pass through), removing the previous hedge-able intraday volatility. Typical
  magnitude **£12–14/MWh** in 2026/27.
- **Capacity Market (CM)**. Pays generators and Demand-Side Response providers a fixed
  £/kW/yr to be available at peak. Auctions run **T-4** (four years ahead, the main
  auction) and **T-1** (one year ahead, a top-up). The cost is recovered from suppliers
  on a £/MWh-equivalent basis (the "smeared" unit rate), expected to exceed **£10/MWh**
  in winter 2025/26. A flexible C&I site can *receive* CM revenue by derating its load
  during the peak window — a value-stack the prototype does not model.

#### 2.5.3 Policy levies (national, flat pass-through)

- **RO** (**R**enewables **O**bligation; closed to new generation 2017 but recovery runs
  until 2037) — ~**3.28 p/kWh** in 2025/26.
- **CfD** (**C**ontracts for **D**ifference). The LCCC levies a top-up cost on suppliers
  to fund CfD generators; ~**£10/MWh** in early 2026.
- **FiT** (**F**eed-in **T**ariff; closed scheme). Recovered nationally; ~**1.0 p/kWh**.
  CPI-indexed from April 2026 (previously RPI).
- **CCL** (**C**limate **C**hange **L**evy) — **0.775 p/kWh** on electricity for business
  consumers; lower for holders of a **CCA** (Climate Change Agreement, voluntary
  energy-intensity commitment).

#### 2.5.4 Reference magnitudes (2025/26 illustrative)

| Component | Typical magnitude | Regional? | Time-of-day? |
|---|---|---|---|
| TNUoS locational demand | £0 – £50/kW/yr of peak capacity | yes (14 GSP zones) | annual fixed |
| TNUoS demand residual | £/site/day, banded by ASC | mild | annual fixed |
| DUoS unit rate (Red/Amber/Green) | 0.1 – 25 p/kWh | yes (14 DNOs) | yes (half-hourly) |
| DUoS capacity | 5 – 25 p/kVA/day on ASC | yes | flat |
| BSUoS | ~£12–14/MWh | no | fixed ahead |
| Capacity Market (smeared) | ~£10/MWh | no | flat |
| RO | ~3.28 p/kWh | no | annual |
| CfD (interim levy) | ~£10/MWh | no | fluctuates |
| FiT | ~1.0 p/kWh | no | annual |
| CCL | 0.775 p/kWh | no | annual |

These are order-of-magnitude figures for the modelling intuition this primer is meant to
build; production work pulls the live NESO TNUoS statements and DNO LC14 statements. The
takeaway for the modelling: **non-commodity charges are dominated by `regional × banded`
structure**, so any extension of `dispatch_lp` toward bill optimisation needs a region
identifier and a Red/Amber/Green calendar, not just wholesale prices.

#### 2.5.5 Ancillary / flexibility revenues (the value stack)

A battery or flexible load can *earn* on top of wholesale arbitrage by stacking:

- **Frequency response** products — Dynamic Containment (DC), Dynamic Moderation (DM),
  Dynamic Regulation (DR). NESO procures these to keep system frequency near 50 Hz; fast
  batteries are the natural provider. Frequency-services share of GB BESS revenue fell
  from ~80% (2022) to ~20% (2024) as the market saturated [10].
- **Balancing Mechanism (BM)** participation as a registered **BMU**. Submit bids/offers
  to NESO; accepted volumes settle at the BM price. The dominant earner today.
- **Demand Flexibility Service (DFS)** — a NESO-run scheme that pays load to turn down
  during declared winter windows.

Empirically, two-hour GB BESS revenue averaged ~**£73k/MW/yr** over the twelve months to
April 2026, with wholesale + BM contributing ~60% of the stack [10]. The prototype models
*only* wholesale arbitrage + imbalance — value stacking is the largest gap between this
model and a real C&I battery business case (see roadmap, §10 #7).

### 2.6 Structural changes on the horizon

Two regulatory programmes are reshaping assumptions baked into §2.2–§2.5 and worth
flagging because they bound the lifetime of any model built against today's GB:

- **MHHS** — **M**arket-wide **H**alf-**H**ourly **S**ettlement. Rolling out through 2025
  with phased completion targeted across 2026: every non-half-hourly meter (residential
  and small SME, historically settled on a *profile*) is migrated to true HH settlement.
  The relevance for this primer is the same as the §1 footnote: *the energy-form identity
  survives any change in settlement granularity, the power-form does not*. MHHS-derived
  data infrastructure is also what would make a future migration to 15-minute settlement
  (in line with the EU's ISP) operationally possible.
- **REMA** — **R**eview of **E**lectricity **M**arket **A**rrangements. A multi-year
  programme considering, among other things, replacing GB's single national clearing
  price (§2.3) with **zonal pricing** — distinct prices for, say, 7–12 GB zones reflecting
  transmission constraints. The single-price assumption is the most material model-risk
  in this primer: every closed-form result above carries an implicit "given GB's current
  pricing arrangements" qualifier. If enacted, three changes propagate:
  - the §2.3 reduced form holds **per zone**, with an explicit basis between zones to be
    modelled and (potentially) hedged;
  - the §2.5.1 TNUoS locational signal partly collapses into the spot price itself, so
    the relative importance of network charges vs energy shifts;
  - PPA valuations become explicitly locational — a wind PPA's capture price now depends
    on the zone it sits in, not just its technology (§5.5 #3).

A real procurement function tracks REMA delivery dates and structures contracts with
zonal triggers; a learning prototype can defer this, but the documentation should be
honest that the simplification is doing real work.

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
- **Economic forecast-error gap** ($B-A$, §7.2): the absolute energy residual $|\Delta_t|$ is
  tiny — a handful of MWh over the test window — because the synthetic net is smooth, so
  the money left on the table is small even though skill is high.

So the README's "the forecast is easy" refers to the **small absolute residual**, not to a
strong naive baseline. On *real, noisy* data both the residual and the economic gap widen,
which is when forecasting value becomes measurable in pounds. **The economic value of a
forecaster is set by the irreducible noise it removes from the cash-out term, not by its
headline skill over a baseline.**

### 4.5 Where the weather comes in

Both legs of $n_t = L_t - S_t$ are weather-driven, on different horizons:

- **Solar.** Decompose PV output once, into a deterministic clear-sky envelope and a
  stochastic clear-sky index. The instantaneous PV **power** is
  $$P^S(s) \;\approx\; \eta_{\text{PV}}\,A\,\text{GHI}^{\text{clear}}(s)\,k(s) \quad [\text{W}],$$
  where $\eta_{\text{PV}}$ is the **panel + system efficiency** (DC→AC, soiling,
  temperature derate; typically $\approx 0.15$–$0.20$ for a modern installation), $A$ is
  the **panel area** [m²], $\text{GHI}^{\text{clear}}(s)$ is the **clear-sky** Global
  Horizontal Irradiance [W/m²] — a closed-form function of solar geometry (date, time,
  latitude) — and $k(s) \in [0,1]$ is the **clear-sky index**, the stochastic attenuation
  due to cloud, aerosols, dust, etc. The **energy** that enters the conservation identity
  of §1 is the SP integral $S_t = \int_{\text{SP } t} P^S(s)\,ds$ [MWh per SP] — typically
  approximated as $\bar P^S_t \cdot \Delta t$ with $\bar P^S_t$ the SP-averaged PV power.
  **A robust pipeline forecasts $k_t = \bar P^S_t / \bar P^{S,\text{clear}}_t$** rather
  than $\bar P^S_t$ directly: $k_t$ is far more stationary across seasons and latitudes
  than the raw output it scales, so the same model generalises across sites and months.
  (The prototype's `synth_solar` in `data.py` carries the same decomposition implicitly —
  a `seasonal × bell` envelope times a beta-distributed cloud factor — without naming
  $k_t$ explicitly.)
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

**A worked toy.** Suppose forecast volume $D \sim \mathcal{N}(5,\,1^2)$ MWh, the
front-quarter forward trades at $\pi^{\text{fwd}}=£85$/MWh, the *expected short-side
cash-out* (averaged over the half-hours in which we end up short — i.e. tight system,
spiking prices) is $\mathbb{E}[\pi^{\text{imb}} \mid D>h] = £120$/MWh, and the
*expected long-side cash-out* (we are long when the system is slack and prices have
dropped) is $\mathbb{E}[\pi^{\text{imb}} \mid D<h] = £55$/MWh. Then
$c_u = 120 - 85 = £35$/MWh, $c_o = 85 - 55 = £30$/MWh, the critical fractile is
$c_u/(c_u+c_o) = 35/65 \approx 0.54$, and
$h^\star = F_D^{-1}(0.54) = 5 + 1\cdot\Phi^{-1}(0.54) \approx 5.10$ MWh —
hedge to the **54th percentile**, slightly above the median. Notice the
asymmetry comes entirely through the *conditional* expectations of cash-out, not
through any difference in the headline imbalance price formula. The covariance of
§2.4 is the *only* reason the optimal hedge is not exactly at the median.

### 5.3 Beyond the single newsvendor

Real hedging is multi-period and path-dependent (you re-hedge as the horizon shrinks and
information arrives), which generalises to **multistage stochastic programming** and to
risk-aware objectives. **Conditional Value-at-Risk** at level $\alpha$ — the expected
cost *conditional on being in the worst $1-\alpha$ tail*,

$$
\text{CVaR}_\alpha(C) \;=\; \mathbb{E}\big[C \,\big|\, C \ge \text{VaR}_\alpha(C)\big],
$$

where $\text{VaR}_\alpha(C) = \inf\{c : \Pr(C \le c)\ge\alpha\}$ is the $\alpha$-quantile
of the loss — is the standard coherent risk measure (unlike variance, it is sub-additive
and convex, so portfolio diversification provably helps). Minimising

$$
\min_{h}\; \mathbb{E}[C(h)] + \lambda\,\text{CVaR}_\alpha[C(h)]
$$

trades expected cost against tail risk via $\lambda \ge 0$. This is the natural home for
the quantile/scenario outputs of the forecaster and the obvious bridge between §4 and §6.

### 5.4 The procurement stack in practice

The newsvendor of §5.2 collapses procurement into a single quantity decision. In a real
C&I procurement function the decision is a **stack** with four orthogonal axes — choose
each independently, optimise the joint:

1. **Hedge ratio** $\rho \in [0,1]$ — the fraction of forecast volume locked at any
   point in time. Buyers run a target ratio that *increases* as delivery approaches
   (more of next month locked than of next year), reflecting that volume uncertainty
   falls as the horizon shrinks.

2. **Tenor** — standardised forward block lengths. The GB OTC market trades:
   - **Month** (`M+1`, `M+2`, …) — the next calendar months.
   - **Quarter** (`Q+1`, …) — calendar quarters.
   - **Season** — `Sum` (Apr–Sep) and `Win` (Oct–Mar), the legacy GB front product.
   - **Calendar year** (`Cal+1`, e.g. `Cal-27`) — the most liquid long-dated tenor.

   Within each tenor, the **baseload** block is 24×7 across all SPs and the **peak**
   block is working-day daytime (conventionally Mon–Fri 07:00–19:00). An **off-peak**
   position is built implicitly as `baseload − peak` rather than traded directly.

3. **Product type** — three families, distinct in *who bears which risk*:
   - **Fixed-shape block.** A forward at a fixed £/MWh for a flat MW shape. The buyer
     bears the *shape risk* — anything consumed off-shape settles at spot/cash-out.
   - **PPA** (Power Purchase Agreement; see §5.5). A bilateral long-dated contract
     delivering a *generator's* output. Transfers price risk to the buyer but introduces
     shape risk and cannibalisation of a particular kind.
   - **Index / spot** — pay $\pi^{\text{DA}}_t$ as it clears, with a fixed supplier
     margin. Zero price hedge; minimum cost in falling markets, maximum in rising.

4. **Trade timing — layering / "click" strategies.** Rather than fix the target ratio
   in a single trade, buyers *layer* over time: e.g. fix 10% of `Cal-27` each month
   from `M-18` to `M-9`, then hold. On average (by Jensen, with martingale forwards) the
   ex-ante expected cost is the same as a single trade at the mean; layering trades
   expected cost against *regret variance* — behavioural insurance against picking a bad
   trade date, valuable when the procurement function is judged ex post.

A typical C&I cover position at $\tau$ months before delivery year $Y$ then aggregates as

$$
\text{cover}^{(Y)}_\tau \;=\; \underbrace{\sum_B \rho^{\text{block}}_{B,\tau}\, E^{\text{block}}_B}_{\text{flexible blocks (deterministic energy)}} \;+\; \underbrace{\sum_g \rho^{\text{PPA}}_{g,\tau}\, \mathbb{E}\!\left[E^{\text{PPA}}_{g,\tau}\right]}_{\text{PPAs (random energy, taken in expectation)}} \;+\; \underbrace{(\text{spot residual})_{\tau}}_{\text{index}}.
$$

The optimisation problem is to choose $\{\rho^{\text{block}}_B,\rho^{\text{PPA}}_g\}$ —
the pre-commitment quantities — under joint price and volume uncertainty, subject to a
tail-risk constraint (CVaR, §5.3) and any policy constraint (e.g. **Scope 2** carbon
targets that mandate a minimum renewable share, forcing a minimum PPA fraction).

This is precisely the problem the prototype's roadmap items 4–5 implement, and is the
natural consumer of the quantile forecasts produced by §4 and the price scenarios from
the §2.3 reduced form.

### 5.5 PPAs: shape risk and cannibalisation

A **Power Purchase Agreement** is a bilateral long-term (typically 10–20 year) contract
for the output of a specific generator $g$, at an agreed **strike** $K$ [£/MWh] —
sometimes inflation-indexed, sometimes fixed-nominal. In GB, **corporate PPAs** today
are almost exclusively renewable (wind, solar, increasingly battery hybrids), motivated
on the buyer side by **Scope 2** / **REGO** (Renewable Energy Guarantees of Origin)
claims and on the seller side by the need to underwrite project financing.

Two contract forms:

- **Physical PPA.** Generation $G_t$ flows into the buyer's settlement account via a
  route-to-market intermediary; the buyer pays $K \cdot G_t$ for every MWh delivered.
- **Virtual PPA (vPPA / "synthetic").** No physical delivery — a financial **contract
  for differences** on $\pi^{\text{DA}}_t$. If $\pi^{\text{DA}}_t > K$ the *generator*
  pays the buyer $(\pi^{\text{DA}}_t - K)\cdot G_t$; if below, the *buyer* pays. The
  buyer continues to consume the spot market and uses the vPPA cash flow as a price
  hedge plus a REGO claim. vPPAs dominate corporate PPAs in 2026 because they are
  legally simpler and decouple the hedge from the buyer's physical supply chain.

Per-SP cost from a vPPA covering generation $G_t$ [MWh per SP]:

$$
C^{\text{PPA}}_t \;=\; (K - \pi^{\text{DA}}_t)\,G_t \quad [\pounds],
$$

with $C^{\text{PPA}}_t < 0$ (revenue to the buyer) whenever $\pi^{\text{DA}}_t > K$.

**Three risks distinguish a PPA from a flat baseload block.**

**1. Shape risk.** $G_t$ is the *generator's* shape, not the buyer's load. A
midday-peaking solar PPA partially hedges a daytime cooling load but barely touches a
winter evening peak. The mismatch $\sum_t |G_t - \alpha\, n_t|$, for the volume scaler
$\alpha = \mathbb{E}[\sum_t n_t]/\mathbb{E}[\sum_t G_t]$, is the residual that must
still be procured in shorter-dated markets.

**2. Cannibalisation (capture-price erosion).** A renewable asset only earns
$\pi^{\text{DA}}_t$ when it is generating. Because *all* solar generates at the same
times — and similarly for wind — high VRE penetration *depresses the very prices the
asset captures*. Formally, the asset's **capture price** is the generation-weighted
average

$$
\bar\pi^{\text{cap}}_g \;=\; \frac{\sum_t G^g_t\, \pi^{\text{DA}}_t}{\sum_t G^g_t},
$$

and the **capture rate** $\bar\pi^{\text{cap}}_g / \overline{\pi^{\text{DA}}}$ falls as
the fleet of like technology grows. In §2.3's reduced form, $\beta_{\text{ren}}\,r_t$ is
precisely the cannibalisation channel: $r_t$ rises *when* $G^g_t$ is high, so the price
the asset earns is systematically below the time-averaged spot. The prototype's
`vre_share` and `vre_mw` series in `data.py` carry the same information; pricing a PPA
correctly means evaluating $K$ against $\bar\pi^{\text{cap}}_g$ rather than against the
headline forward curve.

**3. Basis risk.** Even with $\Delta t$ matching, the asset's locational marginal price
(in a future zonal world — §2.6) or its imbalance settlement vs the DA reference may
differ from the contract reference. Basis is small in GB today, material under REMA's
zonal scenarios.

**A defensible PPA fair value.** The buyer's mark-to-market is

$$
\text{MtM} \;=\; \mathbb{E}\!\left[\sum_t (K - \pi^{\text{DA}}_t)\,G^g_t\right]
\;=\; K\,\mathbb{E}\!\left[\sum_t G^g_t\right] \;-\; \sum_t \mathbb{E}\!\left[\pi^{\text{DA}}_t G^g_t\right],
$$

and the second term is *not* $\sum_t \mathbb{E}[\pi^{\text{DA}}_t]\cdot \mathbb{E}[G^g_t]$
— the covariance penalty $\sum_t \text{Cov}(\pi^{\text{DA}}_t, G^g_t)$ (negative for
correlated renewables) is the cannibalisation discount expressed in pounds. Pricing
reduces to a *joint* model of $(\pi^{\text{DA}}, G^g)$ with the right correlation
structure — which the §2.3 reduced form already provides at the population level
(windier hours have both higher $G^{\text{wind}}_t$ and lower $\pi^{\text{DA}}_t$).
Modern practice for harder joint distributions uses **deep hedging** [9] — training a
neural network to replicate the residual exposure via trades in the available
forwards — when closed-form solutions are out of reach.

---

## 6. Short-term optimisation: battery dispatch as a linear program

### 6.1 The deterministic LP

**This section is the one place in the doc that takes its decision variables in power
units, deliberately.** Battery rate limits ($\bar P$ kW) and SoC capacity ($\bar E$ kWh)
are physical specs of the asset, not energies-per-SP. So the LP variables — charge $c_t$,
discharge $d_t$, grid draw $g_t$ — are SP-averaged powers [kW]; their corresponding
energies are $E^c_t = c_t \Delta t$, etc. We mark this slight notation switch explicitly:

> *Within this section,* $n_t$ *is the SP-averaged net **power** [kW] — i.e. the §1 net
> energy divided by $\Delta t$. The two views are interchangeable here because every SP has
> the same length.*

With round-trip efficiency split as charge/discharge efficiency $\eta$, capacity $\bar E$
[kWh], power rating $\bar P$ [kW] and step $\Delta t = 0.5$ h:

$$
\begin{aligned}
\min_{c,d,\text{SoC},g}\quad & \sum_{t} \pi_t\, g_t\, \tfrac{\Delta t}{1000} && \text{(£/MWh × kW × h / 1000 = £)}\\
\text{s.t.}\quad
& g_t = n_t + c_t - d_t && \text{[kW]: power balance over SP } t\\
& \text{SoC}_t = \text{SoC}_{t-1} + \big(\eta\,c_t - d_t/\eta\big)\,\Delta t && \text{[kWh]: storage dynamics}\\
& 0 \le \text{SoC}_t \le \bar E,\quad 0 \le c_t,d_t \le \bar P && \text{[kWh] / [kW]: capacity, rate limits}\\
& \text{SoC}_0 = \sigma_0 \bar E && \text{[kWh]: initial fill}
\end{aligned}
$$

The objective's $\Delta t / 1000$ factor is the single legitimate use of the unit
conversion in this paper: it turns the LP's power decision variable $g_t$ into the energy
$E^g_t = g_t \Delta t / 1000$ [MWh per SP] that the price actually multiplies. **Equivalent
energy-form LP.** Substitute energy decision variables $E^c_t = c_t \Delta t /1000$,
$E^d_t = d_t \Delta t /1000$, $E^g_t = g_t \Delta t /1000$ [MWh] and the LP becomes:
objective $\sum_t \pi_t \cdot E^g_t$ (no conversion factor), conservation $E^g_t = n_t +
E^c_t - E^d_t$ in MWh, rate limit $E^c_t \le \bar P \cdot \Delta t / 1000$, SoC dynamics
$\text{SoC}_t = \text{SoC}_{t-1} + \eta E^c_t - E^d_t/\eta$ (state and capacity bound now
in MWh: $\bar E_{\text{MWh}} = \bar E_{\text{kWh}}/1000$). Both formulations have the same
optimum; the power form matches the prototype's `dispatch_lp` 1:1, the energy form is
invariant under $\Delta t$ change. Use whichever the rest of your stack speaks.

This is exactly the `dispatch_lp` formulation (power form). The objective is linear, the
constraints are linear, so it is a **linear program** solved here by **CBC** (Coin-or
Branch and Cut) via PuLP. The double application of $\eta$ — multiply on charge, divide on
discharge — encodes a **round-trip efficiency** of $\eta^2$ (here $0.92^2 \approx 0.85$), a
defensible convention (an alternative splits losses as $\sqrt{\eta_{\text{rt}}}$ each way).

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

You **trade day-ahead to your forecast** grid position. Let $E^{g,f}_t$ [MWh per SP] be the
forecast grid energy in SP $t$, computed from the LP's power output $g^f_t$ [kW] as
$E^{g,f}_t = g^f_t \Delta t / 1000$. Reality delivers actual net energy $n^a_t$ [MWh];
applying the *pre-committed* battery schedule to the actual net gives the actual grid
energy $E^{g,a}_t = n^a_t + (c_t - d_t)\Delta t / 1000$ [MWh]. The residual is settled at
cash-out:

$$
C \;=\; \underbrace{\sum_t \pi^{\text{DA}}_t\, E^{g,f}_t}_{\text{bought ahead}} \;+\; \underbrace{\sum_t \pi^{\text{imb}}_t\, \big(E^{g,a}_t - E^{g,f}_t\big)}_{\text{imbalance}} \quad [\pounds].
$$

Each term is price [£/MWh] × energy [MWh]; the $\Delta t / 1000$ conversion lives once,
where the LP's power outputs cross into the energy world, not in every cost formula.
Because the battery schedule appears in *both* $E^{g,a}$ and $E^{g,f}$, it cancels in the
residual:

$$
E^{g,a}_t - E^{g,f}_t \;=\; n^a_t - n^f_t \quad [\text{MWh per SP}].
$$

So **the imbalance is exactly the energy forecast error priced at cash-out** — a clean,
correct result that is the conceptual heart of the prototype, and one that survives any
change of $\Delta t$ because it never mentions $\Delta t$.

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
9. **Limmer, B., et al. (2025).** "Deep Hedging of Green PPAs in Electricity Markets."
   arXiv:2503.13056. https://arxiv.org/abs/2503.13056 — A data-driven hedging policy for
   the joint price/quantity risk of §5.5; entry point to deep-hedging adapted to
   electricity, where the joint $(\pi, G)$ distribution is too complex for closed-form
   PPA valuation.
10. **Modo Energy.** "How does a battery energy storage system make money?"
    https://modoenergy.com/research/en/how-does-battery-energy-storage-make-money —
    Practitioner reference for the GB BESS revenue stack discussed in §2.5.5 (frequency
    response share, BM dominance, ~£73k/MW/yr 2-hour BESS benchmark) and roadmap §10 #7.
