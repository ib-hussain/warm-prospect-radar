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


class OutreachChannel(StrEnum):
    EMAIL = "email"
    DIRECT_MESSAGE = "direct_message"
    COMMENT = "comment"
    SOCIAL_POST = "social_post"
    PICTURE = "picture"
    OTHER = "other"


class OutreachStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    DELIVERED = "delivered"
    FAILED = "failed"


class InteractionKind(StrEnum):
    EMAIL_SENT = "email_sent"
    MESSAGE_SENT = "message_sent"
    COMMENT_POSTED = "comment_posted"
    POST_PUBLISHED = "post_published"
    REPLY_RECEIVED = "reply_received"
    POSITIVE_REPLY = "positive_reply"
    NEGATIVE_REPLY = "negative_reply"
    OTHER = "other"


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


class FeatureFlags(BaseModel):
    """Central workspace switches shared by every person using the application."""

    acquisition_enabled: bool = True
    social_acquisition_enabled: bool = True
    llm_enabled: bool = True
    outreach_enabled: bool = True
    chatbot_enabled: bool = True
    scheduled_refresh_enabled: bool = True
    external_delivery_enabled: bool = True
    updated_at: datetime = Field(default_factory=utc_now)


class OutreachDraft(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    business_id: UUID
    channel: OutreachChannel
    target: str | None = Field(default=None, max_length=1000)
    subject: str | None = Field(default=None, max_length=500)
    body: str = Field(min_length=1, max_length=50_000)
    media_prompt: str | None = Field(default=None, max_length=4000)
    approval_status: OutreachStatus = OutreachStatus.DRAFT
    provider: str | None = None
    provider_message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    reviewed_at: datetime | None = None
    delivered_at: datetime | None = None
    archived_at: datetime | None = None


class ProspectInteraction(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: UUID = Field(default_factory=uuid4)
    business_id: UUID
    occurred_at: datetime = Field(default_factory=utc_now)
    kind: InteractionKind
    channel: str | None = Field(default=None, max_length=100)
    summary: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    archived_at: datetime | None = None


class AssistantExchange(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: UUID = Field(default_factory=uuid4)
    question: str = Field(min_length=1, max_length=4000)
    answer: str = Field(min_length=1, max_length=30_000)
    provider: str = "deterministic"
    business_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
