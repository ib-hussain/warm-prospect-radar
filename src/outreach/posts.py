"""Social-post-specific convenience functions."""

from src.models import BusinessRecord, OutreachChannel, OutreachDraft
from src.outreach.service import OutreachService


def create_post_draft(
    service: OutreachService, business: BusinessRecord, **kwargs: object
) -> OutreachDraft:
    return service.create_draft(business, OutreachChannel.SOCIAL_POST, **kwargs)


def publish_post(service: OutreachService, draft: OutreachDraft) -> OutreachDraft:
    return service.deliver(draft)
