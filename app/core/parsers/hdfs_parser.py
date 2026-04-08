"""HDFS normalization"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from io import StringIO
from pathlib import Path


#strip digit-heavy tokens
_DIGIT_RUN = re.compile(r"[0-9][^a-z^/]*", re.IGNORECASE)
_MULTI_SPACE = re.compile(r"\s+")

_EVENT_HEADER = (
    "TaskID,TID,OpName,StartTime,EndTime,HostAddress,HostName,Agent,Description\n"
)


@dataclass
class HdfsLogNormalizer:
    """Build a single text line from an HDFS event for clustering"""

    def event_row_to_text(self, row: dict[str, str]) -> str:
        op = (row.get("OpName") or "").strip()
        agent = (row.get("Agent") or "").strip()
        desc = (row.get("Description") or "").lower()
        desc = _DIGIT_RUN.sub(" ", desc)
        desc = _MULTI_SPACE.sub(" ", desc).strip()
        parts = [p for p in (op, agent, desc) if p]
        return " | ".join(parts)

    def normalize(self, raw_line: str) -> str:
        """Parse data line and normalize"""
        raw_line = raw_line.strip()
        if not raw_line:
            return ""
        if raw_line.lower().startswith("taskid,"):
            buf = StringIO(raw_line)
            reader = csv.DictReader(buf)
            row = next(reader, None)
            if row is None:
                return ""
            return self.event_row_to_text(row)
        buf = StringIO(_EVENT_HEADER + raw_line)
        reader = csv.DictReader(buf)
        row = next(reader, None)
        if row is None:
            return _MULTI_SPACE.sub(" ", raw_line.lower()).strip()
        return self.event_row_to_text(row)

    def normalize_from_file_row(self, row: dict[str, str]) -> str:
        return self.event_row_to_text(row)

    def source_label(self) -> str:
        return "hdfs"


def iter_event_csv_rows(path: Path, max_rows: int | None = None):
    """Stream rows from csv"""
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        n = 0
        for row in reader:
            yield row
            n += 1
            if max_rows is not None and n >= max_rows:
                break
