#!/usr/bin/env python3
"""
TF-IDF + MiniBatchKMeans

Evaluates clustering with silhouette and Davies–Bouldin, writes result to artifacts/ folder.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings, get_settings
from app.core.clustering.pipeline import LogClusteringEngine, TrainingMetrics, save_metadata
from app.core.parsers import HdfsLogNormalizer, LinuxLogNormalizer
from app.core.parsers.hdfs_parser import iter_event_csv_rows


def read_linux_lines(path: Path, max_lines: int) -> list[str]:
    lines: list[str] = []
    norm = LinuxLogNormalizer()
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n = norm.normalize(line)
            if n:
                lines.append(n)
            if len(lines) >= max_lines:
                break
    return lines


def read_hdfs_documents(path: Path, max_rows: int) -> list[str]:
    norm = HdfsLogNormalizer()
    out: list[str] = []
    for row in iter_event_csv_rows(path, max_rows=max_rows):
        t = norm.normalize_from_file_row(row)
        if t:
            out.append(t)
    return out


def find_default_hdfs_event_csv(datasets_root: Path) -> Path:
    tracebench = datasets_root / "HDFS_v3_TraceBench" / "tracebench"
    candidates = sorted(tracebench.glob("*/event.csv"))
    if not candidates:
        raise FileNotFoundError(f"No event.csv under {tracebench}")
    return candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Train SOC log clustering model.")
    parser.add_argument(
        "--linux",
        type=Path,
        default=ROOT / "datasets" / "Linux" / "Linux.log",
        help="Path to Linux.log",
    )
    parser.add_argument(
        "--hdfs-event",
        type=Path,
        default=None,
        help="Path to TraceBench event.csv (default: first under datasets/HDFS_v3_TraceBench/tracebench).",
    )
    parser.add_argument(
        "--n-clusters",
        type=int,
        default=None,
        help="Override number of clusters (default: from Settings.default_n_clusters).",
    )
    args = parser.parse_args()
    settings: Settings = get_settings()
    n_clusters = args.n_clusters or settings.default_n_clusters

    hdfs_path = args.hdfs_event or find_default_hdfs_event_csv(ROOT / "datasets")
    if not args.linux.is_file():
        raise SystemExit(f"Linux log not found: {args.linux}")
    if not hdfs_path.is_file():
        raise SystemExit(f"HDFS event.csv not found: {hdfs_path}")

    linux_docs = read_linux_lines(args.linux, settings.max_train_lines_linux)
    hdfs_docs = read_hdfs_documents(hdfs_path, settings.max_train_lines_hdfs)
    documents = linux_docs + hdfs_docs
    print(f"Linux samples: {len(linux_docs)}, HDFS samples: {len(hdfs_docs)}, total: {len(documents)}")

    engine = LogClusteringEngine(n_clusters=n_clusters, random_state=settings.random_state)
    metrics: TrainingMetrics = engine.fit(documents)

    out_dir = settings.artifacts_dir
    engine.save(out_dir, settings.vectorizer_name, settings.cluster_model_name)
    save_metadata(out_dir, settings.metadata_name, metrics)
    print("Saved:", out_dir / settings.vectorizer_name)
    print("Metrics:", metrics.to_dict())


if __name__ == "__main__":
    main()
