import csv
from datetime import datetime
from influxdb_client import InfluxDBClient
from pathlib import Path
import shutil

INFLUX_URL = "http://192.168.1.17:18086"
INFLUX_TOKEN = "WYZywK9uhHLCroKYeWi__7cP5ErKcwm0LxFrvmMwPygBMghnJYIayh5gTV7B--OUPEI5cWerverjnSxdbGieXA=="
INFLUX_ORG = "kleinorg"
INFLUX_BUCKET = "homeassistant-live"

client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
query_api = client.query_api()

query = """
from(bucket: "homeassistant-live")
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