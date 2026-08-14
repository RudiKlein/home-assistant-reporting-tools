# **HA Database Reporting Tool**

A command-line diagnostic tool for Home Assistant’s SQLite recorder database (home-assistant_v2.db). It pinpoints what is actually driving storage growth, identifies noisy entities, checks for un-purged statistics bloat, and safe-guards against temporary WAL file read errors—all without extra Python dependencies.

## **Why this exists**

When Home Assistant's database keeps growing despite regular purge routines (recorder.purge), the cause is usually one of three things:

> 1. **Unfiltered high-frequency entities** continually writing state changes or bloated attribute payloads into states and state_attributes.  
> 2. **Long-term statistics accumulation**, which ignores purge_keep_days by design and builds up indefinitely in statistics / statistics_short_term.  
> 3. **Unreclaimed SQLite page fragmentation**, where purges delete rows but the file size doesn't shrink because pages aren't vacuumed or repacked.

Running direct SQLite queries against a live Home Assistant database can easily trigger scary-looking database disk image is malformed errors. This isn't actual corruption—it's an inconsistent read state across the main .db file and its active Write-Ahead Log (-wal).  
This script safely isolates the environment, checkpoints unflushed WAL data, handles schema differences across HA Core versions, and isolates per-table errors so a single unreadable section won't abort your diagnostic run.

## **Requirements**

* Python 3.8+ (uses standard library modules only: sqlite3, argparse, shutil, os)  
* Access to your home-assistant_v2.db file (and any accompanying -wal / -shm sidecar files)

## **Quick Start**

Run the diagnostic directly against your database file:

```Bash  
python3 ha_database_reporting.py /path/to/home-assistant_v2.db
```
Show the top 50 noisiest entities instead of the default 20:

```Bash  
python3 ha_database_reporting.py /path/to/home-assistant_v2.db --top 50
```

> **Note on Live Databases:** By default, the script automatically creates a temporary copy (.diagcopy) of your database and sidecar files before performing a WAL checkpoint and analysis. This allows you to run it safely while Home Assistant is actively running.

## **CLI Options**

| Argument             | Description                                                                                | Default |
|:---------------------|:-------------------------------------------------------------------------------------------|:--------|
| db_path              | **Required.** Path to home-assistant_v2.db (or a copy).                                    | —       |
| --top N              | **Optional.** Number of top noisy entities/events to display per report section.           | 20      |
| --no-copy            | **Optional.**Work directly on db_path instead of creating a temporary .diagcopy file.      | False   |
| --no-checkpoint      | **Optional.** Skip the automatic PRAGMA wal_checkpoint(TRUNCATE) step on the working copy. | False   |
| --output <REPORT.md> | **Optional.** Path to the output the Markdown file with the results.                       | —       |
## **What It Reports**

The script executes a sequential analysis across the database, surfacing key metrics in distinct sections:

> 1. **File-Level & Allocation Info**: Evaluates raw page counts, page sizes, and freelist space. Flags if significant unused pages exist that require a VACUUM to reclaim disk space.  
> 2. **Schema Auto-Detection**: Detects whether the database uses the modern schema split (states_meta / event_types, HA Core $ge$ 2023.4) or legacy inline columns, adjusting internal SQL queries automatically.  
> 3. **Table Sizes**: Utilizes the SQLite dbstat virtual table for byte-accurate table size and percentage breakdowns. Falls back to page-size estimation and row counts if dbstat is unavailable in your Python build.  
> 4. **Top State History Bloat**: Counts state records per entity_id in the states table to locate high-frequency updates (e.g., power meters, sensor noise).  
> 5. **Top Event Types**: Counts record density in events (for legacy/older installations).  
> 6. **Long-Term Statistics Bloat**: Audits statistics and statistics_short_term record counts by entity.  
> 7. **Attribute Payload Bloat**: Measures average and total byte sizes inside state_attributes grouped by entity, identifying entities saving large payloads (e.g., full weather forecast arrays or attributes updated every second).

## **Sample Output**

```Plaintext  
======================================================================  
FILE-LEVEL INFO  
======================================================================  
Total file size (from pages): 1.4GB  
Free/unused pages (reclaimable via VACUUM): 420.0MB  
>> Significant free space exists that a VACUUM/repack hasn't reclaimed.

Schema: new (states_meta/event_types split)

======================================================================  
TABLE SIZES  
======================================================================  
states                                620.4MB  ( 43.5%)  
state_attributes                      412.1MB  ( 28.9%)  
statistics                            210.0MB  ( 14.7%)  
...

======================================================================  
TOP 20 ENTITIES IN 'states' TABLE (row count = history bloat)  
======================================================================  
sensor.realtime_power_consumption             142050  
sensor.processor_use                            98210  
...

======================================================================  
TOP 20 ENTITIES IN 'statistics' / 'statistics_short_term'  
======================================================================  
NOTE: recorder.purge does NOT clean these tables based on keep_days.  
...

## **How to Act on the Findings**

* **If states or state_attributes is huge**: Add the top noisy entities returned by the script to your recorder: exclude configuration in configuration.yaml (entities: or entity_globs:).  
* **If statistics or statistics_short_term dominates**: Decreasing purge_keep_days won't clean this up. Go to **Developer Tools > Actions** in Home Assistant and run recorder.purge_entities on specific high-volume statistic_ids, or exclude them from long-term statistics tracking.  
* **If Free/Unused Pages are large**: Your database contains dead space leftover from purged rows. Stop Home Assistant and run a manual vacuum:  
  Bash  
  sqlite3 home-assistant_v2.db 'VACUUM;'
```

## **Important Notes**

> * These scripts are **not** Home Assistant add-ons. They are standalone Python scripts that run on your local machine or server and query local database files or connect via APIs.  
> * These scripts are not affiliated with or endorsed by Home Assistant. They are independent tools created by someone who thinks he's a developer.  
> * They are designed to be run periodically (e.g., via cron), or manually, to generate a snapshot of your Home Assistant for analysis and reporting.  
> * They are intended for users who are comfortable with Python and command-line tools, and who have a working knowledge of Home Assistant's database architecture.  
> * They are provided as-is, with no warranty or support. Use at your own risk. Live on the edge.  
> * However, if you find them useful, please consider contributing back to the project by submitting issues, pull requests, or comforting compliments.  
> * I want to extend my gratitude to my friend Claude for its support, inspiration, its context drift, hallucination loops, erratic behavior, and false outputs.