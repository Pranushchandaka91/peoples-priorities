"""
FALSE CLOSURE EXPERIMENT

Question: if some verifiers (sarpanches) falsely mark issues "fixed",
how long does reversal-tracking take to isolate them — and how many
HONEST verifiers get falsely flagged along the way?

The second number decides whether this is governance or harassment.

World:
  12 panchayats. Each month, broken assets generate verification tasks.
  Honest verifier: actually fixes (mostly — repairs sometimes fail anyway).
  Cheater: some fraction of closures are lies; asset stays broken.

Signals after a closure:
  - complainant confirmation ping (answered only sometimes; sometimes
    wrong out of grudge; sometimes coerced into "yes" by the sarpanch)
  - re-complaints from reality if the asset is still broken

A closure contradicted within 2 months = a REVERSAL.
Flag rule: Wilson lower bound of verifier's reversal rate > threshold,
with a minimum number of closures (so nobody is flagged off 2 data points).

30 trials. Report medians and worst cases, not best cases.
"""

import numpy as np

# ── world parameters (every one is a judgment call — argue with them) ──
N_MONTHS        = 24
TASKS_PER_MONTH = 6        # verification tasks per panchayat per month
REPAIR_FAILS    = 0.08     # honest fix breaks again anyway (monsoon, wear)
P_RESPOND       = 0.50     # complainant answers the confirmation ping
P_TRUTHFUL_NO   = 0.85     # if still broken, says "not fixed" (rest: coerced/confused)
P_GRUDGE_NO     = 0.08     # if genuinely fixed, says "not fixed" anyway
P_RECOMPLAIN    = 0.55     # still-broken asset draws a new complaint next month
FLAG_THRESHOLD  = 0.18     # Wilson lower bound above this → flagged
MIN_CLOSURES    = 12       # no flags before this many closures

VERIFIERS = (
    [("H%02d" % i, 0.00) for i in range(9)]      # 9 honest (0% lie rate)
    + [("CHEAT_A", 0.60), ("CHEAT_B", 0.35), ("CHEAT_C", 0.20)]
)   # lie rate = fraction of tasks falsely closed without fixing


def wilson_lower(k, n, z=1.96):
    if n == 0:
        return 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom)


def run_trial(rng):
    stats = {v: dict(closures=0, reversals=0, flagged_month=None) for v, _ in VERIFIERS}
    pending = []   # (verifier, month_closed, actually_fixed) awaiting reality's verdict

    for month in range(1, N_MONTHS + 1):
        # reality responds to earlier closures (re-complaints within 2 months)
        still_pending = []
        for v, m0, fixed in pending:
            if month - m0 <= 2:
                if (not fixed) and rng.random() < P_RECOMPLAIN:
                    stats[v]["reversals"] += 1          # caught by recurrence
                else:
                    still_pending.append((v, m0, fixed))
        pending = still_pending

        for v, lie_rate in VERIFIERS:
            for _ in range(TASKS_PER_MONTH):
                lies = rng.random() < lie_rate
                fixed = (not lies) and (rng.random() > REPAIR_FAILS)
                stats[v]["closures"] += 1

                # complainant confirmation ping
                reversed_now = False
                if rng.random() < P_RESPOND:
                    if not fixed and rng.random() < P_TRUTHFUL_NO:
                        reversed_now = True
                    elif fixed and rng.random() < P_GRUDGE_NO:
                        reversed_now = True              # unfair reversal on honest work
                if reversed_now:
                    stats[v]["reversals"] += 1
                else:
                    pending.append((v, month, fixed))

            s = stats[v]
            if (s["flagged_month"] is None and s["closures"] >= MIN_CLOSURES
                    and wilson_lower(s["reversals"], s["closures"]) > FLAG_THRESHOLD):
                s["flagged_month"] = month
    return stats


TRIALS = 30
flag_months = {v: [] for v, _ in VERIFIERS}
false_flags_per_trial = []

for t in range(TRIALS):
    rng = np.random.default_rng(500 + t)
    stats = run_trial(rng)
    ff = 0
    for (v, lie), _ in zip(VERIFIERS, range(len(VERIFIERS))):
        fm = stats[v]["flagged_month"]
        if fm is not None:
            flag_months[v].append(fm)
            if lie == 0.0:
                ff += 1
    false_flags_per_trial.append(ff)

print("=" * 74)
print(f"REVERSAL TRACKING — {TRIALS} trials, {N_MONTHS} months, "
      f"{TASKS_PER_MONTH} tasks/mo, flag if Wilson-LB > {FLAG_THRESHOLD:.0%}")
print("=" * 74)
print(f"{'verifier':<10} {'lie rate':>9} {'flagged in':>12} {'median month':>14} {'worst':>7}")
print("-" * 74)
for v, lie in VERIFIERS:
    fm = flag_months[v]
    n = len(fm)
    med = f"#{int(np.median(fm))}" if fm else "—"
    worst = f"#{max(fm)}" if fm else "—"
    print(f"{v:<10} {lie:>8.0%} {n:>7}/{TRIALS:<4} {med:>14} {worst:>7}")

hf = sum(false_flags_per_trial)
print("-" * 74)
print(f"honest verifiers falsely flagged: {hf} verifier-flags across {TRIALS} trials "
      f"({hf/(9*TRIALS):.1%} of honest verifier-trials)")
print(f"trials with ≥1 false flag: {sum(1 for x in false_flags_per_trial if x>0)}/{TRIALS}")
