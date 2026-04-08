"""Orchestrates normalization, clustering, and persistence"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.clustering.naming import build_cluster_name, normalize_cluster_display_name
from app.core.clustering.pipeline import LogClusteringEngine
from app.core.parsers import HdfsLogNormalizer, LinuxLogNormalizer
from app.db.repository import InferenceRepository
from app.schemas.events import ClusterResponse, EventRequest


class InferenceService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._linux = LinuxLogNormalizer()
        self._hdfs = HdfsLogNormalizer()
        self._engine: LogClusteringEngine | None = None
        self._metadata: dict | None = None

    def load_model(self) -> None:
        d = self._settings.artifacts_dir
        self._engine = LogClusteringEngine.load(
            d,
            self._settings.vectorizer_name,
            self._settings.cluster_model_name,
        )
        meta_path = d / self._settings.metadata_name
        if meta_path.is_file():
            self._metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            self._metadata = {}

    @property
    def ready(self) -> bool:
        return self._engine is not None

    def normalize(self, payload: EventRequest) -> str:
        if payload.source == "linux":
            return self._linux.normalize(payload.raw_line)
        return self._hdfs.normalize(payload.raw_line)

    def predict_and_log(self, payload: EventRequest, db: Session) -> ClusterResponse:
        if self._engine is None:
            raise RuntimeError("Model is not loaded")
        norm = self.normalize(payload)
        if not norm:
            raise ValueError("Normalized text is empty; check raw_line format")

        cid, dist = self._engine.predict_one(norm)
        train_sizes = (self._metadata or {}).get("cluster_sizes") or {}
        top_map = (self._metadata or {}).get("top_terms_per_cluster") or {}
        centroid_terms = list(top_map.get(str(cid), []))

        name_map = (self._metadata or {}).get("cluster_names") or {}
        cluster_name = name_map.get(str(cid)) or build_cluster_name(centroid_terms)
        cluster_name = normalize_cluster_display_name(cluster_name)

        repo = InferenceRepository(db)
        row = repo.add_inference(
            source=payload.source,
            raw_line=payload.raw_line,
            normalized_text=norm,
            cluster_id=cid,
            distance=dist,
            cluster_label=cluster_name,
        )
        api_n = repo.count_for_cluster(cid)

        train_n = train_sizes.get(str(cid))

        hint = None
        if dist > 0.85:
            hint = "High distance to centroid possible rare or anomalous line"

        return ClusterResponse(
            source=payload.source,
            raw_line=payload.raw_line,
            cluster_id=cid,
            cluster_name=cluster_name,
            distance_to_centroid=dist,
            normalized_text=norm,
            training_cluster_size=int(train_n) if train_n is not None else None,
            api_events_in_cluster=api_n,
            top_terms=centroid_terms,
            quality_hint=hint,
            logged_id=row.id,
        )


def artifacts_present(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    d = Path(s.artifacts_dir)
    return (
        (d / s.vectorizer_name).is_file()
        and (d / s.cluster_model_name).is_file()
    )
