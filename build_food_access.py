"""Walking access to food shops, with SLOPE (food-desert map). Run after import_all.py.
Origins  : every residential cadastral building with dwellings (raw.cad_inspire_buildings, centroid), weighted by its dwellings.
Network  : OSM roads (raw.trf_osm_roads) without motorways / trunk roads, undirected graph of consecutive vertices.
Slope    : Copernicus GLO-30 (data_catalog/05_built_environment_planning/terrain). It is a surface model, so in dense blocks it partly contains roofs
           (and bridges, the hill above tunnels); the slope of an edge is capped at 30% (MAX_SLOPE) against such false slopes:
           a 3 x 3 minimum filter (~90 m) approximates street level, then a 3 x 3 mean filter smooths it.
           Walking time per edge = Tobler's hiking function, speed = 6 * exp(-3.5 * |slope + 0.05|) km/h (5 km/h on the flat), averaged over both
           directions (a shopping trip goes and comes back). Older people: 70% of that speed (about 3.5 km/h on the flat).
Targets  : (1) chain supermarkets in ana.store_points incl. stores outside the city, (2) any supermarket-class premise of the 2024 census (independents,
           convenience), (3) municipal markets (2024 premises with sn_mercat), (4) fresh food = (1) + (3) + greengrocers, butchers, fishmongers, poultry shops (2024 census);
           convenience stores and independent mini-markets are NOT fresh food (cf. Baro de Viver: 3 convenience stores, no fresh produce). Dijkstra from all targets of a type at once.
           THREE DEFINITIONS of fresh food (results are reported as main value + range):
             fresh (MAIN, middle)  = strict + supermarket-class premises of the regional chains that sell fresh food (Ametller Origen, BonArea, Coaliment,
                                     Veritas, Coviran, Spar, Suma, Sorli, Supercor ...) and supermarket-class premises named as fruit / vegetable / meat / fish shops
             fresh_strict          = chain supermarkets (10 chains) + markets + greengrocers, butchers, fishmongers, poultry shops
             fresh_broad           = strict + every supermarket-class premise (independent mini-markets and 24 h shops included)
Output   : ana.py_building_food_access (one row per residential building) and ana.py_section_food_access (per census section).
Edge     : the census covers Barcelona only, so targets (2)-(4) OUTSIDE the city come from OpenStreetMap (fetch_ring_food_osm.py, box ~2 km around the city).
           OSM completeness checked inside the city against the census: markets 95%, supermarkets / convenience 61%, fresh shops only 23-33% (gis.osm_completeness) -> outside the
           city fresh food is a LOWER bound. Sections on the city edge with OSM food shops across the boundary are flagged edge_outside_food_uncertain.
Limits   : the OSM extract has few footpaths and no stairs, the terrain is approximate.
"""
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, networkx as nx, psycopg, rasterio
from rasterio.warp import transform as rtransform
from scipy.ndimage import minimum_filter, uniform_filter
from scipy.spatial import cKDTree
from sqlalchemy import create_engine
from sqlalchemy.types import Integer

ROOT = Path(__file__).parent
CONN = "host=localhost port=5432 dbname=supermarket_bcn user=postgres"
eng = create_engine("postgresql+psycopg://postgres@localhost:5432/supermarket_bcn")
DEM = ROOT / "data_catalog" / "05_built_environment_planning" / "terrain" / "Copernicus_DSM_COG_10_N41_00_E002_00_DEM.tif"
OLDER_SPEED = 0.7

# ---------- network with elevation ----------
roads = gpd.read_postgis("select highway, geom from raw.trf_osm_roads where highway !~ '^(motorway|trunk)'", eng, geom_col="geom")
edges = []
for geom in roads.geometry:
    for line in getattr(geom, "geoms", [geom]):
        c = np.round(np.asarray(line.coords)[:, :2], 1)
        for a, b in zip(c[:-1], c[1:]):
            d = float(np.hypot(*(b - a)))
            if d > 0: edges.append((tuple(a), tuple(b), d))
G = nx.Graph(); G.add_weighted_edges_from(edges, weight="len")
G = G.subgraph(max(nx.connected_components(G), key=len)).copy()
nodes = np.array(G.nodes()); idx = {tuple(n): i for i, n in enumerate(nodes)}; tree = cKDTree(nodes)

with rasterio.open(DEM) as src:
    win = rasterio.windows.from_bounds(2.0, 41.25, 2.35, 41.55, src.transform)
    z = src.read(1, window=win).astype(float); tr = src.window_transform(win)
z = uniform_filter(minimum_filter(z, size=3), size=3)                         # roofs out, then smooth
lon, lat = rtransform("EPSG:25831", "EPSG:4326", nodes[:, 0].tolist(), nodes[:, 1].tolist())
col = ((np.array(lon) - tr.c) / tr.a).astype(int); row = ((np.array(lat) - tr.f) / tr.e).astype(int)
elev = z[row.clip(0, z.shape[0] - 1), col.clip(0, z.shape[1] - 1)]
import os
MAX_SLOPE = float(os.environ.get("BCN_MAX_SLOPE", "0.30"))   # sensitivity runs: set BCN_MAX_SLOPE (e.g. 9 = no cap); the surface model holds roofs, bridges and the hill above tunnels: short edges can show false slopes of 100%+, which made
                   # Tobler's speed collapse (e.g. 128 m on the flat taking 10 min). 30% = about the steepest walkable streets of Barcelona (steeper = stairs).
def tobler_h(dist, dz):                                                       # hours to walk dist metres with height change dz
    s = float(np.clip(dz / max(dist, 1.0), -MAX_SLOPE, MAX_SLOPE)); return dist / 1000 / (6 * np.exp(-3.5 * abs(s + 0.05)))
for a, b, d in G.edges(data="len"):
    dz = elev[idx[b]] - elev[idx[a]]
    G[a][b]["min"] = 60 * (tobler_h(d, dz) + tobler_h(d, -dz)) / 2         # minutes, average of both directions
print("graph", G.number_of_nodes(), "nodes; elevation range", round(float(elev.min())), "-", round(float(elev.max())), "m")
steep = sum(1 for a_, b_, d in G.edges(data="len") if abs(elev[idx[b_]] - elev[idx[a_]]) / max(d, 1.0) > MAX_SLOPE)
print("edges with a slope above", MAX_SLOPE, "(capped):", steep, "of", G.number_of_edges())

# ---------- targets ----------
def pts(sql): return pd.read_sql(sql, eng)[["x", "y"]].to_numpy()
T = {"chain": pts("select st_x(geom) x, st_y(geom) y from ana.store_points"),
     "anysuper": pts("select st_x(g) x, st_y(g) y from (select st_transform(st_setsrid(st_makepoint(lon, lat), 4326), 25831) g from raw.cen_census_2024 "
                     "where lon is not null and nom_principal_activitat = 'Actiu' and nom_activitat = 'Autoservei / Supermercat') q"),
     "market": pts("select st_x(g) x, st_y(g) y from (select st_centroid(st_collect(st_transform(st_setsrid(st_makepoint(lon, lat), 4326), 25831))) g "
                   "from raw.cen_census_2024 where sn_mercat and lon is not null group by nom_mercat) q")}
T["anysuper"] = np.vstack([T["anysuper"], T["chain"]])
T["fresh"] = np.vstack([T["chain"], T["market"], pts("select st_x(g) x, st_y(g) y from (select st_transform(st_setsrid(st_makepoint(lon, lat), 4326), 25831) g from raw.cen_census_2024 "
                     "where lon is not null and nom_principal_activitat = 'Actiu' and nom_activitat in ('Fruites i verdures', 'Carn i Porc', 'Peix i marisc', 'Ous i aus')) q")])
# outside the city: OSM food shops (the census covers the city only)
OSM_OUT = """select food_category, nom, ensenya, st_x(g) x, st_y(g) y from (select food_category, nom, ensenya, st_transform(st_setsrid(st_makepoint(lon, lat), 4326), 25831) g
             from raw.com_osm_food_shops_box) o
             where not exists (select 1 from raw.adm_units_polygons u where u.tipus_ua = 'SEC_CENS' and st_intersects(u.geom, o.g))"""
osm = pd.read_sql(OSM_OUT, eng)
def osm_pts(cats): return osm[osm.food_category.isin(cats)][["x", "y"]].to_numpy()
T["market"] = np.vstack([T["market"], osm_pts(["market"])])
T["anysuper"] = np.vstack([T["anysuper"], osm_pts(["supermarket", "convenience"])])
T["fresh"] = np.vstack([T["fresh"], osm_pts(["market", "greengrocer", "butcher", "fishmonger", "poultry_eggs"])])
# fresh food: three definitions (see the docstring); "fresh" = the MAIN (middle) definition
# Supercor removed 2026-10-19: every Supercor in the city is a Supercor Exprés convenience store or a petrol-station shop (Repsol, Pg Santa Coloma 71,
# 250 m from Baro de Viver, had made that food desert disappear under the middle definition)
FRESH_SUPER_RX = r"ametller|bon ?[aà]rea|co ?aliment|veritas|covir[aá]n|\bspar\b|\bsuma\b|sorli|plusfresc|keisy|eroski|fruit|verdur|\bcarn|xarcut|\bpeix|horta"
T["fresh_strict"] = T["fresh"]
# petrol-station shops (supermarket-class premise within 20 m of a 2024 fuel premise) are never fresh food
cs = pd.read_sql("""with p as (select nom_local, nom_activitat, st_transform(st_setsrid(st_makepoint(lon, lat), 4326), 25831) g from raw.cen_census_2024
                               where lon is not null and nom_principal_activitat = 'Actiu')
                    select nom_local, st_x(g) x, st_y(g) y from p a where nom_activitat = 'Autoservei / Supermercat'
                      and not exists (select 1 from p f where f.nom_activitat = 'Combustibles i carburants' and st_dwithin(a.g, f.g, 20))""", eng)
cs_fresh = cs[cs.nom_local.fillna("").str.contains(FRESH_SUPER_RX, case=False, regex=True) & ~cs.nom_local.fillna("").str.contains("sirena", case=False)]
osm_sup = osm[osm.food_category.isin(["supermarket", "convenience"])]
osm_fresh = osm_sup[(osm_sup.nom.fillna("") + " " + osm_sup.ensenya.fillna("")).str.contains(FRESH_SUPER_RX, case=False, regex=True)]
T["fresh"] = np.vstack([T["fresh_strict"], cs_fresh[["x", "y"]].to_numpy(), osm_fresh[["x", "y"]].to_numpy()])
T["fresh_broad"] = np.vstack([T["fresh_strict"], T["anysuper"]])
print("fresh food targets: strict", len(T["fresh_strict"]), "| middle", len(T["fresh"]), f"(+{len(cs_fresh)} census + {len(osm_fresh)} OSM fresh-selling supermarkets)", "| broad", len(T["fresh_broad"]))
print("OSM targets outside the city:", osm.food_category.value_counts().to_dict())
res = {}
for k, P in T.items():
    d_, i_ = tree.query(P); src_nodes = {tuple(nodes[i]) for i, d in zip(i_, d_) if d <= 150}
    res[k + "_min"] = nx.multi_source_dijkstra_path_length(G, src_nodes, cutoff=60, weight="min")
    if k == "chain":
        res["chain_m"] = nx.multi_source_dijkstra_path_length(G, src_nodes, cutoff=3000, weight="len")
    if k == "anysuper":   # network distance to ANY supermarket-class shop (chains + independents): same 500 m test as the chain coverage
        res["anysuper_m"] = nx.multi_source_dijkstra_path_length(G, src_nodes, cutoff=3000, weight="len")
        # elevation of the nearest chain store's network node, for the climb home
        _, paths = nx.multi_source_dijkstra(G, src_nodes, cutoff=60, weight="min")
        res["chain_store_elev"] = {n: elev[idx[p[0]]] for n, p in paths.items()}
    print(k, len(P), "targets")

# ---------- origins ----------
b = pd.read_sql("select referencia_cadastral, dwellings_n, st_x(st_centroid(geom)) x, st_y(st_centroid(geom)) y from raw.cad_inspire_buildings where dwellings_n > 0", eng)
d_b, i_b = tree.query(b[["x", "y"]].to_numpy()); nb = [tuple(nodes[i]) for i in i_b]; walk_extra_min = d_b / 1000 / 5 * 60
b["snap_m"] = d_b.round(1); b["elevation_m"] = elev[i_b].round(1)
b["walk_to_supermarket_m"] = [res["chain_m"].get(n, np.nan) for n in nb] + d_b
b["walk_to_any_supermarket_m"] = [res["anysuper_m"].get(n, np.nan) for n in nb] + d_b
for k in ("chain", "anysuper", "market", "fresh", "fresh_strict", "fresh_broad"):
    b[f"minutes_{k}"] = (np.array([res[k + "_min"].get(n, np.nan) for n in nb]) + walk_extra_min).round(1)
b["minutes_chain_older"] = (b.minutes_chain / OLDER_SPEED).round(1); b["minutes_fresh_older"] = (b.minutes_fresh / OLDER_SPEED).round(1)
b["minutes_fresh_strict_older"] = (b.minutes_fresh_strict / OLDER_SPEED).round(1); b["minutes_fresh_broad_older"] = (b.minutes_fresh_broad / OLDER_SPEED).round(1)
b["climb_home_from_supermarket_m"] = (b.elevation_m - np.array([res["chain_store_elev"].get(n, np.nan) for n in nb])).round(1)
far = b.snap_m > 300
# buildings ON the network that the search did not reach within its cutoff (60 min / 3000 m) are far, not unknown: they get the cutoff value,
# so they count as "beyond 10 min / 500 m" instead of silently leaving the shares and medians (before this fix 1,519 dwellings dropped out)
for c in [c for c in b.columns if c.startswith("minutes_")]:
    cap_min = 60 / (OLDER_SPEED if c.endswith("_older") else 1)
    b.loc[~far & b[c].isna(), c] = round(cap_min, 1)
b.loc[~far & b.walk_to_supermarket_m.isna(), "walk_to_supermarket_m"] = 3000.0
b.loc[~far & b.walk_to_any_supermarket_m.isna(), "walk_to_any_supermarket_m"] = 3000.0
b.loc[far, [c for c in b.columns if c.startswith(("minutes_", "walk_to", "climb_"))]] = np.nan
sec = pd.read_sql("""select b.referencia_cadastral, u.seccio_censal from raw.cad_inspire_buildings b
                     join raw.adm_units_polygons u on u.tipus_ua = 'SEC_CENS' and st_intersects(u.geom, st_pointonsurface(b.geom)) where b.dwellings_n > 0""", eng)
b = b.merge(sec, on="referencia_cadastral", how="inner")

def wmed(v, w):
    ok = v.notna(); v, w = v[ok].to_numpy(), w[ok].to_numpy()
    if not len(v): return np.nan
    o = np.argsort(v); c = np.cumsum(w[o]); return float(v[o][np.searchsorted(c, c[-1] / 2)])
def wshare(cond, v, w):
    ok = v.notna(); return float(100 * w[ok & cond].sum() / max(w[ok].sum(), 1))
rows = []
for s, g in b.groupby("seccio_censal"):
    w = g.dwellings_n
    rows.append(dict(seccio_censal=s, dwellings_n=int(w.sum()),
        median_walk_to_supermarket_m=wmed(g.walk_to_supermarket_m, w),
        share_dwellings_beyond_500m_pct=wshare(g.walk_to_supermarket_m > 500, g.walk_to_supermarket_m, w),
        share_dwellings_beyond_800m_pct=wshare(g.walk_to_supermarket_m > 800, g.walk_to_supermarket_m, w),
        share_dwellings_beyond_500m_any_supermarket_pct=wshare(g.walk_to_any_supermarket_m > 500, g.walk_to_any_supermarket_m, w),
        median_minutes_chain=wmed(g.minutes_chain, w), median_minutes_any_supermarket=wmed(g.minutes_anysuper, w),
        median_minutes_market=wmed(g.minutes_market, w), median_minutes_fresh_food=wmed(g.minutes_fresh, w),
        median_minutes_chain_older=wmed(g.minutes_chain_older, w), median_minutes_fresh_older=wmed(g.minutes_fresh_older, w),
        share_dwellings_chain_over_10min_older_pct=wshare(g.minutes_chain_older > 10, g.minutes_chain_older, w),
        share_dwellings_fresh_over_10min_older_pct=wshare(g.minutes_fresh_older > 10, g.minutes_fresh_older, w),
        share_dwellings_fresh_strict_over_10min_older_pct=wshare(g.minutes_fresh_strict_older > 10, g.minutes_fresh_strict_older, w),
        share_dwellings_fresh_broad_over_10min_older_pct=wshare(g.minutes_fresh_broad_older > 10, g.minutes_fresh_broad_older, w),
        median_climb_home_from_supermarket_m=wmed(g.climb_home_from_supermarket_m, w)))
S = pd.DataFrame(rows)
v = pd.read_sql("select seccio_censal, codi_barri, population_n, share_age_65plus_pct, cars_per_1000_residents, disposable_income_eur_per_person from ana.section_model_table", eng)
S = v.merge(S, on="seccio_censal", how="left")
S["residents_beyond_500m_est"] = (S.population_n * S.share_dwellings_beyond_500m_pct / 100).round(0)
S["residents_beyond_500m_any_supermarket_est"] = (S.population_n * S.share_dwellings_beyond_500m_any_supermarket_pct / 100).round(0)
S["residents_65plus_beyond_500m_est"] = (S.residents_beyond_500m_est * S.share_age_65plus_pct / 100).round(0)
S["residents_65plus_fresh_over_10min_est"] = (S.population_n * S.share_age_65plus_pct / 100 * S.share_dwellings_fresh_over_10min_older_pct / 100).round(0)
# vulnerable population = old (65+ share in the top quarter) OR car-less (cars per 1000 in the bottom quarter)
vulnerable_pop = (S.share_age_65plus_pct >= S.share_age_65plus_pct.quantile(0.75)) | (S.cars_per_1000_residents <= S.cars_per_1000_residents.quantile(0.25))
# MAIN (2026-10-16): the same access test as the food deserts - half the dwellings more than 10 min (older pace, slope-aware) from fresh food (middle definition)
S["vulnerable_low_access"] = (S.share_dwellings_fresh_over_10min_older_pct >= 50) & vulnerable_pop
# second question: access to a FULL chain supermarket, same slope-aware test (the earlier version used network distance > 500 m without slope: 7 sections)
S["vulnerable_low_access_chain"] = (S.share_dwellings_chain_over_10min_older_pct >= 50) & vulnerable_pop
# food desert in the Institut Metropoli sense: fresh food not within ~5 min walk (older pace: 10 min) AND low income (bottom quarter)
S["food_desert_low_income"] = (S.share_dwellings_fresh_over_10min_older_pct >= 50) & (S.disposable_income_eur_per_person <= S.disposable_income_eur_per_person.quantile(0.25))
low_income = S.disposable_income_eur_per_person <= S.disposable_income_eur_per_person.quantile(0.25)
S["food_desert_low_income_strict"] = (S.share_dwellings_fresh_strict_over_10min_older_pct >= 50) & low_income   # upper end of the range
S["food_desert_low_income_broad"] = (S.share_dwellings_fresh_broad_over_10min_older_pct >= 50) & low_income     # lower end of the range
# edge sections with an urban area across the boundary (any OSM food shop outside the city within 600 m): outside fresh shops are under-recorded there
edge = pd.read_sql("""with city as (select st_boundary(st_union(geom)) b from raw.adm_units_polygons where tipus_ua = 'SEC_CENS'),
    o as (""" + OSM_OUT.replace("select food_category, nom, ensenya, st_x(g) x, st_y(g) y", "select g") + """)
    select s.seccio_censal from raw.adm_units_polygons s, city where s.tipus_ua = 'SEC_CENS' and st_dwithin(s.geom, city.b, 1)
      and exists (select 1 from o where st_dwithin(o.g, s.geom, 600))""", eng)
S["edge_outside_food_uncertain"] = S.seccio_censal.isin(edge.seccio_censal)
B = b.drop(columns=["x", "y"])
INT = lambda df: {c: Integer() for c in df.columns if pd.api.types.is_integer_dtype(df[c]) or c in ("seccio_censal", "codi_barri")}   # integer, not bigint (type policy)
B.to_sql("py_building_food_access", eng, schema="ana", if_exists="replace", index=False, dtype=INT(B))
S.to_sql("py_section_food_access", eng, schema="ana", if_exists="replace", index=False, dtype=INT(S))
with psycopg.connect(CONN, autocommit=True) as c:
    c.execute("COMMENT ON TABLE ana.py_building_food_access IS 'Walking distance / slope-aware walking minutes (Tobler) from each residential building to chain supermarkets, any supermarket, municipal markets and any fresh-food shop. Built by build_food_access.py'")
    c.execute("COMMENT ON TABLE ana.py_section_food_access IS 'Food access per census section: distance and slope-aware minutes (adult / older pace), climb home, vulnerability and low-income food-desert flags. Built by build_food_access.py'")
tot = S.population_n.sum()
print("residents beyond 500 m (chain, distance):", int(S.residents_beyond_500m_est.sum()), f"({100 * S.residents_beyond_500m_est.sum() / tot:.1f}%)")
print("residents beyond 500 m (any supermarket incl. independents, distance):", int(S.residents_beyond_500m_any_supermarket_est.sum()), f"({100 * S.residents_beyond_500m_any_supermarket_est.sum() / tot:.1f}%)")
print("65+ with fresh food > 10 min at older pace:", int(S.residents_65plus_fresh_over_10min_est.sum()), "| vulnerable sections:", int(S.vulnerable_low_access.sum()), "(full chain supermarket:", int(S.vulnerable_low_access_chain.sum()), ")", "| low-income food-desert sections:", int(S.food_desert_low_income.sum()), "(range: strict", int(S.food_desert_low_income_strict.sum()), "/ broad", int(S.food_desert_low_income_broad.sum()), ")")

# the gis visualisation layers (dbt tag after_python) read ana.py_section_food_access: rebuild them now
import subprocess
DBT = Path(__file__).parent / "dbt_bcn"
r = subprocess.run(["cmd", "/c", str(DBT / "dbt.cmd"), "build", "--select", "tag:after_python", "--exclude", "tag:after_models"], cwd=DBT, capture_output=True, text=True, encoding="utf-8", errors="replace")
print(chr(10).join(l for l in r.stdout.splitlines() if any(k in l for k in ("OK created", "ERROR", "FAIL", "Done."))))
print("gis layers", "OK" if r.returncode == 0 else f"FAILED (exit {r.returncode})")
