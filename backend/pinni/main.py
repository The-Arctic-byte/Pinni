"""Pinni API. Run with:  uv run uvicorn pinni.main:app --reload"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import db, drafts, errors, graph, vectors
from .config import Settings
from .contract import Contract
from .routers import admin, auth, community, reader
from .seed import ensure_dev_editors, seed, upgrade_reports


async def _newsroom_timer(app: FastAPI) -> None:
    """The agent's rounds: one at startup, then every PINNI_AGENT_EVERY_MINUTES."""
    from . import newsroom

    while True:
        try:
            await asyncio.to_thread(newsroom.run_round, app.state)
        except Exception:  # noqa: BLE001  (a failed round must not stop the next one)
            logging.getLogger("pinni.newsroom").exception("Newsroom round failed")
        await asyncio.sleep(app.state.settings.agent_every_minutes * 60)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = db.connect(settings.db_path)
        try:
            db.init(conn)
            if settings.seed_mock and db.is_empty(conn):
                seed(conn, app.state.contract, settings.dev_accounts, settings.seed_content)
            if settings.dev_accounts:
                ensure_dev_editors(conn)
            upgrade_reports(conn)
            drafts.tidy_agent_stories(conn, app.state.contract)
            drafts.stories_in_whole_seconds(conn, app.state.contract)
            db.stories_as_points(conn)
            app.state.graph = graph.connect(settings)
            if app.state.graph.is_empty():
                graph.rebuild(conn, app.state.graph)
            app.state.vectors = vectors.connect(settings)
            if app.state.vectors.count() == 0:
                app.state.vectors.index(db.docs(conn, "SELECT doc FROM stories"))
        finally:
            conn.close()
        timer = asyncio.create_task(_newsroom_timer(app)) if settings.agent_every_minutes > 0 else None
        yield
        if timer:
            timer.cancel()
        app.state.graph.close()

    app = FastAPI(
        title="Pinni API",
        version="0.1.0",
        description="Implements contract/openapi.yaml. The contract file is the reference; see /openapi.yaml.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.contract = Contract(settings.contract_dir)
    errors.install(app)
    for module in (auth, reader, community, admin):
        app.include_router(module.router)

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/docs")

    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok"}

    @app.get("/openapi.yaml", include_in_schema=False)
    def contract_spec():
        return FileResponse(settings.contract_dir / "openapi.yaml", media_type="application/yaml")

    if settings.admin_dir.is_dir():
        @app.get("/admin", include_in_schema=False)
        def admin_root():
            return RedirectResponse("/admin/")

        app.mount("/admin", StaticFiles(directory=settings.admin_dir, html=True), name="admin")

    return app


app = create_app()
