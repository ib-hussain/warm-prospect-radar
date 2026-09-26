"""Direct-message-specific convenience functions."""

from src.models import BusinessRecord, OutreachChannel, OutreachDraft
from src.outreach.service import OutreachService


def create_message_draft(
    service: OutreachService, business: BusinessRecord, **kwargs: object
) -> OutreachDraft:
    return service.create_draft(business, OutreachChannel.DIRECT_MESSAGE, **kwargs)


def send_message(service: OutreachService, draft: OutreachDraft) -> OutreachDraft:
    return service.deliver(draft)
