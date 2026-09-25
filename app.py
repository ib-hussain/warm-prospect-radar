"""Development entry point for Warm Prospect Radar."""

from src.frontend import create_app

app = create_app()


if __name__ == "__main__":
    settings = app.extensions["settings"]
    app.run(
        host=settings.app_host,
        port=settings.app_port,
        debug=settings.app_debug,
        use_reloader=settings.app_debug,
    )

