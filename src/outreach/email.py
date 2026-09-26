"""Email-specific convenience functions."""

from src.models import BusinessRecord, OutreachChannel, OutreachDraft
from src.outreach.service import OutreachService


def create_email_draft(
    service: OutreachService, business: BusinessRecord, **kwargs: object
) -> OutreachDraft:
    return service.create_draft(business, OutreachChannel.EMAIL, **kwargs)


def send_email(service: OutreachService, draft: OutreachDraft) -> OutreachDraft:
    return service.deliver(draft)
