"""Environment-driven, cross-platform application configuration."""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from src.models import FeatureFlags

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path
    storage_path: Path
    data_backend: str
    supabase_url: str | None
    supabase_key: str | None
    supabase_bucket: str
    supabase_upload_raw: bool
    flask_secret_key: str
    app_host: str
    app_port: int
    app_debug: bool
    scraper_user_agent: str
    scraper_timeout_seconds: float
    scraper_max_pages: int
    scraper_max_depth: int
    scraper_delay_seconds: float
    scraper_respect_robots: bool
    scraper_js_fallback: bool
    playwright_executable_path: str | None
    scraper_verify_tls: bool
    allow_public_social_fallback: bool
    scraper_social_profile_limit: int
    enable_llm: bool
    llm_provider_order: tuple[str, ...]
    ollama_base_url: str
    ollama_model: str
    together_api_key: str | None
    together_model: str
    llm_timeout_seconds: float
    feature_acquisition_default: bool
    feature_social_acquisition_default: bool
    feature_llm_default: bool
    feature_outreach_default: bool
    feature_chatbot_default: bool
    feature_scheduled_refresh_default: bool
    feature_external_delivery_default: bool
    scheduler_interval_hours: float
    scheduler_initial_delay_seconds: float
    scheduler_max_businesses_per_run: int
    scheduler_run_in_web: bool
    assistant_max_businesses: int
    assistant_context_characters: int
    outreach_delivery_mode: str
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from_address: str | None
    smtp_use_tls: bool
    outreach_webhook_url: str | None
    outreach_webhook_secret: str | None

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def supabase_key_is_publishable(self) -> bool:
        if not self.supabase_key:
            return False
        if self.supabase_key.startswith("sb_publishable_"):
            return True
        parts = self.supabase_key.split(".")
        if len(parts) != 3:
            return False
        try:
            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
            return claims.get("role") in {"anon", "authenticated"}
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return False

    @property
    def selected_backend(self) -> str:
        if self.data_backend == "auto":
            return "supabase" if self.supabase_configured else "local"
        return self.data_backend

    def default_feature_flags(self) -> FeatureFlags:
        return FeatureFlags(
            acquisition_enabled=self.feature_acquisition_default,
            social_acquisition_enabled=self.feature_social_acquisition_default,
            llm_enabled=self.feature_llm_default,
            outreach_enabled=self.feature_outreach_default,
            chatbot_enabled=self.feature_chatbot_default,
            scheduled_refresh_enabled=self.feature_scheduled_refresh_default,
            external_delivery_enabled=self.feature_external_delivery_default,
        )

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)
        raw_storage = Path(os.getenv("STORAGE_PATH", "fileStorage")).expanduser()
        storage_path = raw_storage if raw_storage.is_absolute() else PROJECT_ROOT / raw_storage
        providers = tuple(
            item.strip().lower()
            for item in os.getenv("LLM_PROVIDER_ORDER", "ollama,together").split(",")
            if item.strip()
        )
        backend = os.getenv("DATA_BACKEND", "auto").strip().lower()
        if backend not in {"auto", "local", "supabase"}:
            backend = "auto"
        delivery_mode = os.getenv("OUTREACH_DELIVERY_MODE", "dry_run").strip().lower()
        if delivery_mode not in {"dry_run", "live"}:
            delivery_mode = "dry_run"
        return cls(
            project_root=PROJECT_ROOT,
            storage_path=storage_path.resolve(),
            data_backend=backend,
            supabase_url=os.getenv("SUPABASE_URL") or None,
            supabase_key=(os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_KEY") or None),
            supabase_bucket=os.getenv("SUPABASE_BUCKET", "business-snapshots"),
            supabase_upload_raw=_bool("SUPABASE_UPLOAD_RAW", False),
            flask_secret_key=os.getenv("FLASK_SECRET_KEY", "development-only-change-me"),
            app_host=os.getenv("APP_HOST", "127.0.0.1"),
            app_port=_int("APP_PORT", 5000, 1),
            app_debug=_bool("APP_DEBUG", True),
            scraper_user_agent=os.getenv(
                "SCRAPER_USER_AGENT", "WarmProspectRadar/0.1 (+contact@example.com)"
            ),
            scraper_timeout_seconds=_float("SCRAPER_TIMEOUT_SECONDS", 20.0, 1.0),
            scraper_max_pages=_int("SCRAPER_MAX_PAGES", 12, 1),
            scraper_max_depth=_int("SCRAPER_MAX_DEPTH", 2, 0),
            scraper_delay_seconds=_float("SCRAPER_DELAY_SECONDS", 0.15, 0.0),
            scraper_respect_robots=_bool("SCRAPER_RESPECT_ROBOTS", True),
            scraper_js_fallback=_bool("SCRAPER_JS_FALLBACK", True),
            playwright_executable_path=os.getenv("PLAYWRIGHT_EXECUTABLE_PATH") or None,
            scraper_verify_tls=_bool("SCRAPER_VERIFY_TLS", True),
            allow_public_social_fallback=_bool("ALLOW_PUBLIC_SOCIAL_FALLBACK", True),
            scraper_social_profile_limit=_int("SCRAPER_SOCIAL_PROFILE_LIMIT", 4, 0),
            enable_llm=_bool("ENABLE_LLM", True),
            llm_provider_order=providers,
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", "gemma3:1b"),
            together_api_key=os.getenv("TOGETHER_API_KEY") or None,
            together_model=os.getenv("TOGETHER_MODEL", "meta-llama/Llama-3.2-3B-Instruct-Turbo"),
            llm_timeout_seconds=_float("LLM_TIMEOUT_SECONDS", 75.0, 5.0),
            feature_acquisition_default=_bool("ENABLE_ACQUISITION", True),
            feature_social_acquisition_default=_bool("ENABLE_SOCIAL_ACQUISITION", True),
            feature_llm_default=_bool("ENABLE_LLM", True),
            feature_outreach_default=_bool("ENABLE_OUTREACH", True),
            feature_chatbot_default=_bool("ENABLE_CHATBOT", True),
            feature_scheduled_refresh_default=_bool("ENABLE_SCHEDULED_REFRESH", True),
            feature_external_delivery_default=_bool("ENABLE_EXTERNAL_DELIVERY", True),
            scheduler_interval_hours=_float("SCHEDULER_INTERVAL_HOURS", 24.0, 0.05),
            scheduler_initial_delay_seconds=_float("SCHEDULER_INITIAL_DELAY_SECONDS", 60.0, 0.0),
            scheduler_max_businesses_per_run=_int("SCHEDULER_MAX_BUSINESSES_PER_RUN", 100, 1),
            scheduler_run_in_web=_bool("SCHEDULER_RUN_IN_WEB", False),
            assistant_max_businesses=_int("ASSISTANT_MAX_BUSINESSES", 20, 1),
            assistant_context_characters=_int("ASSISTANT_CONTEXT_CHARACTERS", 24_000, 2_000),
            outreach_delivery_mode=delivery_mode,
            smtp_host=os.getenv("SMTP_HOST") or None,
            smtp_port=_int("SMTP_PORT", 587, 1),
            smtp_username=os.getenv("SMTP_USERNAME") or None,
            smtp_password=os.getenv("SMTP_PASSWORD") or None,
            smtp_from_address=os.getenv("SMTP_FROM_ADDRESS") or None,
            smtp_use_tls=_bool("SMTP_USE_TLS", True),
            outreach_webhook_url=os.getenv("OUTREACH_WEBHOOK_URL") or None,
            outreach_webhook_secret=os.getenv("OUTREACH_WEBHOOK_SECRET") or None,
        )
