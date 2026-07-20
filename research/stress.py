"""
Option 3: How messy can the government data get before the model stops working?

In eval.py I cheated: need_signal = truth + 15% noise. Real Census/UDISE
data is much worse — old, indirect, sometimes missing.

So: degrade the data step by step, rerun the ranking, watch when it breaks.

Three kinds of mess, applied together:
  noise    — measurement error (survey was sloppy)
  staleness — data is old; blend in what the ward looked like years ago
  missing  — some ward-sector values simply absent; fall back to district avg

30 random trials per level, because one lucky run proves nothing.
"""

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from generate import generate, WARDS, TRUE_NEED, voice_propensity
from core import corrected_demand, FLOOD_CAP_MULT

pd.set_option("display.width", 200)

subs = generate(400)
wards = WARDS.copy()
wards["expected"] = (wards.apply(voice_propensity, axis=1) * wards["population"] / 1000).round(1)

sectors = list(TRUE_NEED["W07"].keys())
counts = pd.crosstab(subs.ward_id, subs.true_sector).reindex(columns=sectors, fill_value=0)
ward_totals = counts.sum(axis=1)

# demand side — fixed, computed once
base = []
for wid in wards.index:
    exp = wards.loc[wid, "expected"]
    _, corr, _ = corrected_demand(ward_totals[wid], exp)
    for s in sectors:
        raw = counts.loc[wid, s]
        base.append(dict(ward=wid, sector=s,
                         corrected=min(raw, FLOOD_CAP_MULT * exp) * corr,
                         true_need=TRUE_NEED[wid][s]))
df0 = pd.DataFrame(base)
eq = ((100 - wards["literacy_pct"]) / 100)
df0["equity"] = df0["ward"].map(eq)

def unit(s):
    return (s - s.min()) / (s.max() - s.min() + 1e-9)

df0["demand_u"] = unit(df0["corrected"])
district_avg = df0["true_need"].mean()

# an old, wrong version of the world — what stale data actually contains.
# (deliberately misordered vs today's truth in several places)
STALE = {w: {s: np.clip(TRUE_NEED[w][s] * 0.6 + 0.25, 0, 1) for s in sectors} for w in TRUE_NEED}
STALE["W22"]["water"] = 0.45   # the crisis is RECENT; old data doesn't show it
STALE["W07"]["drainage"] = 0.20

def degrade(truth, noise_sd, staleness, missing_pct, rng):
    """One noisy, stale, gap-ridden 'public dataset'."""
    out = []
    for _, r in truth.iterrows():
        if rng.random() < missing_pct:
            v = district_avg                        # missing → fallback
        else:
            fresh = r["true_need"]
            old = STALE[r["ward"]][r["sector"]]
            v = (1 - staleness) * fresh + staleness * old
            v = np.clip(v + rng.normal(0, noise_sd), 0, 1)
        out.append(v)
    return np.array(out)

LEVELS = [
    ("pristine        (15% noise — eval.py's cheat)", 0.15, 0.00, 0.00),
    ("decent survey   (25% noise, a bit stale)",      0.25, 0.20, 0.05),
    ("realistic       (30% noise, half-stale, gaps)", 0.30, 0.50, 0.15),
    ("bad             (40% noise, mostly old, gaps)", 0.40, 0.70, 0.25),
    ("garbage         (50% noise, ancient, holes)",   0.50, 0.90, 0.40),
]

TRIALS = 30
print("=" * 96)
print(f"FULL MODEL (0.3·demand + 0.4·need + 0.2·equity) vs TRUTH — {TRIALS} trials per level")
print("=" * 96)
print(f"{'data quality':<48} {'ρ mean':>8} {'ρ worst':>8}  {'W22 water rank':>15}  {'top8 hits':>10}")
print("-" * 96)

results = []
for label, noise, stale, miss in LEVELS:
    rhos, ranks, hits = [], [], []
    for t in range(TRIALS):
        rng = np.random.default_rng(100 + t)
        need = degrade(df0, noise, stale, miss, rng)
        score = 0.30 * df0["demand_u"] + 0.40 * unit(pd.Series(need)) + 0.20 * df0["equity"]
        rho, _ = spearmanr(score, df0["true_need"])
        rhos.append(rho)
        w22_i = df0[(df0.ward == "W22") & (df0.sector == "water")].index[0]
        ranks.append(int((score > score[w22_i]).sum()) + 1)
        top8 = df0.loc[score.nlargest(8).index, "true_need"]
        hits.append(int((top8 >= 0.6).sum()))
    results.append((label, np.mean(rhos), np.min(rhos), np.median(ranks), np.mean(hits)))
    print(f"{label:<48} {np.mean(rhos):>+8.3f} {np.min(rhos):>+8.3f}  "
          f"{'#' + str(int(np.median(ranks))):>15}  {np.mean(hits):>7.1f}/8")

# reference lines
rho_raw, _ = spearmanr(unit(pd.Series(counts.stack().reindex(
    [(r.ward, r.sector) for r in df0.itertuples()]).values)), df0["true_need"])
print("-" * 96)
print(f"{'raw complaint counts (no data at all)':<48} {rho_raw:>+8.3f}")
print(f"{'equity alone (just literacy)':<48} "
      f"{spearmanr(df0['equity'], df0['true_need'])[0]:>+8.3f}")
