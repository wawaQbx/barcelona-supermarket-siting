# Supermarket siting in Barcelona - project report (working document)

Last updated: 2026-10-13. This is a living document: findings are appended as the work proceeds.
Where things are and how to rebuild: see `README.md`. Table by table description: `docs/data_catalog_supermarket_bcn.xlsx`.

## 1. Goal and scope

Explain why each supermarket chain has its stores where it has them, **inside the city of Barcelona** (analysis units: 1068 census sections, 73 barris, 10 districts).
Planned method: a first statistical model (logistic / Poisson regression, one per brand) of store presence or count per census section on demand, competition,
accessibility, built-form and planning variables; then sensitivity checks (edge effect, distance thresholds).
The database was deliberately built broader than this one question (rents, tourism, ageing, commerce, transport) so that other studies and dashboards can reuse it.

## 2. Status

| Item | State |
|---|---|
| Store list | 964 stores, 16 banners; **701 inside the city** (263 outside are only the corners of the city's bounding box, not a buffer) |
| Database | PostgreSQL 18.6 + PostGIS 3.6.2, `supermarket_bcn`; 95 raw tables, 18 derived tables, 5 metadata tables; rebuilds in ~1-2 minutes |
| Naming and types | Harmonised and audited twice with two different methods (see section 5); 7 residual findings, all text damaged in the source files |
| Derived analysis tables | Stores with features, barri features, dimensions, transit service per stop, age bands, education, motorization (section 6) |
| Regression | v1-v4 done (v4: cadastre / traffic blocks, time-ordered predictors, event study, L10 natural experiment) - section 11, `docs/MODEL_RESULTS.md` |

## 3. Data

Sources: Open Data BCN (population, income, housing, cadastre, commercial census 2014-2024, traffic counters, vehicles, planning, tourism, TMB GTFS), the user's QGIS project
(copied, never modified), official store locators of the chains (Condis, Bon Preu / Esclat, Consum / Charter, Alcampo, Dia until its site started returning 403), OpenStreetMap
(roads, shops; the only source for Mercadona, Caprabo, Lidl, Aldi and Carrefour stores), Renfe / FGC open data (stations).
Every table, its columns, its source file and its caveats are in the Excel catalog (English; a Chinese snapshot sits next to it).

## 4. Pipeline

`data_catalog/` (inputs copied by theme) -> `clean_catalog.py` -> `data_clean/` -> `import_all.py` (loads all tables, then runs `dbt build` in `dbt_bcn/`: the 25 derived tables of schema ana, their tests and the type harmonisation) -> `audit_types.py`.
All naming and typing rules live in `bcn_naming.py`. Rules: shared concepts have one Catalan name in every table (codi_districte, codi_barri, seccio_censal ...); other columns keep
the language of their source table; codes and ids are text; geometry is EPSG:25831; nothing is edited by hand in the database.

## 5. Data-quality findings (what could mislead an analysis)

1. **Census 2019 yes/no flags are inverted** (0 = yes; other editions use 1 / "Si" = yes). Verified on all ten `sn_*` flags (e.g. "inside a market": 4.2% in 2016, 3.3% in 2022, 97.3% raw in 2019).
   Corrected to boolean true = yes; shares are now comparable across years.
2. **Census 2014 coordinates are ED50 (EPSG:23031)**, not ETRS89; the plain X / Y columns of that file are corrupted. Treating them as ETRS89 shifts points by ~100-200 m
   (5 of 145 stores matched instead of 76).
3. **Small-cell secrecy in the Padro (resident register) tables.** Four tables (deaths, births, single-year age, education x sex) withhold every cell below 5 people (marker `..`, loaded as NULL).
   Proven arithmetically on the age table: the withheld cells hold 25,703 people in total, mean 2.45 per cell, never more than 4 in any section. 25.6% of the 65+ cells are withheld (ages 93-100 almost all).
   * The user's QGIS tables `pop_age_groups_by_*` were built from the published cells only: `pop_total` is below the official population in all 1068 sections (mean -1.68%, max -9.5%),
     and the 65+ share is understated (city 20.09% instead of 21.10%; 507 sections change by more than 1 percentage point, up to 4.2). **Corrected in `ana.pop_age_bands_section`**
     (official total minus published cells = exact withheld sum, spread over the bands by number of withheld cells; all 1068 sections reconcile). Always use the ana table for age structure.
   * Deaths and births cannot be reconciled (no published total): use at barri level or as coarse indicators; the 19 + 66 empty sections hide at most 76 deaths and 264 births.
4. **Education:** official levels are 1 no studies, 2 primary, 3 lower secondary, 4 upper secondary, **5 tertiary**, **6 "No consta" (not available)**. The user's `total_alta_educa` added level 6 to level 5.
   Corrected tertiary share (`ana.pop_education_section`): city mean 38.49% instead of 38.97%. Withheld cells occur only in levels 1 and 6, so the corrected share is robust (bounds at most 0.7 pp wide).
5. **Motorization index is published for only 183 of 1068 sections (17%).** The registered-vehicle counts are complete; vehicles / population x 1000 reproduces the published index
   (correlation 0.996, mean ratio 1.000). `ana.motorization_section` provides it for all sections. 13 sections with > 600 cars per 1000 residents are company-fleet artefacts (port, Zona Franca).
6. `trn_parades.id_districte` is a transport id (621-630), not a district code. `inc_renda_gini_by_seccio` duplicates the two raw income tables (identical in all sections).
7. **Census section codes** are district x 1000 + section in some files and only the within-district number in others; harmonised to the composite code.
8. Census text: about 1,800 premise / street names have characters lost in the source files (not recoverable; only the 2016 file had 14 provably repairable values and 3 axis names were repaired from a clean edition).
9. Census editions 2014 and 2016 use other field names; harmonised after comparing values (sector 100%, group 94%, activity 89% overlap). 2016 `id_bcn` is the 2019 `id_bcn_2016`: 70,529 premises link directly.
10. The 2016 census `DATA` is an entry date (not a review date) and 2014 `DATAINICI` is the start of the inventory (first registration, from 2012), neither is an opening date.

## 6. Derived tables added for analysis

`ana.py_stores_model_table_city` (701 city stores x 91 features), `ana.py_barri_features`, `ana.dim_district`, `ana.dim_neighborhood`, `ana.gtfs_stop_service` (weekday / peak / Saturday / Sunday
departures per TMB stop), `ana.pop_age_bands_section` and `_barri`, `ana.pop_education_section`, `ana.motorization_section`,
`ana.store_points` (all stores as points, brand groups, in_city flag, OSM Dia supplement), `ana.store_counts_section` / `_barri` (outcomes under both edge-effect definitions),
`ana.section_model_table` / `ana.barri_model_table` (one row per unit with all predictors).

More renames (2026-10-13): age bands `*_n` / `share_*_pct`, education `tertiary_share_pct`, motorization `*_n` / `*_per_1000_hab`; store features `d<year>` ->
`dist_census_supermarket_<year>_m` (duplicates `d19` / `d24` dropped), `*_census_year` (integer), `imd_*_vehicles_per_day`, `road_rank_max_50m_1to7`, `pgm_street_width_m`,
`official_store_code` (text); barri features `veh_*_n`, `bldg_n`, `bldg_mean_age_years`, `*_per_1000_hab`; Bon Preu months `202111` -> `2021-11`.

Column renames with units (verified): Padro `valor` -> `habitants_n` (people; base, single age, education), `llars_n` (households; the three household tables each sum to 684,077),
`defuncions_n`, `naixements_n`. `adm_units_polygons.area` / `perimetre` equal the measured geometry (m2 / m). Columns whose meaning could not be verified
(trn_corresp_parades `dist_agr`, `bearing_agr`, `ordre_*`; trn_parades `punts_parada`; tourism `indicador`, `dn`) keep their names and are flagged as unverified.

## 7. Store opening timeline: completeness and accuracy

* Five census editions (2014, 2016, 2019, 2022, 2024) give a first-seen bracket for 587 of 701 city stores (83.7%); 629 (89.7%) have some dating evidence; 72 (10.3%) none.
* Precision is coarse: 243 stores (35%) are only "already there in 2014"; 344 (49%) have a 2-3 year bracket; month precision exists only for 6 Bon Preu / Esclat stores (archive from 2021-11).
* Only Bon Preu / Esclat could be validated against an official source (34 of 36 consistent, about 94%).
* 58 of 130 "Dia" stores were first seen as Clarel (Dia-owned drugstores converted): the Dia 2015-16 bracket is the Clarel period.
* No chain publishes opening dates in its store locator; OSM has a start date for 1 of 1,993 shops.

## 8. Decisions (taken 2026-10-13)

1. Edge effect: **plan A** - two outcome definitions (inside the unit; within X m, with and without stores outside the city). Outside ring to collect later: **1 km** (2 km for hypermarkets), not 3 km.
2. Thresholds: 250 / 500 / 1000 m (2000 m hypermarkets).
3. Dia outside the city: gap stated **and** OSM tried: 4 Dia shops added (24 in the 2 km ring, 20 already listed). Quality check of OSM Dia in the city: coverage 39%, 86% of OSM points match an official store (median 15 m), 14% are closed stores still in OSM.
4. Unit: both census section (main) and barri (description / robustness).

Facts behind decision 1: 263 outside stores, of which 51 lie within 500 m and 125 within 1000 m of a city census section; outside stores change the 500 m count of 83 sections.

## 9. Limitations to carry into any conclusion

* Correlation, not causation; store position is the outcome, many drivers are unobserved (land availability, rents of the ground floor, company strategy).
* Mercadona, Caprabo, Lidl, Aldi, Carrefour come from OSM and may miss stores; Dia outside the city cannot be refreshed.
* Census names cannot attribute independent / franchised shops to a brand; opening times are brackets, not dates.
* Withheld small cells (section 5) make death / birth / single-age statistics unsuitable for section-level analysis without the corrections above.
* PGM zone keys are only partly verified (13 = urban densification, 12 = old town, 7 = facilities, 18 = specific volumetric order, 20a = detached, 22a = industrial); about 59% of stores fall in zone 13, so the broad class has little discriminating power.

## 10. Housekeeping done

Project folder is self-contained (inputs in `data_catalog`, rebuild without the QGIS folder); installers and extracted PGM files removed; Chinese-named files removed from the project
(one Chinese catalog snapshot with an ASCII file name is kept in `docs/` at the user's request).

## 11. First models (details: `docs/MODEL_RESULTS.md`)

* Outside-city stores barely change the estimates (coefficients with / without them correlate 0.97-1.00 for every chain): the edge effect is not a threat at 500 m.
* Exact location (stores inside a section) is hard to predict (deviance explained ~10%, AUC 0.50-0.69): ground-floor availability and company strategy are not observed.
* Consistent drivers: commercial street fabric (active ground-floor premises, positive for all chains), population density and share of residents 65+ (positive except Alcampo);
  income adds nothing once education is in; Consum / Charter has the clearest social profile; Aldi follows transit; in 500 m catchments, high car ownership goes with fewer stores.
* Barri-level models fit well only because counts grow with population and area; with 72 units the per-chain estimates are unstable.
* v2 (errors clustered by barri): no over-dispersion (Poisson adequate), no residual spatial autocorrelation (Moran's I about -0.02), competition from other chains not significant
  except Alcampo (negative); Consum's "lower income" effect is no longer significant (p = 0.09), the education effect stays; Lidl's location is not predictable with these variables.
* v3: chains keep distance from their OWN stores and sit near RIVALS (own-chain ratio below 1 in 13 of 14 chain models). Openings 2016-2024 (252 new sites, 92 takeovers,
  57 Clarel conversions excluded) are harder to predict than the old network; Mercadona's recent openings target dense, older areas with large sections;
  Consum's recent openings go to lower-income areas away from rivals. New tables: `ana.store_group_membership`, `ana.store_openings`, `ana.store_openings_section`.
* Correction (section area): area and density correlate -0.95; models now use ln(population) as offset. Mercadona prefers less dense, larger sections, not dense ones.
* v4: cadastre adds information (commercial floor share +, newer buildings +, lower cadastral value +); traffic adds none. With predictors measured before the openings
  (Padro 2015, income 2015, 2014 census) most associations of the 2016-2024 openings disappear. Event study: commerce within 150 m grows about 12% after a new
  supermarket site opens, with no pre-trend: part of the "commercial street" effect is reverse causality. L10 Sud natural experiment: no detectable effect (randomisation p = 0.43, 17 sections).
  New data: Padro population 2007-2026, age and education 2015, income 2015-2023 (`fetch_history.py`); new tables `ana.section_baseline_2015`,
  `ana.store_site_premises_panel`, `ana.section_metro_l10`; cadastre / road / traffic columns in `ana.section_model_table`.
* Catalog correction: `raw.cad_edif_sup` 'Superfície_locals' is the floor area of all cadastral units, not shops.
* Building age decomposed (construction period, PGM zoning, population growth): the "newer buildings" effect weakens to n.s. and is a summary of when / under which plan
  an area was built; commercial floor share and lower cadastral value remain the robust supply-side drivers. The L10 Sud experiment has little external value:
  the dense city is served by L1-L5, and no L1-L5 station opened in 2014-2024.
* v5 (store's own building, cadastre INSPIRE, case-control within barri): supermarkets are in buildings with larger footprints (OR 1.60 per SD, every chain),
  built after 1960 (OR 1.6-2.3 vs pre-1941) and residential (1.88). Building age is mainly a proxy for ground-floor size; for Mercadona only footprint matters.
  Only 19 of 192 new sites opened in a building completed in the previous 10 years. New: `prepare_inspire_buildings.py`, `raw.cad_inspire_buildings`, `ana.site_buildings`.
* Robustness: Caprabo's preference for newer buildings holds in direction (1.19 per decade); Consum's 1961-1980 result is not robust (withdrawn).
  Barri pattern: inside its barri a supermarket uses one of the largest buildings (median footprint percentile 62 Condis - 89 Lidl / Aldi); the constraint binds in
  small-floor barris (77th percentile) and hardly in large-floor ones (56th). Dia is relatively more frequent in small-floor barris, Mercadona in large-floor ones.
* v6: ring check (96% of chain stores within 2 km outside the city were already listed - the edge-effect data are complete); no substitution (small food shops +18%
  after a supermarket opens); chain stores close half as often as independents; conditional-logit site choice = big premises, away from own stores, in less commercial
  sections; out-of-time AUC 0.60 (two-fold lift); ML does not beat the logit; pacified streets: no effect; ~65,000 residents (3.8%, corrected store list; 4.2% before) beyond 500 m walking, mainly hillsides.
  New: `fetch_ring_stores.py`, `fetch_ring_osm.py`, `fetch_streets_prices.py`, `build_food_access.py`, the time-dynamics tables (now dbt models in `dbt_bcn/models/ana/time`).
* Store-list corrections: 57 Clarel drugstores removed from Dia, 51 Condis/Consum coordinates corrected by address, 79 chain supermarkets of the 2024 census added
  (city stores 701 -> 723); automatic validation table `ana.store_list_validation`. All models re-run; Dia's "Clarel conversions" withdrawn (Dia is a shrinking network).
* 2026-10-15 - derived SQL tables moved to dbt: the 13 scripts `sql/ana_*.sql` became 25 dbt models in `dbt_bcn/models/ana` (+ 3 helper tables in schema
  `dbt_int` that replace the TEMP tables and the census point union repeated in five scripts; primary keys as post-hooks; type harmonisation as on-run-end hook;
  49 tests: keys, accepted values, reconciliation). `import_all.py` now runs `dbt build` instead of the SQL files. Checked against a backup of the old tables
  (schema ana_before): 23 of 25 tables identical row by row and type by type; the other two differed only where the old SQL picked an arbitrary row among ties
  (numbering of supermarket_premises_closures, the "nearest 2024 premise" name when several premises share one point) - both are now deterministic.
  Faster: section_pacified_streets 448 s -> 2 s, store_list_validation 59 s -> 1 s. Old scripts kept for reference in `sql/legacy_pre_dbt/` (not executed).
* 2026-10-15 - new data: Padro nationality 2015 + 2026, Inside Airbnb (2026-09), tourist flats 2026 / 2017, hotels, municipal markets -> dbt models
  pop_nationality_section, section_tourism, section_airbnb_reviews_year, market_supermarkets; `analyze_tourism_markets.py` (MODEL_RESULTS section 25):
  after robustness checks (stepwise controls, alternative measures, per-dwelling offset, matched controls): tourist grocery demand is served by
  independent supermarkets, not chains; fewer chain stores where non-EU residents are many (0.82-0.88 per SD), not replaced by independents; 30 of 39 food
  markets have a chain store within 100 m (municipal policy, confirmed by press), fresh shops around markets fell less than around matched places. Noise / air data not used (raster only; out of scope).
* 2026-10-15 - audit of every table the user derived in QGIS (compared with a recomputation from the official source). Correct: population by barri,
  income / Gini by section, building use by section and barri, cadastral value by section, census layers 1 / 3-7. Corrected as dbt models (raw left untouched,
  catalog marks the old tables SUPERSEDED): age location quotients (LQ) recomputed on the reconciled age bands (ana.pop_age_bands_section / _barri;
  129 sections differed by > 0.05 for 65+), higher education per barri (ana.pop_education_barri, level 5 only), income per barri population-weighted
  (ana.income_barri; the simple mean differed up to 783 EUR; a barri Gini cannot be derived from section Ginis -> mean / min / max of the section Gini),
  cadastral value per barri floor-area-weighted (ana.cadastral_value_barri; up to 143 EUR/m2), traditional food shops incl. fishmongers and poultry shops
  (ana.traditional_food_shops_2024; layer 2 missed 697 shops). Geometry of all derived point tables now typed geometry(Point, 25831) for QGIS.
* 2026-10-15 - opening dates completed: stores not dated by census_panel.py (the 79 census-2024 additions and 51 stores with address-corrected coordinates,
  which no longer matched the dating table) now get the earliest census edition with a premise of the chain's name within 60 m (agrees with census_panel.py
  for 500 of 508 stores). Dated city stores 508 -> 639 (88%), openings 2016-2024 276 -> 352; all models re-run (MODEL_RESULTS section 26).
* 2026-10-15 - full rebuild from the source files, then check_quality.py (new): all 17 checks OK (descriptions, typed EPSG:25831 valid geometry, primary
  keys, valid section / barri / district codes, population 1,729,963 in every table, 723 city stores, 351 openings, 88% dated, value ranges, type audit,
  import completeness, unique natural keys, catalogs, 77 dbt tests, independent re-verification). Fixed on the way: row order made the cross-validation,
  holdout and sampled site-choice results depend on the order PostgreSQL returns rows (now sorted, two runs identical); missing primary keys of
  store_points / gtfs_trip_runs / supermarket_premises_closures; barri of 62 traffic counters taken from the polygon.
* 2026-10-16 - food access corrected (MODEL_RESULTS section 27): slope capped at 30% (false slopes of the surface model), buildings beyond the search cutoff no
  longer dropped, markets / supermarkets / fresh shops outside the city added from OSM (lower bound for fresh shops) with an edge-uncertainty flag.
  Low-income food deserts 11 -> 5 sections (the three Institut Metropoli barris still included); the chain-store coverage (96.2% within 500 m) is unchanged.
* 2026-10-16 - fresh food defined in three ways (MODEL_RESULTS section 28): main (middle: chains + fresh-selling regional chains + markets + fresh shops)
  4 low-income food-desert sections, range strict 5 / broad 1; Torre Baro under every definition.
* 2026-10-16 - vulnerable low-access sections now use the slope-aware 10-min test (MODEL_RESULTS section 29): fresh food out of reach 2 sections (Sarria,
  Pedralbes), full chain supermarket out of reach 5 (+ Vall d'Hebron, Vallcarca, Can Baro); the distance-only version (7) is retired.

### Store list audit against official locators (2026-10-16)
Official locators (Mercadona, Aldi), a re-scrape by address (Condis, Consum / Charter, Bon Preu / Esclat), hand-documented removals with evidence and a
census supplement restricted to the chains without a locator removed closed stores and stores counted twice: city stores 723 -> 676 (3.9 per 10k).
A new quality check enforces one store = one point. Changed results: 95.8% of residents within 500 m of a chain (was 96.2%), vulnerable sections 3 / 7
(was 2 / 5); food deserts unchanged. Details in MODEL_RESULTS section 30.
