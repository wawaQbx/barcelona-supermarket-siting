"""Assign PGM qualification (clau) by point-in-polygon; add verified family names. Updates stores_model_table_city.csv."""
import re, pandas as pd, geopandas as gpd
m = pd.read_csv("stores_model_table_city.csv").drop(columns=[c for c in ["pgm_clau_poly", "pgm_family", "pgm_family_name", "pgm_poly_detall"] if c in pd.read_csv("stores_model_table_city.csv", nrows=1).columns])
P = gpd.read_file("data/pgm_qualif_polygons.gpkg")
pts = gpd.GeoDataFrame(m[["lat", "lon"]], geometry=gpd.points_from_xy(m.lon, m.lat), crs=4326).to_crs(25831)
j = gpd.sjoin_nearest(pts, P[["CLAU", "DETALL", "geometry"]], how="left", max_distance=30, distance_col="dd")
j = j.reset_index().sort_values(["index", "dd"]).drop_duplicates("index", keep="first").set_index("index")   # nearest polygon within 30 m (0 m = inside)
m["pgm_poly_dist_m"] = j.dd.round(1).values
m["pgm_clau_poly"] = j.CLAU.values; m["pgm_poly_detall"] = j.DETALL.values
fam = lambda c: None if pd.isna(c) else (re.match(r"^(\d+)", str(c)).group(1) if re.match(r"^\d", str(c)) else str(c))
m["pgm_family"] = m.pgm_clau_poly.map(fam)
NAMES = {  # only names confirmed on AMB Geoportal de Planejament pages
    "7": "Equipaments comunitaris i dotacions", "12": "Nucli antic (alineació a vial)", "13": "Densificació urbana (alineació a vial; 13a intensiva, 13b semintensiva)",
    "18": "Volumetria específica", "20": "Edificació aïllada", "22": "Industrial (22a)", "15": "Conservació de l'estructura urbana i edificatòria",
    "10": "Sistema hoteler dotacional", "T": "Terciari", "HT": "Zona hotelera", "EQ": "Equipament privat", "ZL": "Activitats logístiques"}
m["pgm_family_name"] = m.pgm_family.map(NAMES).fillna("(name not verified)")
print("assigned (<=30 m):", m.pgm_clau_poly.notna().sum(), "of", len(m), "| exactly inside:", int((m.pgm_poly_dist_m == 0).sum()))
old = m.pgm_qualif.astype(str).str.extract(r"^(\d+|[A-Za-z]+)", expand=False)
both = old.notna() & m.pgm_family.notna()
print("agreement nearest-label vs polygon (where both):", round((old[both] == m.pgm_family[both]).mean() * 100, 1), "%  n =", int(both.sum()))
print(pd.crosstab(m.brand_group, m.pgm_family.fillna("none")).to_string())
m.to_csv("stores_model_table_city.csv", index=False, encoding="utf-8")
