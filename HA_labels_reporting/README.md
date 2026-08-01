# Home Assistant Label Audit & Export Tool

A Python script that connects to a running Home Assistant instance over the WebSocket API to export all devices and
entities into CSV files.

Beyond simply exporting data, this tool acts as a **label auditor**. It checks your entire Home Assistant ecosystem to
find devices and entities missing labels, and validates your existing labels against a customizable strict taxonomy
(e.g., requiring every device to have a Brand, Protocol, and Function label).

```
Important Note
```

* This script is **not** a Home Assistant add-on. It is a standalone Python script that runs on your local machine or
  server and connects to Home Assistant via the WebSocket API.
* It is designed to be run periodically (e.g., via cron), or manually, to generate a snapshot of your Home Assistant labels and
  identify any gaps or inconsistencies.
* It is intended for users who are comfortable with Python and command-line tools, and who have a working knowledge of
  Home Assistant's device and entity model.
* It is provided as-is, with no warranty or support. Use at your own risk. Live on the edge.

## Features

* **Comprehensive Entity Export:** Captures standard entities alongside automations (`automation.*`), scripts
  (`script.*`), scenes (`scene.*`), and all helpers (`input_boolean.*`, etc.).
* **Taxonomy Validation:** Enforces a labeling strategy (Brand, Protocol, Function) and flags items that fail these
  rules.
* **Orphan Detection:** Instantly identifies devices or entities with zero labels.
* **Inheritance Mapping:** Accurately reflects Home Assistant's internal logic where entities inherit *areas* from their
  parent devices, but do *not* inherit *labels*.
* **Bypasses REST limitations:** Connects directly to the WebSocket API to access underlying device, entity, area, and
  label registries not fully exposed via the REST API.

---

## Prerequisites

1. **Python 3.7+**
2. **Websockets Library:**
   ```bash
   pip install websockets
    ```

3. **Home Assistant Long-Lived Access Token:**

* In Home Assistant, click your Profile (bottom left) → **Security** → **Long-Lived Access Tokens** → **Create Token**.

---

## Usage

1. **Clone or download** the script (`ha_device_label_export.py`).
2. **Configure environment variables** for your Home Assistant URL and Token.
3. **Run the script.**

### Set your Home Assistant WebSocket URL (use wss:// for https instances)

```
export HA_URL="ws://homeassistant.local:8123/api/websocket"
```

### Set your Long-Lived Access Token

```
export HA_TOKEN="your-long-lived-access-token"
```

### Run the exporter

```
python3 ha_device_label_export.py

```

### Optional Environment Variables

You can customize the output filenames by setting these optional environment variables before running the script:

* `OUTPUT_CSV_DEVICES` (Defaults to `ha_devices_labels.csv`)
* `OUTPUT_CSV_ENTITIES` (Defaults to `ha_entities_labels.csv`)

---

## Customizing Your Label Rules (Important)

By default, the script enforces a strict taxonomy requiring every device/entity to have at least one label from three
categories: **Brand**, **Protocol**, and **Function**.

Before relying on the rule-failure outputs, you must edit the `LABEL_CATEGORIES` dictionary at the top of the Python
script to match the exact, case-sensitive labels used in your Home Assistant instance.

```
LABEL_CATEGORIES = {
    "IKEA": "brand",
    "Zigbee": "protocol",
    "Light": "function",
    "Mobile": "other", # "other" is optional and cross-cutting
    # ... add your own labels here
}
```

*If the script encounters a label on a device that is not in this dictionary, it will print it out as "uncategorized" in
the console so you know to add it to your script.*

---

## Outputs

The script generates two files in the directory it is run from:

### 1. `ha_devices_labels.csv`

Contains a list of physical devices and hub services.

* Includes inherited label sets (labels applied to child entities rolled up to the device view).
* Flags missing labels and rule failures based on your configured categories.

### 2. `ha_entities_labels.csv`

Contains every individual entity in Home Assistant.

* Identifies domain, platform, and parent device.
* Highlights area inheritance (whether the area is set directly on the entity or inherited from the device).
* Flags missing labels and rule failures.

### Console Output

When run, the script prints a helpful diagnostic summary to the terminal, highlighting:

* Total counts of devices and entities.
* Specific items failing your taxonomy rules.
* Any unmapped labels found in Home Assistant that need to be added to the script's `LABEL_CATEGORIES`.
* Diagnostic anomalies (e.g., devices with 0 entities, or items disabled by integrations).

---

## A Note on Home Assistant Quirks

This script exposes a specific Home Assistant behavior regarding labels: **Labels do not roll up or cascade.**

* If you label a Device as "Charger", its underlying switch and sensor entities **do not** inherit the "Charger" label.
  Searching for the "Charger" label in auto-entities or dashboards will not yield those switches unless the label is
  applied to the entities directly.
* **Areas**, however, *are* inherited from parent devices unless explicitly overridden on the entity. This script
  accurately replicates and maps this behavior.

## A Note on the files in this repository

* I have included a few sample CSV files in this repository to illustrate the output format.
* The Excel file `ha_labels_audit.xlsx` is a sample of what you see when you import the CSVs in Excel by using a query,
  into a single workbook with multiple sheets.

```
```