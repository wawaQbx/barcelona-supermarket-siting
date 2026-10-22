"""Official store locators for the chains whose store list came from OpenStreetMap (store list audit, 2026-10-16).
OSM lagged behind openings and closures (e.g. the Mercadona of the Mercat del Poblenou, closed March 2024, was still listed, and the Aldi that
replaced it in December 2024 was missing). Two chains publish their full store list in a machine-readable form:
  Mercadona : https://storage.googleapis.com/pro-bucket-wcorp-files/json/data.js  (all Spanish stores; fields lt / lg / dr / cp / lc / fap = opening date)
  Aldi      : https://www.aldi.es/encuentra-tu-supermercado.html                   (store finder page; every store embedded in __NEXT_DATA__)
Lidl and Carrefour sit behind bot protection (not bypassed) and Caprabo has no public locator data: for them the list stays OSM + the 2024
commercial census supplement, checked against the current OSM (docs/WORK_LOG.md).
Output: data_catalog/01_stores/official_locators/store_official_locators.csv (stores within the widened Barcelona box, same as the ring scripts).
dbt (ana.store_points) uses it to DROP listed Mercadona / Aldi stores that no longer exist and ADD the ones missing (city + 2 km ring).
"""
import csv, json, re, sys
from datetime import date
from pathlib import Path
import requests

BOX = (41.302, 2.026, 41.488, 2.254)                   # south, west, north, east (same as fetch_ring_osm.py)
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Supermarket_BCN research (academic, one-off)"}
OUT = Path(__file__).parent / "data_catalog" / "01_stores" / "official_locators" / "store_official_locators.csv"
in_box = lambda lat, lon: BOX[0] <= lat <= BOX[2] and BOX[1] <= lon <= BOX[3]
rows, today = [], date.today().isoformat()

# Mercadona: one JS file, "var dataJson = {...}"
t = requests.get("https://storage.googleapis.com/pro-bucket-wcorp-files/json/data.js", headers=H, timeout=60).content.decode("utf-8")
j = json.loads(t[t.index("{"): t.rindex("}") + 1])
for x in j["tiendasFull"]:
    if in_box(x["lt"], x["lg"]):
        d = x.get("fap") or ""
        rows.append(dict(ensenya="Mercadona", store_code=str(x["id"]), lat=x["lt"], lon=x["lg"], municipi=x["lc"], adreca=x["dr"].title(), codi_postal=x["cp"],
                         opening_date="-".join(reversed(d.split("/"))) if d else "", locator_date=today))
n_merc = len(rows)

# Aldi: the store finder page embeds every store as escaped JSON; the field order varies, so read each field separately
html = requests.get("https://www.aldi.es/encuentra-tu-supermercado.html", headers=H, timeout=60).content.decode("utf-8").replace('\\"', '"')
def field(seg, k):
    m = re.search(r'"' + k + r'":("([^"]*)"|[-\d.]+|null)', seg)
    return (m.group(2) if m.group(2) is not None else m.group(1)) if m else ""
for part in html.split('"identifier":"')[1:]:
    seg = part.split('"openingHours"')[0]
    lat, lon = float(field(seg, "lat") or 0), float(field(seg, "lng") or 0)
    if in_box(lat, lon):
        rows.append(dict(ensenya="Aldi", store_code=part[:8], lat=lat, lon=lon, municipi=field(seg, "city"), adreca=field(seg, "streetAndNumber"),
                         codi_postal=field(seg, "zip"), opening_date="", locator_date=today))
if n_merc < 50 or len(rows) - n_merc < 20: sys.exit(f"locator parse looks wrong (Mercadona {n_merc}, Aldi {len(rows) - n_merc})")
rows = list({(r["ensenya"], r["store_code"]): r for r in rows}.values())   # a store can appear twice in the Aldi page
OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(len(rows), "locator stores in the box:", {k: sum(r["ensenya"] == k for r in rows) for k in ("Mercadona", "Aldi")},
      "| Barcelona city:", {k: sum(r["ensenya"] == k and r["municipi"] == "Barcelona" for r in rows) for k in ("Mercadona", "Aldi")})
