"""Social post placeholder; publishing is intentionally disabled."""

from src.outreach import disabled_for_current_milestone


def create_post_draft(*_args: object, **_kwargs: object) -> None:
    disabled_for_current_milestone()


def publish_post(*_args: object, **_kwargs: object) -> None:
    disabled_for_current_milestone()

