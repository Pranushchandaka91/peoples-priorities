# BUILD BRIEF — People's Priorities (thin vertical slice)

You are building a working web application from a validated research core.
The scoring engine already exists and is proven — DO NOT rewrite its logic.
Files `core.py` and `generate.py` in this directory are the source of truth
for all scoring math. Port, wrap, and serve them; do not "improve" them.

## What this system is

A constituency development prioritization tool. Citizens file structured
complaints. Public datasets provide per-ward need scores. A solver allocates
a budget across candidate works. The novel feature — build it exactly as
specified in §5 — is a **divergence detector**: complaints that contradict
official records generate disputes, disputes decay trust in specific data
sources, and decayed trust widens uncertainty on need scores and surfaces
verification tasks.

## What this system is NOT (hard scope limits)

- NO voice/audio/ASR, NO translation pipeline, NO WhatsApp integration
- NO maps, NO mobile app
- Text-only complaint intake
- Single constituency, 6 wards, seeded synthetic data
- If a feature is not in this brief, do not build it

## Stack

- Backend: FastAPI (Python 3.11+), SQLAlchemy, Postgres (SQLite acceptable
  for dev if Postgres unavailable — use dialect-neutral SQLAlchemy)
- Solver: OR-Tools CP-SAT (already used in core.py)
- Frontend: React + Vite + Tailwind, single page, no router needed
- Seed data: adapt `generate.py` output into the DB at startup via a seed script

---

## 1. Database schema

```sql
CREATE TABLE wards (
    ward_id TEXT PRIMARY KEY,          -- 'W07'
    population INT NOT NULL,
    literacy_pct REAL NOT NULL,
    smartphone_pct REAL NOT NULL,
    is_urban BOOLEAN NOT NULL,
    km_to_mp_office REAL NOT NULL,
    tap_coverage_pct REAL NOT NULL,
    toilet_coverage_pct REAL NOT NULL,
    km_to_phc REAL NOT NULL,
    dropout_pct REAL NOT NULL,
    km_to_school REAL NOT NULL,
    road_km_per_sqkm REAL NOT NULL,
    sc_st_pct REAL NOT NULL
);

CREATE TABLE data_sources (
    source_id TEXT PRIMARY KEY,        -- 'jal_jeevan', 'udise', 'census'
    name TEXT NOT NULL,
    sectors TEXT NOT NULL,             -- JSON array of sectors it informs
    as_of_date DATE NOT NULL           -- staleness anchor
);

CREATE TABLE assets (
    asset_id TEXT PRIMARY KEY,         -- 'HP-102'
    ward_id TEXT REFERENCES wards,
    sector TEXT NOT NULL,              -- enum: water|health|education|roads|sanitation|drainage
    kind TEXT NOT NULL,                -- 'handpump','borewell','tap_stand','phc','school','road_segment'
    descriptor TEXT NOT NULL,          -- 'handpump near primary school, north side'
    recorded_status TEXT NOT NULL,     -- what the official record claims: 'functional'|'non_functional'
    source_id TEXT REFERENCES data_sources
);

CREATE TABLE complaints (
    complaint_id TEXT PRIMARY KEY,     -- uuid
    ward_id TEXT REFERENCES wards,
    sector TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    asset_id TEXT NULL REFERENCES assets,   -- structured intake may name an asset
    reported_status TEXT NULL,         -- 'not_working'|'degraded'|NULL
    duration_weeks INT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE disputes (
    dispute_id TEXT PRIMARY KEY,
    asset_id TEXT REFERENCES assets,
    complaint_id TEXT REFERENCES complaints,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    -- a dispute exists iff complaint.reported_status contradicts asset.recorded_status
    status TEXT NOT NULL DEFAULT 'open'     -- 'open'|'verified_complaint_right'|'verified_record_right'
);

CREATE TABLE source_trust (
    source_id TEXT REFERENCES data_sources,
    ward_id TEXT REFERENCES wards,
    trust REAL NOT NULL DEFAULT 1.0,   -- [0.3, 1.0], see §5
    PRIMARY KEY (source_id, ward_id)
);

CREATE TABLE works (
    work_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ward_id TEXT REFERENCES wards,
    sector TEXT NOT NULL,
    cost_lakh REAL NOT NULL,
    beneficiaries INT NOT NULL,
    source TEXT NOT NULL               -- 'development_plan'|'derived_from_cluster'
);

CREATE TABLE verification_tasks (
    task_id TEXT PRIMARY KEY,
    asset_id TEXT REFERENCES assets,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending'|'closed_fixed'|'closed_disputed'
    note TEXT NULL
);

CREATE TABLE weight_audit_log (
    id SERIAL PRIMARY KEY,
    changed_at TIMESTAMP NOT NULL DEFAULT now(),
    w_demand REAL, w_need REAL, w_equity REAL, w_cost REAL,
    changed_by TEXT NOT NULL DEFAULT 'demo_user'
);
```

## 2. Seeding

Write `seed.py`:
- Insert the 6 wards from `generate.py`'s WARDS table (all columns above; tap/toilet/phc/dropout/school/road/scst values from `demo.py`'s ward table in this repo — copy them verbatim).
- Create 3 data_sources: jal_jeevan (water, as_of 2022-06-01), udise (education, as_of 2023-09-01), census (all sectors, as_of 2011-03-01).
- Generate 8–12 assets per ward across sectors with plausible descriptors. Mark ~85% 'functional'. IMPORTANT for the demo: in W14 create 11 water assets marked 'functional' whose reality is broken (that's what complaints will dispute).
- Run `generate.py`'s complaint generator, take ~200 text complaints, insert them WITHOUT asset links (legacy free-text).
- Insert the 8 candidate works from `demo.py` verbatim.
- Initialize source_trust to 1.0 for every (source, ward) pair.

## 3. Scoring service (port of core.py — logic frozen)

`scoring.py` wraps core.py functions. The ONLY modification allowed:

**Trust-adjusted need.** Where core.py computes need from a ward attribute
(e.g. tap_coverage for water), look up `source_trust` for the informing
source and that ward, and return an interval instead of a point:

```
t = trust(source, ward)                      # 1.0 = fully trusted
need_point = <core.py need value>
need_low   = need_point
need_high  = need_point + (1 - t) * 0.5     # distrust widens upward only
need_used  = (need_low + need_high) / 2     # used in priority formula
```
Rationale: complaints only ever dispute records in the direction of
"things are worse than recorded", so uncertainty widens toward higher need.

Priority formula and solver: exactly as in core.py (`score_works`, `allocate`),
with weights read from the latest weight_audit_log row (default 0.30/0.40/0.20/0.10).

## 4. API contract

```
POST /complaints
  body: { ward_id, sector, raw_text, asset_id?, reported_status?, duration_weeks? }
  side effects: if asset_id present AND reported_status contradicts
     assets.recorded_status → create dispute (§5 fires)
  returns: complaint + dispute_created: bool

GET /ranking?budget_lakh=200
  runs scoring + CP-SAT allocation
  returns: [ { work_id, name, ward_id, sector, cost_lakh, beneficiaries,
               demand, need_low, need_high, need_used, equity, cost_pen,
               priority, funded: bool, rank,
               data_flags: [ "tap_coverage disputed by N field reports since <date>" ] } ]

GET /works/{work_id}/rationale
  returns the rationale card as structured JSON:
  { rank, name, cost_lakh, submissions, correction_factor,
    sector_evidence: {...ward stats...},
    beneficiaries, cost_per_beneficiary,
    priority_breakdown: {demand, need, equity, cost_pen, weights},
    disputes: [ {asset_id, descriptor, reported_status, weeks, date} ] }

GET /disputes?ward_id=&status=
GET /verification-tasks?status=pending
POST /verification-tasks/{task_id}/close
  body: { outcome: 'fixed'|'confirmed_broken', note }
  side effects: §5 step 4

GET /weights            → current weights + full audit log
POST /weights           → { w_demand, w_need, w_equity, w_cost, changed_by }
  validates weights sum to reasonable range (0.9–1.1), appends to audit log
```

## 5. THE DIVERGENCE DETECTOR (the novel feature — implement exactly)

Constants: `DISPUTE_TRUST_STEP = 0.07`, `TRUST_FLOOR = 0.3`,
`TASK_THRESHOLD = 3`, `RESTORE_STEP = 0.15`, `TRUST_CEILING = 1.0`.

1. **Dispute creation.** On complaint referencing asset A where
   reported_status='not_working'/'degraded' but A.recorded_status='functional':
   insert dispute(open). One complaint → max one dispute; duplicate complaints
   on the same asset within 14 days attach to the existing open dispute
   (store complaint ids in a join table or JSON column).

2. **Trust decay.** On each NEW open dispute:
   `trust(A.source_id, A.ward_id) = max(TRUST_FLOOR, trust − DISPUTE_TRUST_STEP)`.
   Trust changes are per (source, ward) — a dispute in W14 never affects W07.

3. **Verification task spawn.** When an asset accumulates ≥1 open dispute AND
   its ward-sector has ≥ TASK_THRESHOLD open disputes total → create
   verification_task for each disputed asset lacking a pending task.

4. **Task closure.**
   - outcome 'confirmed_broken' → dispute status 'verified_complaint_right';
     asset.recorded_status := 'non_functional'; trust unchanged (the record
     was wrong; decay already applied stands).
   - outcome 'fixed' → dispute 'verified_record_right';
     `trust = min(TRUST_CEILING, trust + RESTORE_STEP)`.

5. **Surfacing.** GET /ranking must include data_flags for any work whose
   ward-sector's informing source has trust < 0.9, phrased:
   `"{attribute} {value} per {source} ({as_of year}) — disputed by {n} field
   reports since {earliest dispute date}"`.

## 6. Frontend — ONE page, three panels

Panel A — **Ranked works table.** Rank, name, ward, cost, priority bar,
funded badge (from solver at budget from a top slider, default ₹200L).
Need shown as a range when need_low ≠ need_high (e.g. "0.10–0.35 ⚠").
Amber flag icon when data_flags non-empty; tooltip shows the flag text.
Clicking a row opens Panel B.

Panel B — **Rationale card.** Render GET /works/{id}/rationale: priority
breakdown as labeled horizontal bars (demand/need/equity/cost × weights),
sector evidence lines, dispute list if any, cost-per-beneficiary.

Panel C — **Field signals.** Two tabs:
  (i) Complaint intake form: ward select, sector select, free text,
      optional asset select (filtered by ward+sector), status, duration.
      On submit, if a dispute was created show a toast:
      "⚡ This report disputes the official record for {asset}".
  (ii) Verification queue: pending tasks with asset descriptor, dispute
      count, age; two buttons per task (Confirmed broken / Actually fixed)
      hitting the close endpoint.

Style: clean, dense, government-dashboard sober. Dark text on light.
No animations beyond the toast. Tailwind defaults fine.

## 7. Acceptance script (build to make this demo work end-to-end)

1. `python seed.py && uvicorn app:app` + `npm run dev` → ranking shows,
   W14 school work funded, W14 water need shown as a POINT (~0.10 territory,
   trust 1.0).
2. Submit 4 structured complaints naming 4 of W14's secretly-broken water
   assets ('not_working', 4–8 weeks). Each shows the dispute toast.
3. Refresh ranking → W14 water rows now show need as a RANGE, amber flag
   reading "tap coverage … disputed by 4 field reports…", jal_jeevan/W14
   trust visibly below 1.0 (expose current trust in the flag tooltip).
4. Verification queue shows tasks. Close two as 'Confirmed broken' →
   those assets flip to non_functional in the record.
5. Close one as 'Actually fixed' → trust partially restores.
6. Change weights via a settings modal → audit log grows; ranking reorders.

## 8. Project layout

```
peoples-priorities/
  backend/
    app.py  models.py  scoring.py  divergence.py  seed.py
    core.py  generate.py          # copied in, unmodified
    tests/test_divergence.py     # cover §5 steps 1–4 with unit tests
  frontend/
    (Vite React app, single page, three panels)
  README.md   # how to run; one paragraph on what the divergence detector is
```

## 9. LIVE DEMO MODE (free-form demonstration, not scripted)

The operator must be able to demonstrate with ARBITRARY audience-suggested
complaints, not only the §7 script. Three additions:

### 9a. Natural-language complaint extraction
New endpoint:
```
POST /complaints/parse
  body: { raw_text }   e.g. "the handpump near the school in W14 has been dry for a month"
  returns: { ward_id?, sector?, asset_candidates: [{asset_id, descriptor, match_score}],
             reported_status?, duration_weeks?, confidence: high|medium|low }
```
Implementation: call the Anthropic API (claude-sonnet-4-6) with a strict
JSON-only system prompt: extract sector (from the fixed enum), ward mentions,
status, duration; then fuzzy-match the location phrase against
assets.descriptor for that ward+sector (rapidfuzz, token_set_ratio ≥ 70).
NEVER auto-submit: the UI pre-fills the intake form with the extraction and
the operator confirms/edits before POST /complaints. Parsing failure must
degrade gracefully to the manual form, never block submission.

### 9b. Hidden reality layer (so any live path is playable)
Add column `assets.actual_status TEXT NOT NULL` — the ground truth, NEVER
exposed through any list/ranking endpoint. Seed it so every ward-sector has
demo-able material: ~70% of assets actual=recorded (honest record), ~20%
actual='non_functional' while recorded='functional' (stale record — divergence
material), ~10% recorded='non_functional' honestly.
New operator-only endpoint `GET /admin/reality/{asset_id}` returns actual_status —
used by the operator when playing the field verifier, so closure outcomes
follow seeded truth instead of improvisation. Frontend: verification queue
shows a small "peek reality" eye-icon visible only in demo mode
(env flag DEMO_MODE=true).

### 9c. Demo reset
`POST /admin/reset` → truncate complaints, disputes, verification_tasks,
restore source_trust to 1.0, restore assets.recorded_status from seed
snapshot, keep wards/works/sources. Frontend: reset button behind the
DEMO_MODE flag with a confirm dialog. Every live demo starts clean.

Acceptance addition: type "borewell at the panchayat office in W19 stopped
working two weeks ago" into a single free-text box → parse pre-fills the
form correctly, submit → if that asset's record says functional, dispute
toast fires; verification flow playable end-to-end using the reality peek;
reset returns the world to pristine.

Write tests for divergence.py before wiring the API. If any instruction
here conflicts with something you'd normally do, follow this brief.

## 10. RICH INTAKE (GATED — do not begin until §7 acceptance passes fully)

Build order within this section: 10a → 10b → 10c. Each gated on the previous.

### 10a. Multilingual text (English / Telugu / Hindi)
Extend §9a's /complaints/parse: system prompt states input may be en, te, or
hi; extract the same JSON fields in English; add field `original_lang`.
Store complaint.raw_text as typed (original script) plus `text_en`.
UI: intake becomes a single chat-style composer (rounded textbox, send
button, attachment affordance — visually similar to a modern chat input).
Rationale cards and dispute records always display the ORIGINAL text with
the English extraction beneath it.

### 10b. Image attachments
Composer accepts image drop/paste (jpeg/png, ≤5MB, max 3 per complaint).
Store to local disk under /media, path on a complaint_attachments table.
On parse, send images to the multimodal model with the text; extracted
caption (e.g. "dry handpump, cracked platform") stored and shown in the
dispute record. Citizen photos appear alongside sarpanch closure evidence
in the verification task view.

### 10c. Voice messages (LAST — new external dependency)
Browser MediaRecorder → webm/opus upload → transcription via OpenAI
Whisper API (env OPENAI_API_KEY; if unset, hide the mic button entirely —
graceful absence, not a broken button). Whisper output (te/hi/en) feeds
the same /complaints/parse path as typed text. Store the audio file and
transcript; dispute records show a small audio player. Add a visible
"transcribed — please confirm" state before submission; never auto-submit
from voice.

Acceptance additions: (a) paste a Telugu complaint naming a seeded asset →
correct extraction, dispute fires, original Telugu shown on the dispute;
(b) attach a photo → caption appears in the dispute record; (c) with an
API key set, record a short Hindi voice note → transcript pre-fills the
form. All three must degrade gracefully (parse failure → manual form).
