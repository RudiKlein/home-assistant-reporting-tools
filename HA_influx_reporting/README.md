# InfluxDB Home Assistant entities reporting

Queries an InfluxDB 2.x bucket for every unique Home Assistant `entity_id`
that has reported a value in the last year, and exports the list to CSV.

Unlike the other export tools in this repo, this one doesn't talk to Home Assistant at all — it reads historical
time-series data straight out of InfluxDB, which is useful when you want a list of entities that have actually
*recorded* data (as opposed to what's currently registered in HA, which may include entities that have never reported,
or exclude entities that were later removed from HA but still have historical data in InfluxDB).

Notes: 
The script is written for InfluxDB 2.x and the `influxdb-client` Python library. It will not work with InfluxDB 1.x, InfluxDB 3.x, or the older `influxdb` library.
The Excel workbook combines the influx_ha_entities.csv output with the home_assistant_entities.csv output to create a comparison of the two datasets. Read the [Excel workbook README](./HA_influx_reporting/README_excel.md) for more information.

## Requirements

- Python 3.x
- `pip install influxdb-client`
- An InfluxDB 2.x instance with an [API token](https://docs.influxdata.com/influxdb/v2/admin/tokens/)
  that has read access to the target bucket
- A bucket populated by the
  standard [Home Assistant InfluxDB integration](https://www.home-assistant.io/integrations/influxdb/), which tags each
  point with `entity_id` and `domain` — this script's query depends on that tag schema being present

## Configuration

Edit the constants at the top of the script:

```python
INFLUX_URL = "your-influxdb-url"  # Example: http://192.168.1.17:8086
INFLUX_TOKEN = "your-influxdb-api-token"
INFLUX_ORG = "your-org-name"
INFLUX_BUCKET = "your-bucket-name"
```

## Usage

```
python3 influx_ha_entities.py
```

Prints the number of unique entity IDs found and the timestamped filename on completion.

## What the query does

```flux
from(bucket: "<bucket>")
  |> range(start: -1y)
  |> filter(fn: (r) => r["_field"] == "value")
  |> last()
  |> keep(columns: ["entity_id", "domain"])
  |> distinct(column: "entity_id")
```

- **`range(start: -1y)`** — only considers data points written in the last year
- **`filter(fn: (r) => r["_field"] == "value")`** — restricts to points recorded under the `value` field
  (see [Known limitations](#known-limitations))
- **`last()`** — takes only the most recent point per series
- **`keep(columns: [...])`** — drops everything except the `entity_id` and `domain` tags
- **`distinct(column: "entity_id")`** — de-duplicates by `entity_id`
  *within* each resulting table (see below — this doesn't guarantee global uniqueness across tables)

## Output

Two files are written to the working directory on each run:

- `influx_ha_entities_YYYYMMDD_HHMMSS.csv` — a timestamped snapshot, never overwritten
- `influx_ha_entities.csv` — a copy of the same data, overwritten every run

Both are written with `utf-8-sig` encoding (UTF-8 with a BOM), which makes them open correctly in Excel on Windows
without character-encoding prompts. Note this differs from the other export scripts in this repo, which use plain
`utf-8`.

| Column           | Notes                                                                                                                                                     |
|------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| `entity_id`      | the raw `entity_id` tag value from InfluxDB — note this is *not* prefixed with the domain (e.g. `kitchen_light`, not `light.kitchen_light`)               |
| `domain`         | the `domain` tag value, e.g. `light`, `sensor`                                                                                                            |
| `full_entity_id` | reconstructed as `{domain}.{entity_id}`, falling back to just `entity_id` if `domain` is empty — this is what you'd normally recognize as an HA entity ID |

Rows are sorted alphabetically by `full_entity_id`.

## Known limitations

- **`distinct()` operates per Flux table, not globally.** Flux's
  `distinct()` de-duplicates within each table produced by the pipeline, not across the whole result set. If the same
  `entity_id` appears under more than one tag-set grouping (e.g. the same entity somehow logged under two different
  `domain` values, or across separate measurements), you can end up with duplicate `entity_id` rows in the CSV despite
  the query's name. The Python code doesn't re-deduplicate afterward — if you need a hard uniqueness guarantee, dedupe
  `rows` on `full_entity_id`
  before writing (e.g. via a `dict` keyed by that column) or add an explicit `group()` before `distinct()` in the Flux
  query.
- **Only entities recorded under the `value` field are included.** The HA InfluxDB integration writes some entity types
  under different field names depending on state type; anything not stored as `value` (for example, certain string-state
  or attribute-only points) won't appear in this export even if they're actively logging data.
- **One-year lookback window.** Entities that haven't reported in the last 12 months (offline devices, decommissioned
  integrations, very low-frequency sensors) won't show up. Adjust `range(start: -1y)` if you need a longer or shorter
  window.
- **No error handling around the query itself.** Unlike the REST-based export script in this repo, there's no status
  check here — a bad token, unreachable host, or malformed bucket name will raise an unhandled exception from the
  `influxdb-client` library rather than printing a clean error message.
- **No pagination** — the full result set is pulled into memory in one query. Fine for a typical homelab-sized entity
  count.

## Important Note

* These scripts are **not** Home Assistant add-ons. They are standalone Python scripts that run on your local machine or server and connect to InfluxDB via the InfluxDB API.
* These scripts are not affiliated with or endorsed by Home Assistant and/or InfluxDB. They are independent tools created by someone who thinks he's a developer.
* They are designed to be run periodically (e.g., via cron), or manually, to generate a snapshot of your Home Assistant for analysis and reporting.
* They are intended for users who are comfortable with Python and command-line tools, and who have a working knowledge of Home Assistant's device and entity model.
* They are provided as-is, with no warranty or support. Use at your own risk. Live on the edge.
* However, if you find them useful, please consider contributing back to the project by submitting issues, pull requests, or comforting compliments.
* I want to extend my gratitude to my friend Claude for its support, inspiration, its context drift, hallucination loops, erratic behavior, and false outputs.
```
```