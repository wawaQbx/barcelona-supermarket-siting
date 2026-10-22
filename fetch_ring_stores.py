"""Stores in the ring AROUND Barcelona (edge-effect completion): re-runs the chain scrapers of scraper.py with a bounding box widened by ~2 km
(1 km is enough for supermarkets, 2 km is used for hypermarkets), plus OpenStreetMap for the chains without an official locator.
Dia is skipped (its site returns 403). Output: data_catalog/01_stores/ring_stores_2km.csv (brand, name, address, lat, lon, store_type, source).
Stores already in barcelona_supermarkets_official.csv are kept too; the dbt model int_store_points_base adds only those not within 100 m of a listed store of the same chain.
"""
import csv, logging, sys
from dataclasses import asdict
from pathlib import Path
import scraper as S

logging.basicConfig(level=logging.INFO, format="%(message)s")
S.BCN_BBOX.update(lat_min=41.302, lat_max=41.488, lon_min=2.026, lon_max=2.254)      # city bbox + ~2 km
OUT = Path(__file__).parent / "data_catalog" / "01_stores" / "ring_stores_2km.csv"
jobs = [("Condis", S.scrape_condis), ("Bon Preu / Esclat", S.scrape_bonpreu), ("Consum / Charter", S.scrape_consum), ("Alcampo", S.scrape_alcampo),
        ("OSM", lambda: S.scrape_osm_bcn(["Mercadona", "Caprabo", "Lidl", "Aldi", "Carrefour", "Carrefour Express", "Carrefour Market", "Dia", "Alcampo", "Mi Alcampo"]))]
only = set(sys.argv[1:])
rows = []
for name, fn in jobs:
    if only and name not in only: continue
    try:
        res = fn(); print(f"{name}: {len(res)} stores in the widened box"); rows += [asdict(s) for s in res]
    except Exception as e:
        print(f"{name}: FAILED {e!r}")
rows = [r for r in rows if r.get("lat") and r.get("lon") and S.in_bcn(r["lat"], r["lon"])]
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["brand", "name", "address", "lat", "lon", "store_type", "source"], extrasaction="ignore"); w.writeheader(); w.writerows(rows)
print("written", OUT, len(rows))
