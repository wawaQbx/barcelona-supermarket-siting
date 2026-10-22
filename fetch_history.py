"""Download historical section-level data from Open Data BCN (for time-ordered models, i.e. predictors measured BEFORE the openings).
Writes long tables (original Open Data column names; harmonised by clean_catalog.py) to
data_catalog/02_demand_population_income_housing/{demographics,income}/history/:
  padro_population_history.csv   population per census section, 1 January 2007-2026      (dataset pad_mdbas)
  padro_age5_2015.csv            five-year age groups per section, 2015-01-01              (pad_mdbas_edat-q)   cells < 5 withheld ('..')
  padro_education_2015.csv       education level x sex per section, 2015-01-01             (pad_mdbas_niv-educa-esta_sexe)
  income_history.csv             disposable income per person per section, 2015-2023        (renda-disponible-llars-bcn)
  padro_nationality_2015_2026.csv  population by nationality group (1 Spain, 2 rest of EU, 3 rest of world, 4 not available) x sex
                                 per section, 2015-01-01 and 2026-01-01 (pad_mdbas_nacionalitat-g_sexe)   cells < 5 withheld ('..')
"""
import io, time
from pathlib import Path
import pandas as pd, requests

B = "https://opendata-ajuntament.barcelona.cat/data/api/3/action/"
ROOT = Path(__file__).parent / "data_catalog" / "02_demand_population_income_housing"
DEM, INC = ROOT / "demographics" / "history", ROOT / "income" / "history"
for d in (DEM, INC): d.mkdir(parents=True, exist_ok=True)

def resources(pkg):
    for i in range(5):
        try: return requests.get(B + "package_show", params={"id": pkg}, timeout=120).json()["result"]["resources"]
        except Exception: time.sleep(5)
    raise RuntimeError(pkg)

def csv(url):
    for i in range(5):
        try: return pd.read_csv(io.BytesIO(requests.get(url, timeout=300).content), encoding="utf-8-sig", dtype=str)
        except Exception: time.sleep(5)
    raise RuntimeError(url)

def grab(pkg, years, out, folder):
    res = {r["name"][:4]: r["url"] for r in resources(pkg) if r["name"].endswith(".csv")}
    parts = []
    for y in years:
        d = csv(res[str(y)]); parts.append(d); print(pkg, y, d.shape)
    df = pd.concat(parts, ignore_index=True); df.to_csv(folder / out, index=False, encoding="utf-8"); print("->", out, df.shape)

grab("pad_mdbas", range(2007, 2027), "padro_population_history.csv", DEM)
grab("pad_mdbas_edat-q", [2015], "padro_age5_2015.csv", DEM)
grab("pad_mdbas_niv-educa-esta_sexe", [2015], "padro_education_2015.csv", DEM)
grab("renda-disponible-llars-bcn", range(2015, 2024), "income_history.csv", INC)
grab("pad_mdbas_nacionalitat-g_sexe", [2015, 2026], "padro_nationality_2015_2026.csv", DEM)
