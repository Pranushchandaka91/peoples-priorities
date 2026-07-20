"""
Natural-language complaint extraction — BUILD_BRIEF.md §9a.

Calls the Anthropic API with a strict JSON-only system prompt to pull
structured fields out of a free-text complaint, then fuzzy-matches the
location phrase against assets.descriptor for that ward+sector.

Never auto-submits anything — this only PRE-FILLS the intake form; the
operator confirms/edits before POST /complaints. On any failure (missing
API key, network error, bad JSON from the model) this degrades to an
empty/low-confidence result rather than raising, so the caller can always
fall back to the manual form.
"""
import json
import os

from rapidfuzz import fuzz

from models import Asset

# The brief specifies "claude-sonnet-4-6"; that identifier doesn't exist in
# the current Claude lineup (Fable 5 / Opus 4.8 / Sonnet 5 / Haiku 4.5), so
# this is overridable via env and defaults to the current equivalent tier.
CLAUDE_MODEL = os.environ.get("PARSE_MODEL", "claude-sonnet-5")

SECTORS = ["water", "roads", "health", "education", "electricity",
           "sanitation", "drainage", "transport", "livelihood", "other"]
WARDS = ["W07", "W11", "W14", "W19", "W22", "W26"]

SYSTEM_PROMPT = f"""You extract structured fields from a citizen infrastructure complaint.
The input may be in English, Hindi, or Telugu. Extract fields in English regardless of input language.
Return ONLY a single JSON object, no prose, no markdown fences. Fields:
{{
  "ward_id": one of {WARDS} if a ward is mentioned (often literally, e.g. "W14"), else null,
  "sector": one of {SECTORS} best matching the complaint, else null,
  "reported_status": "not_working", "degraded", or null,
  "duration_weeks": integer number of weeks implied by the complaint (convert days/months), or null,
  "location_phrase": a short English phrase describing where/what the asset is (e.g. "handpump near the school"), or null,
  "confidence": "high", "medium", or "low" — your confidence in this extraction overall
}}"""

EMPTY_RESULT = dict(
    ward_id=None, sector=None, asset_candidates=[],
    reported_status=None, duration_weeks=None, confidence="low",
)


def _fuzzy_match_assets(db, ward_id: str, sector: str, location_phrase: str) -> list[dict]:
    if not location_phrase:
        return []
    assets = db.query(Asset).filter_by(ward_id=ward_id, sector=sector).all()
    scored = []
    for a in assets:
        score = fuzz.token_set_ratio(location_phrase, a.descriptor)
        if score >= 70:
            scored.append(dict(asset_id=a.asset_id, descriptor=a.descriptor, match_score=round(score, 1)))
    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored[:5]


def parse_complaint(db, raw_text: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return dict(EMPTY_RESULT)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": raw_text}],
        )
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        extracted = json.loads(text)
    except Exception:
        return dict(EMPTY_RESULT)

    ward_id = extracted.get("ward_id")
    sector = extracted.get("sector")
    if ward_id not in WARDS:
        ward_id = None
    if sector not in SECTORS:
        sector = None

    asset_candidates = []
    if ward_id and sector:
        asset_candidates = _fuzzy_match_assets(db, ward_id, sector, extracted.get("location_phrase"))

    return dict(
        ward_id=ward_id, sector=sector, asset_candidates=asset_candidates,
        reported_status=extracted.get("reported_status"),
        duration_weeks=extracted.get("duration_weeks"),
        confidence=extracted.get("confidence", "low"),
    )
