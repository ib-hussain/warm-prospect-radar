"""Immutable snapshot writing to local storage and, optionally, Supabase Storage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.config import Settings
from src.models import BusinessRecord, BusinessSnapshot, PageSnapshot, ScrapeRun


class SnapshotWriter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.storage_path / "json" / "snapshots"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _canonical_bytes(payload: dict[str, Any]) -> bytes:
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def persist(
        self,
        business: BusinessRecord,
        run: ScrapeRun,
        pages: list[PageSnapshot],
        version: int,
    ) -> BusinessSnapshot:
        payload = {
            "business": business.model_dump(mode="json"),
            "run": run.model_dump(mode="json"),
            "pages": [page.model_dump(mode="json") for page in pages],
        }
        encoded = self._canonical_bytes(payload)
        digest = hashlib.sha256(encoded).hexdigest()
        relative = Path(str(business.id)) / f"v{version:04d}-{run.id}.json"
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(encoded)
        temporary.replace(destination)

        object_path: str | None = None
        if self.settings.supabase_configured and self.settings.supabase_upload_raw:
            object_path = relative.as_posix()
            try:
                from supabase import create_client

                client = create_client(self.settings.supabase_url, self.settings.supabase_key)
                bucket = client.storage.from_(self.settings.supabase_bucket)
                try:
                    bucket.upload(
                        object_path,
                        encoded,
                        {"content-type": "application/json", "upsert": "true"},
                    )
                except Exception:
                    bucket.update(
                        object_path,
                        encoded,
                        {"content-type": "application/json", "upsert": "true"},
                    )
            except Exception as exc:
                run.warnings.append(f"Raw Supabase Storage upload failed: {exc}")
                object_path = None

        manifest = {
            "page_count": len(pages),
            "urls": [page.final_url for page in pages],
            "renderers": sorted({page.renderer for page in pages}),
            "raw_html_bytes": sum(len((page.raw_html or "").encode("utf-8")) for page in pages),
            "warnings": [warning for page in pages for warning in page.warnings],
        }
        try:
            local_path = str(destination.relative_to(self.settings.project_root))
        except ValueError:
            local_path = str(destination)
        return BusinessSnapshot(
            business_id=business.id,
            run_id=run.id,
            version=version,
            source_url=run.requested_url,
            structured_data=business.model_dump(mode="json"),
            raw_manifest=manifest,
            local_path=local_path,
            storage_object_path=object_path,
            content_hash=digest,
        )
