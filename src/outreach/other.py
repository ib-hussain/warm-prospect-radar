"""Generic outreach convenience functions."""

from src.models import BusinessRecord, OutreachChannel, OutreachDraft
from src.outreach.service import OutreachService


def create_other_draft(
    service: OutreachService, business: BusinessRecord, **kwargs: object
) -> OutreachDraft:
    return service.create_draft(business, OutreachChannel.OTHER, **kwargs)


def deliver_other(service: OutreachService, draft: OutreachDraft) -> OutreachDraft:
    return service.deliver(draft)
