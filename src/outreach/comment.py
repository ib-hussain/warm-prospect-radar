"""Social comment placeholder; publishing is intentionally disabled."""

from src.outreach import disabled_for_current_milestone


def create_comment_draft(*_args: object, **_kwargs: object) -> None:
    disabled_for_current_milestone()


def publish_comment(*_args: object, **_kwargs: object) -> None:
    disabled_for_current_milestone()

