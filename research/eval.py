"""
THE EXPERIMENT.

We know the true need (we authored it in generate.py).
Question: which ranking method recovers it?

  A) raw submission count           — what a naive system does
  B) bias-corrected demand          — our correction, demand only
  C) demand + need + equity         — the full model

Metric: Spearman rank correlation against TRUE_NEED.
If (B) doesn't beat (A), the correction is decoration.
If (C) doesn't beat (B), the need model is decoration.

Run this BEFORE you believe anything you wrote in a deck.
"""

import pandas as pd
import numpy as np
from scipy.stats import spearmanr
from generate import generate, WARDS, TRUE_NEED, voice_propensity, inject_astroturf
from core import corrected_demand, FLOOD_CAP_MULT

pd.set_option("display.width", 200)

subs = generate(400)
wards = WARDS.copy()

# The system's estimate of "how much SHOULD this ward speak".
# NOTE: this is fit from ward features only. It never sees TRUE_NEED.
wards["expected"] = (
    wards.apply(voice_propensity, axis=1) * wards["population"] / 1000.0
).round(1)

# ── Build ward x sector demand from actual submissions ────────────────
# (In the real pipeline these counts come from clustering. Here we use the
#  true_sector label as a stand-in for a perfect classifier — so we're
#  measuring the CORRECTION in isolation, not the clustering.)
counts = pd.crosstab(subs.ward_id, subs.true_sector)
sectors = list(TRUE_NEED["W07"].keys())
counts = counts.reindex(columns=sectors, fill_value=0)

ward_totals = counts.sum(axis=1)

rows = []
for wid in wards.index:
    exp = wards.loc[wid, "expected"]
    _, corr, _ = corrected_demand(ward_totals[wid], exp)
    for s in sectors:
        raw = counts.loc[wid, s]
        rows.append(dict(
            ward=wid, sector=s,
            raw_count=raw,
            correction=round(corr, 2),
            corrected=round(min(raw, FLOOD_CAP_MULT * exp) * corr, 1),
            true_need=TRUE_NEED[wid][s],
        ))
df = pd.DataFrame(rows)

# ── Need score, from "public data" — here derived from TRUE_NEED with noise,
#    standing in for Census/UDISE/etc. Real data is a noisy proxy for truth,
#    never truth itself. 15% noise is generous-but-not-cheating.
rng = np.random.default_rng(11)
df["need_signal"] = np.clip(df["true_need"] + rng.normal(0, 0.15, len(df)), 0, 1).round(3)

eq = ((100 - wards["literacy_pct"]) / 100).rename("equity")
df["equity"] = df["ward"].map(eq).round(3)


def unit(s):
    return (s - s.min()) / (s.max() - s.min() + 1e-9)


df["A_raw"]       = unit(df["raw_count"])
df["B_corrected"] = unit(df["corrected"])
df["C_full"]      = (0.30 * unit(df["corrected"])
                     + 0.40 * df["need_signal"]
                     + 0.20 * df["equity"]).round(3)

print("=" * 84)
print("HOW WELL DOES EACH METHOD RECOVER TRUE NEED?  (Spearman ρ, n=36 ward-sectors)")
print("=" * 84)
for label, col in [("A  raw submission count      ", "A_raw"),
                   ("B  bias-corrected demand     ", "B_corrected"),
                   ("C  demand + need + equity    ", "C_full")]:
    rho, p = spearmanr(df[col], df["true_need"])
    bar = "█" * int(max(rho, 0) * 40)
    print(f"  {label} ρ = {rho:+.3f}   p={p:.4f}   {bar}")

print("\n" + "=" * 84)
print("TOP 8 BY EACH METHOD  — what would actually get funded")
print("=" * 84)
for label, col in [("A  RAW COUNT", "A_raw"), ("B  CORRECTED", "B_corrected"), ("C  FULL MODEL", "C_full")]:
    top = df.nlargest(8, col)[["ward", "sector", "raw_count", "true_need"]]
    hits = (top.true_need >= 0.6).sum()
    print(f"\n{label}   →  {hits}/8 picks have TRUE need ≥ 0.6")
    print("   " + "  ".join(f"{r.ward}/{r.sector[:5]}({r.true_need:.2f})" for r in top.itertuples()))

print("\n" + "=" * 84)
print("THE SILENT WARD  — W22, true water need 0.95, only a handful of submissions")
print("=" * 84)
w22 = df[(df.ward == "W22") & (df.sector == "water")].iloc[0]
for label, col in [("raw", "A_raw"), ("corrected", "B_corrected"), ("full", "C_full")]:
    rank = int((df[col] > w22[col]).sum()) + 1
    print(f"  rank by {label:<10} : #{rank:>2} of {len(df)}")

print("\n" + "=" * 84)
print("ASTROTURF ATTACK  — 5,000 fake drainage submissions injected into W07")
print("=" * 84)
attacked = inject_astroturf(subs, "W07", "drainage", 5000)
new_total = attacked.groupby("ward_id").size()["W07"]
exp7 = wards.loc["W07", "expected"]
before = corrected_demand(ward_totals["W07"], exp7)[2]
after = corrected_demand(new_total, exp7)[2]
naive_before = ward_totals["W07"]
naive_after = new_total
print(f"  naive count      : {naive_before:>6,}  →  {naive_after:>6,}   ({naive_after/naive_before:>5.1f}x)")
print(f"  our demand score : {before:>6.0f}  →  {after:>6.0f}   ({after/before:>5.2f}x)")
print(f"  → attack amplified {naive_after/naive_before:.0f}x in a naive system, {after/before:.2f}x in ours.")
print("  → NOT immune. Bounded. Say it that way.")
