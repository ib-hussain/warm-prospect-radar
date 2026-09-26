from pathlib import Path

import pytest

from src.models import PageSnapshot, SocialPlatform
from src.scraper.extractor import deterministic_extract
from src.scraper.llm import LLMExtractor
from src.scraper.webpage import FetchResult, WebScraper, _public_host, normalize_url

FIXTURE = Path(__file__).parent / "fixtures" / "company.html"


def test_normalize_url_removes_fragments_and_tracking():
    assert (
        normalize_url("Example.com/about?utm_source=test&id=4#team")
        == "https://example.com/about?id=4"
    )
    assert normalize_url("/about", "https://example.com/") == "https://example.com/about"
    with pytest.raises(ValueError):
        normalize_url("ftp://example.com/file")


def test_private_network_targets_are_rejected():
    assert _public_host("http://127.0.0.1/admin") is False
    assert _public_host("http://[::1]/admin") is False


def test_page_parse_and_deterministic_extraction():
    html = FIXTURE.read_text(encoding="utf-8")
    result = FetchResult(
        html=html,
        final_url="https://acme.example/",
        status_code=200,
        content_type="text/html",
        renderer="http",
        warnings=[],
    )
    page = WebScraper._parse(result, depth=0)
    business = deterministic_extract([page])

    assert page.raw_html == html
    assert business.name == "Acme Robotics"
    assert business.founded_year == 1987
    assert business.employee_count == 250
    assert business.employee_band == "200-499"
    assert business.gics_sector == "Industrials"
    assert business.website == "https://acme.example/"
    assert business.products_services == ["Industrial robots", "control systems"]
    assert "Python" in business.technologies
    assert any(
        item.kind == "email" and item.value == "hello@acme.example" for item in business.contacts
    )
    assert {item.platform for item in business.social_profiles} == {
        SocialPlatform.LINKEDIN,
        SocialPlatform.X,
    }


def test_llm_json_parser_handles_fenced_response():
    parsed = LLMExtractor._parse_json(
        '```json\n{"city":"Detroit","products_services":["Robots"]}\n```'
    )
    assert parsed["city"] == "Detroit"
    assert parsed["products_services"] == ["Robots"]
    assert "gics_sector" in parsed


def test_failed_page_is_not_successful():
    page = PageSnapshot(
        url="https://example.com/private",
        final_url="https://example.com/private",
        warnings=["blocked"],
    )
    assert not page.text
    assert page.status_code is None
