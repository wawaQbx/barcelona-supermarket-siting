"""Why do supermarkets not open in the food-desert areas? Compares the catchment of every existing city store (400 m radius: residents, spending power,
terrain relief, vacant premises, large buildings with shops, distance to the nearest other chain store) with the same profile around the
dwelling-weighted centre of the flagged sections (low-income food desert, strict-definition food desert, older / car-less far from fresh food:
the same sections as the dashboard page-04 table). Run after build_food_access.py.
Output: docs/food_desert_viability.csv and ana.py_food_desert_viability -> dbt gis.food_desert_viability (dashboard page 04).
"""
import sys; sys.path.insert(0, ".")
import analyze_siting as A, numpy as np, pandas as pd
from scipy.spatial import cKDTree
pd.set_option("display.width", 250)
bld = A.load("select b.dwellings_n, b.footprint_area_m2, b.current_use, b.year_of_construction, st_x(st_centroid(b.geom)) x, st_y(st_centroid(b.geom)) y, f.elevation_m, f.seccio_censal from raw.cad_inspire_buildings b left join ana.py_building_food_access f using (referencia_cadastral)")
sec = A.load("select seccio_censal, codi_barri, disposable_income_eur_per_person inc, population_n, d.dw as dw_sec from ana.section_model_table s left join (select seccio_censal, sum(dwellings_n) dw from ana.py_building_food_access group by 1) d using (seccio_censal)")
sec["persons_per_dwelling"] = sec.population_n / sec.dw_sec
bld = bld.merge(sec[["seccio_censal", "inc", "persons_per_dwelling"]], on="seccio_censal", how="left")
bld["residents"] = bld.dwellings_n * bld.persons_per_dwelling.fillna(2.4); bld["spend"] = bld.residents * bld.inc.fillna(22000)
H = bld[bld.dwellings_n > 0].reset_index(drop=True); th = cKDTree(H[["x", "y"]])
cen = A.load("select nom_principal_activitat a, nom_sector_activitat s, st_x(g) x, st_y(g) y from (select *, st_transform(st_setsrid(st_makepoint(lon,lat),4326),25831) g from raw.cen_census_2024 where lon is not null) q")
vac = cen[cen.s.str.startswith("Locals buits", na=False)].reset_index(drop=True); tv = cKDTree(vac[["x", "y"]])
cb = bld[bld.footprint_area_m2 >= 800].reset_index(drop=True); tb = cKDTree(cb[["x", "y"]])                 # buildings large enough for a ~700 m2+ supermarket floor
cen_xy = cKDTree(cen[["x", "y"]]); big_with_shops = cb[[len(cen_xy.query_ball_point(p, 15)) > 0 for p in cb[["x", "y"]].to_numpy()]].reset_index(drop=True); tbs = cKDTree(big_with_shops[["x", "y"]])
st = A.load("select brand_group, st_x(geom) x, st_y(geom) y from ana.store_points"); ts = cKDTree(st[["x", "y"]])
def profile(P):
    out = []
    for x, y in P:
        i = th.query_ball_point((x, y), 400); h = H.iloc[i]
        e = h.elevation_m.dropna()
        out.append(dict(residents_400m=h.residents.sum(), spending_400m_meur=h.spend.sum() / 1e6, income_400m=(h.spend.sum() / max(h.residents.sum(), 1)),
                        elev_range_400m=(e.quantile(.9) - e.quantile(.1)) if len(e) else np.nan,
                        vacant_premises_400m=len(tv.query_ball_point((x, y), 400)), big_buildings_with_shops_400m=len(tbs.query_ball_point((x, y), 400)),
                        nearest_chain_store_m=ts.query((x, y))[0] if True else np.nan))
    return pd.DataFrame(out)
ref = profile(st[st.x.notna()].merge(A.load("select st_x(geom) x, st_y(geom) y, in_city from ana.store_points"), on=["x", "y"]).query("in_city")[["x", "y"]].to_numpy())
ref["nearest_chain_store_m"] = [ts.query((x, y), k=2)[0][1] for x, y in st.merge(A.load("select st_x(geom) x, st_y(geom) y, in_city from ana.store_points"), on=["x", "y"]).query("in_city")[["x", "y"]].to_numpy()]
flag = A.load("""select f.seccio_censal, n.nom_barri from ana.py_section_food_access f join ana.section_model_table m using (seccio_censal)
                 join ana.dim_neighborhood n on n.codi_barri = m.codi_barri
                 where f.food_desert_low_income or f.food_desert_low_income_strict or f.vulnerable_low_access order by 1""")
focus = {f"{r.nom_barri} ({r.seccio_censal})": int(r.seccio_censal) for r in flag.itertuples()}
pts = []
for name, s in focus.items():
    h = H[H.seccio_censal == s]; w = h.dwellings_n; pts.append((float(np.average(h.x, weights=w)), float(np.average(h.y, weights=w))))
F = profile(pts); F.index = list(focus)
q = ref.quantile([.1, .25, .5]).T; q.columns = ["existing stores p10", "p25", "median"]
print(q.round(1).to_string()); print(F.round(1).to_string())
print("\nshare of existing city stores with fewer residents within 400 m than each focus area:")
for n in F.index: print(f"  {n:28s} residents {100 * (ref.residents_400m < F.loc[n, 'residents_400m']).mean():4.0f}%   spending {100 * (ref.spending_400m_meur < F.loc[n, 'spending_400m_meur']).mean():4.0f}%")

out = pd.concat([q.T.rename(index=lambda s: "EXISTING STORES " + s), F])
out.round(1).to_csv(A.ROOT / "docs" / "food_desert_viability.csv")

# database copy for the dashboard: one row per flagged section, with the reference distribution of the existing city stores as columns
from sqlalchemy import create_engine
D = F.rename(columns={"income_400m": "income_400m_eur_per_person", "elev_range_400m": "elev_range_400m_m", "residents_400m": "residents_400m_n",
                      "vacant_premises_400m": "vacant_premises_400m_n", "big_buildings_with_shops_400m": "big_buildings_with_shops_400m_n"}).round(1)
D.insert(0, "seccio_censal", list(focus.values()))
D["share_existing_stores_fewer_residents_pct"] = [round(100 * (ref.residents_400m < v).mean(), 1) for v in F.residents_400m]
for k, qq in (("p10", .1), ("p25", .25), ("median", .5)): D[f"existing_stores_residents_400m_{k}"] = round(ref.residents_400m.quantile(qq), 0)
eng = create_engine("postgresql+psycopg://postgres@localhost:5432/supermarket_bcn")   # password from pgpass.conf
D.to_sql("py_food_desert_viability", eng, schema="ana", if_exists="replace", index=False)
with eng.begin() as c:
    c.exec_driver_sql("COMMENT ON TABLE ana.py_food_desert_viability IS 'Catchment within 400 m of the flagged food-access sections (dwelling-weighted centre) vs the distribution over the existing city chain stores. Built by food_desert_viability.py'")
import subprocess
DBT = A.ROOT / "dbt_bcn"
r = subprocess.run(["cmd", "/c", str(DBT / "dbt.cmd"), "build", "--select", "food_desert_viability"], cwd=DBT, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("gis.food_desert_viability", "OK" if r.returncode == 0 else "FAILED:\n" + r.stdout[-2000:])
