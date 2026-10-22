"""Five commercial-census editions (2014, 2016, 2019, 2022, 2024): per-store presence -> opening-era bracket (city only)."""
import re, json, numpy as np, pandas as pd
P = "data/raw/"
BR = [("Mercadona", r"MERCADONA"), ("Lidl", r"\bLIDL"), ("Aldi", r"\bALDI\b"), ("Dia", r"^(DIA\b|DIA %|DIA MARKET|SUPERMERCADOS DIA|DIA-|LA PLAZA DE DIA)"),
      ("Dia", r"CLAREL"), ("Caprabo", r"CAPRABO"), ("Condis", r"CONDIS"), ("Charter", r"CHARTER"), ("Consum", r"\bCONSUM\b"),
      ("Bon Preu", r"BON ?PREU|BONPREU"), ("Esclat", r"ESCLAT"), ("Carrefour", r"CARREFOUR"), ("Alcampo", r"ALCAMPO")]
def brand(n):
    n = str(n).upper().strip()
    for b, rx in BR:
        if re.search(rx, n): return b
    return None
def mk(df, name, lat, lon, food_mask):
    isclarel = df[name].astype(str).str.upper().str.contains("CLAREL")
    d = df[food_mask | isclarel].copy(); d["legacy"] = isclarel[food_mask | isclarel].values; d["lat"] = pd.to_numeric(d[lat], errors="coerce"); d["lon"] = pd.to_numeric(d[lon], errors="coerce")
    d["cb"] = d[name].map(brand); return d[["lat", "lon", "cb", "legacy"]].dropna(subset=["lat", "lon"])
sup = lambda s: s.astype(str).str.contains("uper|utoserv", case=False, na=False)
E_ = {}
d = pd.read_csv(P + "census_2014.csv", encoding="utf-8-sig", low_memory=False)
from pyproj import Transformer
xx = pd.to_numeric(d.X_ED50.astype(str).str.replace(",", "."), errors="coerce"); yy = pd.to_numeric(d.Y_ED50.astype(str).str.replace(",", "."), errors="coerce")  # ED50 (EPSG:23031); plain X/Y columns are corrupted
ok = xx.between(4e5, 4.5e5) & yy.between(4.5e6, 4.6e6)
d["la"] = np.nan; d["lo"] = np.nan
lo, la = Transformer.from_crs(23031, 4326, always_xy=True).transform(xx[ok].values, yy[ok].values); d.loc[ok, "la"] = la; d.loc[ok, "lo"] = lo
E_[2014] = mk(d, "NOM", "la", "lo", d.BCN2.astype(str).str.contains("ALIMENTARI") | d.NOM.astype(str).str.contains("MERCADONA|LIDL|ALDI|CAPRABO|CONDIS|CONSUM|CHARTER|BONPREU|BON PREU|ESCLAT|CARREFOUR|ALCAMPO", case=False))
d = pd.read_csv(P + "census_2016.csv", low_memory=False)
E_[2016] = mk(d, "N_LOCAL", "LATITUD", "LONGITUD", d.N_ACT.astype(str).str.contains("alimentaci", case=False) | d.N_LOCAL.astype(str).str.contains("MERCADONA|LIDL|ALDI|CAPRABO|CONDIS|CONSUM|CHARTER|BONPREU|BON PREU|ESCLAT|CARREFOUR|ALCAMPO", case=False))
g = json.load(open("data_catalog/03_commercial_census/census_2019_geojson/2019_censcomercialbcn_detall.geojson", encoding="utf-8"))
d = pd.DataFrame([f["properties"] for f in g["features"]]); E_[2019] = mk(d, "Nom_Local", "Latitud", "Longitud", sup(d.Nom_Activitat)); ANY = {2019: d[sup(d.Nom_Activitat)][["Latitud", "Longitud"]].apply(pd.to_numeric, errors="coerce").dropna().values}
d = pd.read_csv(P + "census_2022.csv", encoding="utf-8-sig", low_memory=False); E_[2022] = mk(d, "Nom_Local", "Latitud", "Longitud", sup(d.Nom_Activitat)); ANY[2022] = d[sup(d.Nom_Activitat)][["Latitud", "Longitud"]].dropna().values
d = pd.read_csv("data_catalog/03_commercial_census/qgis_commercial/layers/241021_censcomercialbcn_opendata_2024_v5.csv", low_memory=False); E_[2024] = mk(d, "Nom_Local", "Latitud", "Longitud", sup(d.Nom_Activitat)); ANY[2024] = d[sup(d.Nom_Activitat)][["Latitud", "Longitud"]].dropna().values
cov = pd.DataFrame({y: v.cb.value_counts() for y, v in E_.items()}).fillna(0).astype(int); print("branded rows per census:\n", cov)

s = pd.read_csv("barcelona_supermarkets_official.csv"); s = s[s.municipi == "Barcelona"].reset_index(drop=True)
s["bg"] = s.brand.replace({"Mi Alcampo": "Alcampo", "Carrefour Express": "Carrefour", "Carrefour Market": "Carrefour"})
def mind(a, b):
    global leg
    leg = np.zeros(len(a), dtype=bool)
    out = np.full(len(a), np.nan); leg[:] = False
    for br in a.bg.unique():
        sb = b[b.cb == br]
        if sb.empty: continue
        idx = (a.bg == br).values; A = a.loc[idx, ["lat", "lon"]].values; B = sb[["lat", "lon"]].values
        dy = (A[:, None, 0] - B[None, :, 0]) * 111320.0; dx = (A[:, None, 1] - B[None, :, 1]) * 111320.0 * np.cos(np.radians(41.4))
        D = np.sqrt(dx ** 2 + dy ** 2); out[idx] = D.min(1); leg[idx] = sb.legacy.values[D.argmin(1)]
    return out
YRS = [2014, 2016, 2019, 2022, 2024]
for y in YRS:
    s[f"d{y}"] = mind(s, E_[y]).round(1); s[f"seen_{y}"] = s[f"d{y}"] <= 60; s[f"legacy_{y}"] = leg & s[f"seen_{y}"].values
for y, A in ANY.items():   # any supermarket-class premises within 25 m (brand-agnostic; helps franchised Condis)
    P_ = s[["lat", "lon"]].values
    s[f"anysup_{y}"] = [(np.hypot((A[:, 0] - la) * 111320, (A[:, 1] - lo) * 111320 * np.cos(np.radians(41.4))) <= 25).any() for la, lo in P_]
s["supermarket_premises_since"] = [next((y for y in (2019, 2022, 2024) if r[f"anysup_{y}"]), np.nan) for _, r in s.iterrows()]
BR_LABEL = {2014: "<=2014", 2016: "2015-2016", 2019: "2017-2019", 2022: "2020-2022", 2024: "2023-2024"}
def era(r):
    seen = [y for y in YRS if r[f"seen_{y}"]]
    if not seen: return "no census match"
    return BR_LABEL[seen[0]]
s["first_seen_census"] = [next((y for y in YRS if r[f"seen_{y}"]), np.nan) for _, r in s.iterrows()]
s["last_seen_census"] = [next((y for y in reversed(YRS) if r[f"seen_{y}"]), np.nan) for _, r in s.iterrows()]
s["opening_era"] = s.apply(era, axis=1)
s["gap_in_presence"] = [(sum(r[f"seen_{y}"] for y in YRS if r.first_seen_census <= y <= r.last_seen_census) < sum(1 for y in YRS if r.first_seen_census <= y <= r.last_seen_census)) if pd.notna(r.first_seen_census) else False for _, r in s.iterrows()]
s["first_banner"] = ["Clarel (legacy)" if (pd.notna(r.first_seen_census) and r[f"legacy_{int(r.first_seen_census)}"]) else ("current brand" if pd.notna(r.first_seen_census) else None) for _, r in s.iterrows()]
s["d19"] = s.d2019; s["d24"] = s.d2024
print(pd.crosstab(s.bg, s.opening_era, margins=True).to_string())
print(pd.crosstab(s.bg, s.first_banner.fillna("none")).to_string())
print("no brand match but supermarket premises present:", int(((s.opening_era == "no census match") & s.supermarket_premises_since.notna()).sum()), "of", int((s.opening_era == "no census match").sum()))
print("stores with gaps in presence:", int(s.gap_in_presence.sum()))
s.drop(columns=["bg"]).to_csv("stores_opening_era_city.csv", index=False)
