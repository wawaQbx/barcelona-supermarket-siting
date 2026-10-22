"""City-only (municipi == Barcelona) store feature table: traffic, roads, PGM, terrain, opening era."""
import json, time, numpy as np, pandas as pd, geopandas as gpd, requests
from shapely.geometry import LineString

s = pd.read_csv("barcelona_supermarkets_official.csv")
s = s[s.municipi == "Barcelona"].reset_index(drop=True)
g = gpd.GeoDataFrame(s, geometry=gpd.points_from_xy(s.lon, s.lat), crs=4326).to_crs(25831)
print("stores:", len(g))

# ---- traffic counting stations (IMD) ----
desc = pd.read_csv("data/raw/aforament_desc_2025.csv", encoding="utf-8-sig")
det = pd.read_csv("data/raw/aforament_detall_2025.csv")
det["Id_aforament"] = det.Id_aforament.astype(str); det["Valor_IMD"] = pd.to_numeric(det.Valor_IMD, errors="coerce")
imd = det[det.Desc_tipus_dia == "laborables"].groupby("Id_aforament").Valor_IMD.mean().rename("imd")
desc["Id_aforament"] = desc.Id_aforament.astype(str)
st = desc[desc.Desc_tipus_aforament.isin(["Trànsit", "Rondes"])].merge(imd, on="Id_aforament")
st = gpd.GeoDataFrame(st, geometry=gpd.points_from_xy(st.Longitud, st.Latitud), crs=4326).to_crs(25831)
print("traffic stations with IMD:", len(st), "median IMD", st.imd.median())
xy_s = np.c_[g.geometry.x, g.geometry.y]; xy_t = np.c_[st.geometry.x, st.geometry.y]
D = np.sqrt(((xy_s[:, None, :] - xy_t[None, :, :]) ** 2).sum(-1))
j = D.argmin(1)
g["imd_nearest"] = st.imd.values[j]; g["imd_nearest_dist_m"] = D[np.arange(len(g)), j].round(0)
w = D <= 500
g["imd_mean_500m"] = [st.imd.values[r].mean() if r.any() else np.nan for r in w]
g["n_traffic_stations_500m"] = w.sum(1)
ron = (st.Desc_tipus_aforament == "Rondes").values
g["dist_ronda_station_m"] = D[:, ron].min(1).round(0)

# ---- roads (OSM) ----
R = json.load(open("data/raw/osm_roads.json", encoding="utf-8"))["elements"]
rows = []
for e in R:
    pts = [(p["lon"], p["lat"]) for p in e.get("geometry", [])]
    if len(pts) >= 2:
        t = e.get("tags", {}); rows.append((t.get("highway"), t.get("name"), t.get("lanes"), t.get("maxspeed"), LineString(pts)))
roads = gpd.GeoDataFrame(rows, columns=["highway", "name", "lanes", "maxspeed", "geometry"], crs=4326).to_crs(25831)
RANK = {"motorway": 7, "motorway_link": 7, "trunk": 6, "trunk_link": 6, "primary": 5, "primary_link": 5, "secondary": 4,
        "secondary_link": 4, "tertiary": 3, "tertiary_link": 3, "unclassified": 2, "residential": 2, "living_street": 1, "pedestrian": 1}
roads["rank"] = roads.highway.map(RANK)
def dist_to(mask):
    sub = roads[mask]; return g.geometry.apply(lambda p: sub.distance(p).min()).round(0)
g["dist_motorway_trunk_m"] = dist_to(roads["rank"] >= 6)
g["dist_primary_m"] = dist_to(roads["rank"] >= 5)
g["dist_secondary_m"] = dist_to(roads["rank"] >= 4)
sidx = roads.sindex
hi, hn, ln, ped = [], [], [], []
for p in g.geometry:
    b = p.buffer(50); idx = list(sidx.query(b, predicate="intersects")); near = roads.iloc[idx]
    hi.append(int(near["rank"].max()) if len(near) else np.nan)
    hn.append(near.loc[near["rank"].idxmax(), "highway"] if len(near) else None)
    c = roads.iloc[list(sidx.query(p.buffer(200), predicate="intersects"))]
    c = c.assign(L=c.geometry.intersection(p.buffer(200)).length)
    ln.append(c.L.sum() / 1000.0); ped.append(c[c.highway.isin(["pedestrian", "living_street"])].L.sum() / max(c.L.sum(), 1))
g["road_class_max_50m"] = hn; g["road_rank_max_50m"] = hi
g["road_len_km_200m"] = np.round(ln, 2); g["pedestrian_share_200m"] = np.round(ped, 3)

# ---- PGM labels (qualification key, street width, volumetric text) ----
P = gpd.read_file("zip://data_catalog/05_built_environment_planning/pgm/pgm_qualif.zip", layer="0702060100_BCN_Planejament_Urb_PUNTS_V")
def nearest_label(kind, name):
    sub = P[P.ELEM_DESCR == kind]; sub = sub[sub.LITERAL.notna()]
    a = np.c_[sub.geometry.x, sub.geometry.y]; d = np.sqrt(((xy_s[:, None, :] - a[None, :, :]) ** 2).sum(-1)); k = d.argmin(1)
    g[name] = sub.LITERAL.values[k]; g[name + "_dist_m"] = d[np.arange(len(g)), k].round(0)
nearest_label("Codi de qualificació urbanística", "pgm_qualif")
nearest_label("Cota d'ample oficial de vial o carrer", "pgm_street_width")
nearest_label("Text d'ordenació volumètrica", "pgm_volumetric")
g["pgm_key"] = g.pgm_qualif.str.extract(r"^(\d+[@a-z]?)", expand=False)

# ---- terrain: elevation (OpenTopoData EU-DEM 25 m) + slope over +-60 m ----
ll = g.to_crs(4326); lat0 = ll.geometry.y.values; lon0 = ll.geometry.x.values
off = 60.0; dlat = off / 111320.0; dlon = off / (111320.0 * np.cos(np.radians(41.4)))
pts = [(lat0, lon0), (lat0 + dlat, lon0), (lat0 - dlat, lon0), (lat0, lon0 + dlon), (lat0, lon0 - dlon)]
la = np.concatenate([p[0] for p in pts]); lo = np.concatenate([p[1] for p in pts]); el = np.full(len(la), np.nan)
for i in range(0, len(la), 100):
    loc = "|".join(f"{a:.6f},{b:.6f}" for a, b in zip(la[i:i+100], lo[i:i+100]))
    for attempt in range(6):
        try:
            time.sleep(1.2)
            r = requests.get("https://api.opentopodata.org/v1/eudem25m", params={"locations": loc}, timeout=60).json()
            el[i:i+100] = [x["elevation"] if x["elevation"] is not None else np.nan for x in r["results"]]; break
        except Exception: time.sleep(10)
n = len(g); E0, N, S, Ea, W = [el[k*n:(k+1)*n] for k in range(5)]
g["elevation_m"] = np.round(E0, 1)
g["slope_pct"] = (np.hypot((N - S) / (2 * off), (Ea - W) / (2 * off)) * 100).round(1)
print("elevation NaN:", int(np.isnan(E0).sum()), "slope NaN:", int(g.slope_pct.isna().sum()))

# ---- opening era (census panel) ----
era = pd.read_csv("stores_opening_era_city.csv")
assert len(era) == len(g) and np.allclose(era.lat.values, g.lat.values), "run census_panel.py first"
for c in [c for c in era.columns if c not in g.columns]: g[c] = era[c].values
out = pd.DataFrame(g.drop(columns="geometry"))
out.to_csv("stores_features_city.csv", index=False, encoding="utf-8")
print(out.shape); print(out.describe().T[["count", "mean", "min", "max"]].round(1).to_string())
print(out.pgm_key.value_counts().head(12).to_dict()); print(out.pgm_street_width.head(5).tolist(), out.pgm_volumetric.head(5).tolist())
