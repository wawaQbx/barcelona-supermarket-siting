"""Database quality check of supermarket_bcn - run after every rebuild (after make_catalog.py).
Checks: (1) every table has a description (COMMENT); (2) geometry columns are typed, in EPSG:25831 and valid; (3) primary keys of the derived tables
(ana, gis) and duplicate keys; (4) shared keys hold valid codes (1068 census sections, 73 barris, 10 districts); (5) totals reconcile across tables
(population, city stores, openings); (6) value ranges (shares 0-100, no negative counts, location quotients > 0); (7) type audit (meta.type_audit);
(8) raw import completeness (rows now = rows at import, skipped files); (9) natural keys of raw tables unique; (10) missing shared keys in raw
tables; (11) every table in the Excel catalogs; (12) dbt tests; (13) the independent re-verification (verify_independent.py). Writes docs/quality_check.csv and prints a summary; exit code 1 if a check FAILS (WARN = expected / documented, see the detail column).
"""
import subprocess, sys
from pathlib import Path
import pandas as pd, psycopg

ROOT = Path(__file__).parent
CONN = "host=localhost port=5432 dbname=supermarket_bcn user=postgres"   # password from pgpass.conf
SCHEMAS = ("raw", "ana", "gis")
POPULATION = 1729963          # Padro 2026-01-01, official total
EXPECTED_MISSING_KEYS = {   # raw tables where missing section / barri codes are by design (reason)
    "adm_units_polygons": "other unit types (district, AEB, city ...) have no section / barri code",
    "adm_units_points": "other unit types have no section / barri code",
    "hou_contractes_lloguer_anual": "city- and district-level rows (column nivell)",
    "store_supermarkets_official": "stores outside Barcelona (0 missing inside the city)",
    "rel_religious_facilities": "37 entries without coordinates in the source (not used by any analysis)",
    "trf_aforament_desc_2025": "62 stations without barri code in the source; gis.traffic_counters takes it from the barri polygon"}
NO_PK_OK = {"factor_labels", "chain_list_sources", "gtfs_service_day", "store_points_excluded", "store_group_membership", "store_site_premises_panel", "store_site_premises_by_type",
            "site_buildings", "traditional_food_shops_2024", "dim_district", "dim_neighborhood", "chain_colours"}   # chain_colours: dbt seed, brand_group unique-tested   # long / helper tables, keys tested by dbt or not needed
rows = []
def add(check, status, detail): rows.append(dict(check=check, status=status, detail=str(detail)[:400]))

with psycopg.connect(CONN) as c:
    Q = lambda s, p=None: c.execute(s, p).fetchall()
    tabs = Q("select table_schema, table_name from information_schema.tables where table_schema = any(%s) and table_type = 'BASE TABLE'", (list(SCHEMAS),))
    # (1) descriptions
    missing = [f"{s}.{t}" for s, t in tabs if not Q("select obj_description(%s::regclass)", (f'{s}."{t}"',))[0][0]]
    add("table descriptions", "OK" if not missing else "FAIL", f"{len(tabs)} tables; without comment: {missing}")
    # (2) geometry
    g = Q("select f_table_schema, f_table_name, f_geometry_column, type, srid from geometry_columns where f_table_schema = any(%s)", (list(SCHEMAS),))
    bad = [f"{s}.{t} ({ty}, {srid})" for s, t, col, ty, srid in g if srid != 25831 or ty == "GEOMETRY"]
    add("geometry typed, EPSG:25831", "OK" if not bad else "FAIL", f"{len(g)} geometry columns; not typed / other SRID: {bad}")
    inv = []
    for s, t, col, ty, srid in g:
        n = Q(f'select count(*) from {s}."{t}" where {col} is not null and not ST_IsValid({col})')[0][0]
        if n: inv.append(f"{s}.{t}: {n}")
    add("geometry valid", "OK" if not inv else "WARN", f"invalid geometries: {inv}" if inv else "all valid")
    # (3) primary keys of derived tables
    pk = {t for s, t in Q("""select n.nspname, c.relname from pg_constraint k join pg_class c on c.oid = k.conrelid join pg_namespace n on n.oid = c.relnamespace
                             where k.contype = 'p' and n.nspname in ('ana', 'gis')""")}
    nopk = sorted(t for s, t in tabs if s in ("ana", "gis") and t not in pk and t not in NO_PK_OK and not t.startswith("py_"))
    add("primary keys (ana, gis)", "OK" if not nopk else "WARN", f"{len(pk)} tables with a primary key; without (not in the expected list): {nopk}")
    # (4) shared keys hold valid codes
    valid_sec = {r[0] for r in Q("select seccio_censal from raw.adm_units_polygons where tipus_ua = 'SEC_CENS'")}
    bad = []
    for s, t in tabs:
        if s == "raw": continue
        cols = {r[0] for r in Q("select column_name from information_schema.columns where table_schema = %s and table_name = %s", (s, t))}
        if "seccio_censal" in cols:
            n = Q(f'select count(*) from {s}."{t}" where seccio_censal is not null and not (seccio_censal = any(%s))', (list(valid_sec),))[0][0]
            if n: bad.append(f"{s}.{t}.seccio_censal: {n}")
        if "codi_barri" in cols:
            n = Q(f'select count(*) from {s}."{t}" where codi_barri is not null and codi_barri not between 1 and 73')[0][0]
            if n: bad.append(f"{s}.{t}.codi_barri: {n}")
        if "codi_districte" in cols:
            n = Q(f'select count(*) from {s}."{t}" where codi_districte is not null and codi_districte not between 1 and 10')[0][0]
            if n: bad.append(f"{s}.{t}.codi_districte: {n}")
    add("shared keys hold valid codes", "OK" if not bad else "FAIL", bad or f"{len(valid_sec)} census sections; all keys valid")
    # (5) totals reconcile
    pops = {t: Q(q)[0][0] for t, q in {
        "raw.pop_2026_pad_base": "select sum(habitants_n) from raw.pop_2026_pad_base",
        "ana.pop_age_bands_section": "select sum(pop_official_n) from ana.pop_age_bands_section",
        "ana.section_model_table": "select sum(population_n) from ana.section_model_table",
        "ana.barri_model_table": "select sum(population_n) from ana.barri_model_table",
        "ana.pop_nationality_section": "select sum(population_2026_n) from ana.pop_nationality_section",
        "gis.section_indicators": "select sum(population_n) from gis.section_indicators",
        "gis.barri_indicators": "select sum(population_n) from gis.barri_indicators"}.items()}
    add("population totals", "OK" if set(pops.values()) == {POPULATION} else "FAIL", pops)
    st = {"ana.store_points in_city": Q("select count(*) from ana.store_points where in_city")[0][0],
          "gis.stores in_city": Q("select count(*) from gis.stores where in_city")[0][0],
          "ana.store_list_validation": Q("select count(*) from ana.store_list_validation")[0][0]}
    inside = Q("select sum(stores_all_n) from gis.section_indicators")[0][0]; inside_b = Q("select sum(stores_all_n) from gis.barri_indicators")[0][0]
    ok = len(set(st.values())) == 1 and inside == inside_b and st["gis.stores in_city"] - inside <= 2
    add("city store totals", "OK" if ok else "FAIL", f"{st}; inside a section polygon {inside}, inside a barri polygon {inside_b} (stores on the boundary line count as in the city but in no polygon)")
    op = {"ana.store_openings (excl. Clarel)": Q("select count(*) from ana.store_openings where opening_type <> 'clarel_conversion'")[0][0],
          "gis.section_indicators": Q("select sum(openings_2016_2024_n) from gis.section_indicators")[0][0],
          "gis.barri_indicators": Q("select sum(openings_2016_2024_n) from gis.barri_indicators")[0][0]}
    add("openings totals", "OK" if max(op.values()) - min(op.values()) <= 2 else "FAIL", op)
    dated = Q("select count(*) filter (where first_seen_census_year is not null), count(*) from ana.store_points where in_city")[0]
    add("store dating coverage", "OK" if dated[0] / dated[1] >= 0.85 else "WARN", f"{dated[0]} of {dated[1]} city stores dated ({100 * dated[0] / dated[1]:.1f}%)")
    # one store, several points (user rule 2026-10-16): same chain within 40 m, or two chains within 10 m (a sign change listed twice)
    near = Q("""select a.ensenya || ' / ' || b.ensenya || ' ' || round(st_distance(a.geom, b.geom)) || ' m @ ' ||
                       round(st_y(st_transform(a.geom, 4326))::numeric, 5) || ',' || round(st_x(st_transform(a.geom, 4326))::numeric, 5)
                from ana.store_points a join ana.store_points b on a.store_id < b.store_id
                 and ((a.brand_group = b.brand_group and st_dwithin(a.geom, b.geom, 40)) or (a.brand_group <> b.brand_group and st_dwithin(a.geom, b.geom, 10)))""")
    # reviewed and kept (outside the city, no census to decide; both official locators list a store there, the Dia list dates from 2026-06 and Dia is closing
    # stores, so the Dia point is the likely stale one): Condis / Dia Badalona Av. Sant Salvador 32-34; Charter / Dia L'Hospitalet 41.36953, 2.10201
    REVIEWED = {"Condis / Dia", "Charter / Dia"}
    open_ = [r[0] for r in near if r[0].split(" ")[0] + " / " + r[0].split(" / ")[1].split(" ")[0] not in REVIEWED]
    add("one store = one point", "OK" if not open_ else "FAIL", f"close pairs to review: {open_}; reviewed and kept: {[r[0] for r in near if r[0] not in open_]}")
    # (6) value ranges
    bad = []
    for s, t in tabs:
        if s == "raw": continue
        for (col, dt) in Q("select column_name, data_type from information_schema.columns where table_schema = %s and table_name = %s and data_type in ('integer', 'double precision')", (s, t)):
            if col.endswith("_pct") and not any(k in col for k in ("growth", "change", "_cv_")):
                n = Q(f'select count(*) from {s}."{t}" where "{col}" < 0 or "{col}" > 100.0001')[0][0]
                if n: bad.append(f"{s}.{t}.{col} outside 0-100: {n}")
            elif col.endswith("_n") or col.endswith("_est"):
                n = Q(f'select count(*) from {s}."{t}" where "{col}" < 0')[0][0]
                if n: bad.append(f"{s}.{t}.{col} negative: {n}")
            elif col.endswith("_location_quotient"):
                n = Q(f'select count(*) from {s}."{t}" where "{col}" <= 0')[0][0]
                if n: bad.append(f"{s}.{t}.{col} <= 0: {n}")
    add("value ranges (derived tables)", "OK" if not bad else "FAIL", bad or "shares within 0-100, no negative counts, location quotients > 0")
    # (7) type audit
    ta = Q("select severity, problem, count(*) from meta.type_audit group by 1, 2")
    other = [x for x in ta if not x[1].startswith("source-damaged")]
    add("type audit", "OK" if not other else "FAIL", f"{ta} (source-damaged text = bytes lost in the original file, documented, not recoverable)")

    # (8) raw import completeness
    mt = Q("select table_schema, table_name, n_rows from meta.tables")
    diff = [f"{s}.{t}: {n} at import, {Q(f'select count(*) from {s}.' + chr(34) + t + chr(34))[0][0]} now" for s, t, n in mt
            if Q(f'select count(*) from {s}.' + chr(34) + t + chr(34))[0][0] != n]
    sk = Q("select count(*) from meta.skipped_files")[0][0]
    add("raw import complete", "OK" if not diff else "FAIL", f"{len(mt)} imported tables, row counts unchanged since import: {not diff} {diff}; {sk} files skipped by design (meta.skipped_files)")
    # (9) natural keys of raw tables
    KEYS = {"raw.pop_2026_pad_base": "seccio_censal", "raw.cen_census_2024": "id_global", "raw.cen_census_2022": "id_global", "raw.gtfs_stops": "stop_id",
            "raw.cad_inspire_buildings": "referencia_cadastral", "raw.store_supermarkets_official": "ensenya, adreca, lat, lon", "raw.adm_census_section_lookup": "seccio_censal",
            "raw.tou_airbnb_listings_2026_09": "listing_id", "raw.tou_hut_comunicacio_2026_1t": "n_expedient", "raw.trf_aforament_desc_2025": "id_aforament"}
    dup = {k: Q(f"select count(*) from (select {v} from {k} group by {v} having count(*) > 1) x")[0][0] for k, v in KEYS.items()}
    add("natural keys unique (raw)", "OK" if not any(dup.values()) else "WARN", {k: v for k, v in dup.items()})
    # (10) missing shared keys in raw tables
    miss = []
    for s, t in tabs:
        if s != "raw": continue
        cols = {r[0] for r in Q("select column_name from information_schema.columns where table_schema = %s and table_name = %s", (s, t))}
        for k in ("seccio_censal", "codi_barri"):
            if k in cols:
                n, tot = Q(f'select count(*) filter (where {k} is null), count(*) from raw."{t}"')[0]
                if tot and n / tot > 0.01: miss.append((t, f"raw.{t}.{k}: {n} of {tot} NULL"))
    unexpected = [m for tb, m in miss if tb not in EXPECTED_MISSING_KEYS]
    expected = sorted({f"{tb} ({EXPECTED_MISSING_KEYS[tb]})" for tb, m in miss if tb in EXPECTED_MISSING_KEYS})
    add("shared keys filled (raw)", "OK" if not unexpected else "WARN", f"unexpected: {unexpected}; expected by design: {expected}")

# (11) every table in the catalogs
cat = pd.read_excel(ROOT / "docs" / "data_catalog_supermarket_bcn.xlsx", sheet_name=None)
names = set()
for df_ in cat.values():
    if "table" in df_.columns: names |= set(df_["table"].astype(str))
missing = sorted(f"{s}.{t}" for s, t in tabs if f"{s}.{t}" not in names)
add("tables in the English catalog", "OK" if not missing else "FAIL", missing or f"all {len(tabs)} tables listed")
zh = ROOT / "docs" / "data_catalog_supermarket_bcn_ZH.xlsx"
names_zh = set()
for df_ in pd.read_excel(zh, sheet_name=None).values():
    for col in df_.columns:
        names_zh |= set(df_[col].astype(str))
missing = sorted(f"{s}.{t}" for s, t in tabs if f"{s}.{t}" not in names_zh)
add("tables in the Chinese catalog", "OK" if not missing else "FAIL", missing or f"all {len(tabs)} tables listed")

# (12) dbt tests
r = subprocess.run(["cmd", "/c", str(ROOT / "dbt_bcn" / "dbt.cmd"), "test"], cwd=ROOT / "dbt_bcn", capture_output=True, text=True, encoding="utf-8", errors="replace")
done = [l.strip() for l in r.stdout.splitlines() if "Done." in l]
add("dbt tests", "OK" if r.returncode == 0 else "FAIL", done[-1] if done else r.stdout[-300:])
# (13) independent re-verification (different method from audit_types.py)
r = subprocess.run([sys.executable, str(ROOT / "verify_independent.py")], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
summ = [l.strip() for l in r.stdout.splitlines() if l.startswith("===") or l.startswith("columns checked")]
add("independent re-verification", "OK" if r.returncode == 0 else "FAIL", " | ".join(summ) + " (reviewed 2026-10-15: type findings = codes kept as text by policy (seccio_censal_orig, stop_code, store codes, feed_version); naming = postal-code columns already named codi_postal, an OSM tag and a multi-level name column; details: data/verify_types.csv, data/verify_naming.csv)")

df = pd.DataFrame(rows); df.to_csv(ROOT / "docs" / "quality_check.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 180)
print(df.to_string(index=False))
print("\nRESULT:", "FAIL" if (df.status == "FAIL").any() else ("OK with warnings" if (df.status == "WARN").any() else "OK"))
sys.exit(1 if (df.status == "FAIL").any() else 0)
