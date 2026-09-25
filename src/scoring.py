"""Transparent starter scoring model.

Likelihood intentionally decreases as employee count rises. Prospect score rewards
observed responses and assigns some value to a difficult prospect whose likelihood is
low, matching the initial product hypothesis. Every component is retained for review.
"""

from __future__ import annotations

import math

from src.models import BusinessRecord, InteractionSummary, ScoreBreakdown


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return min(high, max(low, value))


def _size_accessibility(employee_count: int | None) -> float:
    if employee_count is None:
        return 50.0
    if employee_count <= 1:
        return 95.0
    # Approximately: 100 employees -> 82; 10,000 -> 46; 1,000,000 -> 10.
    return _clamp(100 - max(0, math.log10(employee_count) - 1) * 18, 5, 95)


def _contactability(business: BusinessRecord) -> float:
    score = 15.0
    if business.website:
        score += 15
    score += min(35, len(business.contacts) * 14)
    score += min(25, len(business.social_profiles) * 5)
    if business.city or business.country_code:
        score += 10
    return _clamp(score)


def _response_strength(interactions: InteractionSummary) -> float:
    if interactions.attempts == 0:
        return 0.0
    reply_rate = interactions.replies / interactions.attempts
    positive_rate = interactions.positive_replies / interactions.attempts
    evidence = min(1.0, math.log2(interactions.attempts + 1) / 4)
    return _clamp((reply_rate * 70 + positive_rate * 30) * (0.5 + 0.5 * evidence))


def calculate_scores(
    business: BusinessRecord, interactions: InteractionSummary | None = None
) -> ScoreBreakdown:
    interactions = interactions or InteractionSummary()
    size_accessibility = _size_accessibility(business.employee_count)
    contactability = _contactability(business)
    response_strength = _response_strength(interactions)
    completeness = business.data_completeness

    likelihood = _clamp(size_accessibility * 0.80 + contactability * 0.20)
    difficulty_value = 100 - likelihood
    prospect_score = _clamp(
        response_strength * 0.65 + difficulty_value * 0.25 + completeness * 0.10
    )

    employee_label = (
        f"{business.employee_count:,} known employees" if business.employee_count is not None else "unknown size"
    )
    explanation = [
        f"Size accessibility is {size_accessibility:.1f}/100 from {employee_label}; larger companies receive lower likelihood.",
        f"Contactability is {contactability:.1f}/100 from available website, contact and social fields.",
        f"Response strength is {response_strength:.1f}/100 from {interactions.replies} replies across {interactions.attempts} attempts.",
        "Prospect score combines response evidence (65%), difficulty value (25%) and data completeness (10%).",
    ]

    return ScoreBreakdown(
        prospect_likelihood=round(likelihood, 1),
        prospect_score=round(prospect_score, 1),
        size_accessibility=round(size_accessibility, 1),
        contactability=round(contactability, 1),
        response_strength=round(response_strength, 1),
        difficulty_value=round(difficulty_value, 1),
        data_completeness=round(completeness, 1),
        explanation=explanation,
    )


def apply_scores(
    business: BusinessRecord, interactions: InteractionSummary | None = None
) -> BusinessRecord:
    breakdown = calculate_scores(business, interactions)
    business.prospect_likelihood = breakdown.prospect_likelihood
    business.prospect_score = breakdown.prospect_score
    business.score_explanation = breakdown.model_dump(mode="json")
    return business

