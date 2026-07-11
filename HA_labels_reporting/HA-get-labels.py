#!/usr/bin/env python3
"""
Home Assistant device/entity label export tool.

Connects to a running Home Assistant instance (2026.7.x / HAOS 18.8.1
confirmed compatible) over the WebSocket API and exports:

  1. Every DEVICE with its labels -> ha_devices_labels.csv
  2. Every ENTITY with its labels -> ha_entities_labels.csv
     (this includes automations, scripts, scenes, and all helpers --
     they are entities under their own domain: automation.*, script.*,
     scene.*, input_boolean.*, input_select.*, etc.)

Both exports flag:
  - Items with NO labels at all
  - Items whose labels don't satisfy LABEL_CATEGORIES rules (see below)

Requirements:
    pip install websockets

Usage:
    export HA_URL="ws://homeassistant.local:8123/api/websocket"
    export HA_TOKEN="your-long-lived-access-token"
    python3 ha_device_label_export.py

Notes:
  - Device/entity/label/area registries are only exposed via the
    WebSocket API, not the REST API, so this script talks WS directly.
  - Create a long-lived access token in HA: Profile -> Security ->
    Long-Lived Access Tokens -> Create Token.
  - Use ws:// for http:// HA instances, wss:// for https:// instances.
  - IMPORTANT: labels do NOT roll up from device to entity in HA itself.
    A device labeled "Charger" does not make its switch/sensor entities
    show up under a "Charger" label search -- each entity needs the
    label applied directly if you want it included in that grouping.
    Entity AREA, however, IS inherited from the parent device unless
    overridden on the entity itself -- this script replicates that.
"""

import asyncio
import csv
import json
import os
import sys
from collections import defaultdict

import websockets

HA_URL = "ws://192.168.178.53:8123/api/websocket"
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJmYTI2NDA1ZTA2NGI0YjI0YTk0OTgzZmVjNDkzMGRhZSIsImlhdCI6MTc3NzU1OTk1NywiZXhwIjoyMDkyOTE5OTU3fQ.E2dm2LhcCTqhbZhLM417hHR9rVfVaArjDGD9_rK9nKA"

OUTPUT_CSV_DEVICES = os.environ.get("OUTPUT_CSV_DEVICES", "ha_devices_labels.csv")
OUTPUT_CSV_ENTITIES = os.environ.get("OUTPUT_CSV_ENTITIES", "ha_entities_labels.csv")

# ---------------------------------------------------------------------------
# Classify every label you use into one of: "brand", "protocol", "function",
# "other" (cross-cutting groupings like "Charger" that aren't required on
# every device, e.g. things tying together a switch+automation+script).
#
# Fill this in with YOUR actual label names (case-sensitive, must match
# exactly what's in HA). Any label found on a device that ISN'T listed here
# gets reported as "uncategorized" so you know to add it.
#
# A device is considered "correctly labeled" if it has at least one label
# from EACH of brand / protocol / function. "other" labels are optional
# and never required.
# ---------------------------------------------------------------------------
LABEL_CATEGORIES = {
    "Bluetooth": "protocol",
    "Bridge": "function",
    "Button": "function",
    "Camera": "function",
    "Charger": "function",
    "Coordinator": "function",
    "Digital only": "function",
    "Energy meter": "function",
    "Enphase": "brand",
    "Helper": "function",
    "HomeWizard": "brand",
    "IKEA": "brand",
    "Light": "function",
    "Matter": "protocol",
    "Mobile": "other",
    "Nabu Casa": "brand",
    "Node": "function",
    "Presence": "function",
    "RF device": "protocol",
    "Repeater": "function",
    "Router": "function",
    "Samsung": "brand",
    "Sensor": "function",
    "Smartthings": "function",
    "Solar": "function",
    "Switch": "function",
    "Tag": "function",
    "Thermostat": "function",
    "Thread": "protocol",
    "Voice Assistant": "function",
    "WiFi": "protocol",
    "Zigbee": "protocol",
    "haghs_ignore": "function"
    }

REQUIRED_CATEGORIES = ["brand", "protocol", "function"]



def check_label_categories(row):
    """Returns list of failure strings (empty list = passes)."""
    present_categories = set()
    uncategorized = []

    for label in row["label_names_set"]:
        category = LABEL_CATEGORIES.get(label)
        if category is None:
            uncategorized.append(label)
        else:
            present_categories.add(category)

    missing = [c for c in REQUIRED_CATEGORIES if c not in present_categories]
    failures = []
    if missing:
        failures.append("missing category: " + ", ".join(missing))
    if uncategorized:
        failures.append("uncategorized label(s): " + ", ".join(uncategorized))
    return failures


LABEL_RULES = [
    ("category_check", lambda d: not check_label_categories(d)),
]


async def ha_ws_command(ws, msg_id, command_type, extra=None):
    payload = {"id": msg_id, "type": command_type}
    if extra:
        payload.update(extra)
    await ws.send(json.dumps(payload))
    while True:
        resp = json.loads(await ws.recv())
        if resp.get("id") == msg_id:
            if not resp.get("success", True):
                raise RuntimeError(f"HA command {command_type} failed: {resp}")
            return resp.get("result")


async def fetch_registries():
    async with websockets.connect(HA_URL, max_size=None) as ws:
        # Handshake
        hello = json.loads(await ws.recv())
        if hello.get("type") != "auth_required":
            raise RuntimeError(f"Unexpected handshake: {hello}")

        await ws.send(json.dumps({"type": "auth", "access_token": HA_TOKEN}))
        auth_result = json.loads(await ws.recv())
        if auth_result.get("type") != "auth_ok":
            raise RuntimeError(f"Auth failed: {auth_result}")

        msg_id = 1
        labels = await ha_ws_command(ws, msg_id, "config/label_registry/list")
        msg_id += 1
        areas = await ha_ws_command(ws, msg_id, "config/area_registry/list")
        msg_id += 1
        devices = await ha_ws_command(ws, msg_id, "config/device_registry/list")
        msg_id += 1
        entities = await ha_ws_command(ws, msg_id, "config/entity_registry/list")

        return labels, areas, devices, entities


def build_device_rows(labels, areas, devices, entities):
    label_name_by_id = {l["label_id"]: l["name"] for l in labels}
    area_name_by_id = {a["area_id"]: a["name"] for a in areas}

    # Some entities carry labels/area that aren't set on the parent device;
    # roll those up so a device shows labels inherited from its entities too.
    entity_labels_by_device = defaultdict(set)
    for e in entities:
        if e.get("device_id"):
            for lid in e.get("labels", []) or []:
                entity_labels_by_device[e["device_id"]].add(lid)

    rows = []
    for d in devices:
        device_id = d["id"]
        device_label_ids = set(d.get("labels", []) or [])
        inherited_label_ids = entity_labels_by_device.get(device_id, set())
        all_label_ids = device_label_ids | inherited_label_ids

        label_names = sorted(
            label_name_by_id.get(lid, f"<unknown:{lid}>") for lid in all_label_ids
        )
        area_name = area_name_by_id.get(d.get("area_id"), "")

        row = {
            "device_id": device_id,
            "name": d.get("name_by_user") or d.get("name") or "",
            "manufacturer": d.get("manufacturer") or "",
            "model": d.get("model") or "",
            "area": area_name,
            "label_names": ", ".join(label_names),
            "label_count": len(all_label_ids),
            "labels_direct_on_device": ", ".join(
                sorted(label_name_by_id.get(lid, f"<unknown:{lid}>") for lid in device_label_ids)
            ),
            "labels_inherited_from_entities": ", ".join(
                sorted(label_name_by_id.get(lid, f"<unknown:{lid}>") for lid in inherited_label_ids)
            ),
            "disabled_by": d.get("disabled_by") or "",
            "entry_type": d.get("entry_type") or "",
            "config_entries": ", ".join(d.get("config_entries") or []),
            "entity_count": sum(1 for e in entities if e.get("device_id") == device_id),
            "label_names_set": label_names,  # kept for rule checks, stripped before CSV write
        }
        rows.append(row)

    return rows


def build_entity_rows(labels, areas, devices, entities):
    """
    One row per entity -- this naturally includes automations (automation.*),
    scripts (script.*), scenes (scene.*), and every helper domain
    (input_boolean.*, input_select.*, input_number.*, input_text.*,
    input_datetime.*, counter.*, timer.*, schedule.*, zone.*, person.*, etc.)
    since they're all just entities under their own domain.

    Unlike devices, an entity's labels are NEVER inherited from its parent
    device -- only labels applied directly to the entity itself count.
    Area, however, IS inherited from the parent device unless the entity
    has its own area_id override, so that part is replicated here.
    """
    label_name_by_id = {l["label_id"]: l["name"] for l in labels}
    area_name_by_id = {a["area_id"]: a["name"] for a in areas}
    device_name_by_id = {d["id"]: (d.get("name_by_user") or d.get("name") or "") for d in devices}
    device_area_by_id = {d["id"]: d.get("area_id") for d in devices}

    rows = []
    for e in entities:
        entity_id = e["entity_id"]
        domain = entity_id.split(".")[0]
        device_id = e.get("device_id") or ""

        label_ids = set(e.get("labels", []) or [])
        label_names = sorted(
            label_name_by_id.get(lid, f"<unknown:{lid}>") for lid in label_ids
        )

        own_area_id = e.get("area_id")
        effective_area_id = own_area_id or (device_area_by_id.get(device_id) if device_id else None)
        area_name = area_name_by_id.get(effective_area_id, "")
        area_source = "entity" if own_area_id else ("device" if effective_area_id else "")

        row = {
            "entity_id": entity_id,
            "name": e.get("name") or e.get("original_name") or "",
            "domain": domain,
            "platform": e.get("platform") or "",
            "device_id": device_id,
            "device_name": device_name_by_id.get(device_id, "") if device_id else "",
            "area": area_name,
            "area_source": area_source,
            "entity_category": e.get("entity_category") or "",
            "label_names": ", ".join(label_names),
            "label_count": len(label_ids),
            "disabled_by": e.get("disabled_by") or "",
            "hidden_by": e.get("hidden_by") or "",
            "label_names_set": label_names,  # kept for rule checks, stripped before CSV write
        }
        rows.append(row)

    return rows


def apply_rules(rows):
    for row in rows:
        row["missing_labels"] = row["label_count"] == 0
        if row["missing_labels"]:
            row["rule_failures"] = "no labels at all"
        else:
            row["rule_failures"] = "; ".join(check_label_categories(row))
    return rows


def write_csv(rows, path, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


DEVICE_FIELDNAMES = [
    "device_id",
    "name",
    "manufacturer",
    "model",
    "area",
    "label_names",
    "labels_direct_on_device",
    "labels_inherited_from_entities",
    "label_count",
    "missing_labels",
    "rule_failures",
    "disabled_by",
    "entry_type",
    "entity_count",
    "config_entries",
]

ENTITY_FIELDNAMES = [
    "entity_id",
    "name",
    "domain",
    "platform",
    "device_id",
    "device_name",
    "area",
    "area_source",
    "entity_category",
    "label_names",
    "label_count",
    "missing_labels",
    "rule_failures",
    "disabled_by",
    "hidden_by",
]


def print_label_summary(rows, id_field, kind_label):
    total = len(rows)
    unlabeled = [r for r in rows if r["missing_labels"]]
    rule_failed = [r for r in rows if r["rule_failures"]]

    print(f"\nTotal {kind_label}: {total}")
    print(f"{kind_label.capitalize()} with NO labels: {len(unlabeled)}")
    for r in unlabeled:
        print(f"  - {r['name'] or r[id_field]} ({r[id_field]})")

    print(f"\n{kind_label.capitalize()} failing label rules "
          f"(missing brand/protocol/function, or uncategorized labels): {len(rule_failed)}")
    for r in rule_failed:
        print(f"  - {r['name'] or r[id_field]}: {r['rule_failures']}")

    all_labels_seen = set()
    for r in rows:
        all_labels_seen.update(r["label_names_set"])
    uncategorized_overall = sorted(l for l in all_labels_seen if l not in LABEL_CATEGORIES)
    if uncategorized_overall:
        print(f"\nLabels in use on {kind_label} but NOT in LABEL_CATEGORIES yet ({len(uncategorized_overall)}):")
        for l in uncategorized_overall:
            print(f'  "{l}": "???",  # add to LABEL_CATEGORIES as brand/protocol/function/other')
    if not LABEL_CATEGORIES:
        print(f"\nLABEL_CATEGORIES is empty -- every labeled {kind_label[:-1]} will show as 'uncategorized'")
        print("until you fill it in at the top of the script with your brand/protocol/function labels.")


def print_device_diagnostics(rows):
    disabled = [r for r in rows if r["disabled_by"]]
    zero_entity = [r for r in rows if r["entity_count"] == 0]
    service_type = [r for r in rows if r["entry_type"]]
    if disabled or zero_entity or service_type:
        print("\nPossible reasons the GUI device count differs from this export:")
        if disabled:
            print(f"  - {len(disabled)} device(s) disabled (disabled_by set): "
                  + ", ".join(r["name"] for r in disabled))
        if zero_entity:
            print(f"  - {len(zero_entity)} device(s) with 0 entities: "
                  + ", ".join(r["name"] for r in zero_entity))
        if service_type:
            print(f"  - {len(service_type)} device(s) with entry_type set (hub/service, not a physical device): "
                  + ", ".join(f"{r['name']} ({r['entry_type']})" for r in service_type))


def print_entity_domain_breakdown(rows):
    counts = defaultdict(int)
    unlabeled_by_domain = defaultdict(int)
    for r in rows:
        counts[r["domain"]] += 1
        if r["missing_labels"]:
            unlabeled_by_domain[r["domain"]] += 1
    print("\nEntity count by domain (unlabeled in parentheses):")
    for domain in sorted(counts, key=lambda d: -counts[d]):
        print(f"  - {domain}: {counts[domain]} ({unlabeled_by_domain.get(domain, 0)} unlabeled)")


async def main():
    if not HA_TOKEN:
        print("ERROR: set HA_TOKEN environment variable to a long-lived access token.")
        sys.exit(1)

    labels, areas, devices, entities = await fetch_registries()

    print("=" * 70)
    print("DEVICES")
    print("=" * 70)
    device_rows = build_device_rows(labels, areas, devices, entities)
    device_rows = apply_rules(device_rows)
    write_csv(device_rows, OUTPUT_CSV_DEVICES, DEVICE_FIELDNAMES)
    print(f"Wrote {len(device_rows)} devices to {OUTPUT_CSV_DEVICES}")
    print_label_summary(device_rows, "device_id", "devices")
    print_device_diagnostics(device_rows)

    print("\n" + "=" * 70)
    print("ENTITIES (includes automations, scripts, scenes, and all helpers)")
    print("=" * 70)
    entity_rows = build_entity_rows(labels, areas, devices, entities)
    entity_rows = apply_rules(entity_rows)
    write_csv(entity_rows, OUTPUT_CSV_ENTITIES, ENTITY_FIELDNAMES)
    print(f"Wrote {len(entity_rows)} entities to {OUTPUT_CSV_ENTITIES}")
    print_label_summary(entity_rows, "entity_id", "entities")
    print_entity_domain_breakdown(entity_rows)


if __name__ == "__main__":
    asyncio.run(main())