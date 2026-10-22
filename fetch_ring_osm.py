"""Ring stores from OpenStreetMap (Overpass) for the chains without an official locator, appended to data_catalog/01_stores/ring_stores_2km.csv.
Run after fetch_ring_stores.py (its own OSM step often times out). Uses a mirror when overpass-api.de is busy."""
import requests, time, csv, re, collections, sys
q = '[out:json][timeout:120];(nwr["shop"~"supermarket|convenience"](41.302,2.026,41.488,2.254););out center tags;'
H = {"User-Agent": "Supermarket_BCN research (academic, one-off query)", "Accept": "application/json"}
els = None
for attempt in range(3):
    for url in ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]:
        try:
            r = requests.post(url, data={"data": q}, headers=H, timeout=200); print(url, r.status_code)
            if r.status_code == 200: els = r.json()["elements"]; break
        except Exception as e: print(url, repr(e)[:100])
    if els is not None: break
    time.sleep(30)
if els is None: sys.exit("Overpass unavailable")
BR = [("Mercadona", r"mercadona"), ("Caprabo", r"caprabo"), ("Lidl", r"\blidl"), ("Aldi", r"\baldi\b"), ("Carrefour Express", r"carrefour express"),
      ("Carrefour Market", r"carrefour market"), ("Carrefour", r"carrefour"), ("Dia", r"^(dia|supermercados dia|dia market)\b")]
rows = []
for e in els:
    t = e.get("tags", {}); name = (t.get("brand") or t.get("name") or "").strip()
    lat = e.get("lat") or e.get("center", {}).get("lat"); lon = e.get("lon") or e.get("center", {}).get("lon")
    for b, rx in BR:
        if re.search(rx, name.lower()):
            rows.append(dict(brand=b, name=t.get("name", ""), address=" ".join(filter(None, [t.get("addr:street"), t.get("addr:housenumber"), t.get("addr:city")])),
                             lat=lat, lon=lon, store_type="convenience" if t.get("shop") == "convenience" else "supermarket", source="OSM Overpass (ring)")); break
print("OSM chain shops in the widened box:", len(rows), collections.Counter(r["brand"] for r in rows))
with open("data_catalog/01_stores/ring_stores_2km.csv", "a", newline="", encoding="utf-8") as f:
    csv.DictWriter(f, fieldnames=["brand", "name", "address", "lat", "lon", "store_type", "source"]).writerows(rows)
