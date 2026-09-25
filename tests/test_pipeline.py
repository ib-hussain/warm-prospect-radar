from dataclasses import replace

from src.config import Settings
from src.database import LocalRepository
from src.models import PageSnapshot
from src.scraper.scraper import BusinessScrapePipeline


class FakeWebScraper:
    def __init__(self, url, settings):
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def scrape(self):
        return [
            PageSnapshot(
                url=self.url,
                final_url=self.url,
                title="Acme Systems",
                description="Acme makes industrial software and machinery.",
                text=(
                    "Acme Systems was founded in 2002. It has 1,200 employees. "
                    "Contact research@acme.example. The company builds industrial machinery."
                ),
                status_code=200,
                content_type="text/html",
                links=[],
            )
        ]


def test_pipeline_saves_and_versions_refresh(monkeypatch, tmp_path):
    settings = replace(
        Settings.from_env(),
        storage_path=tmp_path,
        data_backend="local",
        enable_llm=False,
        scraper_js_fallback=False,
        scraper_social_profile_limit=0,
    )
    repository = LocalRepository(tmp_path)
    monkeypatch.setattr("src.scraper.scraper.WebScraper", FakeWebScraper)
    pipeline = BusinessScrapePipeline(settings, repository)

    first, first_run = pipeline.run("https://acme.example", "Acme Systems")
    second, second_run = pipeline.run("https://acme.example", "Acme Systems")

    assert first.id == second.id
    assert first_run.pages_succeeded == 1
    assert second_run.pages_succeeded == 1
    snapshots = repository.list_snapshots(first.id)
    assert [item.version for item in snapshots] == [2, 1]
    assert all((settings.project_root / item.local_path).is_file() for item in snapshots)

