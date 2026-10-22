"""Address check of the store list against the 2024 commercial census, and coordinate corrections.
Why: the census-based validation (dbt model store_list_validation) found ~50 Condis stores with no supermarket near their coordinates; matched by ADDRESS
(street + door number), most of them are real Condis stores whose locator coordinates are ~150 m off.
What it does: for every store of the official list (stores with an address), find census 2024 premises on the same street with a door number within +-2;
if one of them is a supermarket premise carrying the SAME chain name, the census position replaces the store coordinates.
Output: data_catalog/01_stores/store_coordinate_corrections.csv (imported as raw.store_coordinate_corrections, applied in the dbt model int_store_points_base)
        data/store_address_check.csv (every checked store and the result, for inspection).
Run after import_all.py (it reads raw tables), then rebuild so that the corrections are applied.
"""
import re, unicodedata
from pathlib import Path
import numpy as np, pandas as pd, psycopg

ROOT = Path(__file__).parent
CONN = "host=localhost port=5432 dbname=supermarket_bcn user=postgres"
BRAND_RX = {"Condis": r"condis", "Dia": r"^(dia\b|dia %|dia market|supermercados dia)", "Caprabo": r"caprabo", "Mercadona": r"mercadona", "Consum": r"\bconsum\b",
            "Charter": r"charter", "Bon Preu": r"bon ?preu", "Esclat": r"esclat", "Lidl": r"\blidl", "Aldi": r"\baldi\b", "Alcampo": r"alcampo", "Mi Alcampo": r"alcampo",
            "Carrefour": r"carrefour", "Carrefour Express": r"carrefour", "Carrefour Market": r"carrefour"}

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()
    s = re.sub(r"^(c/|c\.|calle|carrer|avda\.?|av\.?|avinguda|pza\.?|pl\.?|placa|plaza|pg\.?|passeig|paseo|ronda|rbla\.?|rambla|ctra\.?|carretera|travessera|trav\.?|pi\.?|pje\.?|ptge\.?)\s*", "", s)
    s = re.sub(r"\b(de|del|dels|la|les|el|els|l|d|i)\b", " ", re.sub(r"[^a-z0-9 ]", " ", s))
    return " ".join(s.split())

with psycopg.connect(CONN) as c:
    st = pd.read_sql("select ensenya, nom, adreca, lat, lon, st_x(st_transform(st_setsrid(st_makepoint(lon, lat), 4326), 25831)) x, "
                     "st_y(st_transform(st_setsrid(st_makepoint(lon, lat), 4326), 25831)) y from raw.store_supermarkets_official where codi_barri is not null", c)
    ce = pd.read_sql("select nom_local, nom_activitat, nom_via, num_policia_inicial, num_policia_final, lat, lon, "
                     "st_x(st_transform(st_setsrid(st_makepoint(lon, lat), 4326), 25831)) x, st_y(st_transform(st_setsrid(st_makepoint(lon, lat), 4326), 25831)) y "
                     "from raw.cen_census_2024 where lon is not null", c)
ce["via"] = ce.nom_via.map(norm); ce["n1"] = pd.to_numeric(ce.num_policia_inicial, errors="coerce"); ce["n2"] = pd.to_numeric(ce.num_policia_final, errors="coerce").fillna(ce.n1)
byvia = {k: g for k, g in ce.groupby("via")}
rows = []
for r in st.itertuples():
    base = dict(ensenya=r.ensenya, nom=r.nom, adreca=r.adreca, lat=r.lat, lon=r.lon)
    m = re.match(r"\s*([^,]+),\s*(\d+)", r.adreca) if isinstance(r.adreca, str) else None
    if not m: rows.append({**base, "result": "no usable address"}); continue
    via, num = norm(m.group(1)), int(m.group(2)); g = byvia.get(via)
    if g is None:
        # partial street names only when the shorter one is a long, whole-word part (2026-10-16: "emilia llorca martin" had matched "marti", 4 km away)
        cand = [k for k in byvia if min(len(k), len(via)) >= 8 and (re.search(r"" + re.escape(k) + r"", via) or re.search(r"" + re.escape(via) + r"", k))]
        g = pd.concat([byvia[k] for k in cand]) if cand else None
    if g is None: rows.append({**base, "result": "street not found"}); continue
    h = g[(g.n1 - 2 <= num) & (num <= g.n2 + 2)]
    rx = BRAND_RX.get(r.ensenya, "$^")
    same = h[(h.nom_activitat == "Autoservei / Supermercat") & h.nom_local.astype(str).str.lower().str.contains(rx, regex=True)]
    sup = h[h.nom_activitat == "Autoservei / Supermercat"]
    best = same if len(same) else (sup if len(sup) else h)
    if len(best) == 0: rows.append({**base, "result": "no premise at this door number"}); continue
    b = best.iloc[int(np.argmin(np.hypot(best.x - r.x, best.y - r.y)))]
    res = "same chain at the address" if len(same) else ("other supermarket at the address" if len(sup) else "other premise at the address")
    rows.append({**base, "result": res, "name_at_address": b.nom_local, "activity_at_address": b.nom_activitat,
                 "census_lat": b.lat, "census_lon": b.lon, "coord_offset_m": round(float(np.hypot(b.x - r.x, b.y - r.y)), 1)})
R = pd.DataFrame(rows); R.to_csv(ROOT / "data" / "store_address_check.csv", index=False)
MAX_OFFSET_M = 1000   # a locator is ~100-500 m off at most; a larger "correction" means the address matched another street
fix = R[(R.result == "same chain at the address") & (R.coord_offset_m > 30) & (R.coord_offset_m <= MAX_OFFSET_M)][["ensenya", "nom", "adreca", "lat", "lon", "census_lat", "census_lon", "coord_offset_m"]]
fix.to_csv(ROOT / "data_catalog" / "01_stores" / "store_coordinate_corrections.csv", index=False)
print(R.groupby(["ensenya", "result"]).size().unstack(fill_value=0).to_string())
print("coordinate corrections (same chain at the address, offset > 30 m):", len(fix), "| median offset", fix.coord_offset_m.median(), "m")
print(fix.groupby("ensenya").size().to_string())
