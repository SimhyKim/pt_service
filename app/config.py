"""Application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SOC Log Clustering"
    debug: bool = False

    database_url: str = "postgresql+psycopg2://soc:soc@db:5432/soc_logs"

    artifacts_dir: Path = Path(__file__).resolve().parent.parent / "artifacts"
    vectorizer_name: str = "tfidf_vectorizer.joblib"
    cluster_model_name: str = "kmeans_model.joblib"
    metadata_name: str = "training_metadata.json"

    default_n_clusters: int = 24
    max_train_lines_linux: int = 12000
    max_train_lines_hdfs: int = 12000
    random_state: int = 42


@lru_cache
def get_settings() -> Settings:
    return Settings()
