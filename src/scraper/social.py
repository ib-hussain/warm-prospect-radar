"""Official social APIs with a bounded public-page fallback.

The fallback only reads pages that are already publicly accessible. It never imports
browser cookies, automates login, solves CAPTCHAs, or circumvents access controls.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from src.config import Settings
from src.models import PageSnapshot, SocialPlatform, SocialProfile
from src.scraper.webpage import WebScraper


@dataclass(slots=True)
class SocialAcquisition:
    platform: SocialPlatform
    url: str
    method: str = "unavailable"
    data: dict[str, object] = field(default_factory=dict)
    pages: list[PageSnapshot] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _identifier(profile: SocialProfile) -> str:
    if profile.handle:
        return profile.handle.lstrip("@")
    return urlsplit(profile.url).path.strip("/").split("/")[-1]


def _official_request(profile: SocialProfile, settings: Settings) -> dict[str, object]:
    identifier = _identifier(profile)
    timeout = settings.scraper_timeout_seconds
    if profile.platform in {SocialPlatform.FACEBOOK, SocialPlatform.INSTAGRAM}:
        token = os.getenv("META_ACCESS_TOKEN")
        if not token:
            raise ValueError("META_ACCESS_TOKEN is not configured")
        fields = (
            "id,username,name,biography,website,followers_count,media_count"
            if profile.platform == SocialPlatform.INSTAGRAM
            else "id,name,about,website,location,followers_count"
        )
        response = httpx.get(
            f"https://graph.facebook.com/v21.0/{identifier}",
            params={"fields": fields},
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
    elif profile.platform == SocialPlatform.X:
        token = os.getenv("X_BEARER_TOKEN")
        if not token:
            raise ValueError("X_BEARER_TOKEN is not configured")
        response = httpx.get(
            f"https://api.x.com/2/users/by/username/{identifier}",
            params={"user.fields": "description,location,public_metrics,url,verified"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
    elif profile.platform == SocialPlatform.LINKEDIN:
        token = os.getenv("LINKEDIN_ACCESS_TOKEN")
        organization_id = os.getenv("LINKEDIN_ORGANIZATION_ID")
        if not token or not organization_id:
            raise ValueError("LINKEDIN_ACCESS_TOKEN and LINKEDIN_ORGANIZATION_ID are required")
        response = httpx.get(
            f"https://api.linkedin.com/rest/organizations/{organization_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "LinkedIn-Version": os.getenv("LINKEDIN_API_VERSION", "202501"),
                "X-Restli-Protocol-Version": "2.0.0",
            },
            timeout=timeout,
        )
    elif profile.platform == SocialPlatform.GITHUB:
        token = os.getenv("GITHUB_TOKEN")
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = httpx.get(
            f"https://api.github.com/users/{identifier}", headers=headers, timeout=timeout
        )
    else:
        raise ValueError(f"No official adapter is configured for {profile.platform.value}")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Official platform response was not a JSON object")
    return payload


def acquire_social_profile(profile: SocialProfile, settings: Settings) -> SocialAcquisition:
    result = SocialAcquisition(platform=profile.platform, url=profile.url)
    try:
        result.data = _official_request(profile, settings)
        result.method = "official_api"
        result.pages.append(
            PageSnapshot(
                url=profile.url,
                final_url=profile.url,
                title=f"{profile.platform.value.title()} official API profile",
                text=json.dumps(result.data, ensure_ascii=False),
                status_code=200,
                content_type="application/json",
                renderer="official_api",
            )
        )
        return result
    except Exception as exc:
        result.warnings.append(f"{profile.platform.value} official API unavailable: {exc}")

    if not settings.allow_public_social_fallback:
        return result
    try:
        with WebScraper(profile.url, settings) as scraper:
            result.pages = scraper.scrape(max_pages=1, max_depth=0)
        if any(page.text for page in result.pages):
            result.method = "public_page"
        else:
            result.warnings.append("Public profile did not expose readable content.")
    except Exception as exc:
        result.warnings.append(f"Public profile fallback unavailable: {exc}")
    return result


def acquire_discovered_profiles(
    profiles: list[SocialProfile], settings: Settings, limit: int = 5
) -> tuple[list[PageSnapshot], list[str]]:
    pages: list[PageSnapshot] = []
    warnings: list[str] = []
    for profile in profiles[:limit]:
        acquired = acquire_social_profile(profile, settings)
        pages.extend(acquired.pages)
        warnings.extend(acquired.warnings)
    return pages, warnings
