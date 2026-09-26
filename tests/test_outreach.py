from dataclasses import replace

import pytest

from src.config import Settings
from src.database import LocalRepository
from src.models import BusinessRecord, OutreachChannel, OutreachStatus
from src.outreach import OutreachError, OutreachService


def test_outreach_approval_and_dry_run_delivery(tmp_path):
    settings = replace(
        Settings.from_env(),
        storage_path=tmp_path,
        data_backend="local",
        enable_llm=False,
        outreach_delivery_mode="dry_run",
        scheduler_run_in_web=False,
    )
    repository = LocalRepository(tmp_path)
    business = BusinessRecord(
        name="Acme Robotics",
        website="https://acme.example",
        products_services=["industrial robots"],
    )
    repository.save_business(business)
    service = OutreachService(settings, repository)

    draft = service.create_draft(
        business,
        OutreachChannel.EMAIL,
        target="hello@acme.example",
        goal="discuss a data engineering collaboration",
    )
    assert draft.approval_status == OutreachStatus.DRAFT
    assert "Acme Robotics" in draft.body

    service.submit_for_approval(draft)
    service.review(draft, approve=True)
    delivered = service.deliver(draft)
    assert delivered.approval_status == OutreachStatus.DELIVERED
    assert delivered.provider == "dry_run"
    assert delivered.metadata["simulated_delivery"] is True
    assert repository.list_interactions(business.id)[0].metadata["simulated"] is True
    assert repository.get_business(business.id).score_explanation["response_strength"] == 0

    with pytest.raises(OutreachError, match="cannot be edited"):
        service.update_draft(
            delivered,
            target="new@acme.example",
            subject="Changed",
            body="Changed body",
            media_prompt=None,
        )


def test_external_delivery_feature_gate(tmp_path):
    settings = replace(Settings.from_env(), storage_path=tmp_path, enable_llm=False)
    repository = LocalRepository(tmp_path)
    business = BusinessRecord(name="Acme")
    repository.save_business(business)
    service = OutreachService(settings, repository)
    draft = service.create_draft(business, OutreachChannel.OTHER, body="Hello")
    service.submit_for_approval(draft)
    service.review(draft, approve=True)
    flags = repository.get_feature_flags()
    flags.external_delivery_enabled = False
    repository.save_feature_flags(flags)

    with pytest.raises(OutreachError, match="disabled"):
        service.deliver(draft)


def test_live_smtp_delivery_requires_approval_and_records_attempt(monkeypatch, tmp_path):
    settings = replace(
        Settings.from_env(),
        storage_path=tmp_path,
        enable_llm=False,
        outreach_delivery_mode="live",
        smtp_host="smtp.example",
        smtp_from_address="sender@example.com",
    )
    repository = LocalRepository(tmp_path)
    business = BusinessRecord(name="Acme", employee_count=20)
    repository.save_business(business)
    service = OutreachService(settings, repository)
    draft = service.create_draft(
        business,
        OutreachChannel.EMAIL,
        target="receiver@example.com",
        subject="Hello",
        body="Approved content",
    )

    with pytest.raises(OutreachError, match="approved"):
        service.deliver(draft)

    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent.append((host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def ehlo(self):
            return None

        def starttls(self):
            return None

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr("src.outreach.service.smtplib.SMTP", FakeSMTP)
    service.submit_for_approval(draft)
    service.review(draft, approve=True)
    delivered = service.deliver(draft)
    assert delivered.provider == "smtp"
    assert delivered.approval_status == OutreachStatus.DELIVERED
    assert len(sent) == 2
    assert repository.list_interactions(business.id)[0].kind.value == "email_sent"


def test_live_webhook_delivery_is_signed(monkeypatch, tmp_path):
    settings = replace(
        Settings.from_env(),
        storage_path=tmp_path,
        enable_llm=False,
        outreach_delivery_mode="live",
        outreach_webhook_url="https://hooks.example/outreach",
        outreach_webhook_secret="test-secret",
    )
    repository = LocalRepository(tmp_path)
    business = BusinessRecord(name="Acme")
    repository.save_business(business)
    service = OutreachService(settings, repository)
    draft = service.create_draft(
        business,
        OutreachChannel.SOCIAL_POST,
        target="https://social.example/acme",
        body="Approved post",
    )
    service.submit_for_approval(draft)
    service.review(draft, approve=True)
    captured = {}

    class Response:
        headers = {"X-Message-ID": "provider-123"}

        def raise_for_status(self):
            return None

    def fake_post(url, *, content, headers, timeout):
        captured.update(url=url, content=content, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr("src.outreach.service.httpx.post", fake_post)
    delivered = service.deliver(draft)
    assert delivered.provider_message_id == "provider-123"
    assert captured["headers"]["X-Warm-Prospect-Signature"].startswith("sha256=")
    assert repository.list_interactions(business.id)[0].kind.value == "post_published"
