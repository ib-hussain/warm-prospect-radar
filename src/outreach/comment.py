"""Social-comment-specific convenience functions."""

from src.models import BusinessRecord, OutreachChannel, OutreachDraft
from src.outreach.service import OutreachService


def create_comment_draft(
    service: OutreachService, business: BusinessRecord, **kwargs: object
) -> OutreachDraft:
    return service.create_draft(business, OutreachChannel.COMMENT, **kwargs)


def publish_comment(service: OutreachService, draft: OutreachDraft) -> OutreachDraft:
    return service.deliver(draft)
