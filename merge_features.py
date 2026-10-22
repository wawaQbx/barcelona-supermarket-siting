"""stores_features_city.csv + barri_features.csv (+ user's income/pop/rent by barri) -> stores_model_table_city.csv"""
import pandas as pd
s = pd.read_csv("stores_features_city.csv")
b = pd.read_csv("barri_features.csv").drop(columns=["Nom_Barri"])
m = s.merge(b, on="codi_barri", how="left")
m["brand_group"] = m.brand.replace({"Mi Alcampo": "Alcampo", "Carrefour Express": "Carrefour", "Carrefour Market": "Carrefour"})
m.to_csv("stores_model_table_city.csv", index=False, encoding="utf-8")
print(m.shape, "stores;", m.codi_barri.isna().sum(), "without barri")
cols = ["imd_nearest", "imd_mean_500m", "dist_primary_m", "dist_secondary_m", "road_rank_max_50m", "pedestrian_share_200m", "slope_pct", "elevation_m", "cars_per_1000", "pct_bldg_pre1950", "floor_area_ratio"]
print(m.groupby("brand_group")[cols].median().round(1).to_string())
print(pd.crosstab(m.brand_group, m.opening_era, normalize="index").round(2).to_string())
