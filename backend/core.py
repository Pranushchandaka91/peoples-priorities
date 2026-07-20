"""
People's Priorities — scoring & allocation core.

This is the only part of the system that must be exactly right.
Everything else (ingest, ASR, UI) is plumbing Claude Code can generate.

Design rules, non-negotiable:
  1. No LLM touches the ranking. Every number is traceable arithmetic.
  2. Demand is bias-corrected AND flood-capped by the same mechanism.
  3. Need is computed for every ward whether or not anyone complained.
  4. Allocation is an exact solve, not a greedy sort.
"""

from dataclasses import dataclass, field
from typing import Literal
import numpy as np
import pandas as pd
from ortools.sat.python import cp_model

Sector = Literal["water", "roads", "health", "education", "electricity",
                 "sanitation", "drainage", "transport", "livelihood", "other"]

# Tunables. Exposed as sliders in the dashboard — the MP's office owns these,
# not us. Every change gets written to an audit log.
FLOOD_CAP_MULT = 2.0     # observed submissions capped at N x expected
CORRECTION_MIN = 0.5     # never down-weight a ward more than half
CORRECTION_MAX = 4.0     # never up-weight more than 4x — prevents sparse-data blowup
DAMPING = 0.5            # sqrt. Full ratio (1.0) is unstable on small counts.


# ─────────────────────────────────────────────────────────────
# 1. VOICE MODEL  —  how many submissions *should* this ward produce?
# ─────────────────────────────────────────────────────────────

def fit_voice_model(wards: pd.DataFrame) -> pd.Series:
    """
    Predict expected submission count from ward characteristics ALONE.

    Critical: the features here are all proxies for ABILITY TO COMPLAIN
    (phone, literacy, proximity, population) — never for NEED.
    If you put a need-proxy in here you will divide out the very signal
    you are trying to detect. This is the single easiest way to destroy
    this system without noticing.
    """
    x = (
        wards["population"] / 1000.0
        * (0.35 + 0.65 * wards["smartphone_pct"] / 100.0)
        * (0.50 + 0.50 * wards["literacy_pct"] / 100.0)
        * np.where(wards["is_urban"], 1.25, 1.0)
        * (1.0 / (1.0 + 0.02 * wards["km_to_mp_office"]))
    )
    # Scale so the constituency's expected total matches observed total.
    scale = wards["observed_submissions"].sum() / max(x.sum(), 1e-9)
    return (x * scale).round(1)


def corrected_demand(observed: float, expected: float) -> tuple[float, float, float]:
    """
    Returns (capped_observed, correction_factor, corrected_demand).

    The cap is the anti-flood defense. The correction is the anti-bias defense.
    They are the same line of code. That is not a coincidence — both are
    statements that a ward's submission count carries bounded information.
    """
    capped = min(observed, FLOOD_CAP_MULT * expected)
    ratio = expected / max(capped, 1.0)
    correction = float(np.clip(ratio ** DAMPING, CORRECTION_MIN, CORRECTION_MAX))
    return capped, correction, capped * correction


# ─────────────────────────────────────────────────────────────
# 2. NEED MODEL  —  independent of whether anyone spoke
# ─────────────────────────────────────────────────────────────

def _z(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd > 1e-9 else s * 0.0


def _unit(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    return (s - lo) / (hi - lo) if hi - lo > 1e-9 else s * 0.0 + 0.5


def need_scores(wards: pd.DataFrame) -> pd.DataFrame:
    """Sector-specific deprivation, from public data only. Range [0,1]."""
    n = pd.DataFrame(index=wards.index)
    n["water"]      = _unit(1.0 - wards["tap_coverage_pct"] / 100.0)
    n["health"]     = _unit(_z(wards["km_to_phc"]))
    n["education"]  = _unit(_z(wards["dropout_pct"]) + _z(wards["km_to_school"]))
    n["roads"]      = _unit(-_z(wards["road_km_per_sqkm"]))
    n["sanitation"] = _unit(1.0 - wards["toilet_coverage_pct"] / 100.0)
    for s in ("electricity", "drainage", "transport", "livelihood", "other"):
        n[s] = 0.5  # placeholder until a dataset is wired in — be honest about this
    return n


def equity_scores(wards: pd.DataFrame) -> pd.Series:
    """Structural disadvantage. Deliberately explicit and tunable, not hidden."""
    return _unit(_z(wards["sc_st_pct"]) - _z(wards["literacy_pct"]))


# ─────────────────────────────────────────────────────────────
# 3. WORKS  —  candidate projects
# ─────────────────────────────────────────────────────────────

@dataclass
class Work:
    id: str
    name: str
    ward_id: str
    sector: str
    cost_lakh: float
    beneficiaries: int
    source: str                    # "development_plan" | "derived_from_cluster"
    cluster_submissions: int = 0   # raw count in the matching demand cluster
    rationale: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# 4. PRIORITY
# ─────────────────────────────────────────────────────────────

def score_works(works: list[Work], wards: pd.DataFrame,
                w_demand=0.30, w_need=0.40, w_equity=0.20, w_cost=0.10) -> pd.DataFrame:

    wards = wards.copy()
    wards["expected_submissions"] = fit_voice_model(wards)

    dem = {}
    for wid, r in wards.iterrows():
        capped, corr, d = corrected_demand(r["observed_submissions"], r["expected_submissions"])
        dem[wid] = dict(capped=capped, correction=corr, ward_demand=d,
                        expected=r["expected_submissions"])

    need = need_scores(wards)
    eq = equity_scores(wards)

    rows = []
    for w in works:
        d = dem[w.ward_id]
        # Work-level demand = the work's own cluster size, weighted by its ward's
        # correction factor. A work in an under-reporting ward gets amplified.
        work_demand = min(w.cluster_submissions, FLOOD_CAP_MULT * d["expected"]) * d["correction"]
        rows.append(dict(
            work_id=w.id, name=w.name, ward=w.ward_id, sector=w.sector,
            cost=w.cost_lakh, beneficiaries=w.beneficiaries,
            raw_submissions=w.cluster_submissions,
            correction=round(d["correction"], 2),
            demand_raw=round(work_demand, 1),
            need=round(float(need.loc[w.ward_id, w.sector]), 3),
            equity=round(float(eq.loc[w.ward_id]), 3),
            cost_per_beneficiary=round(w.cost_lakh * 100000 / max(w.beneficiaries, 1)),
        ))
    df = pd.DataFrame(rows).set_index("work_id")

    df["demand"] = _unit(df["demand_raw"]).round(3)
    df["cost_pen"] = _unit(df["cost_per_beneficiary"]).round(3)

    df["priority"] = (
        w_demand * df["demand"]
        + w_need * df["need"]
        + w_equity * df["equity"]
        - w_cost * df["cost_pen"]
    ).round(4)

    return df.sort_values("priority", ascending=False)


# ─────────────────────────────────────────────────────────────
# 5. ALLOCATION  —  exact solve. Not a sort.
# ─────────────────────────────────────────────────────────────

def allocate(scored: pd.DataFrame, budget_lakh: float,
             equity_floor_pct: float = 0.0, priority_wards: list[str] | None = None,
             max_per_sector: int | None = None) -> dict:
    """
    Constrained 0/1 knapsack over candidate works.

    The constraints ARE the MP's political commitments, encoded and guaranteed.
    An LLM asked to 'rank fairly' cannot guarantee a constraint. A solver can.
    """
    m = cp_model.CpModel()
    ids = list(scored.index)
    x = {i: m.NewBoolVar(i) for i in ids}

    SCALE = 100  # CP-SAT is integer-only; scale costs to paise-of-lakh
    cost = {i: int(round(scored.loc[i, "cost"] * SCALE)) for i in ids}
    prio = {i: int(round(scored.loc[i, "priority"] * 10000)) for i in ids}

    m.Add(sum(cost[i] * x[i] for i in ids) <= int(budget_lakh * SCALE))

    if equity_floor_pct > 0 and priority_wards:
        eligible = [i for i in ids if scored.loc[i, "ward"] in priority_wards]
        m.Add(sum(cost[i] * x[i] for i in eligible)
              >= int(equity_floor_pct * budget_lakh * SCALE))

    if max_per_sector:
        for s in scored["sector"].unique():
            in_s = [i for i in ids if scored.loc[i, "sector"] == s]
            m.Add(sum(x[i] for i in in_s) <= max_per_sector)

    m.Maximize(sum(prio[i] * x[i] for i in ids))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    status = solver.Solve(m)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return dict(status="INFEASIBLE", funded=[], note="Constraints cannot be met — relax the equity floor or raise the budget.")

    funded = [i for i in ids if solver.Value(x[i])]
    return dict(
        status=solver.StatusName(status),
        funded=funded,
        total_cost=float(scored.loc[funded, "cost"].sum()),
        total_priority=float(scored.loc[funded, "priority"].sum()),
        beneficiaries=int(scored.loc[funded, "beneficiaries"].sum()),
    )


def allocate_greedy(scored: pd.DataFrame, budget_lakh: float) -> dict:
    """Baseline, purely to demonstrate that the solver beats it. Do not ship."""
    spent, funded = 0.0, []
    for i, r in scored.iterrows():
        if spent + r["cost"] <= budget_lakh:
            funded.append(i); spent += r["cost"]
    return dict(funded=funded, total_cost=spent,
                total_priority=float(scored.loc[funded, "priority"].sum()),
                beneficiaries=int(scored.loc[funded, "beneficiaries"].sum()))


# ─────────────────────────────────────────────────────────────
# 6. RATIONALE  —  the sentence an MP can say out loud in a gram sabha
# ─────────────────────────────────────────────────────────────

def rationale(work_id: str, scored: pd.DataFrame, wards: pd.DataFrame, rank: int) -> str:
    r = scored.loc[work_id]
    w = wards.loc[r["ward"]]
    lines = [
        f"#{rank}  {r['name']}  —  ₹{r['cost']:.0f}L  —  {r['ward']}",
        f"   {int(r['raw_submissions'])} citizen submissions, bias-adjusted x{r['correction']:.2f} "
        f"({'ward under-reports' if r['correction'] > 1 else 'ward over-reports'})",
    ]
    if r["sector"] == "education":
        lines.append(f"   UDISE: dropout {w['dropout_pct']:.0f}% · nearest school {w['km_to_school']:.1f} km")
    elif r["sector"] == "water":
        lines.append(f"   Jal Jeevan: tap coverage {w['tap_coverage_pct']:.0f}%")
    elif r["sector"] == "health":
        lines.append(f"   Nearest PHC: {w['km_to_phc']:.1f} km")
    lines.append(f"   Reaches {r['beneficiaries']:,} people → ₹{r['cost_per_beneficiary']:,.0f} per beneficiary")
    lines.append(f"   Priority {r['priority']:.3f}  =  0.30({r['demand']:.2f}) + 0.40({r['need']:.2f}) "
                 f"+ 0.20({r['equity']:.2f}) − 0.10({r['cost_pen']:.2f})")
    return "\n".join(lines)
