"""Direct-message outreach placeholder; external actions are disabled."""

from src.outreach import disabled_for_current_milestone


def create_message_draft(*_args: object, **_kwargs: object) -> None:
    disabled_for_current_milestone()


def send_message(*_args: object, **_kwargs: object) -> None:
    disabled_for_current_milestone()

