#!/usr/bin/env python3
"""
ha_db_diagnose.py

Diagnose why home-assistant_v2.db keeps growing despite regular purges.

Usage:
    python3 ha_db_diagnose.py /path/to/home-assistant_v2.db [--top N] [--output REPORT.md]

Notes:
    - Run this against a STOPPED Home Assistant instance for accurate results,
      or at minimum against a COPY of the live file:
        cp home-assistant_v2.db home-assistant_v2.db.copy
        python3 ha_db_diagnose.py home-assistant_v2.db.copy
    - Requires Python's built-in sqlite3 module (no extra deps).
    - Uses the dbstat virtual table for byte-accurate table sizes if available;
      falls back to row counts + page-size estimation otherwise.
    - HA's recorder runs SQLite in WAL mode. If a "-wal"/"-shm" file sits next
      to the .db you point this at, querying it directly (especially while HA
      is still running) can throw "database disk image is malformed" even
      though the database is NOT actually corrupted - it's just an
      inconsistent read across the main file and the not-yet-checkpointed
      WAL. This script detects that situation, checkpoints automatically when
      safe to do so, and treats every per-table query as non-fatal so one
      unreadable table doesn't abort the whole report.
"""

import sqlite3
import sys
import os
import shutil
import argparse
from datetime import datetime


class ReportWriter:
    """Helper to handle dual printing to console (stdout) and generating clean Markdown."""

    def __init__(self, output_path=None):
        self.output_path = output_path
        self.md_file = open(output_path, "w", encoding="utf-8") if output_path else None
        if self.md_file:
            self.md_file.write(f"# Home Assistant Database Diagnostic Report\n\n")
            self.md_file.write(f"*Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")

    def print_text(self, text=""):
        """Print plain text to terminal standard output."""
        print(text)

    def write_md(self, text=""):
        """Write raw markdown to the report file if enabled."""
        if self.md_file:
            self.md_file.write(text + "\n")

    def section(self, title):
        """Print a visual separator to console and a heading in Markdown."""
        print("\n" + "=" * 75)
        print(title)
        print("=" * 75)
        if self.md_file:
            self.md_file.write(f"\n## {title}\n\n")

    def close(self):
        if self.md_file:
            self.md_file.close()


def human(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "0.0B"

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def table_exists(cur, name):
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    )
    return cur.fetchone() is not None


def prepare_db_copy(db_path, no_copy=False, checkpoint=True):
    wal_path = db_path + "-wal"
    shm_path = db_path + "-shm"
    has_wal = os.path.exists(wal_path)
    has_shm = os.path.exists(shm_path)

    if has_wal or has_shm:
        print(
            "NOTE: Found WAL/SHM sidecar file(s) next to the database "
            f"({'‑wal ' if has_wal else ''}{'‑shm' if has_shm else ''}).\n"
            "      This usually means Home Assistant is still running, or was not\n"
            "      cleanly stopped. Directly querying tables in this state can\n"
            "      surface 'database disk image is malformed' even when the\n"
            "      database is NOT actually corrupted - it's just an inconsistent\n"
            "      read across the main file and not-yet-checkpointed WAL data.\n"
        )

    work_path = db_path
    if not no_copy:
        work_path = db_path + ".diagcopy"
        print(f"Working on a copy to avoid touching the original: {work_path}")
        shutil.copy2(db_path, work_path)
        if has_wal:
            shutil.copy2(wal_path, work_path + "-wal")
        if has_shm:
            shutil.copy2(shm_path, work_path + "-shm")

    if checkpoint:
        try:
            con = sqlite3.connect(work_path)
            cur = con.cursor()
            cur.execute("PRAGMA journal_mode;")
            mode = cur.fetchone()[0]
            if mode.lower() == "wal":
                cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                result = cur.fetchone()
                print(f"Checkpointed WAL into main file (busy={result[0]}, "
                      f"log_frames={result[1]}, checkpointed={result[2]}).")
            con.commit()
            con.close()
        except sqlite3.DatabaseError as e:
            print(f"WARNING: checkpoint attempt failed ({e}). "
                  "Continuing with per-query error handling instead.")

    return work_path


def safe_execute(cur, sql, params=(), label=""):
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    except sqlite3.DatabaseError as e:
        print(f"  [!] Could not read {label or 'this data'}: {e}")
        print("      Skipping this section and continuing.")
        return None


def has_dbstat(cur):
    try:
        cur.execute("SELECT * FROM dbstat LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def table_sizes_dbstat(cur):
    return safe_execute(
        cur,
        """
        SELECT name, SUM(pgsize) AS bytes
        FROM dbstat
        WHERE aggregate = TRUE
        GROUP BY name
        ORDER BY bytes DESC
        """,
        label="table sizes (dbstat)",
    )


def table_sizes_fallback(cur):
    cur.execute("PRAGMA page_size")
    page_size = cur.fetchone()[0]
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    rows = []
    for t in tables:
        n_rows = safe_execute(cur, f"SELECT COUNT(*) FROM '{t}'", label=f"row count for {t}")
        if n_rows is not None:
            rows.append((t, n_rows[0][0]))
    return rows, page_size


def detect_schema(cur):
    new_states = table_exists(cur, "states_meta")
    new_events = table_exists(cur, "event_types")
    return new_states, new_events


def get_states_time_range(cur):
    return safe_execute(
        cur,
        """
        SELECT datetime(MIN(last_updated_ts), 'unixepoch') AS oldest,
               datetime(MAX(last_updated_ts), 'unixepoch') AS newest
        FROM states;
        """,
        label="states table time range",
    )


def get_events_time_range(cur):
    cur.execute("PRAGMA table_info(events)")
    columns = [col[1] for col in cur.fetchall()]

    if "time_fired_ts" in columns:
        sql = """
            SELECT datetime(MIN(time_fired_ts), 'unixepoch') AS oldest,
                   datetime(MAX(time_fired_ts), 'unixepoch') AS newest
            FROM events;
        """
    else:
        sql = """
            SELECT MIN(time_fired) AS oldest,
                   MAX(time_fired) AS newest
            FROM events;
        """

    return safe_execute(cur, sql, label="events table time range")


def top_states_entities(cur, new_states, top_n):
    if new_states:
        return safe_execute(
            cur,
            """
            SELECT sm.entity_id, COUNT(*) AS n
            FROM states s
            JOIN states_meta sm ON s.metadata_id = sm.metadata_id
            GROUP BY sm.entity_id
            ORDER BY n DESC
            LIMIT ?
            """,
            (top_n,),
            label="top entities in 'states'",
        )
    return safe_execute(
        cur,
        """
        SELECT entity_id, COUNT(*) AS n
        FROM states
        GROUP BY entity_id
        ORDER BY n DESC
        LIMIT ?
        """,
        (top_n,),
        label="top entities in 'states'",
    )


def top_event_types(cur, new_events, top_n):
    if new_events:
        return safe_execute(
            cur,
            """
            SELECT et.event_type, COUNT(*) AS n
            FROM events e
            JOIN event_types et ON e.event_type_id = et.event_type_id
            GROUP BY et.event_type
            ORDER BY n DESC
            LIMIT ?
            """,
            (top_n,),
            label="top event types",
        )
    return safe_execute(
        cur,
        """
        SELECT event_type, COUNT(*) AS n
        FROM events
        GROUP BY event_type
        ORDER BY n DESC
        LIMIT ?
        """,
        (top_n,),
        label="top event types",
    )


def top_statistics_entities(cur, top_n):
    if not table_exists(cur, "statistics_meta"):
        return []
    rows = []
    for tbl in ("statistics", "statistics_short_term"):
        if not table_exists(cur, tbl):
            continue
        result = safe_execute(
            cur,
            f"""
            SELECT sm.statistic_id, COUNT(*) AS n
            FROM {tbl} s
            JOIN statistics_meta sm ON s.metadata_id = sm.id
            GROUP BY sm.statistic_id
            ORDER BY n DESC
            LIMIT ?
            """,
            (top_n,),
            label=f"top entities in '{tbl}'",
        )
        if result is not None:
            rows.append((tbl, result))
    return rows


def top_attribute_bloat(cur, new_states, top_n):
    if not table_exists(cur, "state_attributes"):
        return []
    if new_states:
        result = safe_execute(
            cur,
            """
            SELECT sm.entity_id,
                   AVG(LENGTH(sa.shared_attrs)) AS avg_len,
                   COUNT(*) AS n,
                   SUM(LENGTH(sa.shared_attrs)) AS total_bytes
            FROM state_attributes sa
            JOIN states s ON s.attributes_id = sa.attributes_id
            JOIN states_meta sm ON s.metadata_id = sm.metadata_id
            GROUP BY sm.entity_id
            ORDER BY total_bytes DESC
            LIMIT ?
            """,
            (top_n,),
            label="attribute payload bloat",
        )
    else:
        result = safe_execute(
            cur,
            """
            SELECT s.entity_id,
                   AVG(LENGTH(sa.shared_attrs)) AS avg_len,
                   COUNT(*) AS n,
                   SUM(LENGTH(sa.shared_attrs)) AS total_bytes
            FROM state_attributes sa
            JOIN states s ON s.attributes_id = sa.attributes_id
            GROUP BY s.entity_id
            ORDER BY total_bytes DESC
            LIMIT ?
            """,
            (top_n,),
            label="attribute payload bloat",
        )
    return result if result is not None else []


def main():
    ap = argparse.ArgumentParser(description="Diagnose HA recorder DB growth")
    ap.add_argument("db_path", help="Path to home-assistant_v2.db (or a copy)")
    ap.add_argument("--top", type=int, default=20, help="Top-N rows to show per report")
    ap.add_argument(
        "-o", "--output", help="Optional path to save report as a Markdown (.md) file"
    )
    ap.add_argument(
        "--no-copy", action="store_true",
        help="Work directly on db_path instead of making a .diagcopy (not recommended)",
    )
    ap.add_argument(
        "--no-checkpoint", action="store_true",
        help="Skip the automatic WAL checkpoint step",
    )
    args = ap.parse_args()

    if not os.path.exists(args.db_path):
        print(f"ERROR: {args.db_path} does not exist.")
        sys.exit(1)

    work_path = prepare_db_copy(
        args.db_path, no_copy=args.no_copy, checkpoint=not args.no_checkpoint
    )

    try:
        con = sqlite3.connect(work_path)
        cur = con.cursor()
        cur.execute("SELECT 1")
    except sqlite3.DatabaseError as e:
        print(f"\nFATAL: could not even open {work_path}: {e}")
        print("This suggests genuine file-level corruption rather than a WAL/read")
        print("artifact. Next step: run 'PRAGMA integrity_check;' directly and, if it")
        print("reports problems, use the '.recover' command in the sqlite3 CLI.")
        sys.exit(1)

    writer = ReportWriter(args.output)

    # -------------------------------------------------------------------------
    # FILE-LEVEL INFO
    # -------------------------------------------------------------------------
    writer.section("FILE-LEVEL INFO")
    try:
        cur.execute("PRAGMA page_count")
        page_count = cur.fetchone()[0]
        cur.execute("PRAGMA page_size")
        page_size = cur.fetchone()[0]
        cur.execute("PRAGMA freelist_count")
        freelist = cur.fetchone()[0]
        total_bytes = page_count * page_size
        free_bytes = freelist * page_size

        txt = (
            f"Total file size (from pages): {human(total_bytes)}\n"
            f"Free/unused pages (reclaimable via VACUUM): {human(free_bytes)}"
        )
        writer.print_text(txt)
        writer.write_md(f"- **Total file size (from pages):** `{human(total_bytes)}`")
        writer.write_md(f"- **Free/unused pages (reclaimable via VACUUM):** `{human(free_bytes)}`")

        if free_bytes > 0.05 * total_bytes:
            warn = (
                ">> Significant free space exists that a VACUUM/repack hasn't reclaimed.\n"
                "   If auto_repack ran, this suggests repack isn't fully shrinking the file,\n"
                "   or growth since the last purge has already refilled it."
            )
            writer.print_text(warn)
            writer.write_md(f"\n> ⚠️ **Warning:** Significant free space exists that a `VACUUM`/repack hasn't reclaimed.")

    except sqlite3.DatabaseError as e:
        writer.print_text(f"  [!] Could not read file-level pragmas: {e}")

    new_states, new_events = detect_schema(cur)
    schema_str = 'new (states_meta/event_types split)' if new_states else 'old (inline entity_id/event_type)'
    writer.print_text(f"\nSchema: {schema_str}")
    writer.write_md(f"- **Detected Schema:** {schema_str}")

    # -------------------------------------------------------------------------
    # DATA TIME RANGE ('states')
    # -------------------------------------------------------------------------
    writer.section("DATA TIME RANGE ('states' table)")
    if table_exists(cur, "states"):
        time_range = get_states_time_range(cur)
        if time_range and time_range[0]:
            oldest, newest = time_range[0]
            writer.print_text(f"Oldest State Record: {oldest or 'N/A'} UTC")
            writer.print_text(f"Newest State Record: {newest or 'N/A'} UTC")
            writer.write_md(f"- **Oldest Record:** `{oldest or 'N/A'} UTC`")
            writer.write_md(f"- **Newest Record:** `{newest or 'N/A'} UTC`")
        else:
            writer.print_text("Could not retrieve state time range or table is empty.")
            writer.write_md("Could not retrieve state time range or table is empty.")
    else:
        writer.print_text("No 'states' table found.")
        writer.write_md("No 'states' table found.")

    # -------------------------------------------------------------------------
    # DATA TIME RANGE ('events')
    # -------------------------------------------------------------------------
    writer.section("DATA TIME RANGE ('events' table)")
    if table_exists(cur, "events"):
        time_range = get_events_time_range(cur)
        if time_range and time_range[0]:
            oldest, newest = time_range[0]
            writer.print_text(f"Oldest Event Record: {oldest or 'N/A'} UTC")
            writer.print_text(f"Newest Event Record: {newest or 'N/A'} UTC")
            writer.write_md(f"- **Oldest Record:** `{oldest or 'N/A'} UTC`")
            writer.write_md(f"- **Newest Record:** `{newest or 'N/A'} UTC`")
        else:
            writer.print_text("Could not retrieve event time range or table is empty.")
            writer.write_md("Could not retrieve event time range or table is empty.")
    else:
        writer.print_text("No 'events' table found.")
        writer.write_md("No 'events' table found.")

    # -------------------------------------------------------------------------
    # TABLE SIZES
    # -------------------------------------------------------------------------
    writer.section("TABLE SIZES")
    if has_dbstat(cur):
        rows = table_sizes_dbstat(cur)
        if isinstance(rows, list) and rows:
            total = sum(int(r[1] or 0) for r in rows)
            writer.write_md("| Table Name | Size | Percentage |")
            writer.write_md("| :--- | ---: | ---: |")
            for name, size in rows:
                valid_size = int(size or 0)
                pct = (float(valid_size) / float(total) * 100.0) if total > 0 else 0.0
                writer.print_text(f"{str(name):30s} {human(valid_size):>12s}  ({pct:5.1f}%)")
                writer.write_md(f"| `{name}` | {human(valid_size)} | {pct:.1f}% |")
        else:
            msg = "Could not read table sizes via dbstat (see warning above)."
            writer.print_text(msg)
            writer.write_md(msg)
    else:
        fallback_msg = "(dbstat virtual table unavailable in this sqlite3 build — falling back to row counts)"
        writer.print_text(fallback_msg)
        writer.write_md(f"*{fallback_msg}*\n")
        rows, ps = table_sizes_fallback(cur)
        rows.sort(key=lambda r: r[1], reverse=True)
        writer.write_md("| Table Name | Row Count |")
        writer.write_md("| :--- | ---: |")
        for name, n in rows:
            writer.print_text(f"{name:30s} {n:>12d} rows")
            writer.write_md(f"| `{name}` | {n:,} |")

    # -------------------------------------------------------------------------
    # TOP ENTITIES IN 'states' TABLE
    # -------------------------------------------------------------------------
    writer.section(f"TOP {args.top} ENTITIES IN 'states' TABLE (row count = history bloat)")
    if table_exists(cur, "states"):
        result = top_states_entities(cur, new_states, args.top)
        if isinstance(result, list) and result:
            writer.write_md("| Entity ID | State Count |")
            writer.write_md("| :--- | ---: |")
            for entity_id, n in result:
                writer.print_text(f"{str(entity_id):60s} {int(n):>10d}")
                writer.write_md(f"| `{entity_id}` | {int(n):,} |")
        elif result is not None:
            writer.print_text("(no rows)")
            writer.write_md("*(no rows)*")
    else:
        writer.print_text("No 'states' table found.")
        writer.write_md("No 'states' table found.")

    # -------------------------------------------------------------------------
    # TOP EVENT TYPES IN 'events' TABLE
    # -------------------------------------------------------------------------
    writer.section(f"TOP {args.top} EVENT TYPES IN 'events' TABLE")
    if table_exists(cur, "events"):
        result = top_event_types(cur, new_events, args.top)
        if isinstance(result, list) and result:
            writer.write_md("| Event Type | Count |")
            writer.write_md("| :--- | ---: |")
            for event_type, n in result:
                writer.print_text(f"{str(event_type):60s} {int(n):>10d}")
                writer.write_md(f"| `{event_type}` | {int(n):,} |")
        elif result is not None:
            writer.print_text("(no rows)")
            writer.write_md("*(no rows)*")
    else:
        msg = "No 'events' table found (normal on newer HA — events are mostly replaced by states+logbook)."
        writer.print_text(msg)
        writer.write_md(msg)

    # -------------------------------------------------------------------------
    # TOP ENTITIES IN STATISTICS
    # -------------------------------------------------------------------------
    writer.section(f"TOP {args.top} ENTITIES IN 'statistics' / 'statistics_short_term'")
    note = (
        "NOTE: recorder.purge does NOT clean these tables based on keep_days.\n"
        "      Entities with a state_class accumulate stats indefinitely unless\n"
        "      you run recorder.purge_entities against them specifically."
    )
    writer.print_text(note + "\n")
    writer.write_md(f"> **Note:** `recorder.purge` does **NOT** clean these tables based on `keep_days`. Entities with a `state_class` accumulate stats indefinitely unless you run `recorder.purge_entities` against them specifically.\n")

    stat_rows = top_statistics_entities(cur, args.top)
    if stat_rows:
        for tbl, entries in stat_rows:
            writer.print_text(f"\n-- {tbl} --\n")
            writer.write_md(f"### Table: `{tbl}`\n")
            writer.write_md("| Statistic ID | Count |")
            writer.write_md("| :--- | ---: |")
            for statistic_id, n in entries:
                writer.print_text(f"  {statistic_id:60s} {n:>10d}")
                writer.write_md(f"| `{statistic_id}` | {n:,} |")
    else:
        msg = "No statistics_meta table found, or none of its tables were readable."
        writer.print_text(msg)
        writer.write_md(msg)

    # -------------------------------------------------------------------------
    # ATTRIBUTE PAYLOAD BLOAT
    # -------------------------------------------------------------------------
    writer.section(f"TOP {args.top} ENTITIES BY ATTRIBUTE PAYLOAD SIZE (state_attributes bloat)")
    attr_rows = top_attribute_bloat(cur, new_states, args.top)
    if attr_rows:
        writer.print_text(f"{'entity_id':60s} {'avg_bytes':>10s} {'count':>10s} {'total_bytes':>14s}")
        writer.write_md("| Entity ID | Avg Bytes | Count | Total Size |")
        writer.write_md("| :--- | ---: | ---: | ---: |")
        for entity_id, avg_len, n, total_b in attr_rows:
            avg_val = avg_len or 0
            tot_val = total_b or 0
            writer.print_text(f"{entity_id:60s} {avg_val:>10.0f} {n:>10d} {human(tot_val):>14s}")
            writer.write_md(f"| `{entity_id}` | {avg_val:.0f} B | {n:,} | {human(tot_val)} |")
    else:
        msg = "No state_attributes table found, no data, or it wasn't readable."
        writer.print_text(msg)
        writer.write_md(msg)

    con.close()

    if not args.no_copy:
        writer.print_text(f"\n(Working copy left at {work_path} — delete it once you're done, it is not the original file.)")

    # -------------------------------------------------------------------------
    # SUMMARY / NEXT STEPS
    # -------------------------------------------------------------------------
    writer.section("SUMMARY / SUGGESTED NEXT STEPS")
    summary_txt = (
        "1. Check the 'TABLE SIZES' section above for which table dominates the file.\n"
        "2. If 'statistics' or 'statistics_short_term' is large: purge_keep_days won't\n"
        "   help. Use Developer Tools > Actions > recorder.purge_entities on the noisiest\n"
        "   statistic_ids listed above, or exclude those entities from long-term stats.\n"
        "3. If 'states' is large: add the top entities listed above to your recorder\n"
        "   exclude list (entities: or entity_globs:) if you don't need per-change history\n"
        "   for them.\n"
        "4. If 'state_attributes' is large: investigate the specific entity's attributes\n"
        "   payload (e.g. weather forecast arrays, long lists) - consider excluding just\n"
        "   the attributes or the entity.\n"
        "5. If 'Free/unused pages' was large relative to file size: your repack isn't\n"
        "   fully reclaiming space. Try a manual VACUUM on a STOPPED HA instance:\n"
        "     sqlite3 home-assistant_v2.db 'VACUUM;'\n"
    )
    writer.print_text(summary_txt)

    writer.write_md(
        "1. **Table Sizes:** Check the table sizes above for which table dominates the database file.\n"
        "2. **Statistics Bloat:** If `statistics` or `statistics_short_term` is large: `purge_keep_days` won't "
        "help. Use **Developer Tools > Actions > recorder.purge_entities** on the noisiest `statistic_id`s listed above, or exclude those entities from long-term stats.\n"
        "3. **State History Bloat:** If `states` is large: add the top entities listed above to your recorder "
        "`exclude` list (`entities:` or `entity_globs:`) if you don't need per-change history for them.\n"
        "4. **Attribute Bloat:** If `state_attributes` is large: investigate specific entity attributes payloads "
        "(e.g. weather forecast arrays, large lists) and consider excluding attributes or the entity.\n"
        "5. **Unused Page Fragmentation:** If 'Free/unused pages' was large relative to file size: your repack isn't "
        "fully reclaiming space. Try a manual `VACUUM` on a **STOPPED** HA instance:\n"
        "   ```bash\n"
        "   sqlite3 home-assistant_v2.db 'VACUUM;'\n"
        "   ```"
    )

    writer.close()

    if args.output:
        print(f"\nMarkdown report successfully generated at: {args.output}")


if __name__ == "__main__":
    main()