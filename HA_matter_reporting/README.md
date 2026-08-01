# HA Matter Reporting Tool

A Home Assistant reporting tool that lists every Matter device on your
system with Thread network details, HA registry metadata, and identifiers
useful for telling apart physically identical devices.

Everything is pulled over a **single WebSocket session** to the HA Core API
— no REST calls, no add-ons required.

## Why this exists

Matter (and Thread) devices don't expose the kind of network fingerprint
you'd get on a normal LAN — no ARP table, no hostname, often no visible MAC
until you go digging. When you own two or more identical physical units
(same manufacturer, same model), Home Assistant alone won't tell you which
software entity maps to which unit on your desk unless you've explicitly
labeled or renamed them.

This script surfaces everything HA already knows that can help with that:
node IDs, MAC addresses, Thread role/network info, serial numbers (where
available), labels, and whether a device exposes an **Identify** button —
plus it actively flags device pairs/groups that currently have *no*
distinguishing information at all.

```
Important Note
```
* This script is **not** a Home Assistant add-on. It is a standalone Python script that runs on your local machine or server and connects to Home Assistant via the WebSocket API.
* It is designed to be run periodically (e.g., via cron) to generate a snapshot of your Home Assistant labels and identify any gaps or inconsistencies.
* It is intended for users who are comfortable with Python and command-line tools, and who have a working knowledge of Home Assistant's device and entity model.
* It is provided as-is, with no warranty or support. Use at your own risk. Live on the edge.

## Requirements

- Python 3.10+
- Home Assistant with the Matter integration configured
- A [long-lived access token](https://www.home-assistant.io/docs/authentication/#your-account-profile)
- `pip install websockets`

## Configuration

Edit the constants at the top of the script:

```python
HA_URL   = "http://homeassistant.local:8123"
HA_TOKEN = "your-long-lived-access-token"

OUTPUT   = "csv"   # "table" | "csv" | "json" | "debug"
CSV_FILE = "matter_devices.csv"   # empty string = print CSV to stdout
```

> **Note:** the token is stored in plain text in the script. Don't commit a
> real token to the repo — use an environment variable or a local
> untracked config file if you're sharing this publicly (see
> [Security](#security) below).

## Usage

```bash
python matter_devices.py
```

Progress and diagnostics are written to **stderr**, so piping stdout to a
file (or letting `CSV_FILE` write directly) won't be polluted by log
noise:

```bash
python matter_devices.py > matter_devices.csv
```

## Output modes

| Mode    | Description                                                                                                                                                                                                      |
|---------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `table` | Human-readable summary table + detailed per-device blocks, printed to stdout                                                                                                                                     |
| `csv`   | Spreadsheet-friendly export (see column reference below)                                                                                                                                                         |
| `json`  | Full structured export of all fields (excluding raw diagnostics)                                                                                                                                                 |
| `debug` | Dumps the raw `thread/list_datasets` and `matter/node_diagnostics` payloads per device — useful when HA's diagnostics schema doesn't match what this script expects (it varies across HA/Matter server versions) |

## What it collects

For each Matter device in the HA device registry, the script cross-references:

1. **`config/device_registry/list`** — name, area, manufacturer, model,
   firmware/hardware version, assigned labels
2. **`matter/node_diagnostics`** (per device) — node ID, network type,
   Thread role, MAC address, IPv6 addresses, availability, active Matter
   fabrics
3. **`thread/list_datasets`** — Thread channel, PAN ID, extended PAN ID,
   network name (cross-referenced against the preferred dataset)
4. **`config/label_registry/list`** — resolves label IDs to display names
5. **`config/entity_registry/list`** — detects a `button.*` entity per
   device whose name/translation key suggests it's an Identify control

## Column reference (CSV/JSON)

| Column                                                                           | Source                                                           | Notes                                                                          |
|----------------------------------------------------------------------------------|------------------------------------------------------------------|--------------------------------------------------------------------------------|
| `name`                                                                           | device registry                                                  | user-set name if present, else default                                         |
| `ha_device_id`                                                                   | device registry                                                  | HA's internal device ID                                                        |
| `area_id`                                                                        | device registry                                                  |                                                                                |
| `manufacturer` / `model`                                                         | device registry                                                  |                                                                                |
| `sw_version` / `hw_version`                                                      | device registry                                                  |                                                                                |
| `labels`                                                                         | label registry                                                   | comma-separated label names                                                    |
| `serial_number`                                                                  | device registry, falling back to a defensive scan of diagnostics | may be `—` if the device/integration doesn't report one                        |
| `has_identify_button`                                                            | entity registry                                                  | `yes`/`no` — whether you can trigger a physical blink/beep to confirm identity |
| `ambiguous_twin`                                                                 | computed                                                         | see [below](#ambiguous-twin-detection)                                         |
| `matter_node_id`                                                                 | diagnostics, falling back to parsed unique_id                    |                                                                                |
| `matter_unique_id`                                                               | device registry identifiers                                      | raw HA Matter unique ID string                                                 |
| `fabric_id` / `fabric_label`                                                     | parsed unique_id / active_fabrics                                | HA's own commissioning fabric                                                  |
| `network_type`                                                                   | diagnostics                                                      | `thread` or `wifi`                                                             |
| `available`                                                                      | diagnostics                                                      | current reachability                                                           |
| `mac_address`                                                                    | diagnostics                                                      |                                                                                |
| `thread_role`                                                                    | diagnostics                                                      | Router / Router-ED / Sleepy-ED / End Device                                    |
| `thread_network_name` / `thread_channel` / `thread_pan_id` / `thread_ext_pan_id` | thread datasets                                                  |                                                                                |
| `ipv6_addresses`                                                                 | diagnostics                                                      | semicolon-separated in CSV                                                     |

## Ambiguous-twin detection

Devices are grouped by `(manufacturer, model)`. Within a group of two or
more, a device is flagged `ambiguous_twin = True` only if **all** of the
following are true:

- No label assigned
- No serial number found
- No **unique**, user-set name (a shared default name like "Plug" on two
  units doesn't count — nor does a custom name if it's not unique within
  the group)

A device's MAC address and Matter node ID are always technically unique,
but that's not the same as being *humanly* identifiable — this flag is
about whether you, standing in front of two identical boxes, could tell
which is which in Home Assistant. When the script finds ambiguous twins,
it prints a warning to stderr with each device's ID and whether an
Identify button is available, so you know which ones to physically
blink-test and label next.

## Known limitations

- **Diagnostics schema drift**: `matter/node_diagnostics` and
  `thread/list_datasets` response shapes have changed across HA/Matter
  server versions. The parsing is defensive where possible (see
  `normalise_thread_datasets`, `extract_serial`), but if fields come back
  empty, run in `debug` mode and compare against the raw payload.
- **Serial numbers aren't guaranteed**: many Matter devices simply don't
  report one over the Basic Information cluster. Labeling remains the only
  fully reliable disambiguation method.
- **Identify detection is heuristic**: it matches on entity naming
  patterns (`button.*` + "identify" in the name/translation key/unique
  id), not a guaranteed Matter Identify-cluster capability check. Some
  devices that do support Identify may not surface a dedicated HA button
  entity for it.
- Requires the HA Matter integration; devices on other protocols (Zigbee,
  Z-Wave, etc.) are filtered out entirely.

## Security

This script needs a Home Assistant long-lived access token with full read
access to your instance. Recommendations before pushing to a shared repo:

- Do not commit `HA_URL` / `HA_TOKEN` with real values — load them from
  environment variables instead, e.g.:

  ```python
  import os
  HA_URL = os.environ["HA_URL"]
  HA_TOKEN = os.environ["HA_TOKEN"]
  ```

- Add `matter_devices.csv` (or your chosen `CSV_FILE`) to `.gitignore` —
  the output includes MAC addresses, IPv6 addresses, and Thread network
  details for your home network.

## License

Add a license of your choosing here before publishing.
