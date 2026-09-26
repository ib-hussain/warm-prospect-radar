"""Optional once-daily refresh worker for the central workspace."""

from __future__ import annotations

import argparse
import logging
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime

from src.config import Settings
from src.database import Repository, build_repository
from src.models import RunStatus, utc_now
from src.scraper import BusinessScrapePipeline

LOGGER = logging.getLogger(__name__)
REFRESH_CYCLE_LOCK = threading.Lock()


@dataclass(slots=True)
class RefreshCycleReport:
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    attempted: int = 0
    completed: int = 0
    partial: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def run_refresh_cycle(settings: Settings, repository: Repository) -> RefreshCycleReport:
    report = RefreshCycleReport()
    flags = repository.get_feature_flags()
    if not flags.scheduled_refresh_enabled or not flags.acquisition_enabled:
        report.skipped = len(repository.list_businesses(limit=1000))
        report.finished_at = utc_now()
        return report
    if not REFRESH_CYCLE_LOCK.acquire(blocking=False):
        report.errors.append("Another refresh cycle is already running in this process.")
        report.finished_at = utc_now()
        return report
    businesses = repository.list_businesses(limit=settings.scheduler_max_businesses_per_run)
    effective_social_limit = (
        settings.scraper_social_profile_limit if flags.social_acquisition_enabled else 0
    )
    effective_settings = replace(
        settings,
        enable_llm=settings.enable_llm and flags.llm_enabled,
        scraper_social_profile_limit=effective_social_limit,
    )
    try:
        pipeline = BusinessScrapePipeline(effective_settings, repository)
        for business in businesses:
            if not business.website:
                report.skipped += 1
                continue
            report.attempted += 1
            try:
                _, run = pipeline.run(business.website, business.name)
                if run.status == RunStatus.COMPLETED:
                    report.completed += 1
                elif run.status == RunStatus.PARTIAL:
                    report.partial += 1
                else:
                    report.failed += 1
            except Exception as exc:
                report.failed += 1
                report.errors.append(f"{business.name}: {exc}")
                LOGGER.exception("Scheduled refresh failed for %s", business.name)
    finally:
        report.finished_at = utc_now()
        REFRESH_CYCLE_LOCK.release()
    return report


class RefreshScheduler:
    def __init__(self, settings: Settings, repository: Repository):
        self.settings = settings
        self.repository = repository
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._thread = threading.Thread(
            target=self.run_forever,
            name="warm-prospect-daily-refresh",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def run_forever(self) -> None:
        if self._stop.wait(self.settings.scheduler_initial_delay_seconds):
            return
        interval_seconds = self.settings.scheduler_interval_hours * 3600
        while not self._stop.is_set():
            try:
                report = run_refresh_cycle(self.settings, self.repository)
                LOGGER.info(
                    "Scheduled refresh finished: %s complete, %s partial, %s failed, %s skipped",
                    report.completed,
                    report.partial,
                    report.failed,
                    report.skipped,
                )
            except Exception:
                LOGGER.exception("Scheduled refresh cycle could not start")
            if self._stop.wait(interval_seconds):
                return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run one refresh cycle and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    repository = build_repository(settings)
    if args.once:
        report = run_refresh_cycle(settings, repository)
        print(
            f"attempted={report.attempted} completed={report.completed} "
            f"partial={report.partial} failed={report.failed} skipped={report.skipped}"
        )
        return 1 if report.failed else 0
    scheduler = RefreshScheduler(settings, repository)
    try:
        scheduler.run_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
