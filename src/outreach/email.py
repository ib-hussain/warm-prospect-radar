"""Email outreach placeholder; sending is intentionally disabled."""

from src.outreach import disabled_for_current_milestone


def create_email_draft(*_args: object, **_kwargs: object) -> None:
    disabled_for_current_milestone()


def send_email(*_args: object, **_kwargs: object) -> None:
    disabled_for_current_milestone()

