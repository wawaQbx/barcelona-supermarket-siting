"""Barri-level: vehicles per 1000 residents, cadastre building age/form. -> barri_features.csv"""
import pandas as pd, numpy as np
R = "data/raw/"
pop = pd.read_csv("data_catalog/02_demand_population_income_housing/demographics/2026_pad_base_by_barri.csv")
print(pop.columns.tolist())
num = lambda s: pd.to_numeric(s, errors="coerce")
# vehicles
v = pd.read_csv(R + "parc_vehicles.csv"); v = v[v.Codi_Barri.astype(str).str.isnumeric()]
v["Codi_Barri"] = v.Codi_Barri.astype(int)
vb = v.pivot_table(index="Codi_Barri", columns="Tipologia_parc", values="Nombre_vehicles", aggfunc="sum").fillna(0)
vb.columns = ["veh_" + c.lower().replace(" ", "_") for c in vb.columns]
out = vb.join(pop.set_index("Codi_Barri")[["Nom_Barri", "Total_Poblacio"]])
out["cars_per_1000"] = (out.veh_turismes / out.Total_Poblacio * 1000).round(1)
out["motos_per_1000"] = ((out.veh_motos + out.veh_ciclomotors) / out.Total_Poblacio * 1000).round(1)
out["vans_trucks_per_1000"] = ((out.veh_furgonetes + out.veh_camions) / out.Total_Poblacio * 1000).round(1)
# building age (cadastre)
a = pd.read_csv(R + "cad_edif_any.csv"); a["Nombre"] = num(a.Nombre)
ab = a.pivot_table(index="Codi_barri", columns="Any_construccio", values="Nombre", aggfunc="sum").fillna(0)
print("age classes:", ab.columns.tolist())
tot = ab.sum(1); old = [c for c in ab.columns if c in ("<1901", "1901-1940", "1941-1950")]
out["bldg_total"] = tot
out["pct_bldg_pre1950"] = (ab[old].sum(1) / tot * 100).round(1)
e = pd.read_csv(R + "cad_edif_edat.csv"); e["Edat_mitjana"] = num(e.Edat_mitjana)
out["bldg_mean_age"] = e.groupby("Codi_barri").Edat_mitjana.mean().round(1)
# locals per building
l = pd.read_csv(R + "cad_edif_locals.csv"); l["Nombre"] = num(l.Nombre)
lb = l.pivot_table(index="Codi_barri", columns="Desc_locals", values="Nombre", aggfunc="sum").fillna(0)
print("locals classes:", lb.columns.tolist())
big = [c for c in lb.columns if any(k in c for k in ("més de 50", "de 26", "de 51", ">"))]
out["pct_bldg_large_30plus_units"] = (lb[[c for c in lb.columns if c.startswith(("de 31", "de 51", "més", "de 26"))]].sum(1) / lb.sum(1) * 100).round(1) if True else np.nan
# plot (finca) area & building floor area -> built density proxy
f = pd.read_csv(R + "cad_finques_sup.csv"); f["Superficie_m2"] = num(f.Superficie_m2); print("finques classes:", f.Desc_sup.unique().tolist())
fb = f.pivot_table(index="Codi_barri", columns="Desc_sup", values="Superficie_m2", aggfunc="sum")
b = pd.read_csv(R + "cad_edif_sup.csv"); b["Superficie_m2"] = num(b.Superficie_m2); print("edif classes:", b.Tipus_sup.unique().tolist())
bb = b.pivot_table(index="Codi_barri", columns="Tipus_sup", values="Superficie_m2", aggfunc="sum")
for c in fb.columns: out["plot_" + c] = fb[c]
for c in bb.columns: out["bldg_" + c] = bb[c]
out.index.name = "codi_barri"
out.reset_index().to_csv("barri_features.csv", index=False, encoding="utf-8")
print(out.shape); print(out.describe().T[["count", "mean", "min", "max"]].round(1).to_string())
out["floor_area_ratio"] = (out["plot_Superfície_edificada_sobre_rasant"] / out["plot_Superfície_sòl"]).round(2)
out["flag_fleet_distorted"] = out.cars_per_1000 > 600   # company/fleet registrations (port, Zona Franca...)
out.reset_index().to_csv("barri_features.csv", index=False, encoding="utf-8")
print(out[out.flag_fleet_distorted][["Nom_Barri", "Total_Poblacio", "cars_per_1000"]])
print(out.floor_area_ratio.describe().round(2).to_dict())
