"""Validated records exchanged by scrapers, storage, scoring, and the UI."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class SocialPlatform(StrEnum):
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    LINKEDIN = "linkedin"
    X = "x"
    YOUTUBE = "youtube"
    GITHUB = "github"
    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    OTHER = "other"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ContactPoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str
    value: str
    label: str | None = None
    source_url: str | None = None
    confidence: float = Field(default=0.8, ge=0, le=1)


class SocialProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    platform: SocialPlatform
    url: str
    handle: str | None = None
    source_url: str | None = None
    is_official: bool | None = None
    confidence: float = Field(default=0.75, ge=0, le=1)


class PageSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str
    final_url: str
    title: str | None = None
    description: str | None = None
    text: str = ""
    raw_html: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    depth: int = 0
    fetched_at: datetime = Field(default_factory=utc_now)
    renderer: str = "http"
    links: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class BusinessRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    name: str
    legal_name: str | None = None
    description: str | None = None
    website: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    founded_year: int | None = Field(default=None, ge=1000, le=2200)
    employee_count: int | None = Field(default=None, ge=0)
    employee_band: str | None = None
    gics_sector_code: str | None = Field(default=None, pattern=r"^\d{2}$")
    gics_sector: str | None = None
    gics_industry_group_code: str | None = Field(default=None, pattern=r"^\d{4}$")
    gics_industry_group: str | None = None
    gics_industry_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    gics_industry: str | None = None
    gics_sub_industry_code: str | None = Field(default=None, pattern=r"^\d{8}$")
    gics_sub_industry: str | None = None
    products_services: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    contacts: list[ContactPoint] = Field(default_factory=list)
    social_profiles: list[SocialProfile] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    prospect_likelihood: float = Field(default=0, ge=0, le=100)
    prospect_score: float = Field(default=0, ge=0, le=100)
    score_explanation: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str | None) -> str | None:
        return value.upper()[:2] if value else None

    @property
    def data_completeness(self) -> float:
        checks = [
            bool(self.name),
            bool(self.description),
            bool(self.website),
            bool(self.country_code),
            self.employee_count is not None,
            bool(self.gics_sector or self.gics_sector_code),
            bool(self.contacts),
            bool(self.social_profiles),
            bool(self.products_services),
            bool(self.source_urls),
        ]
        return round(100 * sum(checks) / len(checks), 1)


class InteractionSummary(BaseModel):
    attempts: int = Field(default=0, ge=0)
    replies: int = Field(default=0, ge=0)
    positive_replies: int = Field(default=0, ge=0)


class ScoreBreakdown(BaseModel):
    prospect_likelihood: float = Field(ge=0, le=100)
    prospect_score: float = Field(ge=0, le=100)
    size_accessibility: float = Field(ge=0, le=100)
    contactability: float = Field(ge=0, le=100)
    response_strength: float = Field(ge=0, le=100)
    difficulty_value: float = Field(ge=0, le=100)
    data_completeness: float = Field(ge=0, le=100)
    explanation: list[str]


class ScrapeRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    requested_url: str
    business_id: UUID | None = None
    status: RunStatus = RunStatus.QUEUED
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    pages_attempted: int = 0
    pages_succeeded: int = 0
    renderer_fallbacks: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    extraction_provider: str = "deterministic"


class BusinessSnapshot(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    business_id: UUID
    run_id: UUID
    version: int = Field(default=1, ge=1)
    source_url: str
    structured_data: dict[str, Any]
    raw_manifest: dict[str, Any]
    local_path: str | None = None
    storage_object_path: str | None = None
    content_hash: str
    created_at: datetime = Field(default_factory=utc_now)
