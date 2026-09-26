from dataclasses import replace

from src.chatbot import BusinessAssistant
from src.config import Settings
from src.database import LocalRepository
from src.models import BusinessRecord, RunStatus, ScrapeRun
from src.scheduler import run_refresh_cycle
from src.scoring import apply_scores


def test_assistant_uses_deterministic_fallback(tmp_path):
    settings = replace(
        Settings.from_env(), storage_path=tmp_path, data_backend="local", enable_llm=False
    )
    repository = LocalRepository(tmp_path)
    low = apply_scores(BusinessRecord(name="Large Co", employee_count=1_000_000))
    high = apply_scores(BusinessRecord(name="Small Co", employee_count=10))
    repository.save_business(low)
    repository.save_business(high)

    exchange = BusinessAssistant(settings, repository).answer(
        "Which businesses have the highest prospect score?"
    )
    assert exchange.provider == "deterministic"
    assert "Top prospects" in exchange.answer
    assert "Large Co" in exchange.answer or "Small Co" in exchange.answer
    assert repository.list_assistant_exchanges()[0].id == exchange.id


def test_refresh_cycle_continues_across_businesses(monkeypatch, tmp_path):
    settings = replace(
        Settings.from_env(),
        storage_path=tmp_path,
        data_backend="local",
        enable_llm=False,
        scheduler_max_businesses_per_run=10,
    )
    repository = LocalRepository(tmp_path)
    repository.save_business(BusinessRecord(name="One", website="https://one.example"))
    repository.save_business(BusinessRecord(name="Two", website="https://two.example"))

    class FakePipeline:
        def __init__(self, _settings, _repository):
            pass

        def run(self, website, _name):
            if "two" in website:
                raise RuntimeError("temporary failure")
            return BusinessRecord(name="One", website=website), ScrapeRun(
                requested_url=website,
                status=RunStatus.COMPLETED,
            )

    monkeypatch.setattr("src.scheduler.BusinessScrapePipeline", FakePipeline)
    report = run_refresh_cycle(settings, repository)
    assert report.attempted == 2
    assert report.completed == 1
    assert report.failed == 1
    assert len(report.errors) == 1

    flags = repository.get_feature_flags()
    flags.acquisition_enabled = False
    repository.save_feature_flags(flags)
    disabled_report = run_refresh_cycle(settings, repository)
    assert disabled_report.attempted == 0
    assert disabled_report.skipped == 2
