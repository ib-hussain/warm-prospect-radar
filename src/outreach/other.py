"""Generic outreach placeholder; all external actions are disabled."""

from src.outreach import disabled_for_current_milestone


def create_other_draft(*_args: object, **_kwargs: object) -> None:
    disabled_for_current_milestone()

