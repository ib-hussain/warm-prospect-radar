"""Picture-outreach-specific convenience functions."""

from src.models import BusinessRecord, OutreachChannel, OutreachDraft
from src.outreach.service import OutreachService


def create_picture_draft(
    service: OutreachService, business: BusinessRecord, **kwargs: object
) -> OutreachDraft:
    return service.create_draft(business, OutreachChannel.PICTURE, **kwargs)


def publish_picture(service: OutreachService, draft: OutreachDraft) -> OutreachDraft:
    return service.deliver(draft)
