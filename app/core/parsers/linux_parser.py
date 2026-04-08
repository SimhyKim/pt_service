"""Linux syslog normalization"""

from __future__ import annotations

import re
from dataclasses import dataclass


_TS_HOST = re.compile(
    r"^[A-Za-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\S+\s+",
    re.MULTILINE,
)
_NUM = re.compile(r"\b\d+\b")
_MULTI_SPACE = re.compile(r"\s+")


@dataclass
class LinuxLogNormalizer:

    def normalize(self, raw_line: str) -> str:
        line = raw_line.strip()
        if not line:
            return ""
        line = _TS_HOST.sub("", line, count=1)
        line = line.lower()
        line = _NUM.sub("<num>", line)
        line = _MULTI_SPACE.sub(" ", line).strip()
        return line

    def source_label(self) -> str:
        return "linux"
