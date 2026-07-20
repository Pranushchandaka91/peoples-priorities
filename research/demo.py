"""
Proves the three claims in the pitch with actual arithmetic.
Run this before you print a deck. If a claim doesn't survive here, cut it.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import pandas as pd
from core import (Work, fit_voice_model, corrected_demand, score_works,
                  allocate, allocate_greedy, rationale, FLOOD_CAP_MULT)

pd.set_option("display.width", 200)

# ── Synthetic constituency: 6 wards, deliberately unequal ──────────────
wards = pd.DataFrame([
    # id    pop  lit  phone urban km_off  tap  toilet  phc  drop  school road  scst
    ["W07", 12000, 82, 78, 1,  3, 94, 91, 1.2,  6, 1.1, 4.2, 12],
    ["W11",  9500, 74, 66, 1,  7, 88, 84, 2.1,  9, 1.8, 3.4, 19],
    ["W14", 10500, 61, 47, 0, 18, 61, 58, 5.4, 18, 8.4, 1.9, 34],
    ["W19",  7200, 55, 38, 0, 26, 40, 44, 7.8, 21, 9.6, 1.2, 41],
    ["W22",  9000, 51, 31, 0, 31, 22, 37, 9.1, 24, 7.2, 0.9, 58],
    ["W26",  6100, 68, 58, 0, 12, 77, 71, 3.3, 12, 4.0, 2.6, 22],
], columns=["ward_id", "population", "literacy_pct", "smartphone_pct", "is_urban",
            "km_to_mp_office", "tap_coverage_pct", "toilet_coverage_pct", "km_to_phc",
            "dropout_pct", "km_to_school", "road_km_per_sqkm", "sc_st_pct"]
).set_index("ward_id")

# Observed submissions — the loud wards dominate. This is what reality looks like.
wards["observed_submissions"] = [180, 121, 47, 11, 4, 38]

print("="*78)
print("CLAIM 1 — Bias correction narrows the gap, but does NOT close it.")
print("="*78)
wards["expected"] = fit_voice_model(wards)
rows = []
for wid, r in wards.iterrows():
    capped, corr, dem = corrected_demand(r["observed_submissions"], r["expected"])
    rows.append(dict(ward=wid, urban=bool(r["is_urban"]), phone=r["smartphone_pct"],
                     observed=r["observed_submissions"], expected=r["expected"],
                     correction=round(corr, 2), corrected=round(dem, 1),
                     raw_per_1k=round(r["observed_submissions"] / r["population"] * 1000, 2),
                     corr_per_1k=round(dem / r["population"] * 1000, 2)))
t = pd.DataFrame(rows).set_index("ward")
print(t.to_string())

raw_gap = t.loc["W07", "raw_per_1k"] / t.loc["W22", "raw_per_1k"]
cor_gap = t.loc["W07", "corr_per_1k"] / t.loc["W22", "corr_per_1k"]
print(f"\n  W07 : W22  raw gap       = {raw_gap:5.1f}x")
print(f"  W07 : W22  corrected gap = {cor_gap:5.1f}x   ({(1-cor_gap/raw_gap)*100:.0f}% of the distortion removed)")
print("  → Correction helps. It is NOT sufficient. Say this out loud.\n")

print("="*78)
print("CLAIM 2 — Need + Equity rescue the silent ward, not the correction.")
print("="*78)

works = [
    Work("A", "Bridge over canal",            "W07", "roads",     120, 8000,  "plan", 96),
    Work("B", "Upgrade Govt High School",     "W14", "education",  42, 1240,  "plan", 47),
    Work("C", "Water pipeline + 3 borewells", "W22", "water",      70, 8200,  "cluster", 4),
    Work("D", "PHC equipment upgrade",        "W11", "health",     50, 6400,  "plan", 61),
    Work("E", "Vocational training centre",   "W14", "livelihood", 50,  180,  "plan", 3),
    Work("F", "Storm drains, market road",    "W07", "drainage",   35, 5200,  "plan", 74),
    Work("G", "Link road to block HQ",        "W19", "roads",      65, 4100,  "cluster", 11),
    Work("H", "Toilets + water, 4 schools",   "W22", "sanitation", 28, 2600,  "cluster", 2),
]

scored = score_works(works, wards)
print(scored[["name", "ward", "sector", "raw_submissions", "correction",
              "demand", "need", "equity", "cost_pen", "priority"]].to_string())

print(f"\n  Water pipeline (W22) had FOUR submissions — fewer than any other work.")
print(f"  It ranks #{list(scored.index).index('C')+1} of {len(scored)}.")
print(f"  Demand contributed {0.30*scored.loc['C','demand']:.3f}. "
      f"Need + Equity contributed {0.40*scored.loc['C','need'] + 0.20*scored.loc['C','equity']:.3f}.")
print("  → The data carried it, not the citizens. That is the design.\n")

print("="*78)
print("CLAIM 3 — Solver beats greedy. Same rupees, more delivered.")
print("="*78)
BUDGET = 200.0
g = allocate_greedy(scored, BUDGET)
s = allocate(scored, BUDGET)
print(f"  Greedy : {sorted(g['funded'])}  cost ₹{g['total_cost']:.0f}L  "
      f"priority {g['total_priority']:.3f}  reaches {g['beneficiaries']:,}")
print(f"  CP-SAT : {sorted(s['funded'])}  cost ₹{s['total_cost']:.0f}L  "
      f"priority {s['total_priority']:.3f}  reaches {s['beneficiaries']:,}  [{s['status']}]")
lift = (s['total_priority'] / g['total_priority'] - 1) * 100
blift = (s['beneficiaries'] / max(g['beneficiaries'],1) - 1) * 100
print(f"  → +{lift:.1f}% priority, {blift:+.1f}% beneficiaries, same budget.\n")

print("  With an equity floor (≥30% of budget into W19/W22):")
s2 = allocate(scored, BUDGET, equity_floor_pct=0.30, priority_wards=["W19", "W22"])
print(f"  CP-SAT : {sorted(s2['funded'])}  cost ₹{s2['total_cost']:.0f}L  "
      f"priority {s2['total_priority']:.3f}  [{s2['status']}]")
print("  → A guarantee. Not a suggestion an LLM might forget.\n")

print("="*78)
print("CLAIM 4 — Astroturfing is bounded, not impossible.")
print("="*78)
base_c, base_corr, base_dem = corrected_demand(180, wards.loc["W07", "expected"])
exp7 = wards.loc["W07", "expected"]
print(f"  W07 baseline: observed 180, expected {exp7:.0f} → demand {base_dem:.0f}")
for flood in (500, 2000, 5000, 50000):
    c, corr, dem = corrected_demand(flood, exp7)
    uncapped = flood * min((exp7/max(flood,1))**0.5, 4.0)
    print(f"  flood {flood:>6,} → capped {c:>5.0f} | demand {dem:>5.0f} "
          f"({dem/base_dem:>4.2f}x)   [uncapped would be {uncapped:>6.0f} = {uncapped/base_dem:.1f}x]")
print(f"\n  → Cap is {FLOOD_CAP_MULT}x expected. Attack saturates. "
      f"A 50,000-submission flood buys the same as a 500-submission one.")
print("  → Plus: >3σ burst → quarantine + review queue. Bounded AND visible.\n")

print("="*78)
print("RATIONALE CARDS — what the MP actually reads")
print("="*78)
for rank, wid in enumerate(scored.index[:3], 1):
    print(rationale(wid, scored, wards, rank), "\n")
print(rationale("E", scored, wards, list(scored.index).index("E")+1))
print("\n  ↑ The vocational centre from the problem statement. Ranked, and refuted.")
