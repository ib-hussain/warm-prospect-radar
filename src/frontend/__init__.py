"""Flask application factory and scraper-review routes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from src.config import Settings
from src.database import Repository, StorageError, build_repository
from src.models import RunStatus
from src.scraper import BusinessScrapePipeline, PipelineError
from src.scraper.webpage import normalize_url

WIKIPEDIA_SAMPLES = (
    ("Apple", "https://en.wikipedia.org/wiki/Apple_Inc."),
    ("Microsoft", "https://en.wikipedia.org/wiki/Microsoft"),
    ("Amazon", "https://en.wikipedia.org/wiki/Amazon_(company)"),
    ("Alphabet", "https://en.wikipedia.org/wiki/Alphabet_Inc."),
    ("Meta", "https://en.wikipedia.org/wiki/Meta_Platforms"),
    ("Nvidia", "https://en.wikipedia.org/wiki/Nvidia"),
    ("Tesla", "https://en.wikipedia.org/wiki/Tesla,_Inc."),
    ("JPMorgan Chase", "https://en.wikipedia.org/wiki/JPMorgan_Chase"),
    ("Walmart", "https://en.wikipedia.org/wiki/Walmart"),
    ("Coca-Cola", "https://en.wikipedia.org/wiki/The_Coca-Cola_Company"),
)


def _get_repository(app: Flask) -> Repository:
    return app.extensions["repository"]


def _dashboard_data(repository: Repository) -> dict[str, object]:
    businesses = repository.list_businesses(limit=500)
    runs = repository.list_runs(limit=100)
    finished = [run for run in runs if run.status not in {RunStatus.RUNNING, RunStatus.QUEUED}]
    successful = [run for run in finished if run.status in {RunStatus.COMPLETED, RunStatus.PARTIAL}]
    completeness = (
        round(sum(item.data_completeness for item in businesses) / len(businesses), 1)
        if businesses
        else 0
    )
    return {
        "businesses": businesses,
        "runs": runs,
        "stats": {
            "businesses": len(businesses),
            "runs": len(runs),
            "success_rate": round(100 * len(successful) / len(finished), 1) if finished else 0,
            "completeness": completeness,
        },
    }


def create_app(settings: Settings | None = None, repository: Repository | None = None) -> Flask:
    settings = settings or Settings.from_env()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(
        SECRET_KEY=settings.flask_secret_key,
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        JSON_SORT_KEYS=False,
    )
    repository = repository or build_repository(settings)
    app.extensions["settings"] = settings
    app.extensions["repository"] = repository

    @app.context_processor
    def inject_global_template_data() -> dict[str, object]:
        return {
            "app_user_name": settings.app_user_name,
            "backend_name": repository.backend_name,
            "current_year": datetime.now(UTC).year,
        }

    @app.template_filter("friendly_time")
    def friendly_time(value: datetime | str | None) -> str:
        if not value:
            return "—"
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return value
        return value.astimezone(UTC).strftime("%d %b %Y · %H:%M UTC")

    @app.template_filter("hostname")
    def hostname(value: str | None) -> str:
        from urllib.parse import urlsplit

        return (urlsplit(value or "").hostname or value or "—").removeprefix("www.")

    @app.get("/")
    def dashboard():
        data = _dashboard_data(repository)
        top_businesses = sorted(
            data["businesses"], key=lambda item: item.prospect_score, reverse=True
        )[:6]
        return render_template(
            "dashboard.html",
            active_page="dashboard",
            top_businesses=top_businesses,
            recent_runs=data["runs"][:6],
            stats=data["stats"],
        )

    @app.get("/businesses")
    def businesses():
        query = request.args.get("q", "").strip()
        sector = request.args.get("sector", "").strip()
        items = repository.list_businesses(query=query, sector=sector, limit=500)
        all_items = repository.list_businesses(limit=500)
        sectors = sorted({item.gics_sector for item in all_items if item.gics_sector})
        return render_template(
            "businesses.html",
            active_page="businesses",
            businesses=items,
            sectors=sectors,
            query=query,
            selected_sector=sector,
        )

    @app.get("/businesses/<uuid:business_id>")
    def business_detail(business_id: UUID):
        business = repository.get_business(business_id)
        if not business or business.archived_at:
            abort(404)
        snapshots = repository.list_snapshots(business_id)
        runs = [run for run in repository.list_runs(200) if run.business_id == business_id]
        return render_template(
            "business_detail.html",
            active_page="businesses",
            business=business,
            snapshots=snapshots,
            runs=runs[:10],
        )

    @app.post("/businesses/<uuid:business_id>/refresh")
    def refresh_business(business_id: UUID):
        business = repository.get_business(business_id)
        if not business or business.archived_at:
            abort(404)
        if not business.website:
            flash("This record has no website to refresh.", "error")
            return redirect(url_for("business_detail", business_id=business_id))
        try:
            updated, run = BusinessScrapePipeline(settings, repository).run(
                business.website, business.name
            )
            level = "warning" if run.status == RunStatus.PARTIAL else "success"
            flash(
                f"Refresh finished with {run.pages_succeeded}/{run.pages_attempted} readable pages.",
                level,
            )
            return redirect(url_for("business_detail", business_id=updated.id))
        except PipelineError as exc:
            flash(f"Refresh failed: {exc}", "error")
            return redirect(url_for("business_detail", business_id=business_id))

    @app.post("/businesses/<uuid:business_id>/archive")
    def archive_business(business_id: UUID):
        if repository.archive_business(business_id):
            flash("Business archived. Its history remains available in storage.", "success")
        else:
            flash("Business was not found or was already archived.", "warning")
        return redirect(url_for("businesses"))

    @app.route("/acquire", methods=["GET", "POST"])
    def acquire():
        if request.method == "POST":
            raw_url = request.form.get("url", "").strip()
            name = request.form.get("business_name", "").strip() or None
            if not raw_url:
                flash("Enter a public website or Wikipedia URL.", "error")
                return redirect(url_for("acquire"))
            try:
                normalized = normalize_url(raw_url)
                business, run = BusinessScrapePipeline(settings, repository).run(normalized, name)
                level = "warning" if run.status == RunStatus.PARTIAL else "success"
                flash(
                    f"Saved {business.name}. {run.pages_succeeded}/{run.pages_attempted} pages were readable.",
                    level,
                )
                return redirect(url_for("business_detail", business_id=business.id))
            except (ValueError, PipelineError) as exc:
                flash(f"Acquisition failed: {exc}", "error")
                return redirect(url_for("acquire"))
        return render_template(
            "acquire.html",
            active_page="acquire",
            wikipedia_samples=WIKIPEDIA_SAMPLES,
            settings=settings,
        )

    @app.get("/progress")
    def progress():
        runs = repository.list_runs(limit=250)
        return render_template("progress.html", active_page="progress", runs=runs)

    @app.get("/settings")
    def settings_page():
        providers = {
            "Ollama": {
                "ready": settings.enable_llm,
                "detail": f"{settings.ollama_model} at {settings.ollama_base_url}",
            },
            "Together AI": {
                "ready": bool(settings.together_api_key),
                "detail": settings.together_model,
            },
            "Supabase": {
                "ready": settings.supabase_configured,
                "detail": "Configured" if settings.supabase_configured else "Local fallback active",
            },
            "Playwright": {
                "ready": settings.scraper_js_fallback,
                "detail": "Enabled; Chromium must be installed locally",
            },
        }
        return render_template(
            "settings.html",
            active_page="settings",
            settings=settings,
            providers=providers,
        )

    @app.get("/businesses/<uuid:business_id>/snapshots/<uuid:snapshot_id>")
    def download_snapshot(business_id: UUID, snapshot_id: UUID):
        snapshot = next(
            (
                item
                for item in repository.list_snapshots(business_id)
                if item.id == snapshot_id
            ),
            None,
        )
        if not snapshot or not snapshot.local_path:
            abort(404)
        path = (settings.project_root / snapshot.local_path).resolve()
        if not path.is_relative_to(settings.storage_path.resolve()) or not path.is_file():
            abort(404)
        return send_file(path, as_attachment=True, download_name=path.name)

    @app.get("/api/health")
    def api_health():
        return jsonify(
            {
                "status": "ok",
                "backend": repository.backend_name,
                "supabase_configured": settings.supabase_configured,
                "llm_enabled": settings.enable_llm,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    @app.get("/api/businesses")
    def api_businesses():
        items = repository.list_businesses(
            query=request.args.get("q", ""), sector=request.args.get("sector", ""), limit=500
        )
        return jsonify(
            {
                "success": True,
                "rows": [item.model_dump(mode="json") for item in items],
                "count": len(items),
            }
        )

    @app.post("/api/scrape")
    def api_scrape():
        payload = request.get_json(silent=True) or {}
        raw_url = str(payload.get("url", "")).strip()
        if not raw_url:
            return jsonify({"success": False, "error": "url is required"}), 400
        try:
            business, run = BusinessScrapePipeline(settings, repository).run(
                raw_url, str(payload.get("business_name", "")).strip() or None
            )
            return jsonify(
                {
                    "success": True,
                    "business": business.model_dump(mode="json"),
                    "run": run.model_dump(mode="json"),
                }
            )
        except (ValueError, PipelineError) as exc:
            return jsonify({"success": False, "error": str(exc)}), 422

    @app.errorhandler(404)
    def not_found(_: Exception):
        return render_template(
            "error.html",
            active_page="",
            code=404,
            title="Signal not found",
            message="That record or page is not available.",
        ), 404

    @app.errorhandler(StorageError)
    def storage_error(exc: StorageError):
        app.logger.exception("Storage operation failed")
        return render_template(
            "error.html",
            active_page="",
            code=503,
            title="Storage is unavailable",
            message=str(exc) if app.debug else "The configured data store could not complete this request.",
        ), 503

    return app


__all__ = ["create_app"]
