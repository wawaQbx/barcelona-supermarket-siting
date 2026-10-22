"""Spanish cadastre INSPIRE buildings (Dirección General del Catastro, ATOM feed, municipality 08900 = Barcelona) -> compact GeoPackage.
Input : data_catalog/05_built_environment_planning/cadastre/inspire_buildings/A.ES.SDGC.BU.08900.zip   (50 MB; GML 338 + 815 MB inside, read in place)
Output: data_catalog/05_built_environment_planning/cadastre/inspire_buildings/inspire_buildings.gpkg    (imported by import_all.py as raw.cad_inspire_buildings)
One row = one cadastral building (footprint, EPSG:25831). Kept: cadastral reference, year of construction (INSPIRE dateOfConstruction 'beginning'),
current use, building units, dwellings, gross floor area, footprint area, and the max floors above / below ground of the building parts.
Source: https://www.catastro.hacienda.gob.es/INSPIRE/Buildings/08/08900-BARCELONA/A.ES.SDGC.BU.08900.zip (last modified 2026-08-21)
"""
from pathlib import Path
import geopandas as gpd, pandas as pd, pyogrio

D = Path(__file__).parent / "data_catalog" / "05_built_environment_planning" / "cadastre" / "inspire_buildings"
Z = "/vsizip/" + str((D / "A.ES.SDGC.BU.08900.zip").resolve()).replace("\\", "/")

b = pyogrio.read_dataframe(Z + "/A.ES.SDGC.BU.08900.building.gml",
                           columns=["reference", "beginning", "conditionOfConstruction", "currentUse", "numberOfBuildingUnits", "numberOfDwellings", "value", "value_uom"])
print("buildings", len(b), b.crs)
assert (b.value_uom.dropna() == "m2").all()
out = pd.DataFrame({
    "referencia_cadastral": b.reference,
    "year_of_construction": pd.to_numeric(b.beginning.str[:4], errors="coerce").astype("Int64"),
    "condition_of_construction": b.conditionOfConstruction,
    "current_use": b.currentUse,
    "building_units_n": b.numberOfBuildingUnits,
    "dwellings_n": b.numberOfDwellings,
    "gross_floor_area_m2": b.value,
    "footprint_area_m2": b.geometry.area.round(1)})

p = pyogrio.read_dataframe(Z + "/A.ES.SDGC.BU.08900.buildingpart.gml", columns=["localId", "numberOfFloorsAboveGround", "numberOfFloorsBelowGround"], read_geometry=False)
print("building parts", len(p))
p["referencia_cadastral"] = p.localId.str.split("_").str[0]
fl = p.groupby("referencia_cadastral").agg(floors_above_ground_max=("numberOfFloorsAboveGround", "max"), floors_below_ground_max=("numberOfFloorsBelowGround", "max"),
                                           building_parts_n=("localId", "size")).reset_index()
out = out.merge(fl, on="referencia_cadastral", how="left")
g = gpd.GeoDataFrame(out, geometry=b.geometry.values, crs=b.crs)
dst = D / "inspire_buildings.gpkg"
if dst.exists(): dst.unlink()
pyogrio.write_dataframe(g, dst, layer="inspire_buildings")
print("written", dst, len(g), "| year missing:", int(g.year_of_construction.isna().sum()), "| floors missing:", int(g.floors_above_ground_max.isna().sum()))
print(g.current_use.value_counts().to_string()); print(g.year_of_construction.describe().to_string())
