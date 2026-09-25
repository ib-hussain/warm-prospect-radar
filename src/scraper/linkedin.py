"""LinkedIn acquisition adapter."""

from src.config import Settings
from src.models import SocialPlatform, SocialProfile
from src.scraper.social import SocialAcquisition, acquire_social_profile


def scrape_profile(url: str, handle: str | None = None, settings: Settings | None = None) -> SocialAcquisition:
    return acquire_social_profile(
        SocialProfile(platform=SocialPlatform.LINKEDIN, url=url, handle=handle),
        settings or Settings.from_env(),
    )

