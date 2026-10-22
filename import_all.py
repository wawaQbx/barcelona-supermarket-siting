"""Load every cleaned file into PostgreSQL/PostGIS (db supermarket_bcn).
Schemas: raw (imported as-is after cleaning), analysis (our own derived tables), meta (catalog / dictionary / skipped files).
Credentials come from %APPDATA%\\postgresql\\pgpass.conf (libpq) - nothing secret in this script. Re-runnable: tables are dropped and rebuilt."""
import io, json, re, subprocess, sys, time, unicodedata, traceback
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, psycopg
from psycopg import sql
from sqlalchemy import create_engine, text

ROOT = Path(r"D:\Claudecode\Supermarket_BCN"); CAT = ROOT / "data_catalog"; CLEAN = ROOT / "data_clean"
CONN = "host=localhost port=5432 dbname=supermarket_bcn user=postgres"
ENGINE = create_engine("postgresql+psycopg://postgres@localhost:5432/supermarket_bcn")
SRID = 25831
GEO_LANG = {"plazaparc_clean.geojson": "en", "inspire_buildings.gpkg": "en"}   # OSM tags are English; every Open Data BCN layer is Catalan
ANA = "ana"            # schema for tables derived by our own pipeline (short on purpose)

import bcn_naming as N
clean_name = N.clean_name

THEME = [  # (path prefix inside data_catalog, table prefix)
    ("01_stores", "store"), ("02_demand_population_income_housing/demographics", "pop"), ("02_demand_population_income_housing/income", "inc"),
    ("02_demand_population_income_housing/housing", "hou"), ("03_commercial_census/census_editions", "cen"), ("03_commercial_census/census_2019_geojson", "cen"),
    ("03_commercial_census/qgis_commercial", "com"), ("03_commercial_census/parc_plaza", "com"), ("03_commercial_census/osm_ring", "com"), ("04_transport_traffic/public_transport", "trn"),
    ("04_transport_traffic/traffic_vehicles_roads", "trf"), ("04_transport_traffic/streets", "trf"), ("04_transport_traffic/gtfs_tmb", "gtfs"), ("05_built_environment_planning/cadastre", "cad"), ("05_built_environment_planning/pgm", "pgm"),
    ("06_admin_boundaries", "adm"), ("07_opening_history", "hist"), ("08_tourism_other/tourism", "tou"), ("08_tourism_other/religion", "rel")]
def prefix_for(rel):
    r = str(rel).replace("\\", "/")
    for p, k in THEME:
        if r.startswith(p): return k
    return "misc"
ALIASES = {  # readable, non-redundant names (keeps theme prefix; source file is recorded in meta.tables)
    "adm_0301100100_unitats_adm_poligons": "adm_units_polygons", "adm_0301100100_unitats_adm_punts": "adm_units_points",
    "cad_cad_edif_any": "cad_edif_any", "cad_cad_edif_edat": "cad_edif_edat", "cad_cad_edif_locals": "cad_edif_locals",
    "cad_cad_edif_sup": "cad_edif_sup", "cad_cad_finques_sup": "cad_finques_sup",
    "cen_2019_censcomercialbcn_detall": "cen_census_2019", "com_241021_censcomercialbcn_opendata_2024_v5": "cen_census_2024",
    "pgm_pgm_qualif_polygons": "pgm_qualif_polygons", "hou_barcelonaciutat_seccionscensals_fixed": "adm_census_section_lookup",
    "rel_opendatabcn_llista_equipaments_serveis_religiosos": "rel_religious_facilities", "tou_opendatabcn_allotjament_hotels": "tou_hotels",
    "tou_2026_1t_hut_comunicacio_opendata": "tou_hut_comunicacio_2026_1t", "store_barcelona_supermarkets_official": "store_supermarkets_official",
    "store_store_coordinate_corrections": "store_coordinate_corrections",
    "store_store_official_locators": "store_official_locators", "store_store_removals_manual": "store_removals_manual"}
USED = set()
def tbl_stem(stem):
    s = unicodedata.normalize("NFKD", str(stem)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_"); return re.sub(r"_csv$", "", s)
def table_name(rel, stem):
    base = f"{prefix_for(rel)}_{tbl_stem(stem)}"[:60]; base = ALIASES.get(base, base); n, k = base, 1
    while n in USED: k += 1; n = f"{base}_{k}"
    USED.add(n); return n

def norm_path(rel):   # same as clean_catalog output path
    parts = [re.sub(r"[^a-z0-9_]+", "_", unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()) for x in rel.parts[:-1]]
    return CLEAN.joinpath(*parts, re.sub(r"[^a-z0-9_.]+", "_", unicodedata.normalize("NFKD", rel.name).encode("ascii", "ignore").decode().lower()))

# ---------- dimension maps for name overwrite on spatial attributes ----------
DIM_D = pd.read_csv(CLEAN / "dims/dim_district.csv"); DIM_N = pd.read_csv(CLEAN / "dims/dim_neighborhood.csv")
MAP_D = dict(zip(DIM_D.codi_districte, DIM_D.nom_districte)); MAP_N = dict(zip(DIM_N.codi_barri, DIM_N.nom_barri))

# ---------- type inference for CSV columns ----------
ISO_D = r"\d{4}-\d{2}-\d{2}"; DMY = r"\d{1,2}/\d{1,2}/\d{4}"
TS_TZ = r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}(:?\d{2})?)"; TS = r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?"
def infer(s, name=""):
    """Column type policy: identifiers/codes -> text; the shared keys -> integer; lat/lon/UTM -> double; everything else inferred strictly."""
    s = s.dropna().astype(str)
    if name in N.INT_KEYS:
        return ("integer" if s.str.fullmatch(r"-?\d+").all() and (s.empty or s.astype("int64").abs().max() < 2**31) else "text")
    if name in N.FLOAT_KEYS: return "double precision" if s.str.fullmatch(r"-?\d+(\.\d+)?([eE][-+]?\d+)?").all() else "text"
    if N.CODE_RX.match(name): return "text"
    if s.empty: return "date" if re.search(r"(^|_)(date|data)($|_)", name) else "text"     # all-NULL date column keeps its meaning
    if s.isin(["True", "False"]).all(): return "boolean"
    if N.is_count_name(name) and s.str.fullmatch(r"-?\d+(\.0+)?").all(): return "integer" if s.astype(float).abs().max() < 2**31 else "bigint"   # counts written as 12.0
    if s.str.fullmatch(r"-?\d+").all():
        if s.str.match(r"^-?0\d").any() or s.str.len().max() > 18: return "text"
        return "integer" if s.astype("int64").abs().max() < 2**31 else "bigint"
    if s.str.fullmatch(r"-?\d+(\.\d+)?([eE][-+]?\d+)?").all(): return "double precision"
    if s.str.fullmatch(ISO_D).all() and pd.to_datetime(s, format="%Y-%m-%d", errors="coerce").notna().all(): return "date"
    if s.str.fullmatch(DMY).all() and pd.to_datetime(s, format="%d/%m/%Y", errors="coerce").notna().all(): return "date"
    if s.str.fullmatch(TS_TZ).all(): return "timestamptz"
    if s.str.fullmatch(TS).all(): return "timestamp"
    return "text"

OSM_TABLES = {"trf_osm_roads", "hist_osm_shops", "com_plazaparc_clean"}
SOURCE_STEM = {}      # free-text tag dumps: keep as text
from shapely.validation import make_valid
from shapely.ops import unary_union
def fix_geom(g):
    if g is None or g.is_valid: return g
    v = make_valid(g)
    if v.geom_type == "GeometryCollection":
        polys = [p for p in v.geoms if p.geom_type in ("Polygon", "MultiPolygon")]
        if polys: v = unary_union(polys)
    return v

GOOD_EIX = pd.read_csv(CLEAN / "03_commercial_census/census_editions/census_2022.csv", usecols=["nom_eix"])["nom_eix"].dropna().unique().tolist()
def coerce_attrs(gdf, tname):
    """GeoJSON/GPKG properties arrive as strings: strip, NA tokens -> NULL, safe mojibake repair, then type by the same policy as CSV."""
    gname = gdf.geometry.name
    gdf = N.merge_dup_keys(gdf)
    stem = SOURCE_STEM.get(tname, "")
    if tname in OSM_TABLES:                                   # OSM tag dumps: every attribute is free text
        for c in [c for c in gdf.columns if c != gname]:
            gdf[c] = gdf[c].map(lambda v: None if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v))
        return gdf
    for c in [c for c in gdf.columns if c.startswith("sn_")]:
        gdf[c] = N.sn_to_bool(gdf[c], inverted=stem in N.SN_INVERTED_STEMS); log(f"    {tname}.{c}: -> boolean" + (" (inverted source coding)" if stem in N.SN_INVERTED_STEMS else ""))
    for c in [c for c in gdf.columns if c.startswith("data") and c != gname]:
        new, ok = N.yyyymmdd_to_iso(gdf[c])
        if ok: gdf[c] = new; log(f"    {tname}.{c}: yyyymmdd integer -> date")
    for c in [c for c in gdf.columns if c != gname]:
        if N.CODE_RX.match(c) and c not in N.INT_KEYS and pd.api.types.is_numeric_dtype(gdf[c]) and tname not in OSM_TABLES:
            v = gdf[c]; gdf[c] = v.map(lambda x: None if pd.isna(x) else (str(int(x)) if float(x).is_integer() else str(x))); continue
        if pd.api.types.is_datetime64_any_dtype(gdf[c]):        # already datetime from the reader: all-midnight -> date
            v = gdf[c].dropna()
            if len(v) and (v.dt.tz_localize(None) if getattr(v.dt, "tz", None) else v).dt.normalize().eq(v.dt.tz_localize(None) if getattr(v.dt, "tz", None) else v).all():
                gdf[c] = gdf[c].dt.date
            continue
        if c in N.INT_COLS and pd.api.types.is_float_dtype(gdf[c]): gdf[c] = gdf[c].round().astype("Int64"); continue   # integers that came back as float because of NULLs
        if N.is_count_name(c) and pd.api.types.is_float_dtype(gdf[c]) and (gdf[c].dropna() == gdf[c].dropna().round()).all():
            gdf[c] = gdf[c].round().astype("Int64"); continue                                                          # counts stored as float in the source
        if not (pd.api.types.is_object_dtype(gdf[c]) or pd.api.types.is_string_dtype(gdf[c])): continue
        s = gdf[c].astype("string").str.strip(); s = s.where(~s.isin(N.NA_TOKENS), pd.NA)
        s = s.map(lambda v: N.fix_mojibake(v) if isinstance(v, str) else v)
        if c == "nom_eix": s, nfix, nbad = N.repair_fffd(s.astype(object), GOOD_EIX); s = s.astype("string")
        s2, bad = N.stray_markers_to_na(s.astype(object), c)
        if bad: s = s2.astype("string"); log(f"    {tname}.{c}: placeholder words {bad} -> NULL")
        if tname in OSM_TABLES: gdf[c] = s.astype(object).where(s.notna(), None); continue
        ty = infer(s, c)
        if ty in ("integer", "bigint"): gdf[c] = pd.to_numeric(s, errors="coerce").astype("Int64")
        elif ty == "double precision": gdf[c] = pd.to_numeric(s, errors="coerce")
        elif ty == "boolean": gdf[c] = s.map({"True": True, "False": False}).astype("boolean")
        elif ty == "date":
            fmt = "%Y-%m-%d" if s.dropna().str.fullmatch(ISO_D).all() else "%d/%m/%Y"; gdf[c] = pd.to_datetime(s, format=fmt, errors="coerce").dt.date
        elif ty == "timestamptz": gdf[c] = pd.to_datetime(s, utc=True, errors="coerce")
        elif ty == "timestamp":
            ts = pd.to_datetime(s, errors="coerce")
            gdf[c] = ts.dt.date if (ts.dropna().dt.normalize() == ts.dropna()).all() else ts    # all midnight -> it is a date
        else: gdf[c] = s.astype(object).where(s.notna(), None)
    return gdf

LOG = open(ROOT / "data/import.log", "w", encoding="utf-8")
def log(*a):
    m = " ".join(str(x) for x in a); print(m, flush=True); LOG.write(m + "\n"); LOG.flush()

CATALOG, COLS, SKIPPED = [], [], []

def ensure_schemas():
    with psycopg.connect(CONN, autocommit=True) as c:
        for s in ("raw", ANA, "meta"): c.execute(f"DROP SCHEMA IF EXISTS {s} CASCADE"); c.execute(f"CREATE SCHEMA {s}")
        c.execute("CREATE EXTENSION IF NOT EXISTS postgis")

def load_csv(path, schema, tname, source_rel, lang):
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], low_memory=False)
    types = {c: infer(df[c], c) for c in df.columns}
    # counts written as "12.0": COPY cannot put them into an integer column -> load as double, convert after the COPY
    staged = [c for c, t in types.items() if t in ("integer", "bigint") and df[c].dropna().str.contains(".", regex=False).any()]
    ddl = ", ".join(f'"{c}" {"double precision" if c in staged else t}' for c, t in types.items())
    with psycopg.connect(CONN) as conn:
        conn.execute("SET datestyle = 'ISO, DMY'")                     # dd/mm/yyyy columns (census 2014)
        conn.execute(f'DROP TABLE IF EXISTS {schema}."{tname}" CASCADE'); conn.execute(f'CREATE TABLE {schema}."{tname}" ({ddl})')
        cols = ", ".join(f'"{c}"' for c in df.columns)
        with conn.cursor().copy(f"COPY {schema}.\"{tname}\" ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')") as cp:
            with open(path, "rb") as fh:
                while chunk := fh.read(1 << 20): cp.write(chunk)
        for c in staged: conn.execute(f'ALTER TABLE {schema}."{tname}" ALTER COLUMN "{c}" TYPE {types[c]} USING round("{c}")::{types[c]}')
        n = conn.execute(f'SELECT count(*) FROM {schema}."{tname}"').fetchone()[0]
        conn.execute(sql.SQL("COMMENT ON TABLE {} IS {}").format(sql.Identifier(schema, tname), sql.Literal(f"source: {source_rel}; language: {lang}")))
    assert n == len(df), f"{tname}: loaded {n} != {len(df)}"
    CATALOG.append((schema, tname, prefix_for(source_rel), source_rel, "csv", n, len(df.columns), None, None, None, lang))
    for c, t in types.items(): COLS.append((schema, tname, c, t))
    log(f"OK  {schema}.{tname:45s} {n:>8} rows {len(df.columns):>4} cols  {'':15s} [{lang}] <- {source_rel}")

def std_frame(gdf, lang, stem):
    K = N.KEYS[lang]; geomname = gdf.geometry.name; attr = [c for c in gdf.columns if c != geomname]
    new_attr = [c + "_attr" if c in ("geom", "geometry") else c for c in N.std_cols(attr, lang, stem)]
    gdf = gdf.rename(columns=dict(zip(attr, new_attr)))
    for code in (K["dcode"], K["bcode"]):
        if code in gdf.columns: gdf[code] = pd.to_numeric(gdf[code], errors="coerce").astype("Int64"); gdf.loc[gdf[code] <= 0, code] = pd.NA
    for code, name, mp in ((K["dcode"], K["dname"], MAP_D), (K["bcode"], K["bname"], MAP_N)):
        if code in gdf.columns and name in gdf.columns:
            new = gdf[code].map(mp); gdf[name] = new.where(new.notna(), gdf[name])
    return N.compose_section(gdf)

def load_geo(gdf, schema, tname, source_rel, orig_crs, lang):
    gdf = std_frame(gdf, lang, Path(source_rel).stem)
    SOURCE_STEM[tname] = Path(source_rel).stem.lower()
    gdf = coerce_attrs(gdf, tname)
    gdf = gdf.rename_geometry("geom")
    n_inv = int((~gdf.geometry.is_valid).sum())
    if n_inv: gdf["geom"] = gdf.geometry.map(fix_geom); gdf = gdf.set_geometry("geom"); log(f"    repaired {n_inv} invalid geometries in {tname}")
    gt_set = set(gdf.geometry.geom_type.dropna())
    if gt_set == {"Polygon", "MultiPolygon"} or gt_set == {"LineString", "MultiLineString"}:   # one geometry type per table
        from shapely.geometry import MultiPolygon, MultiLineString
        gdf["geom"] = gdf.geometry.map(lambda g: MultiPolygon([g]) if g is not None and g.geom_type == "Polygon" else (MultiLineString([g]) if g is not None and g.geom_type == "LineString" else g))
        gdf = gdf.set_geometry("geom"); log(f"    {tname}: promoted to a single Multi* geometry type")
    if gdf.crs is None: raise ValueError("no CRS")
    gdf = gdf.to_crs(SRID)
    with ENGINE.begin() as c: c.execute(text(f'DROP TABLE IF EXISTS {schema}."{tname}" CASCADE'))
    gdf.to_postgis(tname, ENGINE, schema=schema, if_exists="replace", index=False)
    with psycopg.connect(CONN, autocommit=True) as cc:
        for (col,) in cc.execute("select column_name from information_schema.columns where table_schema=%s and table_name=%s and data_type='bigint'", (schema, tname)).fetchall():
            mx = cc.execute(sql.SQL("select max(abs({}::numeric)) from {}").format(sql.Identifier(col), sql.Identifier(schema, tname))).fetchone()[0]
            if mx is None or mx < 2**31: cc.execute(sql.SQL("alter table {} alter column {} type integer").format(sql.Identifier(schema, tname), sql.Identifier(col)))
    with ENGINE.begin() as c:
        n = c.execute(text(f'SELECT count(*) FROM {schema}."{tname}"')).scalar()
        gt = c.execute(text(f"SELECT coalesce(max(GeometryType(geom)),'') FROM {schema}.\"{tname}\"")).scalar()
        cols = c.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema=:s AND table_name=:t ORDER BY ordinal_position"), {"s": schema, "t": tname}).fetchall()
    with psycopg.connect(CONN, autocommit=True) as cc:
        cc.execute(sql.SQL("COMMENT ON TABLE {} IS {}").format(sql.Identifier(schema, tname), sql.Literal(f"source: {source_rel}; language: {lang}; original CRS {orig_crs}; geom reprojected to EPSG:{SRID}")))
    assert n == len(gdf), f"{tname}: loaded {n} != {len(gdf)}"
    CATALOG.append((schema, tname, prefix_for(source_rel), source_rel, "spatial", n, len(cols), gt, SRID, str(orig_crs), lang))
    for cn, dt in cols: COLS.append((schema, tname, cn, dt))
    log(f"OK  {schema}.{tname:45s} {n:>8} rows {len(cols):>4} cols  {gt:15s} [{lang}] <- {source_rel}")

def read_spatial(f):
    ext = f.suffix.lower()
    return gpd.read_file(f, encoding="cp1252") if ext == ".shp" else gpd.read_file(f)

def fix_mojibake(s):
    return s.encode("cp1252", errors="ignore").decode("utf-8", errors="ignore") if isinstance(s, str) else s

def main():
    ensure_schemas()
    # ---------- 1. CSV ----------
    FR = pd.read_csv(CLEAN / "FILE_REPORT.csv"); LANG_OF = dict(zip(FR.clean_file, FR.language))
    skip_csv = {"housing/barcelonaciutat_seccionscensals.csv": "superseded by _fixed version (same data, within-district codes)"}
    for f in sorted(CLEAN.rglob("*.csv")):
        if f.name.startswith(("COLUMN_", "FILE_")) or "dims" in f.parts: continue
        if f.name == "manifest.csv": SKIPPED.append(("MANIFEST.csv", "file inventory, not data")); continue
        rel = f.relative_to(CLEAN); relposix = str(rel).replace("\\", "/")
        if any(relposix.endswith(k) for k in skip_csv): SKIPPED.append((relposix, skip_csv[[k for k in skip_csv if relposix.endswith(k)][0]])); continue
        if relposix.startswith("01_stores") and f.name not in ("barcelona_supermarkets_official.csv", "ring_stores_2km.csv", "store_coordinate_corrections.csv", "store_official_locators.csv", "store_removals_manual.csv"):   # scraped store lists are raw input
            schema, tname = ANA, "py_" + tbl_stem(f.stem)          # derived by our Python pipeline
        else:
            schema, tname = "raw", table_name(relposix, f.stem)
        try: load_csv(f, schema, tname, relposix, LANG_OF.get(relposix, "en"))
        except Exception as e: log("FAIL", relposix, repr(e)[:200]); traceback.print_exc(file=LOG)
    for f in sorted((CLEAN / "dims").glob("*.csv")):
        try: load_csv(f, ANA, f.stem, "dims/" + f.name, "en")
        except Exception as e: log("FAIL", f, repr(e)[:200])
    # ---------- 2. spatial layers ----------
    keep = {  # file (relative to data_catalog) -> why imported
        "03_commercial_census/census_2019_geojson/2019_censcomercialbcn_detall.geojson": 1,
        "03_commercial_census/parc_plaza/plazaparc_clean.geojson": 1,
        "04_transport_traffic/public_transport/accessos.geojson": 1, "04_transport_traffic/public_transport/corresp_parades.geojson": 1,
        "04_transport_traffic/public_transport/estacions_metro.geojson": 1, "04_transport_traffic/public_transport/intercs.geojson": 1,
        "04_transport_traffic/public_transport/linies_bus.geojson": 1, "04_transport_traffic/public_transport/parades.geojson": 1,
        "05_built_environment_planning/pgm/pgm_qualif_polygons.gpkg": 1,
        "05_built_environment_planning/cadastre/inspire_buildings/inspire_buildings.gpkg": 1,
        "04_transport_traffic/streets/streets_pacified_2020_2022.gpkg": 1, "04_transport_traffic/streets/streets_pedestrian_priority_2023_2026.gpkg": 1,
        "06_admin_boundaries/geo_units/0301100100_UNITATS_ADM_POLIGONS.json": 1, "06_admin_boundaries/geo_units/0301100100_UNITATS_ADM_PUNTS.json": 1,
        "08_tourism_other/tourism/2017_huts_illa.gpkg": 1, "08_tourism_other/tourism/2019_turisme_allotjament.gpkg": 1}
    why = {"barcelona_supermarkets_official.geojson": "duplicate of the store CSV (lat/lon)", "barcelona_transit_other.geojson": "duplicate of barcelona_transit_stations.csv",
           "other.geojson": "duplicate of barcelona_transit_stations.csv", "plazaparc.geojson": "superseded by plazaparc_clean (910 rows, deduplicated, bus stops removed)",
           "Barri.geojson": "QGIS-joined derivative of official admin units (imported once as adm_units_polygons)", "DSITRI.geojson": "QGIS derivative of official admin units",
           "SCensal.geojson": "QGIS-joined derivative of official admin units"}
    for f in sorted(CAT.rglob("*")):
        if f.suffix.lower() not in (".geojson", ".gpkg", ".shp", ".json") or f.is_dir(): continue
        rel = str(f.relative_to(CAT)).replace("\\", "/")
        if f.name in ("osm_roads.json", "osm_shops.json") or "pgm_tematic" in rel: continue
        if rel in keep:
            try:
                g = read_spatial(f); oc = g.crs
                if f.suffix.lower() == ".json" and "UNITATS_ADM_POLIGONS" in f.name: g = g[g.geometry.notna()]
                load_geo(g, "raw", table_name(rel, f.stem), rel, oc, GEO_LANG.get(f.name, "ca"))
            except Exception as e: log("FAIL", rel, repr(e)[:300]); traceback.print_exc(file=LOG)
        else: SKIPPED.append((rel, why.get(f.name, "QGIS derived copy (_copy/_trimmed); same content as an imported official layer")))
    # ---------- 3. OSM roads / shops ----------
    try:
        from shapely.geometry import LineString, Point
        R = json.load(open(CAT / "04_transport_traffic/traffic_vehicles_roads/osm_roads.json", encoding="utf-8"))["elements"]
        rows = [dict(osm_id=e["id"], highway=e["tags"].get("highway"), name=e["tags"].get("name"), lanes=e["tags"].get("lanes"), maxspeed=e["tags"].get("maxspeed"),
                     oneway=e["tags"].get("oneway"), geometry=LineString([(p["lon"], p["lat"]) for p in e["geometry"]])) for e in R if len(e.get("geometry", [])) >= 2]
        load_geo(gpd.GeoDataFrame(rows, crs=4326), "raw", "trf_osm_roads", "04_transport_traffic/traffic_vehicles_roads/osm_roads.json", "EPSG:4326 (Overpass)", "en")
        S = json.load(open(CAT / "07_opening_history/osm_shops.json", encoding="utf-8"))
        rows = []
        for e in S:
            lat = e.get("lat") or e.get("center", {}).get("lat"); lon = e.get("lon") or e.get("center", {}).get("lon")
            if lat is None: continue
            t = e.get("tags", {}); rows.append(dict(osm_type=e["type"], osm_id=e["id"], name=t.get("name"), brand=t.get("brand"), shop=t.get("shop"), start_date=t.get("start_date"), check_date=t.get("check_date"), tags=json.dumps(t, ensure_ascii=False), geometry=Point(lon, lat)))
        load_geo(gpd.GeoDataFrame(rows, crs=4326), "raw", "hist_osm_shops", "07_opening_history/osm_shops.json", "EPSG:4326 (Overpass)", "en")
    except Exception as e: log("FAIL osm", repr(e)[:300]); traceback.print_exc(file=LOG)
    # ---------- 4. PGM label points (street width / volumetric text only) ----------
    try:
        p = gpd.read_file("zip://" + str(CAT / "05_built_environment_planning/pgm/pgm_qualif.zip"), layer="0702060100_BCN_Planejament_Urb_PUNTS_V", encoding="cp1252", columns=["ELEM_DESCR", "LITERAL", "TEXT_AUX"])
        p["ELEM_DESCR"] = p.ELEM_DESCR.map(fix_mojibake)
        p = p[p.ELEM_DESCR.str.contains("Cota d'ample|volum", na=False)].rename(columns={"ELEM_DESCR": "label_type", "LITERAL": "label"})
        p["label_type"] = np.where(p.label_type.str.contains("Cota", na=False), "street_width", "volumetric")
        load_geo(p, "raw", "pgm_label_points", "05_built_environment_planning/pgm/pgm_qualif.zip (PUNTS shapefile, street-width + volumetric labels only)", "EPSG:25831", "en")
    except Exception as e: log("FAIL pgm points", repr(e)[:300]); traceback.print_exc(file=LOG)
    # ---------- 5. metadata ----------
    with psycopg.connect(CONN) as conn:
        for t in ("tables", "columns", "skipped_files"): conn.execute(f"DROP TABLE IF EXISTS meta.{t}")
        conn.execute("CREATE TABLE meta.tables (table_schema text, table_name text, theme text, source_file text, kind text, n_rows bigint, n_cols int, geom_type text, srid int, original_crs text, language text, loaded_at timestamptz DEFAULT now())")
        conn.execute("CREATE TABLE meta.columns (table_schema text, table_name text, column_name text, data_type text)")
        conn.execute("CREATE TABLE meta.skipped_files (source_file text, reason text)")
        conn.cursor().executemany("INSERT INTO meta.tables (table_schema,table_name,theme,source_file,kind,n_rows,n_cols,geom_type,srid,original_crs,language) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", CATALOG)
        conn.cursor().executemany("INSERT INTO meta.columns VALUES (%s,%s,%s,%s)", COLS)
        conn.cursor().executemany("INSERT INTO meta.skipped_files VALUES (%s,%s)", SKIPPED)
    # ---------- 6. derived tables of schema ana: dbt project dbt_bcn (models/ana), rebuilt on every run ----------
    # (dbt.cmd turns off the dbt Cloud "state" login and uses .venv-dbt; dbt also runs the tests and the type harmonisation)
    # the gis visualisation layers (tag after_python) need the tables of build_food_access.py and are built at the end of that script
    r = subprocess.run(["cmd", "/c", str(ROOT / "dbt_bcn" / "dbt.cmd"), "build", "--exclude", "tag:after_python"], cwd=ROOT / "dbt_bcn", capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in r.stdout.splitlines():
        if any(k in line for k in ("OK created", "ERROR", "FAIL", "WARN ", "Done.")): log("dbt", line.strip())
    log(f"dbt build {'OK' if r.returncode == 0 else 'FAILED (exit %d)' % r.returncode}")
    log(f"\nDONE: {len(CATALOG)} tables loaded, {len(SKIPPED)} files skipped")

if __name__ == "__main__":
    t0 = time.time(); main(); log(f"elapsed {time.time()-t0:.0f}s")
