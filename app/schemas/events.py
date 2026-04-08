"""API request/response model"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EventRequest(BaseModel):
    """Analyst submits one log line, then source selects normalizer"""

    source: Literal["linux", "hdfs"] = Field(
        ...,
        description="linux: raw syslog line; hdfs: one event.csv per row (no header).",
    )
    raw_line: str = Field(..., min_length=1, description="Raw log line or csv row")


class ClusterResponse(BaseModel):
    source: str = Field(..., description="Echo of request source")
    raw_line: str = Field(..., description="Echo of submitted line")
    cluster_id: int
    cluster_name: str = Field(..., description="Human label from centroid terms at train time")
    distance_to_centroid: float = Field(..., description="Distance in L2-normalized TF-IDF space")
    normalized_text: str
    training_cluster_size: int | None = Field(None, description="Events in this cluster in training sample")
    api_events_in_cluster: int = Field(0, description="Events assigned to this cluster via this api since deploy")
    top_terms: list[str] = Field(default_factory=list, description="Frequent TF-IDF terms for this cluster")
    quality_hint: str | None = Field(
        None,
        description="High distance may indicate a rare pattern",
    )
    logged_id: int | None = Field(None, description="Primary key of the stored user request row")


class ArtifactsHealth(BaseModel):
    vectorizer_present: bool
    model_present: bool
    metadata_present: bool
    missing_paths: list[str]


class SchemaHealth(BaseModel):
    ok: bool
    expected_tables: list[str]
    missing_tables: list[str]
    column_issues: list[str]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    database: str
    artifacts: ArtifactsHealth | None = None
    schema_check: SchemaHealth | None = Field(None, description="ORM vs database: tables and columns.")
