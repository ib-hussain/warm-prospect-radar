"""Repository layer for local development and Supabase-backed shared use."""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from src.config import Settings
from src.models import BusinessRecord, BusinessSnapshot, ScrapeRun


class StorageError(RuntimeError):
    """Raised when a configured persistence backend cannot complete an operation."""


class Repository(Protocol):
    backend_name: str

    def list_businesses(
        self, query: str = "", sector: str = "", limit: int = 200
    ) -> list[BusinessRecord]: ...

    def get_business(self, business_id: str | UUID) -> BusinessRecord | None: ...

    def save_business(self, business: BusinessRecord) -> BusinessRecord: ...

    def archive_business(self, business_id: str | UUID) -> bool: ...

    def save_run(self, run: ScrapeRun) -> ScrapeRun: ...

    def list_runs(self, limit: int = 100) -> list[ScrapeRun]: ...

    def save_snapshot(self, snapshot: BusinessSnapshot) -> BusinessSnapshot: ...

    def list_snapshots(self, business_id: str | UUID) -> list[BusinessSnapshot]: ...


class LocalRepository:
    """Small atomic JSON repository used when Supabase is not configured.

    It makes the application immediately runnable and testable. Supabase should be
    used for multiple processes or multiple machines.
    """

    backend_name = "local"

    def __init__(self, storage_path: Path):
        self.path = storage_path / "json" / "local_database.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write({"businesses": {}, "runs": {}, "snapshots": {}})

    def _read(self) -> dict[str, Any]:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"Local data store could not be read: {exc}") from exc
        payload.setdefault("businesses", {})
        payload.setdefault("runs", {})
        payload.setdefault("snapshots", {})
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
            temporary.replace(self.path)
        except OSError as exc:
            raise StorageError(f"Local data store could not be written: {exc}") from exc

    def list_businesses(
        self, query: str = "", sector: str = "", limit: int = 200
    ) -> list[BusinessRecord]:
        with self._lock:
            items = [BusinessRecord.model_validate(row) for row in self._read()["businesses"].values()]
        query_folded = query.casefold().strip()
        sector_folded = sector.casefold().strip()
        filtered = [
            item
            for item in items
            if item.archived_at is None
            and (
                not query_folded
                or query_folded in item.name.casefold()
                or query_folded in (item.description or "").casefold()
                or query_folded in (item.website or "").casefold()
            )
            and (
                not sector_folded
                or sector_folded in (item.gics_sector or "").casefold()
                or sector_folded in (item.gics_sector_code or "").casefold()
            )
        ]
        return sorted(filtered, key=lambda item: item.updated_at, reverse=True)[:limit]

    def get_business(self, business_id: str | UUID) -> BusinessRecord | None:
        with self._lock:
            row = self._read()["businesses"].get(str(business_id))
        return BusinessRecord.model_validate(row) if row else None

    def save_business(self, business: BusinessRecord) -> BusinessRecord:
        with self._lock:
            payload = self._read()
            payload["businesses"][str(business.id)] = business.model_dump(mode="json")
            self._write(payload)
        return business

    def archive_business(self, business_id: str | UUID) -> bool:
        from src.models import utc_now

        with self._lock:
            payload = self._read()
            row = payload["businesses"].get(str(business_id))
            if not row:
                return False
            row["archived_at"] = utc_now().isoformat()
            self._write(payload)
        return True

    def save_run(self, run: ScrapeRun) -> ScrapeRun:
        with self._lock:
            payload = self._read()
            payload["runs"][str(run.id)] = run.model_dump(mode="json")
            self._write(payload)
        return run

    def list_runs(self, limit: int = 100) -> list[ScrapeRun]:
        with self._lock:
            runs = [ScrapeRun.model_validate(row) for row in self._read()["runs"].values()]
        return sorted(runs, key=lambda item: item.started_at, reverse=True)[:limit]

    def save_snapshot(self, snapshot: BusinessSnapshot) -> BusinessSnapshot:
        with self._lock:
            payload = self._read()
            payload["snapshots"][str(snapshot.id)] = snapshot.model_dump(mode="json")
            self._write(payload)
        return snapshot

    def list_snapshots(self, business_id: str | UUID) -> list[BusinessSnapshot]:
        target = str(business_id)
        with self._lock:
            rows = self._read()["snapshots"].values()
            snapshots = [
                BusinessSnapshot.model_validate(row)
                for row in rows
                if str(row.get("business_id")) == target
            ]
        return sorted(snapshots, key=lambda item: item.version, reverse=True)


class SupabaseRepository:
    """Shared repository implemented through Supabase's PostgREST client."""

    backend_name = "supabase"

    def __init__(self, settings: Settings):
        if not settings.supabase_configured:
            raise StorageError("Supabase URL and key are required for the Supabase backend.")
        try:
            from supabase import create_client
        except ImportError as exc:
            raise StorageError("Install the 'supabase' package before using this backend.") from exc
        self.client = create_client(settings.supabase_url, settings.supabase_key)

    @staticmethod
    def _business_row(business: BusinessRecord) -> dict[str, Any]:
        return {
            "id": str(business.id),
            "name": business.name,
            "legal_name": business.legal_name,
            "description": business.description,
            "website": business.website,
            "city": business.city,
            "region": business.region,
            "country_code": business.country_code,
            "founded_year": business.founded_year,
            "employee_count": business.employee_count,
            "employee_band": business.employee_band,
            "gics_sector_code": business.gics_sector_code,
            "gics_sector": business.gics_sector,
            "gics_industry_group_code": business.gics_industry_group_code,
            "gics_industry_group": business.gics_industry_group,
            "gics_industry_code": business.gics_industry_code,
            "gics_industry": business.gics_industry,
            "gics_sub_industry_code": business.gics_sub_industry_code,
            "gics_sub_industry": business.gics_sub_industry,
            "products_services": business.products_services,
            "technologies": business.technologies,
            "keywords": business.keywords,
            "source_urls": business.source_urls,
            "prospect_likelihood": business.prospect_likelihood,
            "prospect_score": business.prospect_score,
            "score_explanation": business.score_explanation,
            "created_at": business.created_at.isoformat(),
            "updated_at": business.updated_at.isoformat(),
            "archived_at": business.archived_at.isoformat() if business.archived_at else None,
        }

    def _hydrate(self, rows: Iterable[dict[str, Any]]) -> list[BusinessRecord]:
        base_rows = list(rows)
        if not base_rows:
            return []
        ids = [row["id"] for row in base_rows]
        contacts = (
            self.client.table("business_contacts")
            .select("business_id,kind,value,label,source_url,confidence")
            .in_("business_id", ids)
            .is_("archived_at", "null")
            .execute()
            .data
            or []
        )
        profiles = (
            self.client.table("business_social_profiles")
            .select("business_id,platform,url,handle,source_url,is_official,confidence")
            .in_("business_id", ids)
            .is_("archived_at", "null")
            .execute()
            .data
            or []
        )
        contact_map: dict[str, list[dict[str, Any]]] = {item: [] for item in ids}
        profile_map: dict[str, list[dict[str, Any]]] = {item: [] for item in ids}
        for contact in contacts:
            contact_map.setdefault(contact.pop("business_id"), []).append(contact)
        for profile in profiles:
            profile_map.setdefault(profile.pop("business_id"), []).append(profile)
        hydrated = []
        for row in base_rows:
            row = dict(row)
            row["contacts"] = contact_map.get(row["id"], [])
            row["social_profiles"] = profile_map.get(row["id"], [])
            hydrated.append(BusinessRecord.model_validate(row))
        return hydrated

    def list_businesses(
        self, query: str = "", sector: str = "", limit: int = 200
    ) -> list[BusinessRecord]:
        request = (
            self.client.table("businesses")
            .select("*")
            .is_("archived_at", "null")
            .order("updated_at", desc=True)
            .limit(limit)
        )
        if query.strip():
            safe = re.sub(r"[%(),*]", " ", query.strip())[:120]
            request = request.or_(f"name.ilike.%{safe}%,description.ilike.%{safe}%,website.ilike.%{safe}%")
        if sector.strip():
            safe_sector = re.sub(r"[%(),*]", " ", sector.strip())[:100]
            request = request.ilike("gics_sector", f"%{safe_sector}%")
        try:
            return self._hydrate(request.execute().data or [])
        except Exception as exc:
            raise StorageError(f"Supabase could not list businesses: {exc}") from exc

    def get_business(self, business_id: str | UUID) -> BusinessRecord | None:
        try:
            rows = (
                self.client.table("businesses")
                .select("*")
                .eq("id", str(business_id))
                .limit(1)
                .execute()
                .data
                or []
            )
            hydrated = self._hydrate(rows)
            return hydrated[0] if hydrated else None
        except Exception as exc:
            raise StorageError(f"Supabase could not load the business: {exc}") from exc

    def save_business(self, business: BusinessRecord) -> BusinessRecord:
        try:
            self.client.table("businesses").upsert(self._business_row(business)).execute()
            observed_at = business.updated_at.isoformat()
            if business.website:
                website_id = uuid5(NAMESPACE_URL, f"{business.id}:website:{business.website}")
                self.client.table("business_websites").upsert(
                    {
                        "id": str(website_id),
                        "business_id": str(business.id),
                        "url": business.website,
                        "label": "Primary website",
                        "is_primary": True,
                        "last_seen_at": observed_at,
                        "archived_at": None,
                    }
                ).execute()
            contact_rows = []
            for contact in business.contacts:
                stable = uuid5(NAMESPACE_URL, f"{business.id}:contact:{contact.kind}:{contact.value}")
                contact_rows.append(
                    {
                        "id": str(stable),
                        "business_id": str(business.id),
                        **contact.model_dump(mode="json"),
                        "last_seen_at": observed_at,
                        "archived_at": None,
                    }
                )
            profile_rows = []
            for profile in business.social_profiles:
                stable = uuid5(NAMESPACE_URL, f"{business.id}:social:{profile.platform}:{profile.url}")
                profile_rows.append(
                    {
                        "id": str(stable),
                        "business_id": str(business.id),
                        **profile.model_dump(mode="json"),
                        "last_seen_at": observed_at,
                        "archived_at": None,
                    }
                )
            if contact_rows:
                self.client.table("business_contacts").upsert(contact_rows).execute()
            if profile_rows:
                self.client.table("business_social_profiles").upsert(profile_rows).execute()
            return business
        except Exception as exc:
            raise StorageError(f"Supabase could not save the business: {exc}") from exc

    def archive_business(self, business_id: str | UUID) -> bool:
        try:
            result = self.client.rpc(
                "archive_business",
                {"p_business_id": str(business_id), "p_actor_user_id": None},
            ).execute()
            return result.data is True
        except Exception as exc:
            raise StorageError(f"Supabase could not archive the business: {exc}") from exc

    def save_run(self, run: ScrapeRun) -> ScrapeRun:
        row = run.model_dump(mode="json")
        row["id"] = str(run.id)
        row["business_id"] = str(run.business_id) if run.business_id else None
        try:
            self.client.table("scrape_runs").upsert(row).execute()
            return run
        except Exception as exc:
            raise StorageError(f"Supabase could not save the scrape run: {exc}") from exc

    def list_runs(self, limit: int = 100) -> list[ScrapeRun]:
        try:
            rows = (
                self.client.table("scrape_runs")
                .select("*")
                .order("started_at", desc=True)
                .limit(limit)
                .execute()
                .data
                or []
            )
            return [ScrapeRun.model_validate(row) for row in rows]
        except Exception as exc:
            raise StorageError(f"Supabase could not list scrape runs: {exc}") from exc

    def save_snapshot(self, snapshot: BusinessSnapshot) -> BusinessSnapshot:
        row = snapshot.model_dump(mode="json")
        for field in ("id", "business_id", "run_id"):
            row[field] = str(row[field])
        try:
            self.client.table("business_snapshots").upsert(row).execute()
            return snapshot
        except Exception as exc:
            raise StorageError(f"Supabase could not save the snapshot: {exc}") from exc

    def list_snapshots(self, business_id: str | UUID) -> list[BusinessSnapshot]:
        try:
            rows = (
                self.client.table("business_snapshots")
                .select("*")
                .eq("business_id", str(business_id))
                .order("version", desc=True)
                .execute()
                .data
                or []
            )
            return [BusinessSnapshot.model_validate(row) for row in rows]
        except Exception as exc:
            raise StorageError(f"Supabase could not list snapshots: {exc}") from exc


def build_repository(settings: Settings) -> Repository:
    if settings.selected_backend == "supabase":
        return SupabaseRepository(settings)
    return LocalRepository(settings.storage_path)
