# HA pull entity data

A minimal Home Assistant export tool. Pulls the current state of every entity via the REST API (`/api/states`) and
writes it to a timestamped CSV, plus a rolling `home_assistant_entities.csv` that always reflects the most recent run.

Unlike the WebSocket-based tools in this repo (`matter_devices.py`,
`ha_get_labels.py`), this one only needs the REST API — no `websockets`
dependency, no persistent connection. It's a quick point-in-time snapshot of entity states rather than a registry/label
audit.

Notes: 
The Excel workbook combines the influx_ha_entities.csv output with the home_assistant_entities.csv output to create a comparison of the two datasets. Read the [Excel workbook README](./HA_entities_reporting/README_excel.md) for more information.

## Requirements

- Python 3.x
- `pip install requests`
- A Home Assistant [long-lived access token](https://www.home-assistant.io/docs/authentication/#your-account-profile)

## Configuration

Edit the constants at the top of the script:

```python
HA_URL = "YOUR_URL_HERE"  # Example http://192.168.178.53:8123"
HA_TOKEN = "YOUR_HA_TOKEN_HERE"
```

## Usage

```
python3 ha_pull_entity_data.py
```

On success, prints the number of entities exported and the timestamped filename. On failure (non-200 response), prints
the HTTP status code and response body.

## Output

Two files are written to the working directory on each run:

- `home_assistant_entities_YYYYMMDD_HHMMSS.csv` — a timestamped snapshot, never overwritten
- `home_assistant_entities.csv` — a copy of the same data, overwritten every run, useful if you always want "the latest
  export" at a fixed path (e.g. for another tool or script to read)

Each row contains:

| Column          | Notes                                                                                                                                |
|-----------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `entity_id`     | e.g. `light.kitchen`                                                                                                                 |
| `state`         | current state at request time                                                                                                        |
| `domain`        | derived from `entity_id` (everything before the first `.`)                                                                           |
| `last_changed`  | ISO timestamp of the last state *change*                                                                                             |
| `last_updated`  | ISO timestamp of the last state *update* (can differ from `last_changed` — HA updates attributes without necessarily changing state) |
| `friendly_name` | from entity attributes; empty string if not set                                                                                      |

## Notes on the data itself

- `state` reflects each entity's state at request time — this is a snapshot, not a history export. For historical data,
  HA's `/api/history`
  endpoint would be the right tool instead.
- `friendly_name` falls back to an empty string when an entity doesn't define one (e.g. some internal/diagnostic
  entities).
- No filtering is applied — every entity in the system is exported, including disabled/hidden ones, helpers, and
  internal domains like
  `persistent_notification` or `zone`.

## Known limitations

- **No pagination or size limiting** — `/api/states` returns the full entity list in one response. Fine for a typical
  homelab instance; a very large entity count means a correspondingly large single request/ response.
- **No retry logic** — a single failed request (network blip, HA restarting, token expiry) prints an error and exits;
  nothing is retried automatically.
- **Timestamped files accumulate** — nothing here prunes old
  `home_assistant_entities_*.csv` snapshots. If you run this on a schedule (cron, systemd timer, etc.), add your own
  cleanup / retention policy.

## Important Note

* These scripts are **not** Home Assistant add-ons. They are standalone Python scripts that run on your local machine or server and connect to Home Assistant via the HA websocket api.
* These scripts are not affiliated with or endorsed by Home Assistant. They are independent tools created by someone who thinks he's a developer.
* They are designed to be run periodically (e.g., via cron), or manually, to generate a snapshot of your Home Assistant for analysis and reporting.
* They are intended for users who are comfortable with Python and command-line tools, and who have a working knowledge of Home Assistant's device and entity model.
* They are provided as-is, with no warranty or support. Use at your own risk. Live on the edge.
* However, if you find them useful, please consider contributing back to the project by submitting issues, pull requests, or comforting compliments.
* I want to extend my gratitude to my friend Claude for its support, inspiration, its context drift, hallucination loops, erratic behavior, and false outputs.
```
```