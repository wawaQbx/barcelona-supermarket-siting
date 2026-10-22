"""Food shops OUTSIDE the city for the walking-access model (edge effect of build_food_access.py).
The 2024 commercial census covers Barcelona only, so residents of edge sections could not reach a market, greengrocer or independent supermarket
just across the municipal boundary. This script takes them from OpenStreetMap (Overpass) in the same widened box as fetch_ring_osm.py.
Writes data_catalog/03_commercial_census/osm_ring/osm_food_shops_box.csv: one row per OSM object with its food category.
build_food_access.py uses only the rows OUTSIDE the city (inside the city the census is complete and better).
Completeness of OSM is checked inside the city against the census (printed and documented in PROJECT_REPORT).
"""
import csv, sys, time
from pathlib import Path
import requests

BOX = (41.302, 2.026, 41.488, 2.254)                   # south, west, north, east (same as fetch_ring_osm.py)
q = ('[out:json][timeout:180];('
     f'nwr["shop"~"^(greengrocer|butcher|seafood|poultry|supermarket|convenience)$"]({",".join(map(str, BOX))});'
     f'nwr["amenity"="marketplace"]({",".join(map(str, BOX))});'
     ');out center tags;')
H = {"User-Agent": "Supermarket_BCN research (academic, one-off query)", "Accept": "application/json"}
els = None
for attempt in range(3):
    for url in ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]:
        try:
            r = requests.post(url, data={"data": q}, headers=H, timeout=240); print(url, r.status_code)
            if r.status_code == 200: els = r.json()["elements"]; break
        except Exception as e: print(url, repr(e)[:100])
    if els is not None: break
    time.sleep(30)
if els is None: sys.exit("Overpass unavailable")

CAT = {"greengrocer": "greengrocer", "butcher": "butcher", "seafood": "fishmonger", "poultry": "poultry_eggs",
       "supermarket": "supermarket", "convenience": "convenience"}
rows = []
for e in els:
    t = e.get("tags", {})
    lat = e.get("lat") or e.get("center", {}).get("lat"); lon = e.get("lon") or e.get("center", {}).get("lon")
    if lat is None: continue
    cat = "market" if t.get("amenity") == "marketplace" else CAT.get(t.get("shop"))
    if cat is None: continue
    rows.append(dict(osm_id=f'{e["type"]}/{e["id"]}', food_category=cat, nom=t.get("name", ""), ensenya=t.get("brand", ""),
                     lat=lat, lon=lon, opening_hours=t.get("opening_hours", "")))
out = Path(__file__).parent / "data_catalog" / "03_commercial_census" / "osm_ring" / "osm_food_shops_box.csv"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
import collections
print(len(rows), "food shops in the box:", dict(collections.Counter(r["food_category"] for r in rows)))
