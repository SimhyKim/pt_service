#!/usr/bin/env python3
"""Печать последних записей из SQLite (удобно на Windows без sqlite3.exe)."""

from __future__ import annotations

import argparse
import sqlite3


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=str, default="soc_local.db", help="Путь к файлу SQLite")
    p.add_argument("--limit", type=int, default=20)
    args = p.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    print("tables:", [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])

    sql = """
        SELECT id, source, cluster_id,
               cluster_label,
               round(distance_to_centroid, 4) AS dist,
               substr(raw_line, 1, 100) AS raw_preview,
               created_at
        FROM user_inference_logs
        ORDER BY id DESC
        LIMIT ?
        """
    try:
        rows = cur.execute(sql, (args.limit,)).fetchall()
    except sqlite3.OperationalError:
        rows = cur.execute(
            """
            SELECT id, source, cluster_id,
                   round(distance_to_centroid, 4) AS dist,
                   substr(raw_line, 1, 100) AS raw_preview,
                   created_at
            FROM user_inference_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
    print(f"\nlast {args.limit} user_inference_logs:")
    for r in rows:
        print(dict(r))

    stats = cur.execute("SELECT cluster_id, api_event_count FROM cluster_stats ORDER BY cluster_id").fetchall()
    print("\ncluster_stats:")
    for r in stats:
        print(dict(r))
    con.close()


if __name__ == "__main__":
    main()
