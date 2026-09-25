"""Outreach image placeholder; generation and publishing are deferred."""

from src.outreach import disabled_for_current_milestone


def create_picture_draft(*_args: object, **_kwargs: object) -> None:
    disabled_for_current_milestone()

