from dataclasses import replace

import pytest

from src.config import Settings
from src.database import LocalRepository
from src.frontend import create_app
from src.models import BusinessRecord, ContactPoint, SocialPlatform, SocialProfile
from src.scoring import apply_scores


@pytest.fixture()
def app(tmp_path):
    settings = replace(
        Settings.from_env(),
        storage_path=tmp_path,
        data_backend="local",
        enable_llm=False,
        scraper_js_fallback=False,
        allow_public_social_fallback=False,
        app_debug=False,
    )
    repository = LocalRepository(tmp_path)
    business = apply_scores(
        BusinessRecord(
            name="Acme Robotics",
            description="Industrial automation systems.",
            website="https://acme.example",
            country_code="US",
            employee_count=250,
            gics_sector_code="20",
            gics_sector="Industrials",
            products_services=["Robotics"],
            source_urls=["https://acme.example"],
            contacts=[ContactPoint(kind="email", value="hello@acme.example")],
            social_profiles=[
                SocialProfile(
                    platform=SocialPlatform.LINKEDIN,
                    url="https://linkedin.com/company/acme",
                )
            ],
        )
    )
    repository.save_business(business)
    flask_app = create_app(settings, repository)
    flask_app.config.update(TESTING=True)
    flask_app.extensions["test_business"] = business
    return flask_app


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/", b"Find the signal"),
        ("/businesses", b"Acme Robotics"),
        ("/acquire", b"Wikipedia starters"),
        ("/progress", b"Acquisition progress"),
        ("/settings", b"Runtime settings"),
        ("/api/health", b'"status":"ok"'),
        ("/api/businesses", b"Acme Robotics"),
    ],
)
def test_routes_render(app, path, expected):
    response = app.test_client().get(path)
    assert response.status_code == 200
    assert expected in response.data


def test_business_detail_renders_score_and_evidence(app):
    business = app.extensions["test_business"]
    response = app.test_client().get(f"/businesses/{business.id}")
    assert response.status_code == 200
    assert b"Why this score?" in response.data
    assert b"hello@acme.example" in response.data


def test_unknown_business_returns_custom_404(app):
    response = app.test_client().get("/businesses/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 404
    assert b"Signal not found" in response.data

