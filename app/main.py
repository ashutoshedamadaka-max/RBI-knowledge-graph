import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config.settings import get_settings
from app.ingestion.service import IngestionService


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(message)s")
    application = FastAPI(title=settings.app_name, version="0.1.0")
    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    application.state.settings = settings
    application.state.ingestion_service = IngestionService(settings)
    application.include_router(router)
    static_dir = Path(__file__).parent / "static"
    application.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    @application.get("/", include_in_schema=False)
    def frontend() -> FileResponse:
        return FileResponse(static_dir / "index.html")
    return application


app = create_app()
