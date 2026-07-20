"""
Synthetic submission generator with KNOWN GROUND TRUTH.

The point is not to make fake data that looks real.
The point is to make fake data where WE know the true need, so we can ask:

    does the bias correction actually recover it?

If it doesn't, the whole thesis is decoration. Better to find that out
on synthetic data tonight than on real data in front of someone.

No API key needed. Template-based, deterministic, reproducible.
Swap in an LLM paraphrase pass later if you want messier text.
"""

import random
import pandas as pd
import numpy as np

SEED = 7
random.seed(SEED)
np.random.seed(SEED)

# ─────────────────────────────────────────────────────────────
# GROUND TRUTH — we author this. The system must never see it.
# ─────────────────────────────────────────────────────────────
# true_need[ward][sector] ∈ [0,1].  This is reality.
# Note: W22 is the deprived, silent ward. W07 is rich and loud.

TRUE_NEED = {
    "W07": {"water": 0.05, "health": 0.10, "education": 0.15, "roads": 0.20, "sanitation": 0.10, "drainage": 0.55},
    "W11": {"water": 0.15, "health": 0.35, "education": 0.25, "roads": 0.30, "sanitation": 0.20, "drainage": 0.40},
    "W14": {"water": 0.45, "health": 0.50, "education": 0.85, "roads": 0.55, "sanitation": 0.45, "drainage": 0.30},
    "W19": {"water": 0.65, "health": 0.75, "education": 0.70, "roads": 0.90, "sanitation": 0.60, "drainage": 0.25},
    "W22": {"water": 0.95, "health": 0.85, "education": 0.60, "roads": 0.70, "sanitation": 0.80, "drainage": 0.20},
    "W26": {"water": 0.30, "health": 0.30, "education": 0.35, "roads": 0.40, "sanitation": 0.35, "drainage": 0.35},
}

# ─────────────────────────────────────────────────────────────
# VOICE PROPENSITY — how likely is this ward to actually SPEAK?
# Driven by phone/literacy/urban. Deliberately uncorrelated with need.
# This is the distortion we are trying to undo.
# ─────────────────────────────────────────────────────────────

WARDS = pd.DataFrame([
    #  id    pop  literacy smartphone urban km_to_office
    ["W07", 12000, 82, 78, 1,  3],
    ["W11",  9500, 74, 66, 1,  7],
    ["W14", 10500, 61, 47, 0, 18],
    ["W19",  7200, 55, 38, 0, 26],
    ["W22",  9000, 51, 31, 0, 31],
    ["W26",  6100, 68, 58, 0, 12],
], columns=["ward_id", "population", "literacy_pct", "smartphone_pct",
            "is_urban", "km_to_mp_office"]).set_index("ward_id")


def voice_propensity(w) -> float:
    """Submissions per 1000 people, if need were identical everywhere."""
    return (
        18.0
        * (0.30 + 0.70 * w["smartphone_pct"] / 100)
        * (0.45 + 0.55 * w["literacy_pct"] / 100)
        * (1.30 if w["is_urban"] else 1.0)
        * (1 / (1 + 0.022 * w["km_to_mp_office"]))
    )


# ─────────────────────────────────────────────────────────────
# TEXT TEMPLATES — 3 languages x 6 sectors. Same meaning, different words.
# Clustering must merge these. If it doesn't, your embeddings are wrong.
# ─────────────────────────────────────────────────────────────

TEMPLATES = {
    "water": {
        "en": ["No water supply in our colony for {n} days",
               "Borewell has dried up, we walk {n} km for water",
               "Handpump broken near the school, no drinking water",
               "Water tanker has not come this week at all"],
        "hi": ["हमारी कॉलोनी में {n} दिन से पानी नहीं आ रहा",
               "बोरवेल सूख गया है, {n} किलोमीटर चलना पड़ता है",
               "स्कूल के पास का हैंडपंप खराब है, पीने का पानी नहीं",
               "इस हफ्ते पानी का टैंकर बिल्कुल नहीं आया"],
        "te": ["మా కాలనీలో {n} రోజులుగా నీళ్లు రావట్లేదు",
               "బోరు ఎండిపోయింది, {n} కిలోమీటర్లు నడవాలి",
               "స్కూల్ దగ్గర హ్యాండ్ పంప్ పాడైంది, తాగునీరు లేదు",
               "ఈ వారం నీళ్ల ట్యాంకర్ అస్సలు రాలేదు"],
    },
    "health": {
        "en": ["Nearest PHC is {n} km away, no ambulance",
               "Doctor does not come to the health centre",
               "No medicines available at the clinic",
               "Pregnant women have to travel {n} km for checkup"],
        "hi": ["नज़दीकी पीएचसी {n} किलोमीटर दूर है, एम्बुलेंस नहीं",
               "स्वास्थ्य केंद्र में डॉक्टर नहीं आते",
               "क्लिनिक में दवाइयाँ नहीं मिलतीं",
               "गर्भवती महिलाओं को {n} किमी जाना पड़ता है"],
        "te": ["దగ్గర్లో పీహెచ్‌సీ {n} కిలోమీటర్లు, అంబులెన్స్ లేదు",
               "ఆరోగ్య కేంద్రానికి డాక్టర్ రావట్లేదు",
               "క్లినిక్‌లో మందులు దొరకట్లేదు",
               "గర్భిణీలు {n} కిమీ ప్రయాణించాలి"],
    },
    "education": {
        "en": ["School has no teachers for {n} months",
               "Children walk {n} km to reach the high school",
               "School building roof is leaking, classes stopped",
               "No toilets in the government school, girls dropping out"],
        "hi": ["स्कूल में {n} महीने से शिक्षक नहीं हैं",
               "बच्चे {n} किलोमीटर चलकर हाई स्कूल जाते हैं",
               "स्कूल की छत टपक रही है, कक्षाएं बंद",
               "सरकारी स्कूल में शौचालय नहीं, लड़कियाँ पढ़ाई छोड़ रहीं"],
        "te": ["స్కూల్‌లో {n} నెలలుగా టీచర్లు లేరు",
               "పిల్లలు {n} కిలోమీటర్లు నడిచి హైస్కూల్‌కి వెళ్తారు",
               "స్కూల్ పైకప్పు కారుతోంది, తరగతులు ఆగిపోయాయి",
               "ప్రభుత్వ స్కూల్‌లో టాయిలెట్లు లేవు, అమ్మాయిలు మానేస్తున్నారు"],
    },
    "roads": {
        "en": ["Road to the village is broken, buses do not come",
               "No link road to the block headquarters, {n} km detour",
               "Potholes everywhere, two accidents last month",
               "Road becomes unusable in the rains"],
        "hi": ["गाँव की सड़क टूटी है, बसें नहीं आतीं",
               "ब्लॉक मुख्यालय तक सड़क नहीं, {n} किमी घूमना पड़ता है",
               "हर जगह गड्ढे, पिछले महीने दो हादसे",
               "बारिश में सड़क बेकार हो जाती है"],
        "te": ["ఊరికి రోడ్డు పాడైంది, బస్సులు రావట్లేదు",
               "బ్లాక్ ఆఫీసుకి లింక్ రోడ్డు లేదు, {n} కిమీ చుట్టూ",
               "అంతటా గుంతలు, గత నెల రెండు ప్రమాదాలు",
               "వర్షాలకు రోడ్డు పనికిరాకుండా పోతుంది"],
    },
    "sanitation": {
        "en": ["Open drainage next to houses, mosquitoes everywhere",
               "No toilets, {n} families using open fields",
               "Garbage not collected for {n} weeks",
               "Sewage water entering our street"],
        "hi": ["घरों के पास खुली नाली, हर जगह मच्छर",
               "शौचालय नहीं, {n} परिवार खुले में जाते हैं",
               "{n} हफ्ते से कचरा नहीं उठाया गया",
               "नाले का पानी हमारी गली में घुस रहा है"],
        "te": ["ఇళ్ల పక్కన ఓపెన్ డ్రైనేజీ, దోమలు",
               "టాయిలెట్లు లేవు, {n} కుటుంబాలు బయటకే",
               "{n} వారాలుగా చెత్త తీయట్లేదు",
               "మురుగు నీరు మా వీధిలోకి వస్తోంది"],
    },
    "drainage": {
        "en": ["Market road floods every time it rains",
               "Storm drains blocked, water stands for {n} days",
               "Waterlogging in front of the shops",
               "Drain overflow near the bus stand"],
        "hi": ["बारिश में बाज़ार की सड़क में पानी भर जाता है",
               "नालियाँ जाम हैं, {n} दिन पानी खड़ा रहता है",
               "दुकानों के सामने जलभराव",
               "बस स्टैंड के पास नाली ओवरफ्लो"],
        "te": ["వర్షం పడితే మార్కెట్ రోడ్డు మునిగిపోతుంది",
               "డ్రైన్లు మూసుకుపోయాయి, {n} రోజులు నీరు నిలుస్తోంది",
               "షాపుల ముందు నీరు నిలుస్తోంది",
               "బస్ స్టాండ్ దగ్గర డ్రైన్ పొంగుతోంది"],
    },
}

CHANNELS = ["gram_sabha", "whatsapp", "portal", "letter", "pwa"]
# Channel mix depends on the ward. Rural/low-phone wards speak at meetings.
CHANNEL_WEIGHTS_URBAN = [0.05, 0.40, 0.30, 0.10, 0.15]
CHANNEL_WEIGHTS_RURAL = [0.45, 0.20, 0.10, 0.20, 0.05]

# Language mix — urban wards skew English/Hindi, rural skew Telugu
LANG_URBAN = {"en": 0.45, "hi": 0.35, "te": 0.20}
LANG_RURAL = {"en": 0.10, "hi": 0.25, "te": 0.65}


def _pick(d: dict) -> str:
    return random.choices(list(d.keys()), weights=list(d.values()))[0]


def generate(total_target: int = 400) -> pd.DataFrame:
    rows, sid = [], 0

    for wid, w in WARDS.iterrows():
        # HOW MANY people speak — driven by voice, NOT by need.
        base = voice_propensity(w) * w["population"] / 1000.0
        n_subs = max(1, int(np.random.poisson(base)))

        needs = TRUE_NEED[wid]
        sectors = list(needs.keys())
        # WHAT they speak about — driven by need. Need shapes the mix,
        # voice shapes the volume. That separation is the whole experiment.
        weights = [needs[s] ** 1.5 + 0.05 for s in sectors]

        urban = bool(w["is_urban"])
        ch_w = CHANNEL_WEIGHTS_URBAN if urban else CHANNEL_WEIGHTS_RURAL
        lang_mix = LANG_URBAN if urban else LANG_RURAL

        for _ in range(n_subs):
            sector = random.choices(sectors, weights=weights)[0]
            lang = _pick(lang_mix)
            tpl = random.choice(TEMPLATES[sector][lang])
            text = tpl.format(n=random.choice([2, 3, 4, 5, 6, 7, 8, 9, 12]))
            sid += 1
            rows.append(dict(
                submission_id=f"S{sid:05d}",
                ward_id=wid,
                raw_text=text,
                lang=lang,
                channel=random.choices(CHANNELS, weights=ch_w)[0],
                true_sector=sector,          # for eval only — pipeline must re-derive
            ))

    df = pd.DataFrame(rows)

    # Scale to roughly the requested total, preserving the ward skew
    if len(df) > total_target:
        df = df.sample(total_target, random_state=SEED).reset_index(drop=True)
    return df


def inject_astroturf(df: pd.DataFrame, ward: str = "W07",
                     sector: str = "drainage", n: int = 5000) -> pd.DataFrame:
    """A contractor floods one ward. Near-duplicate text — realistic attack."""
    tpl = TEMPLATES[sector]["en"][0]
    fake = pd.DataFrame([dict(
        submission_id=f"X{i:05d}", ward_id=ward,
        raw_text=tpl + random.choice(["", ".", "!", " please", " sir", " urgent"]),
        lang="en", channel="whatsapp", true_sector=sector,
    ) for i in range(n)])
    return pd.concat([df, fake], ignore_index=True)


if __name__ == "__main__":
    df = generate(400)
    df.to_csv("submissions.csv", index=False)
    WARDS.to_csv("wards.csv")

    print(f"Generated {len(df)} submissions\n")

    print("VOLUME is driven by voice, not need:")
    t = df.groupby("ward_id").size().rename("submissions").to_frame()
    t["per_1k"] = (t["submissions"] / WARDS["population"] * 1000).round(2)
    t["smartphone_%"] = WARDS["smartphone_pct"]
    t["TRUE water need"] = [TRUE_NEED[w]["water"] for w in t.index]
    print(t.to_string())
    print("\n  ↑ W22 has the HIGHEST true water need (0.95) and the FEWEST submissions.")
    print("    W07 has the LOWEST (0.05) and the MOST. That is the distortion, by construction.\n")

    print("MIX is driven by need (within each ward):")
    print(pd.crosstab(df.ward_id, df.true_sector).to_string())
    print("\nLanguage split:")
    print(df.groupby(["ward_id", "lang"]).size().unstack(fill_value=0).to_string())
    print("\nWrote submissions.csv, wards.csv")
