"""Open Data BCN downloads for v6:
  carrers-pacificats-bici-bcn   pacified streets ("eixos verds", COVID tactical urbanism), quarterly 2020-3T ... 2022-2T  -> natural experiment
  carrers-plataforma-unica-bcn  single-platform streets with pedestrian priority (current layer + quarterly 2023-2026)    -> walkability
  locve-evolucio                asking prices of commercial premises per barri, 2008-2011                                  -> only open premises price series
Files go to data_catalog/04_transport_traffic/streets/ and data_catalog/02_demand_population_income_housing/housing/.
"""
import time
from pathlib import Path
import requests

A = "https://opendata-ajuntament.barcelona.cat/data/api/3/action/package_show"
ROOT = Path(__file__).parent / "data_catalog"
ST = ROOT / "04_transport_traffic" / "streets"; ST.mkdir(parents=True, exist_ok=True)
HO = ROOT / "02_demand_population_income_housing" / "housing"

def res(pkg):
    for i in range(5):
        try: return requests.get(A, params={"id": pkg}, timeout=120).json()["result"]["resources"]
        except Exception: time.sleep(5)

def save(url, dst):
    for i in range(5):
        try:
            r = requests.get(url, timeout=300); r.raise_for_status(); dst.write_bytes(r.content); print(dst.name, len(r.content)); return
        except Exception: time.sleep(5)
    raise RuntimeError(url)

for x in res("carrers-pacificats-bici-bcn"):
    save(x["url"], ST / ("pacified_" + x["name"].lower()))
for x in res("carrers-plataforma-unica-bcn"):
    if x["name"].endswith(".zip"): save(x["url"], ST / ("pedestrian_priority_" + x["name"].lower()))
for x in res("locve-evolucio"):
    save(x["url"], HO / "locve_evolucio.csv")

# tidy the premises price table: wide years -> long; "2.176" uses the Catalan thousands separator -> 2176 EUR per m2; "--" = not available
import pandas as pd, re, shutil
raw = Path(__file__).parent / "data" / "raw" / "locve_evolucio_raw.csv"
if (HO / "locve_evolucio.csv").exists(): shutil.move(HO / "locve_evolucio.csv", raw)
d = pd.read_csv(raw, encoding="utf-8-sig", dtype=str)
yr = {"DOSZEROONZE": 2011, "DOSZERODEU": 2010, "DOSZEROZERONOU": 2009, "DOSZEROZEROVUIT": 2008}
long = d.melt(id_vars=["DTE", "BARRIS"], value_vars=list(yr), var_name="y", value_name="v")
long["Any"] = long.y.map(yr); long["Codi_Districte"] = long.DTE.astype(int)
long["Codi_Barri"] = long.BARRIS.str.extract(r"^\s*(\d+)\.")[0].astype(int)
long["Preu_Oferta_Local_EUR_m2"] = pd.to_numeric(long.v.str.replace(".", "", regex=False).replace("--", None), errors="coerce")
long[["Any", "Codi_Districte", "Codi_Barri", "Preu_Oferta_Local_EUR_m2"]].to_csv(HO / "locve_preu_oferta_locals_2008_2011.csv", index=False)
print("tidy premises prices", len(long), long.Preu_Oferta_Local_EUR_m2.describe().round(0).to_dict())

# stack the quarterly street layers into two GeoPackages (one row per street segment and quarter) for import_all.py
import geopandas as gpd
for prefix, out in (("pacified_", "streets_pacified_2020_2022.gpkg"), ("pedestrian_priority_", "streets_pedestrian_priority_2023_2026.gpkg")):
    parts = []
    for z in sorted(ST.glob(prefix + "*.zip")):
        g = gpd.read_file("zip://" + str(z).replace("\\", "/"))
        m = re.search(r"(\d{4})_(\d)t", z.name)
        g["any_"] = int(m.group(1)) if m else None; g["trimestre"] = int(m.group(2)) if m else None   # None = the current (undated) layer
        g["layer_file"] = z.name; parts.append(g[["any_", "trimestre", "layer_file", "ID", "TOOLTIP", "geometry"]])
    allg = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs).rename(columns={"ID": "id_segment", "TOOLTIP": "tipus"})
    allg.to_file(ST / out, driver="GPKG"); print(out, len(allg), allg.groupby(["any_", "trimestre"], dropna=False).size().to_dict())
