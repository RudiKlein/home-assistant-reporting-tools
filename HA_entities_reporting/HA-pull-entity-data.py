import requests
import csv
from datetime import datetime
from pathlib import Path
import shutil

HA_URL = "http://192.168.178.53:8123"
HA_TOKEN = "<ADD_YOUR_HA_TOKEN_HERE>"

headers = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

response = requests.get(f"{HA_URL}/api/states", headers=headers)

if response.status_code == 200:
    entities = response.json()

    filename_u = f"home_assistant_entities_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filename_g = f"home_assistant_entities.csv"

    with open(filename_u, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Header row
        writer.writerow(["entity_id", "state", "domain", "friendly_name"])

        for e in entities:
            entity_id = e["entity_id"]
            domain = entity_id.split(".")[0]
            friendly_name = e.get("attributes", {}).get("friendly_name", "")

            writer.writerow([
                entity_id,
                e["state"],
                domain,
                e["last_changed"],
                e["last_updated"],
                friendly_name,
            ])

    print(f"Saved {len(entities)} entities to {filename_u}")
    src = Path(filename_u)
    dst = Path(filename_g)

    shutil.copy2(src, dst)
else:
    print(f"Error {response.status_code}: {response.text}")
