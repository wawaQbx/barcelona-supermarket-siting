"""Export census-section and barri boundaries for the dashboard (Power BI / Tableau): GeoJSON in WGS84 (EPSG:4326), simplified.
Only the join keys and names are written; the indicators come from the gis tables through the key (seccio_censal / codi_barri),
so the boundary files never go stale when the data change. Output: dashboard/boundaries/*.geojson.
Simplification: 3 m tolerance in EPSG:25831 with topology kept (shared borders stay shared), then 6 decimals (~0.1 m) of longitude / latitude.
Also TopoJSON copies (*.topojson) for the Power BI Shape map visual, which only reads TopoJSON (map key = codi_barri / seccio_censal).
"""
from pathlib import Path
import geopandas as gpd, psycopg, topojson

ROOT = Path(__file__).parent
OUT = ROOT / "dashboard" / "boundaries"; OUT.mkdir(parents=True, exist_ok=True)
CONN = "host=localhost port=5432 dbname=supermarket_bcn user=postgres"   # password from pgpass.conf

LAYERS = {
    "sections_wgs84.geojson": "select seccio_censal, codi_barri, nom_barri, codi_districte, nom_districte, "
                              "ST_SimplifyPreserveTopology(geom, 3) as geom from gis.section_indicators order by seccio_censal",
    "barris_wgs84.geojson":   "select codi_barri, nom_barri, codi_districte, nom_districte, "
                              "ST_SimplifyPreserveTopology(geom, 3) as geom from gis.barri_indicators order by codi_barri",
}
with psycopg.connect(CONN) as c:
    for name, sql in LAYERS.items():
        g = gpd.read_postgis(sql, c, geom_col="geom").to_crs(4326)
        g.to_file(OUT / name, driver="GeoJSON", COORDINATE_PRECISION=6)
        print(name, len(g), "features", round((OUT / name).stat().st_size / 1e6, 2), "MB")
        tj = OUT / name.replace(".geojson", ".topojson")
        for col in ("codi_barri", "seccio_censal", "codi_districte"):   # keys as text: the Shape map matches them to the data as text
            if col in g: g[col] = g[col].astype(str)
        tj.write_text(topojson.Topology(g.rename_geometry("geometry"), prequantize=1e6, toposimplify=False).to_json(), encoding="utf-8")
        print(tj.name, round(tj.stat().st_size / 1e6, 2), "MB")
