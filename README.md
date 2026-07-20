# People's Priorities

A constituency development prioritization tool: citizens file structured complaints,
public datasets give per-ward need scores, and a CP-SAT solver allocates a budget
across candidate works. Single constituency, 6 wards, seeded synthetic data.
Text-only intake — no voice/ASR, no translation pipeline, no WhatsApp, no maps.

## The divergence detector

The novel piece. Official records (Jal Jeevan, UDISE, Census) say an asset is
`functional`. When a citizen complaint says otherwise, that's a **dispute**, and
a dispute is evidence the record itself might be stale. Each new dispute decays
trust in the specific (data source, ward) pair that produced the record — never
globally, never for other wards. As trust decays, the need score for that
ward-sector stops being a point estimate and becomes an interval that widens
upward (distrust only ever means "things could be worse than recorded", never
better), which is what actually gets used in the priority formula. Once a
ward-sector accumulates enough open disputes, verification tasks are spawned for
field staff to close out — confirming the complaint (record flips) or the record
(trust partially recovers). The effect is visible everywhere downstream: the
ranking table's need column, an amber "disputed by N field reports" flag, and a
structured rationale card an MP can read out loud.

## Stack

- Backend: FastAPI + SQLAlchemy (SQLite for dev, Postgres via `DATABASE_URL`)
- Solver: OR-Tools CP-SAT (`core.py`, frozen — the scoring math is not touched)
- Frontend: React + Vite + Tailwind, single page, three panels
- `core.py` and `generate.py` are copied in unmodified; everything else wraps them

## Running it

```bash
# one-time setup — isolated venv, avoids clobbering any global Python packages
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements.txt   # Windows
# .venv/bin/pip install -r backend/requirements.txt     # macOS/Linux

cd backend
../.venv/Scripts/python seed.py        # seeds wards, assets, complaints, works
../.venv/Scripts/python -m uvicorn app:app --reload

# in another terminal
cd frontend
npm install
npm run dev   # http://localhost:5173, proxies /api/* to the backend on :8000
```

Run the divergence detector's unit tests with:
```bash
cd backend && ../.venv/Scripts/python -m pytest tests/ -v
```

### Demo mode

Set `DEMO_MODE=true` on the backend to expose two operator-only affordances in
the UI: a "peek reality" eye icon in the verification queue (reveals the
seeded ground-truth `actual_status` of an asset, never exposed through any
regular list/ranking endpoint) and a "Reset demo" button that wipes complaints/
disputes/tasks and restores trust and asset records to their seeded state.

```bash
DEMO_MODE=true ../.venv/Scripts/python -m uvicorn app:app --reload
```

### Natural-language complaint parsing (§9a)

`POST /complaints/parse` calls the Anthropic API to pre-fill the complaint
intake form from free text (never auto-submits — the operator always confirms).
Set `ANTHROPIC_API_KEY` to enable it; without a key the endpoint degrades
gracefully to a low-confidence empty result and the UI falls back to the manual
form. (The brief names model id `claude-sonnet-4-6`, which doesn't exist in the
current Claude lineup — the model is overridable via `PARSE_MODEL` and defaults
to `claude-sonnet-5`.)

## Notable deviations from the brief

- **A 9th work.** §2 says to insert the 8 candidate works from `demo.py`
  verbatim, but none of them target W14+water — which §7's acceptance script
  requires ("W14 water need shown as a point, then a range"). Added one more
  work (`W14 water system repairs`, `derived_from_cluster`) so that row exists.
- **`GET /assets`.** Not in §4's endpoint list, but §6 requires an asset
  dropdown "filtered by ward + sector" in the intake form, which needs
  somewhere to fetch from.
- **`GET /config`.** Lets the frontend discover `DEMO_MODE` without baking the
  flag into the build.
