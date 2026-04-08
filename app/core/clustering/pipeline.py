"""TF-IDF + MiniBatchKMeans clustering"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.cluster import MiniBatchKMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import davies_bouldin_score, silhouette_score
from sklearn.preprocessing import normalize as l2_normalize

from app.core.clustering.naming import build_cluster_name


@dataclass
class TrainingMetrics:
    n_samples: int
    n_clusters: int
    silhouette_sample: float | None
    davies_bouldin: float | None
    inertia: float
    cluster_sizes: dict[str, int] = field(default_factory=dict)
    top_terms_per_cluster: dict[str, list[str]] = field(default_factory=dict)
    cluster_names: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_samples": self.n_samples,
            "n_clusters": self.n_clusters,
            "silhouette_sample": self.silhouette_sample,
            "davies_bouldin": self.davies_bouldin,
            "inertia": self.inertia,
            "cluster_sizes": self.cluster_sizes,
            "top_terms_per_cluster": self.top_terms_per_cluster,
            "cluster_names": self.cluster_names,
        }


class LogClusteringEngine:
    """
    Represents log lines as TF-IDF vectors and clusters with MiniBatch K-Means
    L2-normalization applied to vectors so euclidean distance relates to cosine similarity
    """

    def __init__(
        self,
        n_clusters: int = 24,
        max_features: int = 20_000,
        random_state: int = 42,
    ) -> None:
        self.n_clusters = n_clusters
        self.random_state = random_state
        self._vectorizer = TfidfVectorizer(
            max_features=max_features,
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.95,
            sublinear_tf=True,
        )
        self._model = MiniBatchKMeans(
            n_clusters=n_clusters,
            batch_size=1024,
            random_state=random_state,
            n_init="auto",
        )
        self._feature_names: np.ndarray | None = None

    def fit(self, documents: list[str]) -> TrainingMetrics:
        if len(documents) < self.n_clusters:
            raise ValueError("Need at least n_clusters documents to train.")
        X = self._vectorizer.fit_transform(documents)
        self._feature_names = np.array(self._vectorizer.get_feature_names_out())
        Xn = l2_normalize(X)
        self._model.fit(Xn)
        labels = self._model.labels_
        inertia = float(self._model.inertia_)

        sample_size = min(8000, Xn.shape[0])
        rng = np.random.default_rng(self.random_state)
        idx = rng.choice(Xn.shape[0], size=sample_size, replace=False)
        Xs = Xn[idx]
        ls = labels[idx]
        Xd = Xs.toarray()
        sil: float | None
        try:
            sil = float(silhouette_score(Xd, ls, metric="euclidean"))
        except Exception:
            sil = None
        try:
            dbi = float(davies_bouldin_score(Xd, ls))
        except Exception:
            dbi = None

        sizes: dict[str, int] = {}
        for c in range(self.n_clusters):
            sizes[str(c)] = int(np.sum(labels == c))

        top_terms = self._extract_top_terms(Xn, labels)
        cluster_names = {cid: build_cluster_name(terms) for cid, terms in top_terms.items()}

        return TrainingMetrics(
            n_samples=len(documents),
            n_clusters=self.n_clusters,
            silhouette_sample=sil,
            davies_bouldin=dbi,
            inertia=inertia,
            cluster_sizes=sizes,
            top_terms_per_cluster=top_terms,
            cluster_names=cluster_names,
        )

    def _extract_top_terms(self, X, labels: np.ndarray, top_k: int = 8) -> dict[str, list[str]]:
        if self._feature_names is None:
            return {}
        out: dict[str, list[str]] = {}
        Xc = X.tocsr()
        for c in range(self.n_clusters):
            mask = labels == c
            if not np.any(mask):
                out[str(c)] = []
                continue
            sub = Xc[mask]
            centroid = np.asarray(sub.mean(axis=0)).ravel()
            if centroid.size == 0:
                out[str(c)] = []
                continue
            top_idx = np.argsort(-centroid)[:top_k]
            out[str(c)] = [str(self._feature_names[i]) for i in top_idx if centroid[i] > 0]
        return out

    def predict_one(self, text: str) -> tuple[int, float]:
        """Returns cluster id and distance to assigned centroid in normalized space"""
        X = self._vectorizer.transform([text])
        Xn = l2_normalize(X)
        cid = int(self._model.predict(Xn)[0])
        center = self._model.cluster_centers_[cid]
        vec = Xn.toarray().ravel()
        dist = float(np.linalg.norm(vec - center))
        return cid, dist

    def save(self, directory: Path, vectorizer_name: str, model_name: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._vectorizer, directory / vectorizer_name)
        payload = {
            "model": self._model,
            "feature_names": self._feature_names,
            "n_clusters": self.n_clusters,
        }
        joblib.dump(payload, directory / model_name)

    @classmethod
    def load(cls, directory: Path, vectorizer_name: str, model_name: str) -> LogClusteringEngine:
        vectorizer = joblib.load(directory / vectorizer_name)
        payload = joblib.load(directory / model_name)
        engine = cls(n_clusters=int(payload["n_clusters"]), random_state=0)
        engine._vectorizer = vectorizer
        engine._model = payload["model"]
        fn = payload.get("feature_names")
        engine._feature_names = np.array(fn) if fn is not None else None
        return engine


def save_metadata(directory: Path, filename: str, metrics: TrainingMetrics) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(json.dumps(metrics.to_dict(), indent=2), encoding="utf-8")
