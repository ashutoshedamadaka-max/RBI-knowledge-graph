import logging

from fastapi import FastAPI

from app.api.routes import router
from app.config.settings import get_settings
from app.ingestion.service import IngestionService


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.state.ingestion_service = IngestionService(settings)
    application.include_router(router)
    return application


app = create_app()

