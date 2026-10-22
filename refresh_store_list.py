"""Refresh the official store list (data_catalog/01_stores/barcelona_supermarkets_official.csv) for the chains whose locators still answer
(store list audit, 2026-10-16). Re-scrapes Condis, Consum / Charter and Bon Preu / Esclat with scraper.py and compares by ADDRESS (the Condis locator
coordinates are ~150-250 m off, so a distance match would report false changes; they are corrected later by check_store_addresses.py):
  unchanged address -> the existing row is kept as it is;  new address -> row added (municipi from the address, barri / district by spatial join);
  address gone      -> row dropped (closed).
Not refreshed: Dia (dia.es answers 403 since 2026-10, not bypassed), Alcampo (locator needs Selenium, hangs), and the OSM-sourced chains (Mercadona
and Aldi come from fetch_official_locators.py; Lidl, Carrefour, Caprabo stay OSM + census supplement).
The previous list is archived in data_catalog/01_stores/unused_downloads/ (skipped by clean_catalog). Run before clean_catalog.py.
"""
import re, shutil, unicodedata
from datetime import date
from pathlib import Path
import pandas as pd, psycopg
import scraper as S

ROOT = Path(__file__).parent
LIST = ROOT / "data_catalog" / "01_stores" / "barcelona_supermarkets_official.csv"
CONN = "host=localhost port=5432 dbname=supermarket_bcn user=postgres"
CHAINS = [("Condis", S.scrape_condis, ["Condis"], "Condis Group"), ("Consum", S.scrape_consum, ["Consum", "Charter"], "Consum Group"),
          ("Bon Preu", S.scrape_bonpreu, ["Bon Preu", "Esclat"], "Bon Preu Group")]

def key(a):   # street + door number + postcode, accents / punctuation removed
    a = unicodedata.normalize("NFKD", str(a)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", a.split(",")[0] + "".join(re.findall(r"\b\d+\b", a)[:1]) + (re.findall(r"\b\d{5}\b", a) or [""])[0])

old = pd.read_csv(LIST, dtype={"codi_barri": "Int64", "codi_districte": "Int64"})
arch = LIST.parent / "unused_downloads"; arch.mkdir(exist_ok=True)
shutil.copy2(LIST, arch / f"barcelona_supermarkets_official_before_{date.today().isoformat()}.csv")
keep, added = [old[~old.brand.isin(sum([c[2] for c in CHAINS], []))]], []
for name, fn, brands, group in CHAINS:
    new = pd.DataFrame([s.__dict__ for s in fn()])
    if len(new) < 0.8 * old.brand.isin(brands).sum(): raise SystemExit(f"{name}: only {len(new)} stores scraped, list not refreshed")
    o = old[old.brand.isin(brands)]; ok, nk = set(o.address.map(key)), set(new.address.map(key))
    keep.append(o[o.address.map(key).isin(nk)])
    a = new[~new.address.map(key).isin(ok)].assign(group=group)
    added.append(a)
    print(f"{name}: kept {o.address.map(key).isin(nk).sum()}, closed {(~o.address.map(key).isin(nk)).sum()}, new {len(a)}")
    for r in o[~o.address.map(key).isin(nk)].itertuples(): print("   - ", r.address)
    for r in a.itertuples(): print("   + ", r.address)
A = pd.concat(added, ignore_index=True)
if len(A):
    A["municipi"] = A.address.str.split(",").str[-1].str.strip().str.title().replace({"Barcelona": "Barcelona"})
    with psycopg.connect(CONN) as c:
        b = [c.execute("""select u.codi_barri, n.nom_barri, n.codi_districte from raw.adm_units_polygons u join ana.dim_neighborhood n using (codi_barri)
                          where u.tipus_ua = 'SEC_CENS' and st_intersects(u.geom, st_transform(st_setsrid(st_makepoint(%s, %s), 4326), 25831))""", (r.lon, r.lat)).fetchone()
             for r in A.itertuples()]
    A["codi_barri"] = [x[0] if x else None for x in b]; A["barri"] = [x[1] if x else None for x in b]; A["codi_districte"] = [x[2] if x else None for x in b]
out = pd.concat(keep + [A[old.columns]] if len(A) else keep, ignore_index=True)
out.to_csv(LIST, index=False, encoding="utf-8")
print("store list:", len(old), "->", len(out), "rows")
