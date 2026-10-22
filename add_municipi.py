"""Add municipi (+ barri/district for in-city stores) to the supermarket CSV/GeoJSON."""
import re, json, unicodedata
import geopandas as gpd, pandas as pd

CSV = "barcelona_supermarkets_official.csv"
GJ = "barcelona_supermarkets_official.geojson"
BARRI = "data_catalog/06_admin_boundaries/admin/Barri.geojson"

df = pd.read_csv(CSV).drop(columns=["municipi", "codi_barri", "barri", "codi_districte"], errors="ignore")
pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326).to_crs(25831)
barri = gpd.read_file(BARRI); barri = barri[barri.Codi_Barri.notna()].copy()


j = gpd.sjoin(pts, barri[["Codi_Barri", "NOM", "Codi_Districte", "geometry"]], how="left", predicate="within")
j = j[~j.index.duplicated()]
inside = j.Codi_Barri.notna()

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper().strip()
    return s
TOWNS = {  # normalised address token -> canonical name
    "HOSPITALET DE LLOBREGAT": "L'Hospitalet de Llobregat", "L'HOSPITALET DE LLOBREGAT": "L'Hospitalet de Llobregat",
    "SANTA COLOMA DE GRAMENET": "Santa Coloma de Gramenet", "CORNELLA DE LLOBREGAT": "Cornellà de Llobregat",
    "BADALONA": "Badalona", "EL PRAT DE LLOBREGAT": "El Prat de Llobregat",
    "SANT ADRIA DE BESOS": "Sant Adrià de Besòs", "ESPLUGUES DE LLOBREGAT": "Esplugues de Llobregat",
    "SANT JOAN DESPI": "Sant Joan Despí", "SANT FELIU DE LLOBREGAT": "Sant Feliu de Llobregat",
    "SANT JUST DESVERN": "Sant Just Desvern", "SANT CUGAT DEL VALLES": "Sant Cugat del Vallès",
    "SANT BOI DE LLOBREGAT": "Sant Boi de Llobregat", "SANT BOI DEL LLOBREGAT": "Sant Boi de Llobregat",
    "SANT QUIRZE DEL VALLES": "Sant Quirze del Vallès", "BARCELONA": "Barcelona", "BARCELONNE": "Barcelona",
}
def town_from_addr(a):
    parts = [p.strip() for p in str(a).split(",")]
    found = [TOWNS[norm(p)] for p in parts if norm(p) in TOWNS]
    others = [f for f in found if f != "Barcelona"]
    return others[-1] if others else ("Barcelona" if found else None)   # trailing BARCELONA may be the province

# Postal-code prefix fallback for rows with no town in address (08xxx)
ZIP = {"08820": "El Prat de Llobregat", "08905": "L'Hospitalet de Llobregat", "08980": "Sant Feliu de Llobregat"}
df["municipi"] = [("Barcelona" if i else None) for i in inside]
for k in df.index[~inside]:
    t = town_from_addr(df.at[k, "address"])
    if t is None:
        m = re.search(r"\b(08\d{3})\b", str(df.at[k, "address"]))
        t = ZIP.get(m.group(1)) if m else None
    df.at[k, "municipi"] = t
df["municipi"] = df.municipi.replace({"l'Hospitalet de Llobregat": "L'Hospitalet de Llobregat", "el Prat de Llobregat": "El Prat de Llobregat"})
cb = j.Codi_Barri.copy(); nm = j.NOM.copy()
need = (df.municipi == "Barcelona") & cb.isna()          # address says Barcelona, point just outside polygon edge
near = gpd.sjoin_nearest(pts[need][["geometry"]], barri[["Codi_Barri", "NOM", "geometry"]], max_distance=300, distance_col="dd")
near = near[~near.index.duplicated()]
cb.loc[near.index] = near.Codi_Barri; nm.loc[near.index] = near.NOM
print("nearest-barri fallback:", len(near), "of", int(need.sum()))
DIST = [(1, 1, 4), (2, 5, 10), (3, 11, 18), (4, 19, 21), (5, 22, 27), (6, 28, 32), (7, 33, 43), (8, 44, 56), (9, 57, 63), (10, 64, 73)]
dist_of = lambda c: next((d for d, lo, hi in DIST if lo <= c <= hi), None) if pd.notna(c) else None
df["codi_barri"] = cb.astype("Int64")
df["barri"] = nm
df["codi_districte"] = pd.array([dist_of(c) for c in cb], dtype="Int64")
print(df.municipi.value_counts(dropna=False))
# conflicts: address says non-BCN but point inside BCN or vice versa
conf = df[inside & df.address.map(town_from_addr).notna() & (df.address.map(town_from_addr) != "Barcelona")]
print("addr/geom conflicts:", len(conf)); print(conf[["brand","address"]].head())
df.to_csv(CSV, index=False, encoding="utf-8")
out = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
out.to_file(GJ, driver="GeoJSON")
print("written", len(df))
