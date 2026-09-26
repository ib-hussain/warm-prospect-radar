"""Flask application factory and scraper-review routes."""

from __future__ import annotations

import os
from dataclasses import replace
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

from src.chatbot import AssistantError, BusinessAssistant
from src.config import Settings
from src.database import Repository, StorageError, build_repository
from src.models import (
    FeatureFlags,
    InteractionKind,
    OutreachChannel,
    OutreachStatus,
    ProspectInteraction,
    RunStatus,
)
from src.outreach import OutreachError, OutreachService
from src.scheduler import RefreshScheduler, run_refresh_cycle
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
            "pending_approvals": len(
                repository.list_outreach_drafts(status=OutreachStatus.PENDING_APPROVAL)
            ),
        },
    }


def _effective_scraper_settings(settings: Settings, flags: FeatureFlags) -> Settings:
    return replace(
        settings,
        enable_llm=settings.enable_llm and flags.llm_enabled,
        scraper_social_profile_limit=(
            settings.scraper_social_profile_limit if flags.social_acquisition_enabled else 0
        ),
    )


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

    scheduler_process = not settings.app_debug or os.getenv("WERKZEUG_RUN_MAIN") == "true"
    if settings.scheduler_run_in_web and scheduler_process:
        scheduler = RefreshScheduler(settings, repository)
        scheduler.start()
        app.extensions["refresh_scheduler"] = scheduler

    def feature_flags() -> FeatureFlags:
        return repository.get_feature_flags()

    def require_feature(attribute: str, label: str) -> FeatureFlags:
        flags = feature_flags()
        if not getattr(flags, attribute):
            abort(403, description=f"{label} is disabled in central feature controls.")
        return flags

    @app.context_processor
    def inject_global_template_data() -> dict[str, object]:
        return {
            "backend_name": repository.backend_name,
            "current_year": datetime.now(UTC).year,
            "feature_flags": feature_flags(),
            "delivery_mode": settings.outreach_delivery_mode,
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
        interactions = repository.list_interactions(business_id, limit=30)
        drafts = repository.list_outreach_drafts(business_id=business_id, limit=20)
        return render_template(
            "business_detail.html",
            active_page="businesses",
            business=business,
            snapshots=snapshots,
            runs=runs[:10],
            interactions=interactions,
            drafts=drafts,
            interaction_kinds=list(InteractionKind),
        )

    @app.post("/businesses/<uuid:business_id>/refresh")
    def refresh_business(business_id: UUID):
        flags = require_feature("acquisition_enabled", "Acquisition")
        business = repository.get_business(business_id)
        if not business or business.archived_at:
            abort(404)
        if not business.website:
            flash("This record has no website to refresh.", "error")
            return redirect(url_for("business_detail", business_id=business_id))
        try:
            updated, run = BusinessScrapePipeline(
                _effective_scraper_settings(settings, flags), repository
            ).run(business.website, business.name)
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
        flags = feature_flags()
        if request.method == "POST":
            if not flags.acquisition_enabled:
                abort(403, description="Acquisition is disabled in central feature controls.")
            raw_url = request.form.get("url", "").strip()
            name = request.form.get("business_name", "").strip() or None
            if not raw_url:
                flash("Enter a public website or Wikipedia URL.", "error")
                return redirect(url_for("acquire"))
            try:
                normalized = normalize_url(raw_url)
                business, run = BusinessScrapePipeline(
                    _effective_scraper_settings(settings, flags), repository
                ).run(normalized, name)
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
            acquisition_enabled=flags.acquisition_enabled,
        )

    @app.get("/progress")
    def progress():
        runs = repository.list_runs(limit=250)
        return render_template("progress.html", active_page="progress", runs=runs)

    @app.get("/settings")
    def settings_page():
        flags = feature_flags()
        providers = {
            "Ollama": {
                "ready": settings.enable_llm and flags.llm_enabled,
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
            "SMTP": {
                "ready": bool(settings.smtp_host and settings.smtp_from_address),
                "detail": (
                    f"{settings.smtp_host}:{settings.smtp_port}"
                    if settings.smtp_host
                    else "Dry-run remains available without SMTP"
                ),
            },
            "Outreach webhook": {
                "ready": bool(settings.outreach_webhook_url),
                "detail": "Configured"
                if settings.outreach_webhook_url
                else "Optional for live social delivery",
            },
        }
        return render_template(
            "settings.html",
            active_page="settings",
            settings=settings,
            providers=providers,
            flags=flags,
            scheduler_running=bool(
                app.extensions.get("refresh_scheduler")
                and app.extensions["refresh_scheduler"].running
            ),
        )

    @app.post("/settings/features")
    def update_feature_flags():
        fields = {
            "acquisition_enabled",
            "social_acquisition_enabled",
            "llm_enabled",
            "outreach_enabled",
            "chatbot_enabled",
            "scheduled_refresh_enabled",
            "external_delivery_enabled",
        }
        current = feature_flags()
        for field in fields:
            setattr(current, field, request.form.get(field) == "on")
        repository.save_feature_flags(current)
        flash("Central feature controls were updated for the whole workspace.", "success")
        return redirect(url_for("settings_page"))

    @app.post("/settings/scheduler/run")
    def run_scheduler_now():
        require_feature("scheduled_refresh_enabled", "Scheduled refresh")
        report = run_refresh_cycle(settings, repository)
        level = "warning" if report.failed or report.partial or report.errors else "success"
        flash(
            "Refresh cycle finished: "
            f"{report.completed} complete, {report.partial} partial, "
            f"{report.failed} failed and {report.skipped} skipped.",
            level,
        )
        return redirect(url_for("progress"))

    @app.route("/outreach", methods=["GET", "POST"])
    def outreach():
        flags = require_feature("outreach_enabled", "Outreach")
        if request.method == "POST":
            try:
                business_id = UUID(request.form.get("business_id", ""))
                business = repository.get_business(business_id)
                if not business or business.archived_at:
                    raise ValueError("Choose an active business.")
                channel = OutreachChannel(request.form.get("channel", ""))
                service_settings = replace(
                    settings, enable_llm=settings.enable_llm and flags.llm_enabled
                )
                draft = OutreachService(service_settings, repository).create_draft(
                    business,
                    channel,
                    target=request.form.get("target", "").strip() or None,
                    subject=request.form.get("subject", "").strip() or None,
                    body=request.form.get("body", "").strip() or None,
                    media_prompt=request.form.get("media_prompt", "").strip() or None,
                    goal=request.form.get("goal", "").strip(),
                    tone=request.form.get("tone", "professional").strip() or "professional",
                    use_llm=request.form.get("use_llm") == "on",
                )
                flash("Outreach draft created. Review it before requesting approval.", "success")
                return redirect(url_for("outreach", selected=str(draft.id)))
            except (ValueError, OutreachError) as exc:
                flash(f"Draft could not be created: {exc}", "error")
                return redirect(url_for("outreach"))
        selected_id = request.args.get("selected", "")
        drafts = repository.list_outreach_drafts(limit=250)
        selected = next((item for item in drafts if str(item.id) == selected_id), None)
        return render_template(
            "outreach.html",
            active_page="outreach",
            businesses=repository.list_businesses(limit=500),
            drafts=drafts,
            selected=selected,
            channels=list(OutreachChannel),
            statuses=list(OutreachStatus),
            flags=flags,
            settings=settings,
        )

    def load_draft(draft_id: UUID):
        draft = repository.get_outreach_draft(draft_id)
        if not draft or draft.archived_at:
            abort(404)
        return draft

    @app.post("/outreach/<uuid:draft_id>/update")
    def update_outreach_draft(draft_id: UUID):
        require_feature("outreach_enabled", "Outreach")
        draft = load_draft(draft_id)
        try:
            OutreachService(settings, repository).update_draft(
                draft,
                target=request.form.get("target", "").strip() or None,
                subject=request.form.get("subject", "").strip() or None,
                body=request.form.get("body", "").strip(),
                media_prompt=request.form.get("media_prompt", "").strip() or None,
            )
            flash("Draft changes saved; approval status returned to draft.", "success")
        except (ValueError, OutreachError) as exc:
            flash(f"Draft could not be updated: {exc}", "error")
        return redirect(url_for("outreach", selected=draft_id))

    @app.post("/outreach/<uuid:draft_id>/submit")
    def submit_outreach_draft(draft_id: UUID):
        require_feature("outreach_enabled", "Outreach")
        try:
            OutreachService(settings, repository).submit_for_approval(load_draft(draft_id))
            flash("Draft submitted to the central approval queue.", "success")
        except OutreachError as exc:
            flash(str(exc), "error")
        return redirect(url_for("outreach", selected=draft_id))

    @app.post("/outreach/<uuid:draft_id>/review")
    def review_outreach_draft(draft_id: UUID):
        require_feature("outreach_enabled", "Outreach")
        try:
            approve = request.form.get("decision") == "approve"
            OutreachService(settings, repository).review(load_draft(draft_id), approve)
            flash("Draft approved." if approve else "Draft rejected for revision.", "success")
        except OutreachError as exc:
            flash(str(exc), "error")
        return redirect(url_for("outreach", selected=draft_id))

    @app.post("/outreach/<uuid:draft_id>/deliver")
    def deliver_outreach_draft(draft_id: UUID):
        require_feature("outreach_enabled", "Outreach")
        require_feature("external_delivery_enabled", "External delivery")
        try:
            draft = OutreachService(settings, repository).deliver(load_draft(draft_id))
            simulated = draft.metadata.get("simulated_delivery") is True
            flash(
                "Dry-run delivery completed; no external action was taken."
                if simulated
                else "The approved draft was delivered through the configured provider.",
                "success",
            )
        except OutreachError as exc:
            flash(str(exc), "error")
        return redirect(url_for("outreach", selected=draft_id))

    @app.post("/businesses/<uuid:business_id>/interactions")
    def record_interaction(business_id: UUID):
        require_feature("outreach_enabled", "Outreach")
        business = repository.get_business(business_id)
        if not business or business.archived_at:
            abort(404)
        try:
            interaction = ProspectInteraction(
                business_id=business_id,
                kind=InteractionKind(request.form.get("kind", "")),
                channel=request.form.get("channel", "").strip() or None,
                summary=request.form.get("summary", "").strip() or None,
                metadata={"recorded_manually": True},
            )
            repository.save_interaction(interaction)
            flash("Interaction recorded and the explainable score recalculated.", "success")
        except ValueError as exc:
            flash(f"Interaction could not be recorded: {exc}", "error")
        return redirect(url_for("business_detail", business_id=business_id))

    @app.route("/assistant", methods=["GET", "POST"])
    def assistant_page():
        require_feature("chatbot_enabled", "Data assistant")
        selected = None
        if request.method == "POST":
            try:
                selected = BusinessAssistant(settings, repository).answer(
                    request.form.get("question", "")
                )
                flash("The answer was generated from the central business records.", "success")
            except AssistantError as exc:
                flash(str(exc), "error")
        exchanges = repository.list_assistant_exchanges(limit=30)
        return render_template(
            "assistant.html",
            active_page="assistant",
            selected=selected,
            exchanges=exchanges,
        )

    @app.get("/businesses/<uuid:business_id>/snapshots/<uuid:snapshot_id>")
    def download_snapshot(business_id: UUID, snapshot_id: UUID):
        snapshot = next(
            (item for item in repository.list_snapshots(business_id) if item.id == snapshot_id),
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
        flags = feature_flags()
        return jsonify(
            {
                "status": "ok",
                "backend": repository.backend_name,
                "supabase_configured": settings.supabase_configured,
                "features": flags.model_dump(mode="json"),
                "llm_enabled": settings.enable_llm and flags.llm_enabled,
                "delivery_mode": settings.outreach_delivery_mode,
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
        flags = feature_flags()
        if not flags.acquisition_enabled:
            return jsonify({"success": False, "error": "acquisition is disabled"}), 403
        payload = request.get_json(silent=True) or {}
        raw_url = str(payload.get("url", "")).strip()
        if not raw_url:
            return jsonify({"success": False, "error": "url is required"}), 400
        try:
            business, run = BusinessScrapePipeline(
                _effective_scraper_settings(settings, flags), repository
            ).run(raw_url, str(payload.get("business_name", "")).strip() or None)
            return jsonify(
                {
                    "success": True,
                    "business": business.model_dump(mode="json"),
                    "run": run.model_dump(mode="json"),
                }
            )
        except (ValueError, PipelineError) as exc:
            return jsonify({"success": False, "error": str(exc)}), 422

    @app.post("/api/assistant")
    def api_assistant():
        if not feature_flags().chatbot_enabled:
            return jsonify({"success": False, "error": "data assistant is disabled"}), 403
        payload = request.get_json(silent=True) or {}
        try:
            exchange = BusinessAssistant(settings, repository).answer(
                str(payload.get("question", ""))
            )
            return jsonify({"success": True, "exchange": exchange.model_dump(mode="json")})
        except AssistantError as exc:
            return jsonify({"success": False, "error": str(exc)}), 422

    @app.get("/api/outreach/drafts")
    def api_outreach_drafts():
        if not feature_flags().outreach_enabled:
            return jsonify({"success": False, "error": "outreach is disabled"}), 403
        drafts = repository.list_outreach_drafts(limit=500)
        return jsonify(
            {
                "success": True,
                "rows": [item.model_dump(mode="json") for item in drafts],
                "count": len(drafts),
            }
        )

    @app.errorhandler(404)
    def not_found(_: Exception):
        return render_template(
            "error.html",
            active_page="",
            code=404,
            title="Signal not found",
            message="That record or page is not available.",
        ), 404

    @app.errorhandler(403)
    def forbidden(exc: Exception):
        message = getattr(exc, "description", "This central workspace feature is disabled.")
        return render_template(
            "error.html",
            active_page="",
            code=403,
            title="Feature switched off",
            message=message,
        ), 403

    @app.errorhandler(StorageError)
    def storage_error(exc: StorageError):
        app.logger.exception("Storage operation failed")
        return render_template(
            "error.html",
            active_page="",
            code=503,
            title="Storage is unavailable",
            message=str(exc)
            if app.debug
            else "The configured data store could not complete this request.",
        ), 503

    return app


__all__ = ["create_app"]
