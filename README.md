# People's Priorities

**A divergence-audited constituency development prioritization system.**

Built as an internship learning project at Delasoft. Single constituency, synthetic
data, not deployed — the point was to find out what actually works before anything
ships, and the most valuable results were the negative ones.

---

## What it is

Complaints arrive through many doors — an app is one, but also village meetings,
sarpanch channels, and existing grievance systems — so being heard never requires
owning the app. The need ranking is pre-determined by government data; incoming
complaints that *contradict* that data reform it. Silent wards still surface,
because the baseline ranking requires zero complaints. Where field reports dispute
specific recorded assets, need becomes a range — the recorded value at the bottom,
the disputed reality at the top — and what gets triggered is a verification task,
not money: the verifier closes it with photo evidence, the complainant confirms,
and every action and inaction is logged. A CP-SAT solver then converts confirmed
scores, costs, and the budget into a funded list that maximizes delivered benefit
under hard guarantees like equity floors.

One sentence: **complaints stop being votes and become fact-checkers — when people
contradict the record, the system stops trusting the record and asks a human to
go look.**

## What the research found (before anything was built)

Every design claim was tested against a synthetic world with authored ground truth
(`research/`). Three numbers define the project:

| Ranking method | Spearman ρ vs true need |
|---|---|
| Raw complaint volume (naive system) | **−0.23** — worse than random |
| Full model on realistic-quality data | **+0.58** |
| One census column (literacy) alone | **+0.73** |

- **Complaint volume measures loudness, not need.** Bias correction narrows the
  loud/silent ward gap 34× → 11× but cannot close it — you can't correct a signal
  that was never sent. (`research/demo.py`, `research/eval.py`)
- **A one-column baseline beats the whole pipeline** on chronic, poverty-shaped
  need. The system's only honest jobs are the ones the baseline can't do: detect
  what *changed* recently, rank sectors *within* a ward, count beneficiaries under
  a budget, and audit stale records. (`research/stress.py`)
- **Astroturfing is bounded, not prevented**: a 50,000-message flood buys the same
  score as 500 (cap at 2× expected rate). False verifier closures are isolated by
  reversal tracking — in simulation, a 60%-dishonest verifier is flagged in a
  median of 2 months, with zero honest verifiers falsely flagged across 30 trials.
  (`research/closure.py`)
- **Stale data misses new crises** — which is exactly when a prioritization tool
  matters most. That failure is what the divergence detector exists to patch.

## The divergence detector (the novel part)

Complaints that name a specific asset the record marks "functional" create a
**dispute**. Disputes decay trust in that data source *for that ward*. Decayed
trust widens the need score into a range and surfaces a flag. Enough disputes
spawn **verification tasks** — a demand for one day of checking, not a rupee.

Verified end-to-end by hand. Work "W14 water system repairs", before and after
four field reports against assets recorded as functional:

```
before:  need 0.458 (point)     data_flags: []
after:   need 0.458 – 0.598     data_flags: ["tap_coverage_pct 61% per
                                 Jal Jeevan Mission (2022) — disputed by
                                 5 field reports since 2026-07-20"]
```

Four complaints bought W14 doubt and an inspection — not money. That is the
design: you cannot complain your way to funding; you can only complain your way
to a verification.

## Running it

```bash
# backend
cd backend
pip install fastapi uvicorn sqlalchemy ortools pandas numpy
python seed.py            # builds the synthetic constituency (incl. the W14 trap)
uvicorn app:app           # API on :8000  (interactive docs at /docs)

# frontend
cd frontend
npm install
npm run dev               # UI on :5173
```

Demo mode (`DEMO_MODE=true`) adds a reality-peek endpoint and a world reset for
live, unscripted demonstrations. NL complaint parsing activates if
`ANTHROPIC_API_KEY` is set; degrades to the manual form otherwise.

## Research harness

```bash
cd research
python demo.py       # the four claims, with arithmetic
python eval.py       # ranking methods vs authored ground truth
python stress.py     # how bad can the data get before the model breaks
python closure.py    # false-closure / dishonest-verifier detection
```

Every quantitative claim in this README is reproduced by one of these scripts.

## Honest limits

- **Not unbiased — no *hidden* bias.** The weights (0.30 demand / 0.40 need /
  0.20 equity / 0.10 cost) are open value judgments, set by a human, audit-logged.
  The severity tradeoff (millions inconvenienced vs. hundreds endangered) has no
  technical answer; the system makes it explicit, enforces floors, and keeps
  receipts. It does not make it correct.
- **The capture problem is institutional, not software.** Deployed inside a
  decision-maker's office, this is decision-support with an internal audit trail.
  Its accountability teeth — receipts that bind the decision-maker — exist only
  under an ownership and publication structure no vendor can unilaterally
  provide. What software *can* guarantee: tamper-evident, externally archived
  logs, so the records survive until someone with standing comes asking.
- **Synthetic world.** All numbers above are from an authored test world with
  controlled ground truth. They demonstrate mechanism soundness, not field
  performance. Coercion rates, response rates, and real data quality are
  field-measurable unknowns.

## Stack

FastAPI · SQLAlchemy · OR-Tools CP-SAT · React + Vite + Tailwind ·
pandas / numpy / scipy (research)
