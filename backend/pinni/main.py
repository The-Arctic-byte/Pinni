"""Pinni API. Run with:  uv run uvicorn pinni.main:app --reload"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import db, errors, graph, vectors
from .config import Settings
from .contract import Contract
from .routers import admin, auth, community, reader
from .seed import seed


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = db.connect(settings.db_path)
        try:
            db.init(conn)
            if settings.seed_mock and db.is_empty(conn):
                seed(conn, app.state.contract, settings.dev_accounts)
            app.state.graph = graph.connect(settings)
            if app.state.graph.is_empty():
                graph.rebuild(conn, app.state.graph)
            app.state.vectors = vectors.connect(settings)
            if app.state.vectors.count() == 0:
                app.state.vectors.index(db.docs(conn, "SELECT doc FROM stories"))
        finally:
            conn.close()
        yield
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
