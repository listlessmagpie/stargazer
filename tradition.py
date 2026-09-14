"""Traditional electional astrology rules for financial decisions.

Encodes centuries of electional practice as a second signal layer
alongside the empirical backtest data. The oracle already provides
the factors these rules need: moon sign, phase, waxing/waning,
void of course, and active retrogrades.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TraditionalReading:
    score: float          # -1.0 (strongly avoid) to +1.0 (strongly favor)
    factors: list[str]    # plain language reasons
    cautions: list[str]   # warnings even if score is positive


# Moon sign affinities for financial matters (traditional electional)
SIGN_FINANCE = {
    # Earth signs: material world, stability, practical gain
    "Taurus":     +0.3,   # Venus ruled, values, possessions, steady growth
    "Virgo":      +0.2,   # Mercury ruled, analysis, precision, careful investment
    "Capricorn":  +0.2,   # Saturn ruled, discipline, long term gain, structure

    # Scorpio: other people's money, transformation, deep research
    "Scorpio":    +0.25,  # Pluto/Mars ruled, shared resources, strategic moves

    # Fixed signs carry staying power
    "Leo":        +0.1,   # Sun ruled, confidence, but ego can cloud judgment
    "Aquarius":   +0.1,   # Saturn/Uranus ruled, innovation, unconventional plays

    # Mutable signs: adaptability but less stability for finance
    "Gemini":     +0.0,   # Mercury ruled, quick but scattered
    "Sagittarius": +0.05, # Jupiter ruled, expansion, but overreach risk

    # Cardinal water: emotions drive decisions
    "Cancer":     -0.2,   # Moon ruled, emotional spending, insecurity
    "Pisces":     -0.2,   # Neptune ruled, confusion, illusion, dissolving boundaries

    # Cardinal fire: impulsive
    "Aries":      -0.1,   # Mars ruled, impulsive, hasty decisions

    # Cardinal air: indecision
    "Libra":      -0.05,  # Venus ruled but cardinal air, weighing without acting
}

# Moon phase traditional meanings for finance
PHASE_FINANCE = {
    "new_moon":          -0.2,   # too early, seeds not yet sprouted, wait
    "waxing_crescent":   +0.2,   # intention setting, early momentum
    "first_quarter":     +0.1,   # action phase, challenges to overcome
    "waxing_gibbous":    +0.25,  # building toward fullness, strong momentum
    "full_moon":         +0.1,   # culmination, clarity, but emotional peaks
    "waning_gibbous":    -0.05,  # gratitude phase, begin releasing
    "last_quarter":      -0.1,   # release, let go, not ideal for new positions
    "waning_crescent":   -0.15,  # surrender, rest, closing out
}

# Retrograde impacts on financial decisions
RETROGRADE_RULES: dict[str, tuple[float, str]] = {
    "Mercury": (-0.3, "Mercury retrograde: communication breakdowns, contract errors, revisit rather than initiate"),
    "Venus":   (-0.25, "Venus retrograde: reassess values and worth, avoid new purchases or investments"),
    "Mars":    (-0.2, "Mars retrograde: depleted drive, avoid aggressive or speculative trades"),
    "Jupiter": (-0.1, "Jupiter retrograde: inward growth, expansion stalls, review rather than expand"),
    "Saturn":  (-0.05, "Saturn retrograde: karmic review, internal restructuring, existing commitments still hold"),
}


def assess(
    moon_sign: str,
    moon_phase: str,
    waxing: bool,
    void_of_course: bool,
    retrogrades: list[str],
) -> TraditionalReading:
    """Assess current conditions through the lens of traditional electional astrology."""
    score = 0.0
    factors = []
    cautions = []

    # Moon sign
    sign_val = SIGN_FINANCE.get(moon_sign, 0.0)
    score += sign_val
    if sign_val > 0.15:
        factors.append(f"Moon in {moon_sign} traditionally favors financial matters")
    elif sign_val > 0:
        factors.append(f"Moon in {moon_sign} is mildly supportive for finance")
    elif sign_val < -0.1:
        cautions.append(f"Moon in {moon_sign} traditionally cautions against financial decisions")
    elif sign_val < 0:
        cautions.append(f"Moon in {moon_sign} is mildly unfavorable for finance")

    # Moon phase
    phase_val = PHASE_FINANCE.get(moon_phase, 0.0)
    score += phase_val
    if phase_val > 0.15:
        factors.append(f"{moon_phase.replace('_', ' ').title()} is a strong phase for financial growth")
    elif phase_val > 0:
        factors.append(f"{moon_phase.replace('_', ' ').title()} supports action")
    elif phase_val < -0.1:
        cautions.append(f"{moon_phase.replace('_', ' ').title()} traditionally favors releasing, not acquiring")

    # Waxing vs waning (fundamental electional principle)
    if waxing:
        score += 0.1
        factors.append("Waxing moon supports growth and new acquisitions")
    else:
        score -= 0.1
        cautions.append("Waning moon favors completion and release over new positions")

    # Void of course (the cardinal rule of electional astrology)
    if void_of_course:
        score -= 0.5
        cautions.append("Moon is void of course: nothing begun now will come to fruition (the strongest electional prohibition)")

    # Retrogrades
    for planet in retrogrades:
        planet_clean = planet.strip().title()
        if planet_clean in RETROGRADE_RULES:
            penalty, reason = RETROGRADE_RULES[planet_clean]
            score += penalty
            cautions.append(reason)

    score = max(-1.0, min(1.0, score))

    return TraditionalReading(
        score=round(score, 3),
        factors=factors,
        cautions=cautions,
    )


def explain_sign(sign: str) -> str:
    """Return a brief traditional interpretation of a moon sign for finance."""
    explanations = {
        "Aries": "Cardinal fire. Impulsive energy, first to act. Risk of hasty financial decisions. Better for bold moves than careful planning.",
        "Taurus": "Fixed earth, Venus ruled. The sign of material value, possessions, and steady accumulation. One of the strongest financial signs.",
        "Gemini": "Mutable air, Mercury ruled. Quick trades, information gathering, dual positions. Adaptable but scattered.",
        "Cancer": "Cardinal water, Moon ruled. Emotional attachment to security. Fear driven decisions. Traditional caution for financial matters.",
        "Leo": "Fixed fire, Sun ruled. Confident, generous, but ego can inflate risk tolerance. Good for leadership positions, risky for speculation.",
        "Virgo": "Mutable earth, Mercury ruled. Analytical, precise, detail oriented. Favors careful analysis and incremental gains.",
        "Libra": "Cardinal air, Venus ruled. Seeks balance and fairness. Can lead to indecision in fast moving markets.",
        "Scorpio": "Fixed water, Pluto/Mars ruled. Other people's money, shared resources, deep research. Transformation and strategic moves.",
        "Sagittarius": "Mutable fire, Jupiter ruled. Expansion, optimism, big picture thinking. Risk of overextension.",
        "Capricorn": "Cardinal earth, Saturn ruled. Discipline, structure, long term planning. Favors conservative, well structured positions.",
        "Aquarius": "Fixed air, Saturn/Uranus ruled. Innovation, unconventional approaches. Good for new technology plays.",
        "Pisces": "Mutable water, Neptune ruled. Intuition and imagination, but also confusion and illusion. Poor clarity for financial decisions.",
    }
    return explanations.get(sign, f"No traditional data for {sign}")
