from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from webapp.config import get_settings


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def _configure_shared_state(app: FastAPI, mode: str) -> None:
    app.state.settings = get_settings()
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.runtime_mode = mode


def create_public_app() -> FastAPI:
    from webapp.routers import catalog

    app = FastAPI(title="Shoe Mapping", version="2.0.0")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    _configure_shared_state(app, mode="public")
    app.include_router(catalog.public_router)
    app.include_router(catalog.catalog_api_router)
    return app


def create_personalization_app() -> FastAPI:
    from personalization.db import ensure_database
    from webapp.routers import catalog, feedback, imports, personalization, rotation, strava, visualizations

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        ensure_database()
        yield

    app = FastAPI(title="Shoe Mapping Personalization API", version="2.0.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    _configure_shared_state(app, mode="personalization")
    app.include_router(personalization.page_router)
    app.include_router(catalog.catalog_api_router)
    app.include_router(personalization.api_router)
    app.include_router(imports.router)
    app.include_router(rotation.router)
    app.include_router(feedback.router)
    app.include_router(strava.router)
    app.include_router(visualizations.router)

    return app
