"""Repositories"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ClusterStat, UserInferenceLog


class InferenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_inference(
        self,
        *,
        source: str,
        raw_line: str,
        normalized_text: str,
        cluster_id: int,
        distance: float,
        cluster_label: str | None = None,
    ) -> UserInferenceLog:
        row = UserInferenceLog(
            source=source,
            raw_line=raw_line,
            normalized_text=normalized_text,
            cluster_id=cluster_id,
            distance_to_centroid=distance,
            cluster_label=cluster_label,
        )
        self._session.add(row)
        self._bump_cluster_stat(cluster_id)
        self._session.commit()
        self._session.refresh(row)
        return row

    def _bump_cluster_stat(self, cluster_id: int) -> None:
        stat = self._session.get(ClusterStat, cluster_id)
        if stat is None:
            stat = ClusterStat(cluster_id=cluster_id, api_event_count=1)
            self._session.add(stat)
        else:
            stat.api_event_count += 1

    def count_for_cluster(self, cluster_id: int) -> int:
        st = self._session.get(ClusterStat, cluster_id)
        return int(st.api_event_count) if st else 0


class ClusterStatRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self) -> list[ClusterStat]:
        return list(self._session.scalars(select(ClusterStat).order_by(ClusterStat.cluster_id)))
