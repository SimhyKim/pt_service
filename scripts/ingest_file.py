#!/usr/bin/env python3
"""
Sending raws from file POST /api/v1/events. One raw per request

Example:
  python scripts/ingest_file.py --source linux --file datasets/Linux/Linux.log --limit 50
  python scripts/ingest_file.py --source hdfs --file path/to/event.csv --skip-header
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def post_event(base_url: str, source: str, raw_line: str, timeout: float) -> dict:
    url = base_url.rstrip("/") + "/api/v1/events"
    body = json.dumps({"source": source, "raw_line": raw_line}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def iter_lines(path: Path, skip_header: bool) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if skip_header and text:
        text = text[1:]
    return [ln for ln in text if ln.strip()]


def main() -> None:
    p = argparse.ArgumentParser(description="Sending logs from file")
    p.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base url api")
    p.add_argument("--source", choices=("linux", "hdfs"), required=True)
    p.add_argument("--file", type=Path, required=True, help="Logfile")
    p.add_argument("--limit", type=int, default=0, help="Max rows (0 equals to all))")
    p.add_argument("--skip-header", action="store_true", help="Skip first raw (for csv headers, if any)")
    p.add_argument("--sleep", type=float, default=0.0, help="Pause between requests")
    p.add_argument("--timeout", type=float, default=60.0)
    args = p.parse_args()

    lines = iter_lines(args.file, args.skip_header)
    if args.limit > 0:
        lines = lines[: args.limit]

    ok, err = 0, 0
    for i, line in enumerate(lines, 1):
        try:
            out = post_event(args.base_url, args.source, line, args.timeout)
            cid = out.get("cluster_id")
            dist = out.get("distance_to_centroid")
            name = (out.get("cluster_name") or "")[:60]
            print(f"[{i}/{len(lines)}] cluster={cid} name={name!r} distance={dist:.4f} id={out.get('logged_id')}")
            ok += 1
        except urllib.error.HTTPError as e:
            print(f"[{i}] HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:500]}", file=sys.stderr)
            err += 1
        except Exception as e:
            print(f"[{i}] error: {e}", file=sys.stderr)
            err += 1
        if args.sleep > 0:
            time.sleep(args.sleep)

    print(f"Done: ok={ok}, errors={err}")


if __name__ == "__main__":
    main()
