import csv
from datetime import datetime
from influxdb_client import InfluxDBClient
from pathlib import Path
import shutil

INFLUX_URL = "YOUR_URL_HERE"  # Example http://192.168.1.17:18086"
INFLUX_TOKEN = "YOUR_TOKEN_HERE"
INFLUX_ORG = "YOUR_ORG_HERE"
INFLUX_BUCKET = "YOUR_BUCKET_NAME_HERE"

client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
query_api = client.query_api()

query = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -1y)
  |> filter(fn: (r) => r["_field"] == "value")
  |> last()
  |> keep(columns: ["entity_id", "domain"])
  |> distinct(column: "entity_id")
"""

tables = query_api.query(query)

filename_u = f"influx_ha_entities_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
filename_g = f"influx_ha_entities.csv"

rows = []
for table in tables:
    for record in table.records:
        entity_id = record.values.get("entity_id", "")
        domain = record.values.get("domain", "")
        full_entity_id = f"{domain}.{entity_id}" if domain else entity_id
        rows.append([entity_id, domain, full_entity_id])

rows.sort(key=lambda x: x[2])  # sort by full_entity_id

with open(filename_u, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(["entity_id", "domain", "full_entity_id"])
    writer.writerows(rows)

src = Path(filename_u)
dst = Path(filename_g)

shutil.copy2(src, dst)

print(f"Found {len(rows)} unique entity IDs, saved to {filename_u}")
client.close()