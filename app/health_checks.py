"""Extended readiness checks: artifacts on disk and ORM schema."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.config import Settings, get_settings
from app.db.base import Base


def check_artifacts(settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    root = Path(s.artifacts_dir)
    v = root / s.vectorizer_name
    m = root / s.cluster_model_name
    meta = root / s.metadata_name
    missing: list[str] = []
    if not v.is_file():
        missing.append(str(v))
    if not m.is_file():
        missing.append(str(m))
    if not meta.is_file():
        missing.append(str(meta))
    return {
        "vectorizer_present": v.is_file(),
        "model_present": m.is_file(),
        "metadata_present": meta.is_file(),
        "missing_paths": missing,
    }


def check_schema(engine: Engine) -> dict[str, Any]:
    expected_tables = sorted(Base.metadata.tables.keys())
    insp = inspect(engine)
    present_tables = set(insp.get_table_names())
    missing_tables = [t for t in expected_tables if t not in present_tables]
    column_issues: list[str] = []

    for tname in expected_tables:
        if tname not in present_tables:
            continue
        model_cols = {c.name for c in Base.metadata.tables[tname].columns}
        db_cols = {c["name"] for c in insp.get_columns(tname)}
        for c in sorted(model_cols - db_cols):
            column_issues.append(f"{tname}.{c} missing in database")

    ok = not missing_tables and not column_issues
    return {
        "ok": ok,
        "expected_tables": expected_tables,
        "missing_tables": missing_tables,
        "column_issues": column_issues,
    }
