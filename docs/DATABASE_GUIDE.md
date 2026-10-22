# Database guide - where is what, and how to find it

Goal: explain why each supermarket chain opens where it does in Barcelona (city only, 676 stores). Everything lives in
a PostgreSQL + PostGIS database (`supermarket_bcn`, localhost:5432, program and data in `D:\PostgreSQL`) and in this folder.

## 1. Find a table (start here)

1. Open **`docs/data_catalog_supermarket_bcn.xlsx`** (Chinese version: `docs/data_catalog_supermarket_bcn_ZH.xlsx`).
   - Sheet `tables`: one row per table (category, content, what one row is, rows, columns, key columns, **notes**, source file).
     Use the filter arrows on the header: filter `category`, read `content` and `notes`, copy the value of `table`.
   - Sheet `harmonised_names`: the shared column names (codi_barri, seccio_censal ...) and their old names.
   - Sheet `all_columns`: every column with its data type. Sheet `not_imported`: files that were left out and why.
2. Open **DBeaver** -> connection `supermarket_bcn` -> `Databases > supermarket_bcn > Schemas > raw | ana | meta > Tables`.
   Double-click a table, tab `Data` shows rows, tab `Properties` shows columns.
3. Or in a SQL editor: `SELECT * FROM raw.pop_2026_pad_base LIMIT 100;` (schema.table, as written in the catalog).
4. Ask the database itself: `SELECT * FROM meta.tables ORDER BY table_schema, table_name;` and
   `SELECT column_name, data_type FROM meta.columns WHERE table_name = '<table>';`

Schemas: `raw` = imported source data (never edited) - `ana` = tables we derive (stores, dimensions, transit service) - `meta` = catalog and audit.

## 2. Folder map

| Folder / file | What it is |
|---|---|
| `docs/` | The data catalogs (Excel, English + Chinese snapshot), `PROJECT_REPORT.md` (status, findings, decisions), `CENSUS_GUIDE.md` (how to read the commercial census tables), `MODEL_RESULTS.md` + `model_*.csv` (siting models v1 and v2). |
| `data_catalog/` | All input files copied from the QGIS folder and from downloads, grouped by theme (`01_stores` ... `08_tourism_other`). `MANIFEST.csv` lists each file and where it came from. |
| `data_clean/` | The same CSV files after cleaning (UTF-8, harmonised names and types). `COLUMN_DICTIONARY.csv` = old name -> new name per file; `FILE_REPORT.csv` = what was changed per file; `dims/` = district and barri lookups. |
| `data/` | Working files: raw downloads (`raw/`), Bon Preu / Condis / Consum archives, logs (`import.log`), audit outputs (`type_audit.csv`), ad-hoc SQL checks. |
| `gis` schema (dbt `models/gis`) | VISUALISATION layers for QGIS and the dashboard: section / barri boundaries with indicators, stores, markets. Curated copies of `ana` tables - not for modelling. Rebuilt at the end of `build_food_access.py`. Design and column choice: `docs/DASHBOARD_DESIGN.md`. |
| `sql/legacy_pre_dbt/` | The 13 old derived-table SQL scripts, kept only for reference: since 2026-10-15 the derived tables of schema `ana` are dbt models (`dbt_bcn/models/ana`). Not executed any more. |
| `bcn_naming.py` | **All naming and typing rules** in one place. |
| `clean_catalog.py` -> `import_all.py` -> `audit_types.py` | The rebuild pipeline (see section 3). |
| `check_quality.py` | Database quality check after every rebuild (descriptions, geometry, keys, codes, totals, ranges, import completeness, catalogs, dbt tests, independent re-verification) -> `docs/quality_check.csv`. |
| `make_catalog.py` | Rebuilds `docs/data_catalog_supermarket_bcn.xlsx` from the live database. |
| `fetch_ring_stores.py`, `fetch_ring_osm.py` | Stores in the 2 km ring around the city (official locators + OSM). |
| `fetch_streets_prices.py` | Pacified / pedestrian-priority streets and premises prices 2008-2011 (Open Data BCN). |
| `check_store_addresses.py` | Address check of the store list against the 2024 census; writes the coordinate corrections used by the dbt model `int_store_points_base` (re-run only when the store list changes). |
| `build_food_access.py` | Walking distance and slope-aware minutes (Copernicus terrain, Tobler) from every residential building to supermarkets, markets and fresh food. |
| `food_desert_viability.py` | Catchment of existing stores vs the food-desert areas (why no supermarket opens there) for the flagged page-04 sections -> `docs/food_desert_viability.csv`, `ana.py_food_desert_viability`, dbt `gis.food_desert_viability`. Run after build_food_access.py. |
| `fetch_airbnb.py` | Inside Airbnb Barcelona snapshot (listings + reviews per year; host data not kept) -> `data_catalog/08_tourism_other/tourism/`. |
| `export_dashboard_boundaries.py` | Section and barri boundaries as simplified WGS84 GeoJSON (keys + names only) for Power BI / Tableau maps -> `dashboard/boundaries/`. |
| `analyze_tourism_markets.py` | v7: tourism and store formats, foreign residents, municipal markets -> `docs/model_v7_*.csv` (run after `analyze_siting.py`). |
| `prepare_inspire_buildings.py` | Cadastre INSPIRE buildings zip -> compact `inspire_buildings.gpkg` (run once after downloading; imported as `raw.cad_inspire_buildings`). |
| `scraper.py`, `scrape_transit.py`, `bonpreu_history.py`, `fetch_*.py` (incl. `fetch_history.py`: Padro 2007-2026, income 2015-2023, nationality 2015 + 2026) | Data collection from official websites / open-data portals / OSM. |
| `census_panel.py`, `build_store_features.py`, `build_barri_features.py`, `merge_features.py`, `add_municipi.py` | The store-feature pipeline (writes the `stores_*.csv` and `barri_features.csv` loaded as `ana.py_*`). |
| `verify_independent.py` | A second, independent data check (values, not names). |
| `analyze_siting.py` | Siting models per chain, section and barri: v1 Poisson by outcome definition, v2 clustered errors + competition + vacancy + Moran residual check, v3 format split + own vs other chains + openings 2016-2024, v4 cadastre / traffic blocks + time ordering + event study + L10 natural experiment -> `docs/model_*.csv`. |
| `.venv/` | Python environment. |
| `dbt_bcn/`, `.venv-dbt/` | **dbt project that builds every derived SQL table of schema `ana`** (dbt-core 1.12 + dbt-postgres on Python 3.11): `models/ana/` (transit, population, stores, time, model_tables; 25 tables) read the raw tables through `models/sources.yml`; `models/intermediate/` = helper tables shared by several models (schema `dbt_int`, replaces the old TEMP tables); `macros/` = schema naming, primary keys, type harmonisation (on-run-end); `models/staging` + `models/marts` = the learning example (schema `dbt`). `import_all.py` runs `dbt build` at its end. Run it by hand inside `dbt_bcn` with `.\dbt build` (all) or `.\dbt build --select store_points+` (one model and everything downstream). `dbt.cmd` sets DBT_ENGINE_MANAGE_STATE=false so dbt 1.12 does not ask for a dbt State / Cloud browser login. |

Where the original data is: `D:\QGIS..44\projects\barcelona` (untouched). Nothing in this project reads it any more except a few one-off historical scripts.

## 3. Rebuild the whole database (about 15 minutes)

```
.venv\Scripts\python.exe clean_catalog.py       # data_catalog -> data_clean
.venv\Scripts\python.exe import_all.py          # data_clean + spatial files -> PostgreSQL (drops and recreates raw, ana, meta; then runs dbt build = all ana tables + tests)
.venv\Scripts\python.exe build_food_access.py   # walking access (ana.py_*_food_access), then rebuilds the gis visualisation layers
.venv\Scripts\python.exe audit_types.py         # type / value audit -> meta.type_audit
.venv\Scripts\python.exe make_catalog.py        # refresh the Excel catalog
.venv\Scripts\python.exe check_quality.py       # 15 database checks + dbt tests + independent re-verification -> docs/quality_check.csv
.venv\Scripts\python.exe analyze_siting.py      # models v1-v6 -> docs/model_*.csv
.venv\Scripts\python.exe analyze_tourism_markets.py   # v7 tourism / foreign residents / markets -> docs/model_v7_*.csv
```
Downloads are separate and only needed to refresh the inputs: `fetch_history.py`, `fetch_streets_prices.py`, `fetch_ring_stores.py` + `fetch_ring_osm.py`,
the cadastre INSPIRE zip + `prepare_inspire_buildings.py`.
Change a rule in `bcn_naming.py`, run the first three again. Never edit tables by hand: the next rebuild overwrites them.
The password is read from `%APPDATA%\postgresql\pgpass.conf`; no secret is stored in this folder.

## 4. Conventions

- Column names: lowercase ascii snake_case. Shared concepts have one Catalan name in every table
  (`codi_districte`, `nom_districte`, `codi_barri`, `nom_barri`, `seccio_censal`, `any_`, `data_revisio`, `total_poblacio`, `municipi`);
  other columns keep the language of their source table; GTFS keeps the international English names.
- `seccio_censal` = district x 1000 + section inside the district (1001-10237).
- Types: codes / ids / postal codes are text; counts, people and years are integer (also when the source writes 12.0); continuous measures (rates, shares, money, distances, areas) are double precision (no numeric); dates are date (year-months as the first day of the month); yes/no flags are boolean. Exceptions: OSM free-text tags, estimated (fractional) counts `*_estimated_n`, mean values `*_mean_n`, the mixed-unit column `hou_2026_locals_us_desti.nombre`. `sql/ana_zz_type_harmonisation.sql` enforces this on the derived tables; `audit_types.py` flags any other mismatch.
- Geometry column `geom` is always EPSG:25831 (metres). `lat` / `lon` are WGS84 degrees. The 2014 census only has ED50 (EPSG:23031).

## 5. Most used tables

`ana.store_points` (one row per store; `in_city` = the 676 city stores) - `gis.stores` (the same with display labels) - `ana.dim_neighborhood` / `ana.dim_district` -
`raw.adm_units_polygons` (filter `tipus_ua`) - `raw.pop_2026_pad_base` - `raw.inc_2022_renda_disponible_llars_per_persona` -
`ana.gtfs_stop_service` - `raw.cen_census_2024` (see `docs/CENSUS_GUIDE.md`) - `ana.pop_age_bands_section`, `ana.pop_education_section`, `ana.motorization_section` (corrected versions: use these instead of the QGIS-derived age / education / motorization tables) -
`ana.section_model_table` + `ana.store_counts_section` (one row per census section: predictors + store counts, the base for the models).
