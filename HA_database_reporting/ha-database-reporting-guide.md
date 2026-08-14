# Home Assistant Database Auditing Guide

A practical guide for diagnosing why `home-assistant_v2.db` keeps growing
despite regular purges, and how to work with it safely.

---

## 1. Before you touch anything: understand the two failure modes

A bloated recorder database usually comes from one of two very different
problems, and it's important not to conflate them:

1. **Purge isn't actually enforcing `purge_keep_days`** - the config is
   wrong, disabled, or silently failing.
2. **Purge is working exactly as configured, but the configured window
   still contains an enormous number of rows** because one or more
   entities are writing state changes far more often than expected.

There's also a third thing that *looks* like corruption but usually isn't:
**reading a live WAL-mode database incorrectly.** Section 3 covers this in
detail, because it's an easy trap and can send you down a corruption-recovery
path for nothing.

---

## 2. Recorder config sanity check

Start by reviewing your `recorder:` block in `configuration.yaml`. A minimal,
sane config looks like:

```yaml
recorder:
  purge_keep_days: 7
  auto_purge: true
  auto_repack: true
  commit_interval: 10
  exclude:
    domains:
      - automation
      - scene
    entities:
      - sensor.some_noisy_entity
    entity_globs:
      - sensor.some_prefix*
```

Things to check:

- **`auto_purge: true`** - without this, purge only runs when manually
  triggered.
- **`auto_repack: true`** - without this, deleted rows are marked free
  internally but the file doesn't shrink.
- **Overly broad domain excludes** - excluding an entire domain (e.g.
  `climate`, `binary_sensor`) removes history/statistics for *every* entity
  in that domain, which may be more than intended. Prefer specific
  `entities:` or `entity_globs:` over blanket domain excludes unless you
  really mean "none of these, ever."
- **Dead/placeholder globs** - a glob like `everything*` that doesn't match
  any real entity_id does nothing. Double check every glob actually matches
  something with a quick query (Section 5) before relying on it.
- **`exclude` only affects the *recorder* database.** If you also export
  states to InfluxDB, Prometheus, etc., those integrations read from the
  state bus directly and are unaffected by recorder excludes - safe to
  exclude noisy entities from recorder without losing your Grafana/InfluxDB
  history.

### The purge automation itself

If you run purge via an automation/script rather than relying on
`auto_purge`, make sure it's actually configured correctly:

```yaml
sequence:
  - action: recorder.purge
    data:
      repack: true
      keep_days: 7
alias: Database cleanup (purge)
```

This is correct - `repack: true` is what reclaims disk space, and
`keep_days` should match (or be tighter than) your `purge_keep_days` config.
If this runs without error in the HA log, purge is executing. Whether it's
*sufficient* is a separate question, answered in Section 6.

---

## 3. WAL mode: read this before running any manual SQL

Home Assistant's recorder runs SQLite in **WAL (Write-Ahead Logging) mode**.
In WAL mode, recent writes live in a separate `home-assistant_v2.db-wal`
file (plus a `-shm` shared-memory index file) until they're checkpointed
back into the main `.db` file.

**Symptom:** you open the `.db` file directly - especially while HA is still
running - and get:

```
Error: database disk image is malformed
```

on some queries (often ones touching indexes, like a `JOIN`), while
`PRAGMA integrity_check;` still reports `ok`.

**What's actually happening:** this is *not* real file corruption. It's an
inconsistent read across the main file and the not-yet-checkpointed WAL
data. `integrity_check` walks the whole logical database (including WAL) and
finds it structurally fine; a raw table scan against just the main file can
still trip over pages that reference data currently sitting in the WAL.

**How to resolve it:**

> **Note**  
> Stopping and Starting Home Assistant  
The way you stop and start Home Assistant depends on your installation type. Use the appropriate commands for your setup:

```
Stop Home Assistant

# Linux systemd
systemctl stop home-assistant   
or
# Home Assistant OS / Supervised
ha core stop  


Start Home Assistant

# Linux systemd
systemctl start home-assistant   
or
# Home Assistant OS / Supervised
ha core start 
```

```bash
# 1. Stop Home Assistant so nothing is actively writing

# 2. Force a full checkpoint, merging -wal into the main file
sqlite3 home-assistant_v2.db "PRAGMA wal_checkpoint(TRUNCATE);"

# 3. Confirm the -wal file is now empty or gone
ls -la home-assistant_v2.db*

# 4. Work against a COPY from here on, never the live file
cp home-assistant_v2.db home-assistant_v2.db.copy
sqlite3 home-assistant_v2.db.copy
```

Then re-run your query. If it now succeeds, the earlier error was purely a
live-read artifact - nothing is actually wrong with the database.

**Rule of thumb:** if you see `-wal` and/or `-shm` files sitting next to
`home-assistant_v2.db`, do not draw any conclusions about corruption until
you've stopped HA (or at least checkpointed a copy) and re-tested.

---

## 4. Real corruption: how to tell, and what to do

If, *after* checkpointing on a stopped instance, you still get errors, check
properly:

```sql
PRAGMA integrity_check;
```

- **Returns `ok`** → the database is structurally sound. Any earlier error
  was a WAL/read artifact (Section 3) or something narrower like a damaged
  single index - try `REINDEX <table>;` and re-test.
- **Returns a list of problems** → genuine corruption. Recovery options, in
  order of preference:

```bash
# Modern sqlite3 CLI has a purpose-built recovery command
sqlite3 home-assistant_v2.db.corrupt-backup ".recover" | sqlite3 recovered.db
sqlite3 recovered.db "PRAGMA integrity_check;"
```

If `.recover` produces a clean database, swap it in:


Stop Home Assistant!
```bash
mv home-assistant_v2.db home-assistant_v2.db.old
mv recovered.db home-assistant_v2.db
```

Start Home Assistant!  

If recovery isn't clean, or the corruption is extensive, it's often faster
and more reliable to let HA rebuild a fresh database rather than nurse a
damaged file back to health - especially if the `statistics` table (see
Section 6) was already dominating the file size and not worth preserving
anyway:

Stop Home Assistant!
```bash
mv home-assistant_v2.db home-assistant_v2.db.corrupt-backup-$(date +%F)
mv home-assistant_v2.db-wal home-assistant_v2.db-wal.bak 2>/dev/null
mv home-assistant_v2.db-shm home-assistant_v2.db-shm.bak 2>/dev/null
```

Start Home Assistant!   
**Why databases corrupt in the first place** - worth checking so it doesn't
recur:
- Unclean shutdown / power loss mid-write
- SD card wear (common on HAOS/Raspberry Pi installs - SQLite + SD cards is
  a known long-term reliability weak point)
- Underlying storage/filesystem issues (disk errors, snapshot problems,
  unexpected container/pod restarts if HA runs in a VM or container)

If this is a recurring risk, consider moving the recorder to MariaDB/Postgres
instead of SQLite - worthwhile if you already run a database server
elsewhere in your infrastructure.

---

## 5. Finding what's actually filling the database

Once you're confident you're reading a consistent copy (Section 3), the
investigation is table-by-table.

### 5.1 Row counts per table

```sql
SELECT 'states' AS tbl, COUNT(*) FROM states
UNION ALL SELECT 'events', COUNT(*) FROM events
UNION ALL SELECT 'state_attributes', COUNT(*) FROM state_attributes
UNION ALL SELECT 'statistics', COUNT(*) FROM statistics
UNION ALL SELECT 'statistics_short_term', COUNT(*) FROM statistics_short_term;
```

### 5.2 Actual disk bytes per table

Row counts alone can mislead if some rows are much larger than others (e.g.
big attribute blobs). Use `dbstat` for byte-accurate sizing:

```sql
SELECT name, SUM(pgsize) AS bytes
FROM dbstat
GROUP BY name
ORDER BY bytes DESC
LIMIT 15;
```

(Requires a `sqlite3` build with `SQLITE_ENABLE_DBSTAT_VTAB` - most distro
builds have it.)

### 5.3 Top entities by state-change count

On HA core ≥ 2023.4, `states` no longer stores `entity_id` inline - it's
split into `states_meta`:

```sql
SELECT sm.entity_id, COUNT(*) AS n
FROM states s
JOIN states_meta sm ON s.metadata_id = sm.metadata_id
GROUP BY sm.entity_id
ORDER BY n DESC
LIMIT 25;
```

On older schemas, `entity_id` is a direct column on `states`:

```sql
SELECT entity_id, COUNT(*) AS n
FROM states
GROUP BY entity_id
ORDER BY n DESC
LIMIT 25;
```

### 5.4 Top event types

```sql
SELECT et.event_type, COUNT(*) AS n
FROM events e
JOIN event_types et ON e.event_type_id = et.event_type_id
GROUP BY et.event_type
ORDER BY n DESC
LIMIT 25;
```

### 5.5 Attribute payload bloat

Some entities carry unusually large `attributes` payloads (long lists,
forecast arrays, JSON blobs) - this shows up in `state_attributes`, not
`states` row count:

```sql
SELECT sm.entity_id, AVG(LENGTH(sa.shared_attrs)) AS avg_len, COUNT(*) AS n
FROM state_attributes sa
JOIN states s ON s.attributes_id = sa.attributes_id
JOIN states_meta sm ON s.metadata_id = sm.metadata_id
GROUP BY sm.entity_id
ORDER BY avg_len * n DESC
LIMIT 20;
```

### 5.6 Data range actually stored

This is the key check for whether purge is enforcing its window at all:

```sql
SELECT datetime(MIN(last_updated_ts), 'unixepoch') AS oldest,
       datetime(MAX(last_updated_ts), 'unixepoch') AS newest
FROM states;
```

If `oldest` is much older than your configured `purge_keep_days`, purge is
not working - check the HA log for `recorder.purge` errors. If the range
matches your configured window, purge is working correctly and the row
count you're seeing really is what your setup generates in that window -
the problem is entity-level noise, not purge.

---

## 6. The gotcha almost everyone misses: `statistics` isn't purged by keep_days

`recorder.purge` and `purge_keep_days` govern the `states` and `events`
tables. They do **not** clean the `statistics` table, regardless of how
short you set `keep_days`.

Any entity with a `state_class` (most sensors - power, energy, temperature,
etc.) gets long-term statistics generated and retained **indefinitely** by
default, because these feed the Energy dashboard and long-term history
graphs. Only `statistics_short_term` is auto-cleaned (kept roughly 10 days).

If you have many sensors with `state_class` set - which is typical for
energy monitoring integrations - `statistics` can dwarf `states` even when
purge is working perfectly.

**Check it:**

```sql
SELECT sm.statistic_id, COUNT(*) AS n
FROM statistics s
JOIN statistics_meta sm ON s.metadata_id = sm.id
GROUP BY sm.statistic_id
ORDER BY n DESC
LIMIT 25;
```

**Fix:** use **Developer Tools → Actions → `recorder.purge_entities`**
against the noisiest `statistic_id`s. Unlike a normal purge, this *does*
remove statistics for the targeted entities. Alternatively, exclude the
entity entirely via `recorder: exclude`, understanding this removes both
`states` and `statistics` for it - fine for instantaneous readings you don't
need historical stats on, not fine for anything feeding the Energy
dashboard.

---

## 7. Case study: HomeWizard energy sockets

A concrete pattern worth calling out because it's common with any
high-frequency energy-monitoring integration (HomeWizard, Shelly, Tuya
power plugs, etc.):

Each energy socket typically exposes multiple sensors:

- **Cumulative totals** (kWh import/export) - update relatively rarely,
  monotonically increasing, feed the Energy dashboard. **Worth keeping.**
- **Instantaneous readings** (active power W, voltage V, current A,
  power factor, frequency) - update every few seconds, only useful in the
  moment, not meaningful as long-term history. **Prime purge/exclude
  candidates.**

With several sockets each exposing 4-6 instantaneous sensors polling every
few seconds, this alone can generate well over a million `states` rows per
day - entirely independent of any purge misconfiguration.

**Diagnosis:**

```sql
SELECT sm.entity_id, COUNT(*) AS n
FROM states s
JOIN states_meta sm ON s.metadata_id = sm.metadata_id
WHERE sm.entity_id LIKE 'sensor.energy%'
GROUP BY sm.entity_id
ORDER BY n DESC;
```

**Fix** - exclude the instantaneous sensors by pattern, keep the cumulative
ones:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.energy*_power
      - sensor.energy*_voltage
      - sensor.energy*_current
      - sensor.energy*_apparentpower
      - sensor.energy*_powerfactor
      - sensor.energy*_frequency
```

Adjust suffixes to match your actual entity naming (varies by device model /
firmware). Do **not** exclude the `_total_power_import_kwh`-style entities -
those are what the Energy dashboard and long-term statistics depend on.

---

## 8. Reclaiming disk space after cleanup

Excluding entities and purging stops *future* growth, but existing bloat
needs to be reclaimed:

```sql
-- Check free/reclaimable space first
PRAGMA freelist_count;
PRAGMA page_count;
PRAGMA page_size;
-- free_bytes = freelist_count * page_size
```

If there's substantial free space that repack hasn't reclaimed, run a
manual `VACUUM` on a **stopped** HA instance (VACUUM rewrites the entire
file, so this can take a while on a multi-GB database):


Stop Home Assistant! 
```bash
sqlite3 home-assistant_v2.db "VACUUM;"
```
Start Home Assistant!

---

## 9. Quick-reference checklist

Run through in this order when the database is growing unexpectedly:

1. ☐ Check for `-wal`/`-shm` files before running any manual SQL - if
   present, stop HA (or checkpoint a copy) before drawing conclusions.
2. ☐ `PRAGMA integrity_check;` - confirm the database is structurally sound.
3. ☐ Check `MIN(last_updated_ts)`/`MAX(last_updated_ts)` on `states` -
   confirm purge is actually enforcing `purge_keep_days`.
4. ☐ Row counts / byte sizes per table - identify which table dominates.
5. ☐ If `states` dominates: top-entities-by-count query → add noisy
   entities to `exclude`.
6. ☐ If `statistics`/`statistics_short_term` dominates: top statistic_ids
   query → `recorder.purge_entities` on the worst offenders (purge_keep_days
   won't touch these).
7. ☐ If `state_attributes` dominates: attribute-bloat query → investigate
   the specific entity's payload.
8. ☐ After cleanup: check `freelist_count` for reclaimable space; `VACUUM`
   on a stopped instance if needed.
9. ☐ Review recorder config for overly broad domain excludes or dead glob
   patterns that aren't matching anything.
