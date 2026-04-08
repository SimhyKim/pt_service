"""FastAPI entrypoint for SOC log clustering."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import Base
from app.db.session import engine, get_db

import app.db.models  # noqa: F401 — регистрация таблиц в Base.metadata
from app.health_checks import check_artifacts, check_schema
from app.schemas.events import (
    ArtifactsHealth,
    ClusterResponse,
    EventRequest,
    HealthResponse,
    SchemaHealth,
)
from app.services.inference_service import InferenceService, artifacts_present

logger = logging.getLogger(__name__)
_inference = InferenceService()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)  # пустая БД: полная схема из models.py
    if artifacts_present():
        _inference.load_model()
    yield


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)


@app.get("/api/v1/training-metrics")
def training_metrics() -> dict:
    """Last offline training metrics (silhouette, Davies–Bouldin, cluster sizes, top terms)."""
    path = Path(get_settings().artifacts_dir) / get_settings().metadata_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="training_metadata.json not found; run scripts/train_model.py")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    db_ok = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = "error"

    schema_raw = check_schema(engine)
    schema_check = SchemaHealth(
        ok=bool(schema_raw["ok"]),
        expected_tables=list(schema_raw["expected_tables"]),
        missing_tables=list(schema_raw["missing_tables"]),
        column_issues=list(schema_raw["column_issues"]),
    )

    art_raw = check_artifacts()
    artifacts = ArtifactsHealth(
        vectorizer_present=bool(art_raw["vectorizer_present"]),
        model_present=bool(art_raw["model_present"]),
        metadata_present=bool(art_raw["metadata_present"]),
        missing_paths=list(art_raw["missing_paths"]),
    )

    artifacts_ready = not art_raw["missing_paths"]
    core_ok = (
        db_ok == "ok"
        and schema_check.ok
        and artifacts_ready
        and _inference.ready
    )
    status = "ok" if core_ok else "degraded"

    return HealthResponse(
        status=status,
        model_loaded=_inference.ready,
        database=db_ok,
        artifacts=artifacts,
        schema_check=schema_check,
    )


@app.post("/api/v1/events", response_model=ClusterResponse)
def assign_event(payload: EventRequest, db: Session = Depends(get_db)) -> ClusterResponse:
    if not _inference.ready:
        raise HTTPException(
            status_code=503,
            detail="Model artifacts missing. Run scripts/train_model.py and restart.",
        )
    try:
        return _inference.predict_and_log(payload, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
