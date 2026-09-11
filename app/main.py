import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config.settings import get_settings
from app.ingestion.service import IngestionService


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(message)s")
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.state.settings = settings
    application.state.ingestion_service = IngestionService(settings)
    application.include_router(router)
    application.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="frontend")
    return application


app = create_app()
