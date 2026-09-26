from dataclasses import replace

from src.config import Settings
from src.database import LocalRepository
from src.models import (
    AssistantExchange,
    BusinessRecord,
    BusinessSnapshot,
    FeatureFlags,
    InteractionKind,
    OutreachChannel,
    OutreachDraft,
    OutreachStatus,
    ProspectInteraction,
    RunStatus,
    ScrapeRun,
)
from src.scoring import apply_scores


def test_local_repository_round_trip(tmp_path):
    repository = LocalRepository(tmp_path)
    business = BusinessRecord(name="Acme", website="https://acme.example")
    repository.save_business(business)
    assert repository.get_business(business.id).name == "Acme"
    assert repository.list_businesses(query="acme")[0].id == business.id

    run = ScrapeRun(
        requested_url="https://acme.example",
        business_id=business.id,
        status=RunStatus.COMPLETED,
        pages_attempted=2,
        pages_succeeded=2,
    )
    repository.save_run(run)
    assert repository.list_runs()[0].id == run.id

    snapshot = BusinessSnapshot(
        business_id=business.id,
        run_id=run.id,
        version=1,
        source_url=run.requested_url,
        structured_data=business.model_dump(mode="json"),
        raw_manifest={"page_count": 2},
        content_hash="a" * 64,
    )
    repository.save_snapshot(snapshot)
    assert repository.list_snapshots(business.id)[0].content_hash == "a" * 64

    assert repository.archive_business(business.id)
    assert repository.list_businesses() == []
    assert repository.get_business(business.id).archived_at is not None


def test_local_repository_full_workspace_records(tmp_path):
    repository = LocalRepository(tmp_path)
    business = apply_scores(
        BusinessRecord(name="Acme", website="https://acme.example", employee_count=100)
    )
    repository.save_business(business)

    flags = FeatureFlags(chatbot_enabled=False, external_delivery_enabled=False)
    repository.save_feature_flags(flags)
    assert repository.get_feature_flags().chatbot_enabled is False

    draft = OutreachDraft(
        business_id=business.id,
        channel=OutreachChannel.EMAIL,
        target="hello@acme.example",
        subject="Hello",
        body="A test draft.",
        approval_status=OutreachStatus.PENDING_APPROVAL,
    )
    repository.save_outreach_draft(draft)
    assert repository.get_outreach_draft(draft.id).target == "hello@acme.example"
    assert repository.list_outreach_drafts(status=OutreachStatus.PENDING_APPROVAL)[0].id == draft.id

    repository.save_interaction(
        ProspectInteraction(
            business_id=business.id,
            kind=InteractionKind.EMAIL_SENT,
            channel="email",
        )
    )
    repository.save_interaction(
        ProspectInteraction(
            business_id=business.id,
            kind=InteractionKind.POSITIVE_REPLY,
            channel="email",
        )
    )
    rescored = repository.get_business(business.id)
    assert rescored.score_explanation["response_strength"] > 0
    assert len(repository.list_interactions(business.id)) == 2

    exchange = AssistantExchange(
        question="What is Acme?",
        answer="Acme is a stored business.",
        business_ids=[business.id],
    )
    repository.save_assistant_exchange(exchange)
    assert repository.list_assistant_exchanges()[0].id == exchange.id


def test_publishable_supabase_key_is_recognised():
    settings = replace(
        Settings.from_env(),
        supabase_url="https://example.supabase.co",
        supabase_key="sb_publishable_example",
    )
    assert settings.supabase_key_is_publishable
