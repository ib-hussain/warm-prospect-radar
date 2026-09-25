from src.models import (
    BusinessRecord,
    ContactPoint,
    InteractionSummary,
    SocialPlatform,
    SocialProfile,
)
from src.scoring import calculate_scores


def business_with_size(name: str, employees: int) -> BusinessRecord:
    return BusinessRecord(
        name=name,
        employee_count=employees,
        website=f"https://{name.lower()}.example",
        description="A test business with enough data for scoring.",
        country_code="US",
        gics_sector_code="45",
        gics_sector="Information Technology",
        products_services=["Software"],
        source_urls=[f"https://{name.lower()}.example"],
        contacts=[ContactPoint(kind="email", value=f"hello@{name.lower()}.example")],
        social_profiles=[SocialProfile(platform=SocialPlatform.LINKEDIN, url="https://linkedin.com/company/test")],
    )


def test_likelihood_is_inversely_related_to_company_size():
    small = calculate_scores(business_with_size("Small", 25))
    large = calculate_scores(business_with_size("Large", 250_000))
    assert small.prospect_likelihood > large.prospect_likelihood
    assert large.difficulty_value > small.difficulty_value


def test_response_evidence_increases_prospect_score():
    business = business_with_size("Acme", 5000)
    no_response = calculate_scores(business)
    replies = calculate_scores(
        business,
        InteractionSummary(attempts=10, replies=6, positive_replies=4),
    )
    assert replies.response_strength > no_response.response_strength
    assert replies.prospect_score > no_response.prospect_score
    assert any("65%" in line for line in replies.explanation)

