from src.database import LocalRepository
from src.models import BusinessRecord, BusinessSnapshot, RunStatus, ScrapeRun


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

