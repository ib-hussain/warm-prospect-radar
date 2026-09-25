"""Outreach boundary for a later milestone.

No module in this package sends, publishes, comments, messages, or uploads content.
The current product is intentionally acquisition-and-review only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


class OutreachDisabledError(RuntimeError):
    pass


@dataclass(slots=True)
class OutreachDraft:
    business_id: UUID
    channel: str
    subject: str | None = None
    body: str = ""
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    approval_status: str = "draft"


def disabled_for_current_milestone() -> None:
    raise OutreachDisabledError(
        "Outreach is disabled in the scraper-first milestone. No external action was taken."
    )


__all__ = ["OutreachDisabledError", "OutreachDraft", "disabled_for_current_milestone"]

