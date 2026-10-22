"""Add official-source date clues to stores_opening_era_city.csv: Bon Preu/Esclat first-seen month (Wayback), Condis numeric id."""
import pandas as pd, numpy as np
e = pd.read_csv("stores_opening_era_city.csv")
f = pd.read_csv("data/bonpreu_first_seen.csv"); c = pd.read_csv("data/condis_raw.csv")
def nearest(r, ref, la, lo, lim=30):
    d = np.hypot((ref[la] - r.lat) * 111320, (ref[lo] - r.lon) * 111320 * np.cos(np.radians(41.4))); k = d.idxmin(); return (k if d[k] <= lim else None)
e["official_first_seen"] = None; e["official_first_seen_note"] = None; e["official_store_code"] = np.nan
for i, r in e.iterrows():
    if r.brand in ("Bon Preu", "Esclat"):
        k = nearest(r, f, "lat", "lon")
        if k is not None:
            fs = int(f.at[k, "first_seen"]); e.at[i, "official_store_code"] = f.at[k, "codi"]
            e.at[i, "official_first_seen"] = f"{fs // 100}-{fs % 100:02d}"
            e.at[i, "official_first_seen_note"] = "on or before 2021-11 (archive start)" if fs == 202111 else "first appears in official finder"
    elif r.brand == "Condis":
        k = nearest(r, c, "lat", "lng")
        if k is not None: e.at[i, "official_store_code"] = c.at[k, "idn"]
e["condis_id_proxy"] = np.where(e.brand.eq("Condis") & e.official_store_code.notna(), np.where(e.official_store_code >= 3100, "id>=3100 (mostly opened 2019+)", "id<3100 (older)"), None)
e.to_csv("stores_opening_era_city.csv", index=False)
print(e[e.brand.isin(["Bon Preu", "Esclat"])].official_first_seen.value_counts(dropna=False).to_dict()); print(pd.crosstab(e[e.brand == "Condis"].condis_id_proxy.fillna("no id"), e[e.brand == "Condis"].opening_era))
