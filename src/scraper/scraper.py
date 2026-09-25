"""End-to-end acquisition, extraction, scoring, and snapshot pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

from src.config import Settings
from src.database import Repository
from src.models import BusinessRecord, RunStatus, ScrapeRun
from src.scoring import apply_scores
from src.scraper.extractor import deterministic_extract, merge_llm_data
from src.scraper.llm import LLMExtractor
from src.scraper.social import acquire_discovered_profiles
from src.scraper.webpage import WebScraper, normalize_url, successful_pages
from src.storage import SnapshotWriter


class PipelineError(RuntimeError):
    def __init__(self, message: str, run: ScrapeRun):
        super().__init__(message)
        self.run = run


class BusinessScrapePipeline:
    def __init__(self, settings: Settings, repository: Repository):
        self.settings = settings
        self.repository = repository
        self.llm = LLMExtractor(settings)
        self.snapshot_writer = SnapshotWriter(settings)

    def _existing_match(self, candidate: BusinessRecord) -> BusinessRecord | None:
        matches = self.repository.list_businesses(query=candidate.name, limit=20)
        candidate_host = (urlsplit(candidate.website or "").hostname or "").removeprefix("www.")
        for item in matches:
            item_host = (urlsplit(item.website or "").hostname or "").removeprefix("www.")
            if candidate_host and item_host == candidate_host:
                return item
            if item.name.casefold() == candidate.name.casefold():
                return item
        return None

    def run(self, url: str, business_name: str | None = None) -> tuple[BusinessRecord, ScrapeRun]:
        normalized = normalize_url(url)
        run = ScrapeRun(requested_url=normalized, status=RunStatus.RUNNING)
        self.repository.save_run(run)
        pages = []
        try:
            with WebScraper(normalized, self.settings) as scraper:
                pages = scraper.scrape()
            good_pages = successful_pages(pages)
            run.pages_attempted = len(pages)
            run.pages_succeeded = len(good_pages)
            run.renderer_fallbacks = sum(page.renderer == "playwright" for page in good_pages)
            run.warnings.extend(warning for page in pages for warning in page.warnings)
            if not good_pages:
                raise ValueError("No page could be acquired and parsed. Review the run warnings.")

            business = deterministic_extract(good_pages, fallback_name=business_name)
            if business.social_profiles and self.settings.scraper_social_profile_limit:
                social_pages, social_warnings = acquire_discovered_profiles(
                    business.social_profiles,
                    self.settings,
                    limit=self.settings.scraper_social_profile_limit,
                )
                pages.extend(social_pages)
                run.warnings.extend(social_warnings)
                good_pages = successful_pages(pages)
                enriched = deterministic_extract(good_pages, fallback_name=business.name)
                contacts = {(item.kind, item.value): item for item in business.contacts}
                contacts.update({(item.kind, item.value): item for item in enriched.contacts})
                business.contacts = list(contacts.values())
                profiles = {(str(item.platform), item.url): item for item in business.social_profiles}
                profiles.update({(str(item.platform), item.url): item for item in enriched.social_profiles})
                business.social_profiles = list(profiles.values())
                business.source_urls = list(dict.fromkeys([*business.source_urls, *enriched.source_urls]))
                business.technologies = list(dict.fromkeys([*business.technologies, *enriched.technologies]))

            run.pages_attempted = len(pages)
            run.pages_succeeded = len(good_pages)
            run.renderer_fallbacks = sum(page.renderer == "playwright" for page in good_pages)
            llm_data, provider, llm_warnings = self.llm.extract(good_pages)
            run.extraction_provider = provider
            run.warnings.extend(llm_warnings)
            if llm_data:
                business = merge_llm_data(business, llm_data)

            existing = self._existing_match(business)
            if existing:
                business.id = existing.id
                business.created_at = existing.created_at
                # Previously confirmed fields and observations are retained on sparse refreshes.
                for field in (
                    "legal_name",
                    "city",
                    "region",
                    "country_code",
                    "gics_industry_group_code",
                    "gics_industry_group",
                    "gics_industry_code",
                    "gics_industry",
                    "gics_sub_industry_code",
                    "gics_sub_industry",
                ):
                    if getattr(business, field) in (None, ""):
                        setattr(business, field, getattr(existing, field))
                known_contacts = {(item.kind, item.value): item for item in existing.contacts}
                known_contacts.update({(item.kind, item.value): item for item in business.contacts})
                business.contacts = list(known_contacts.values())
                known_social = {(str(item.platform), item.url): item for item in existing.social_profiles}
                known_social.update({(str(item.platform), item.url): item for item in business.social_profiles})
                business.social_profiles = list(known_social.values())
                business.source_urls = list(dict.fromkeys([*existing.source_urls, *business.source_urls]))

            business.updated_at = datetime.now(UTC)
            business = apply_scores(business)
            self.repository.save_business(business)
            run.business_id = business.id
            previous = self.repository.list_snapshots(business.id)
            version = max((item.version for item in previous), default=0) + 1
            run.status = RunStatus.PARTIAL if run.warnings else RunStatus.COMPLETED
            run.finished_at = datetime.now(UTC)
            snapshot = self.snapshot_writer.persist(business, run, pages, version)
            self.repository.save_snapshot(snapshot)
            self.repository.save_run(run)
            return business, run
        except Exception as exc:
            run.status = RunStatus.FAILED
            run.finished_at = datetime.now(UTC)
            run.errors.append(str(exc))
            try:
                self.repository.save_run(run)
            except Exception:
                pass
            raise PipelineError(str(exc), run) from exc


def save_business_json(
    url: str, settings: Settings, repository: Repository, business_name: str | None = None
) -> BusinessRecord:
    """Small compatibility function for scripts that only need the saved record."""
    business, _ = BusinessScrapePipeline(settings, repository).run(url, business_name)
    return business
