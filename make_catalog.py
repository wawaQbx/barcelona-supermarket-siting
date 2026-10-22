"""Build docs/data_catalog_supermarket_bcn.xlsx from the live database + curated descriptions (English)."""
from pathlib import Path
import pandas as pd, psycopg

conn = psycopg.connect("host=localhost port=5432 dbname=supermarket_bcn user=postgres", autocommit=True)
Q = lambda s, a=None: conn.execute(s, a).fetchall()

CAT = {"adm": "Administrative units / boundaries", "cad": "Cadastre & built form", "cen": "Commercial census (every ground-floor premise)",
       "com": "Commercial facilities & census layers", "gtfs": "Public transport timetable (TMB GTFS)", "hist": "Store opening-history clues",
       "hou": "Housing, land use & rentals", "inc": "Income", "pgm": "Urban planning (PGM)", "pop": "Population", "rel": "Other facilities",
       "store": "Supermarket stores", "tou": "Tourism", "trf": "Traffic, vehicles & roads", "trn": "Public transport stops & lines"}
# table -> (content, one row =, key columns, notes)
D = {
 # ---------------- ana ----------------
 "dim_district": ("The 10 districts: code and official name (authoritative lookup)", "one district", "codi_districte, nom_districte", "Every district name in the database is overwritten from this table"),
 "dim_neighborhood": ("The 73 barris: code, official name and district", "one barri", "codi_barri, nom_barri, codi_districte", "Every barri name in the database is overwritten from this table"),
 "gtfs_service_day": ("Services running on the 3 representative days (weekday 2026-10-14, Saturday 10-17, Sunday 10-18)", "representative day x service", "dia, tipus_dia, service_id", "Intermediate table for the departure counts"),
 "gtfs_trip_runs": ("How many runs each trip makes per day (headway-based trips expanded)", "one trip", "trip_id, runs", "Intermediate; the 2 funicular headway trips expand to 174 runs"),
 "gtfs_stop_service": ("Departures per stop/station on a weekday, weekday 7-9h peak, Saturday and Sunday, plus number of routes", "one stop (metro platforms rolled up to the station)",
                       "stop_id, nom, departures_weekday, departures_weekday_7_9h, n_routes, codi_barri, geom",
                       "Built by dbt model gtfs_stop_service on every rebuild; codi_barri is NULL outside the city; L9N skipping La Sagrera on weekdays is the real timetable"),
 "py_barri_features": ("Barri-level vehicle ownership (per 1000 residents) and cadastral building statistics (age, share built before 1950, floor-area ratio)", "one barri",
                       "codi_barri, cars_per_1000_hab, pct_bldg_pre1950, floor_area_ratio", "la Marina del Prat Vermell is inflated by company fleets (flag_fleet_distorted = true): exclude it"),
 "py_stores_features_city": ("City stores + traffic, roads, PGM, terrain, census timeline (version before barri features were merged)", "one store in the city",
                             "nom, ensenya, lat, lon, codi_barri", "pgm_qualif / pgm_key come from the old nearest-label method (~30% agreement with polygons): do not use; use pgm_clau_poly in py_stores_model_table_city"),
 "py_stores_model_table_city": ("[MAIN TABLE] The 701 city stores with every feature: brand, location, traffic, roads, PGM zone, terrain, opening era, barri features", "one store in the city",
                                "nom, ensenya, brand_std, lat, lon, codi_barri, codi_districte, opening_era, pgm_clau_poly",
                                "For zoning use pgm_clau_poly / pgm_family (polygon method), not pgm_qualif / pgm_key; opening_era has 2-3 year precision; Dia's 2015-16 bracket is mostly the Clarel period"),
 "py_stores_opening_era_city": ("Opening-time clues per store: presence in 5 census editions, first census seen, Clarel predecessor, Bon Preu archive month, Condis id",
                                "one store in the city", "first_seen_census_year, opening_era, first_banner, official_first_seen",
                                "First seen = upper bound of the opening date; 'no census match' does not mean a new store (franchise shops may use another name)"),
 "pop_age_bands_section": ("[USE THIS FOR AGE] Population by 5 age bands per census section, reconciled with the official population (withheld single-age cells re-added exactly)", "one census section", "seccio_censal, pop_official_n, age_*_estimated_n, share_65plus_pct, has_withheld_cells",
                          "Method: official total minus published cells = exact sum of the withheld cells, spread over the bands by number of withheld cells (each holds 1-4 people); all 1068 sections reconcile. City 65+ share 21.10% (the QGIS table gives 20.09%). Built by dbt model pop_age_bands_section"),
 "pop_age_bands_barri": ("Same as ana.pop_age_bands_section summed to barri", "one barri", "codi_barri, age_*_estimated_n, share_65plus_pct, share_0_17_pct", "Derived from the section table"),
 "pop_education_section": ("Educational attainment per census section (both sexes) with the correct 'tertiary' definition = level 5 only; shares with lower/upper bounds for withheld cells", "one census section", "seccio_censal, n_tertiary, tertiary_share_pct, tertiary_share_lower_bound_pct, tertiary_share_upper_bound",
                           "Level 6 = 'No consta' (not available) is NOT higher education; withheld cells (<5) occur only in levels 1 and 6, none in 2-5, so tertiary_share_pct is robust (bounds at most 0.7 pp wide). Built by dbt model pop_education_section"),
 "motorization_section": ("Vehicles per 1000 residents for ALL 1068 census sections by vehicle type, recomputed from registered vehicles / population", "one census section", "seccio_censal, cars_per_1000_hab, motorcycles_per_1000_hab, vans_trucks_per_1000_hab, all_vehicles_per_1000_hab, fleet_distorted",
                          "The published index covers only 183 sections (17%); recomputation reproduces it (correlation 0.996, mean ratio 1.000). 13 sections with cars_per_1000_hab > 600 are distorted by company fleets (fleet_distorted = true); max 1886 in la Marina del Prat Vermell. Built by dbt model motorization_section"),
 # ---------------- meta ----------------
 "store_points": ("Store list (Clarel drugstores excluded, 51 coordinates corrected) + census-2024 chain supermarkets missing from the list + OSM Dia and ring stores outside the city (point_source) as points (EPSG:25831) with brand group and in_city flag", "one store", "store_id, point_source, ensenya, brand_group, store_type, in_city, geom", "Banners merged into chains: Consum+Charter, Bon Preu+Esclat, Alcampo+Mi Alcampo, all Carrefour formats. Source: raw.store_supermarkets_official"),
 "store_counts_section": ("Stores per census section and brand group (and ALL): inside the section and within 250/500/1000/2000 m of its boundary", "census section x brand group", "seccio_censal, brand_group, n_inside, n_inside_new_2016_2024, n_inside_legacy_2014, n_ring_500m, n_city_within_*m, n_all_within_*m", "brand_group also holds the format groups. n_ring_* = within X m but outside the section (competition). n_city_* = stores inside the city only; n_all_* = also the stores outside the city (edge-effect definition). Counts within X m overlap between neighbouring sections. Stores outside the city are incomplete for Dia and OSM chains"),
 "store_group_membership": ("Store -> group lookup (chain, format group, ALL) used for all counts", "store x group", "store_id, grp", "Format groups from the store_type of the official list: Alcampo_hypermarket, Alcampo_MiAlcampo, Carrefour_convenience, Carrefour_supermarket"),
 "store_openings": ("City stores first seen in a census after 2014 (2016-2024) and what stood at the site in the previous census", "one store", "store_id, brand_group, format_group, first_seen_census_year, opening_type, previous_food_premise_name", "opening_type: new_site / takeover_of_food_premise (food shop within 25 m in the previous edition) / clarel_conversion. Only stores still open today are seen (closures are not)"),
 "store_openings_section": ("Openings 2016-2024 per census section and group, by opening type", "census section x group", "seccio_censal, brand_group, n_openings_2016_2024, n_openings_new_site, n_openings_takeover, n_openings_clarel", "Outcome of the v3 opening models"),
 "section_baseline_2015": ("Predictors measured BEFORE the 2016-2024 openings: Padro 2015 population, density, 65+ share (reconciled), tertiary share; income 2015; 2014 census premises", "one census section", "seccio_censal, population_2015_n, population_per_ha_2015, share_age_65plus_2015_pct, share_tertiary_education_2015_pct, disposable_income_2015_eur_per_person, premises_active_2014_n", "For time-ordered models (against reverse causality). Section codes are stable 2007-2026 (year-to-year correlation >= 0.976)"),
 "store_site_premises_panel": ("Event-study panel: active ground-floor premises within 150 m of each dated city store in each census edition (own premise within 20 m excluded)", "store x census edition", "store_id, opening_type, first_seen_census_year, census_year, active_premises_150m_n", "Vacancy not used: its categories change between editions. Use with edition fixed effects"),
 "section_metro_l10": ("Natural experiment: sections that gained metro access with L10 Sud (Foc / Foneria, opened 8 Sep 2018) vs the rest; supermarket openings before / after", "one census section", "seccio_censal, treated, near_new_l10_station, had_metro_500m_before, openings_pre_2014_2016_n, openings_post_2017_2024_n", "17 treated sections only: low statistical power"),
 "pop_padro_population_history": ("Population per census section on 1 January of every year 2007-2026 (Open Data BCN pad_mdbas, fetch_history.py)", "census section x year", "data_referencia, seccio_censal, habitants_n", "Same 1068 section codes every year"),
 "pop_padro_age5_2015": ("Population by five-year age group per census section, 2015-01-01", "census section x age group", "seccio_censal, edat_q (0 = 0-4 ... 20 = 100+), habitants_n", "Cells below 5 withheld (NULL), as in the 2026 tables"),
 "pop_padro_education_2015": ("Population 16+ by education level x sex per census section, 2015-01-01", "census section x level x sex", "seccio_censal, niv_educa_esta (1-6, 5 = tertiary, 6 = not available), sexe, habitants_n", "Cells below 5 withheld (NULL)"),
 "inc_income_history": ("Disposable income per person per census section, 2015-2023", "census section x year", "any_, seccio_censal, renda_disponible_eur_per_persona", "Open Data BCN renda-disponible-llars-bcn"),
 "cad_inspire_buildings": ("Every cadastral building of Barcelona (Spanish cadastre INSPIRE, 2026-08): footprint, year of construction, current use, units, dwellings, gross floor area, floors", "one building (footprint)", "referencia_cadastral, year_of_construction, current_use, building_units_n, dwellings_n, gross_floor_area_m2, footprint_area_m2, floors_above_ground_max, geom", "69,911 buildings; 341 without year; a few historic buildings have years before 1700. footprint = building, not shop area. Built by prepare_inspire_buildings.py"),
 "site_buildings": ("Building of every city store and of every other active ground-floor premise 2024 (controls for the case-control test)", "one site", "site_id, site_type (store / control_premise), store_id, brand_group, opening_type, codi_barri, year_of_construction, footprint_area_m2, floors_above_ground_max, current_use", "Point matched to the containing footprint, else nearest within 15 m; 675 of 701 stores matched"),
 "store_ring_stores_2km": ("Chain stores in the city box widened by ~2 km (official locators of Condis, Bon Preu / Esclat, Consum / Charter, Alcampo; OSM for the other chains)", "one store", "ensenya, nom, adreca, lat, lon, store_type, source", "Includes city stores; the dbt model int_store_points_base adds the outside ones not within 100 m of a listed store (5 added: the list already covered the ring)"),
 "hou_locve_preu_oferta_locals_2008_2011": ("Asking price of commercial premises per barri, 2008-2011 (Open Data BCN locve-evolucio)", "barri x year", "any_, codi_barri, preu_oferta_local_eur_m2", "EUR per m2; source used '.' as thousands separator ('2.176' = 2,176); 69 NULL ('--')"),
 "trf_streets_pacified_2020_2022": ("Pacified streets (Eixample 'eixos verds'), one layer per quarter 2020 Q3 - 2022 Q2", "street line x quarter", "any_, trimestre, id_segment, geom", "Natural experiment 2 (ana.section_pacified_streets)"),
 "trf_streets_pedestrian_priority_2023_2026": ("Single-platform streets with pedestrian priority, quarterly layers 2023-2026 + current layer (any_ NULL)", "street segment x quarter", "any_, trimestre, id_segment, geom", "Almost unchanged 2023-2026 (2,558 -> 2,591 segments)"),
 "store_site_premises_by_type": ("Event-study panel by premise type within 150 m of each dated city store", "store x census edition x premise type", "store_id, opening_type, census_year, ptype, premises_150m_n", "ptype: daily_food_other, other_retail, restaurants_bars (2016+), services_other, supermarket_class (2019+)"),
 "supermarket_premises_closures": ("Supermarket-class premises of the 2019 and 2022 censuses and whether they are gone in the next census", "one premise x census", "census_year, nom_local, brand_group (from the sign), closed_by_next_census, supermarkets_300m_n, footprint_area_m2", "Closed = no supermarket premise within 20 m in the next census (closure or relocation)"),
 "section_pacified_streets": ("Natural experiment 2: sections along the 2020 pacified streets vs the rest; active premises 2016-2024, openings before / after", "one census section", "seccio_censal, treated_pacified_street, active_premises_<year>_n, openings_2014_2019_n, openings_2020_2024_n", "Use Eixample (codi_districte = 2) as control group"),
 "section_walkability": ("Pedestrian-priority street length per census section", "one census section", "seccio_censal, pedestrian_priority_len_m", ""),
 "py_building_food_access": ("Walking distance from each residential building to the nearest chain supermarket (OSM network, stores outside the city included)", "one residential building", "referencia_cadastral, seccio_censal, dwellings_n, walk_to_supermarket_m", "Built by build_food_access.py; NULL when the building is > 300 m from a mapped street"),
 "pop_nationality_section": ("Foreign residents per census section, 1 January 2015 and 2026 (Spain / rest of EU / rest of world), reconciled with the official total", "one census section", "seccio_censal, share_foreign_2026_pct, share_foreign_non_eu_2026_pct, share_foreign_2015_pct, share_foreign_change_2015_2026_pp", "Cells < 5 withheld at source; remainder spread like the age bands. City 2026: 26.6% foreign (19.5% non-EU); 2015: 16.4%. Built by dbt model pop_nationality_section"),
 "section_tourism": ("Tourist accommodation per census section: licensed tourist flats and beds (HUT 2026, 2017 per block), hotels, Airbnb listings and reviews of the last 12 months", "one census section", "seccio_censal, hut_beds_n, hut_beds_2017_n, hotels_n, airbnb_listings_n, hut_beds_per_100_residents, airbnb_listings_per_100_residents", "10,730 HUT flats / 62,111 beds; 445 hotels in the city (no beds or stars in the open data); 15,234 Airbnb listings. Built by dbt model section_tourism"),
 "section_airbnb_reviews_year": ("Airbnb reviews per census section and year 2010-2026 (proxy of tourist activity over time)", "one census section and year", "seccio_censal, review_year, airbnb_reviews_n", "Only listings online on 2026-09-17: listings removed earlier are missing (survivorship bias), early years under-counted; compare sections, not years. Built by dbt model section_airbnb_reviews_year"),
 "market_supermarkets": ("Municipal markets (43, 39 food) and chain supermarkets: chain stores at the market (50 / 100 m) and within 300 m, nearest chain store, openings nearby, fresh-food shops in a 100-400 m ring per census edition 2016-2024", "one municipal market", "nom_mercat, food_market, chain_stores_50m_n, chain_stores_100m_n, chain_stores_300m_n, nearest_chain_store_m, fresh_shops_ring_100_400m_2019_n, fresh_shops_ring_100_400m_2024_n", "22 / 30 of 39 food markets have a chain store within 50 / 100 m. Fresh = meat, fruit and vegetables, poultry and eggs, fish (coded identically 2016-2024); stalls within 100 m excluded (market stalls are census premises). Built by dbt model market_supermarkets"),
 "pop_padro_nationality_2015_2026": ("Padro: population by nationality group (1 Spain, 2 rest of EU, 3 rest of world, 4 not available) and sex per census section, 1 January 2015 and 2026", "one section x nationality group x sex x date", "data_referencia, seccio_censal, nacionalitat_g, sexe, habitants_n", "Cells < 5 withheld ('..' -> NULL); use ana.pop_nationality_section. Downloaded by fetch_history.py"),
 "tou_airbnb_listings_2026_09": ("Inside Airbnb snapshot of Barcelona, 2026-09-17: every listing with position, room type, price, reviews, availability and licence type", "one Airbnb listing", "listing_id, lat, lon, room_type, price, number_of_reviews_ltm, availability_365, license_type, license", "CC BY 4.0. Host names / ids and titles not kept. license_type from the licence text: tourist_flat_hutb 5,602, none_declared 5,466, seasonal_non_tourist 3,281, hotel_or_hostel 830. Downloaded by fetch_airbnb.py"),
 "tou_airbnb_reviews_per_year": ("Inside Airbnb review dates aggregated to reviews per listing and year (2010-2026)", "one listing x year", "listing_id, any_, reviews_n", "1.13 M reviews of the listings online in 2026-09 (survivorship bias). Downloaded by fetch_airbnb.py"),
 "pop_education_barri": ("Education per barri: tertiary share (level 5 only) with bounds", "one barri", "codi_barri, tertiary_share_pct, tertiary_share_lower_bound_pct, tertiary_share_upper_bound_pct", "Sums of the section counts of ana.pop_education_section. Built by dbt model pop_education_barri"),
 "income_barri": ("Income per barri (population-weighted mean of the sections) and the population-weighted mean / min / max of the section Gini", "one barri", "codi_barri, disposable_income_eur_per_person, mean_section_gini_0_100, min_section_gini_0_100, max_section_gini_0_100, income_between_sections_cv_pct", "The source has only sections; mean_section_gini is the typical inequality inside a section, not a barri Gini. Built by dbt model income_barri"),
 "cadastral_value_barri": ("Cadastral value per m2 by barri, weighted by floor area", "one barri", "codi_barri, cadastral_value_eur_per_m2, floor_area_m2, land_share_of_value_pct", "Total value / total floor area of the sections (raw.hou_2026_loc_hab_valors). Built by dbt model cadastral_value_barri"),
 "traditional_food_shops_2024": ("Traditional fresh-food shops of the 2024 census: bakery, butcher, greengrocer, fishmonger, poultry / eggs", "one premise", "premise_id, nom_local, fresh_category, seccio_censal, codi_barri, geom", "4,503 active shops. Built by dbt model traditional_food_shops_2024"),
 "section_indicators": ('VISUALISATION LAYER: census-section boundaries with every mappable indicator (108 columns): population and age LQ, education, foreign residents, income, buildings and planning, transport and streets, commerce, tourism, chain stores, openings, food access', 'one census section', 'seccio_censal, nom_barri, age_*_location_quotient, premises_active_per_ha, transit_departures_weekday_300m_n, stores_*_n, median_minutes_fresh_older, geom', 'Curated copy of ana tables for QGIS and the dashboard; do not use for modelling. Column groups and colour guide: docs/DASHBOARD_DESIGN.md. Built by dbt model gis.section_indicators'),
 "barri_indicators": ('VISUALISATION LAYER: barri boundaries with the same indicators (78 columns), aggregated correctly from the sections', 'one barri', 'codi_barri, nom_barri, age_*_location_quotient, metro_stations_n, premises_active_per_ha, stores_*_n, share_residents_beyond_500m_pct, geom', 'Counts summed, shares recomputed, other rates population-weighted; do not use for modelling. Built by dbt model gis.barri_indicators'),
 "stores": ('VISUALISATION LAYER: every store (city + 2 km ring) with chain, format, opening history, validation evidence, building and lon / lat', 'one store', 'store_id, brand_group, format_group, in_city, opening_type, validation_evidence, lon, lat, geom', 'Curated copy of ana.store_points and related tables; do not use for modelling. Built by dbt model gis.stores'),
 "markets": ('VISUALISATION LAYER: municipal markets with chain stores at the market and fresh-food shops around them 2016-2024', 'one market', 'nom_mercat, food_market, chain_stores_50m_n, fresh_shops_ring_100_400m_*_n, lon, lat, geom', 'Curated copy of ana.market_supermarkets; do not use for modelling. Built by dbt model gis.markets'),
 "transit_stops": ('VISUALISATION LAYER: TMB bus stops and metro / funicular stations with routes and departures (weekday, 7-9 h, Saturday, Sunday)', 'one stop / station', 'stop_id, nom, stop_kind, n_routes, departures_weekday, departures_weekday_7_9h, lon, lat, geom', 'Platforms rolled up to the station; curated copy of ana.gtfs_stop_service, do not use for modelling. Built by dbt model gis.transit_stops'),
 "traffic_counters": ('VISUALISATION LAYER: traffic counting stations 2025 with mean vehicles per day on working days, Saturdays and Sundays', 'one counting station', 'id_aforament, desc_aforament, lanes_n, imd_working_day_vehicles_per_day, lon, lat, geom', 'Means over the months of 2025; do not use for modelling. Built by dbt model gis.traffic_counters'),
 "chain_colours": ("VISUALISATION: one fixed colour per chain (Tableau 10, colour-blind safe) for every map and chart, display label and sort order", "one chain", "brand_group, chain_label, colour_hex, sort_order", "dbt seed from dbt_bcn/seeds/chain_colours.csv; edit the CSV and run dbt seed"),
 "com_osm_food_shops_box": ("OpenStreetMap food shops and markets in the box ~2 km around the city (greengrocers, butchers, fishmongers, supermarkets, convenience, marketplaces)", "one OSM object", "osm_id, food_category, nom, ensenya, lat, lon", "Used only OUTSIDE the city by build_food_access.py (inside, the census is complete). OSM completeness in the city vs census (gis.osm_completeness): markets 95%, supermarkets 61%, fresh shops 23-33%. Downloaded by fetch_ring_food_osm.py"),
 "py_section_food_access": ("Food access per census section: distance and slope-aware walking minutes (adult / older pace) to chain supermarkets, any supermarket, markets and fresh food; climb home; vulnerability and low-income food-desert flags", "one census section", "seccio_censal, median_walk_to_supermarket_m, share_dwellings_beyond_500m_pct, residents_beyond_500m_est, vulnerable_low_access", "Slope from Copernicus GLO-30 (approximate); OSM has few footpaths and no stairs"),
 "store_points_excluded": ("Store-list entries left out of every analysis: 57 Clarel drugstores that the Dia locator listed as 'Dia Market'", "one excluded store", "store_id, ensenya, brand_group, exclusion_reason, geom", "Rule: no Dia-named census premise within 60 m in any edition and a Clarel premise within 60 m in 2024. Dia in the city: 130 -> 73 stores"),
 "store_list_validation": ("Validation of every city store against the commercial censuses: chain name within 60 m (2024 / earlier), other supermarket within 30 m, nearest 2024 premise", "one city store", "store_id, brand_group, point_source, evidence, brand_seen_in_census, nearest_2024_activity", "evidence = brand_in_2024 / brand_earlier_only / other_supermarket / no_evidence. Built by dbt model store_list_validation"),
 "store_coordinate_corrections": ("Stores whose locator coordinates were replaced by the census position of the same chain at the store's address", "one store", "ensenya, adreca, lat, lon, census_lat, census_lon, coord_offset_m", "51 stores (Condis 50, Consum 1), median offset 80 m. Built by check_store_addresses.py"),
 "store_counts_barri": ("Stores per barri and brand group (and ALL): inside, and within 500/1000 m of the boundary", "barri x brand group", "codi_barri, brand_group, n_inside, n_city_within_*m, n_all_within_*m", "Same definitions as store_counts_section"),
 "section_model_table": ("[BASE TABLE FOR MODELS] One row per census section with the predictors: population, density, age, education, income, Gini, vehicles, transit, 2024 census premises, housing, cadastral value, position", "one census section", "seccio_censal, population_n, population_per_ha, share_age_*_pct, disposable_income_eur_per_person, cars_per_1000_residents, transit_departures_weekday_300m_n, premises_*_n", "Uses the corrected age / education / motorization tables. cars_fleet_distorted marks 13 sections with company fleets. Join ana.store_counts_section for the outcomes"),
 "barri_model_table": ("Same predictors aggregated to the 73 barris (rates population-weighted)", "one barri", "codi_barri, population_n, share_age_65plus_pct, disposable_income_eur_per_person, ...", "cars_per_1000_residents excludes fleet-distorted sections (NULL for a barri made only of such sections)"),
 "tables": ("File card of every imported table: source file, rows, columns, language, CRS", "one table", "table_schema, table_name, source_file, language", "Written by import_all.py"),
 "columns": ("Every column of every table with its data type", "one column", "table_name, column_name, data_type", "Written by import_all.py"),
 "skipped_files": ("Files that were not imported and why", "one file", "source_file, reason", ""),
 "type_audit": ("Data-type audit result (only 7 source-damaged text columns left)", "one finding", "severity, table_name, column_name, problem", "Written by audit_types.py"),
 # ---------------- raw: admin ----------------
 "adm_census_section_lookup": ("The 1068 census sections with their barri, district and AEB = Area Estadistica Basica / Basic Statistical Area (233 AEBs; boundaries as WKT text)", "one census section", "seccio_censal, codi_barri, codi_districte",
                               "Boundaries are WKT text columns (geometria_*), not a geom column; this file is the authoritative source of names"),
 "adm_units_polygons": ("Official administrative boundaries, 8 kinds in one table: municipality, districts, barris, big barris, AEB, census sections, Urban Audit, areas of interest",
                        "one administrative unit", "tipus_ua / elem_descr (unit kind), codi_barri, codi_districte, seccio_censal, geom",
                        "Always filter by tipus_ua or elem_descr first (e.g. tipus_ua = 'BARRI'), otherwise units are counted several times"),
 "adm_units_points": ("Map label points of the administrative units", "one label", "tipus_ua, nom, geom", "For cartography, not for analysis"),
 # ---------------- raw: cadastre ----------------
 "cad_edif_any": ("Buildings per census section by construction period", "census section x period", "seccio_censal, any_construccio, nombre", "Long table: pivot by period before comparing"),
 "cad_edif_edat": ("Mean building age (years) per census section", "one census section", "seccio_censal, edat_mitjana_anys", ""),
 "cad_edif_locals": ("Buildings grouped by number of premises they contain", "census section x group", "seccio_censal, desc_locals, nombre", "Long table"),
 "cad_edif_sup": ("Cadastral floor area per census section by type", "census section x area type", "seccio_censal, tipus_sup, superficie_m2", "Long table. Superfície_locals = floor area of ALL cadastral units (116.5 km2, ~90% of the 128.7 km2 built area), NOT shops; Superfície_serveis (13.6 km2) meaning unverified. For shop floor area use hou_2026_us_desti (locals_comercials_m2)"),
 "cad_finques_sup": ("Plot area and built area (above / below ground / total) per census section", "census section x area type", "seccio_censal, desc_sup, superficie_m2",
                     "Long table; floor-area ratio = above-ground built area / plot area"),
 # ---------------- raw: census ----------------
 "cen_census_2014": ("2014 commercial census: name, activity, address and ids of every ground-floor premise", "one premise", "nom_local, nom_activitat, nom_grup_activitat, codi_barri, x_ed50, y_ed50",
                     "Coordinates are ED50 (EPSG:23031), not ETRS89 - declare 23031 when transforming; no lat/lon; data_inici is the first census registration (from 2012), not an opening date; ~1500 street names have bytes lost in the source"),
 "cen_census_2016": ("2016 commercial census (column names harmonised to the 2019+ schema)", "one premise", "id_bcn_2016, nom_local, nom_activitat, sn_carrer, codi_barri, seccio_censal, lat, lon",
                     "id_bcn_2016 links directly to 2019/2022/2024 (70,529 matches with 2019); sn_* converted to boolean; data_entrada = official 'Data d'entrada' (date the premise entered the inventory), not a review date. See docs/CENSUS_GUIDE.md"),
 "cen_census_2019": ("2019 commercial census (spatial table)", "one premise", "id_bcn_2019, id_bcn_2016, nom_local, nom_activitat, sn_*, codi_barri, seccio_censal, geom",
                     "The original sn_* flags are INVERTED (0 = yes); corrected to boolean true = yes; data_revisio was an integer like 20191002, now a date"),
 "cen_census_2022": ("2022 commercial census", "one premise", "id_global, id_bcn_2016, nom_local, nom_activitat, sn_*, codi_barri, seccio_censal, lat, lon",
                     "sn_* converted from Si/No to boolean; no geom column: build points from lat/lon"),
 "cen_census_2024": ("2024 commercial census (latest)", "one premise", "id_global, id_bcn_2016, nom_local, nom_activitat, sn_*, codi_barri, seccio_censal, lat, lon",
                     "sn_* converted from Si/No to boolean; no geom column: build points from lat/lon"),
 # ---------------- raw: commercial ----------------
 "com_layer1_supermercat": ("Self-service / supermarket premises of the 2024 census (subset you cut in QGIS)", "one premise", "nom_local, codi_barri, seccio_censal, lat, lon",
                            "Subset of cen_census_2024; names are the signs recorded by surveyors, including independent shops"),
 "com_layer2_alimentacio_tradicional": ("Traditional food shops (bakery, butcher, greengrocer) of the 2024 census", "one premise", "nom_local, nom_activitat, codi_barri, lat, lon", "Subset of cen_census_2024 | SUPERSEDED: use ana.traditional_food_shops_2024 (adds fishmongers 437 and poultry / egg shops 260)"),
 "com_layer3_restauracio": ("Restaurants and bars of the 2024 census", "one premise", "nom_local, nom_activitat, codi_barri, lat, lon", "Subset of cen_census_2024"),
 "com_layer4_equipaments_comunitat": ("Health, education and pharmacies of the 2024 census", "one premise", "nom_local, categoria, codi_barri, lat, lon", "Subset of cen_census_2024"),
 "com_layer5_eix_comercial": ("Premises on commercial axes of the 2024 census", "one premise", "nom_local, nom_activitat, codi_barri, lat, lon", "Subset of cen_census_2024"),
 "com_layer6_locals_buits": ("Vacant premises (for rent / for sale) of the 2024 census", "one premise", "nom_activitat, codi_barri, lat, lon", "Subset of cen_census_2024"),
 "com_layer7_magatzems": ("Warehouses of the 2024 census", "one premise", "nom_local, codi_barri, lat, lon", "Subset of cen_census_2024"),
 "com_equipaments_comercials_clean": ("Municipal markets, large shopping centres and large stores (your curated list)", "one facility", "nom_mercat, tipus, nom_barri, lat, lon", ""),
 "com_mercats_municipals_clean": ("The 43 municipal markets (your curated list)", "one market", "nom_mercat, nom_barri, lat, lon", ""),
 "com_llista_equipaments_mercats_i_centres_comercials": ("Open Data BCN facility register: markets, shopping centres, large stores, street markets", "facility x one contact entry",
                                                         "register_id, nom, values_attribute_name, values_value, lat, lon",
                                                         "A facility can appear on several rows (one per phone / contact): count DISTINCT register_id; English field structure from Open Data BCN"),
 "com_mercats_centrescomercials_mercats_municipals": ("Open Data BCN facility register: municipal markets", "facility x one contact entry", "register_id, nom, lat, lon", "Several rows per facility: count DISTINCT register_id"),
 "com_plazaparc_clean": ("OSM shopping centres, squares and parks with commercial use (deduplicated, bus stops removed)", "one OSM object", "id, nom, geom", "256 raw OSM tag columns kept as text"),
 # ---------------- raw: gtfs ----------------
 "gtfs_agency": ("Operator (TMB)", "one operator", "agency_name", "GTFS standard field names kept in English"),
 "gtfs_feed_info": ("Validity period: 2026-06-12 to 2026-12-31", "one row", "feed_start_date, feed_end_date", ""),
 "gtfs_routes": ("116 routes: 105 bus, 10 metro, 1 funicular", "one route", "route_id, route_short_name, route_type (1 = metro, 3 = bus, 7 = funicular)", ""),
 "gtfs_trips": ("73,001 trips (one vehicle run of a route in one direction); each trip belongs to a service calendar", "one trip", "trip_id, route_id, service_id, direction_id, shape_id",
                "Which trips run on a date depends on gtfs_calendar + gtfs_calendar_dates (see ana.gtfs_service_day)"),
 "gtfs_stop_times": ("Arrival / departure time of every trip at every stop", "trip x stop", "trip_id, stop_id, departure_time, stop_sequence",
                     "1.68 M rows; times can exceed 24:00 (after midnight); indexed on trip_id and stop_id"),
 "gtfs_stops": ("3,445 stops: bus stops, metro platforms, metro stations, entrances", "one stop", "stop_id, stop_name, stop_lat, stop_lon, location_type, parent_station",
                "location_type: 0 = platform/stop, 1 = station, 2 = entrance; platforms belong to a station through parent_station"),
 "gtfs_calendar": ("4 regular service calendars (days of week + date range)", "one service", "service_id, monday...sunday, start_date, end_date", ""),
 "gtfs_calendar_dates": ("22,598 services added on specific dates", "service x date", "service_id, date, exception_type (1 = added, 2 = removed)", "This feed only contains additions"),
 "gtfs_frequencies": ("8 headway-based trips (e.g. every 600 s)", "one headway window", "trip_id, start_time, end_time, headway_secs", "Must be expanded when counting departures, otherwise they count as 1 run"),
 "gtfs_shapes": ("Route geometry as ordered coordinate points", "one shape point", "shape_id, shape_pt_sequence, shape_pt_lat, shape_pt_lon", "Join points by shape_id to draw lines"),
 "gtfs_pathways": ("Walkways inside stations (platform - entrance)", "one pathway", "from_stop_id, to_stop_id, pathway_mode", ""),
 "gtfs_transfers": ("Transfer rules", "one transfer", "from_stop_id, to_stop_id, min_transfer_time", ""),
 # ---------------- raw: history ----------------
 "hist_bonpreu_first_seen": ("First and last month each Bon Preu / Esclat store appears in the archived official store finder (all Catalonia)", "one store",
                             "codi, primer_mes, ultim_mes, ensenya, lat, lon", "The archive starts in 2021-11: primer_mes = 2021-11 means 'already existed' (left-censored); codi is not an opening order"),
 "hist_bonpreu_snapshots_long": ("Bon Preu / Esclat store list in every archived month", "archive month x store", "mes_captura, codi, ensenya", "Long table"),
 "hist_condis_raw": ("Raw store list from the Condis website API (Spanish field names)", "one store", "id, idn, adreca, municipi, talla, tipo_tienda, lat, lon",
                     "Kept in its original language (Spanish); higher idn tends to mean newer (correlation 0.67 with first census: weak clue)"),
 "hist_consum_now": ("Current Consum / Charter stores from the website (whole province)", "one store", "ensenya, lat, lon, link", "Column addr is not yet harmonised to adreca"),
 "hist_osm_shops": ("OSM objects tagged as supermarket / convenience", "one OSM object", "osm_id, nom, ensenya, shop, geom", "Only 1 of 1993 has a start_date; tags is raw JSON text"),
 # ---------------- raw: housing ----------------
 "hou_2026_loc_hab_valors": ("Cadastral values per census section (total and per m2, land / building)", "census section x value type", "seccio_censal, desc_valors, valors", "Long table"),
 "hou_2026_locals_us_desti": ("Property units by main use per census section: number, area (m2) and value (EUR). 15 uses: housing, commerce, warehouse, parking, offices, education & culture, tourism & hospitality, health, sport, religious, industry, entertainment, other, public administration, unbuilt land", "census section x use x measure", "seccio_censal, desc_us_desti_principal, concepte (Nombre / Superficie_m2 / Valor_EUR), nombre", "Long table; not every section has every use (e.g. industry only in 292 sections)"),
 "hou_2026_us_desti_by_barri": ("Your barri land-use indicators built from hou_2026_locals_us_desti. Column names now carry the unit: *_n = number of units, *_m2 = area, *_eur = value; ratios say per what", "one barri", "codi_barri, habitatges_n, locals_comercials_n, locals_comercials_per_100_habitatges, valor_comercial_eur_per_m2", "Source categories verified against the long table: habitatges = Habitatge, locals_comercials = Comerc, aparcaments = Aparcaments, oficines = Oficines, magatzems = Magatzem, turisme_hostaleria = Turisme i hostaleria. Ratios: locals_comercials_per_100_habitatges and turisme_hostaleria_per_100_habitatges = units per 100 dwellings; oficines_m2_per_100_m2_habitatge and magatzems_m2_per_100_m2_habitatge = m2 per 100 m2 of housing; habitatges_per_local_comercial = dwellings per commercial unit; valor_comercial_eur_per_m2 = commercial value / commercial m2 (formulas checked on real rows)"),
 "hou_2026_us_desti_by_seccio": ("Same as above at census-section level", "one census section", "seccio_censal, habitatges_n, locals_comercials_n, locals_comercials_per_100_habitatges, valor_comercial_eur_per_m2", "Same column definitions as the barri table"),
 "hou_2026_valor_cadastral_by_barri": ("Mean cadastral value in EUR per m2 by barri", "one barri", "codi_barri, valor_cadastral_eur_per_m2", " | SUPERSEDED: use ana.cadastral_value_barri (floor-area weighted; simple mean was up to 143 EUR/m2 off)"),
 "hou_2026_valor_cadastral_by_seccio": ("Mean cadastral value in EUR per m2 by census section", "one census section", "seccio_censal, valor_cadastral_eur_per_m2", ""),
 "hou_barcelona_contracte_2025": ("Rental contracts per barri in 2025", "one barri", "codi_barri, contractes_2025", "Superseded by hou_contractes_lloguer_anual (identical values)"),
 "hou_contractes_lloguer_anual": ("Rental contracts per year: city and districts 2000-2025, barris 2013-2025", "unit x year", "nivell (municipi / districte / barri), codi_districte, codi_barri, any_, nombre_contractes",
                                  "Filter by nivell first; barri level covers only 81% / 89% / 94% of the district totals in 2013 / 2014 / 2015 - start barri trends in 2016"),
 # ---------------- raw: income ----------------
 "inc_2022_renda_disponible_llars_per_persona": ("Household disposable income per person per census section (EUR per person, 2022)", "one census section", "seccio_censal, renda_disponible_eur_per_persona", ""),
 "inc_2023_atles_renda_index_gini": ("Gini index (income inequality) per census section (2023)", "one census section", "seccio_censal, index_gini", ""),
 "inc_renda_gini_by_barri": ("Your barri summary of income (EUR per person) and Gini", "one barri", "codi_barri, renda_disponible_eur_per_persona, index_gini", "Derived from the section tables | SUPERSEDED: use ana.income_barri (income = population-weighted mean, up to 783 EUR different; Gini = mean of section Ginis, a barri Gini cannot be derived)"),
 "inc_renda_gini_by_seccio": ("Your census-section table that joins the 2022 income and the 2023 Gini", "one census section", "seccio_censal, renda_disponible_eur_per_persona, index_gini", "REDUNDANT: identical to inc_2022_renda_disponible_llars_per_persona + inc_2023_atles_renda_index_gini in all 1068 sections (checked); kept only as a convenience join"),
 # ---------------- raw: planning ----------------
 "pgm_qualif_polygons": ("PGM zoning polygons", "one zoning parcel", "clau, detall, classific, geom",
                         "Keys partly verified: 13 = urban densification (13a intensive, 13b semi-intensive), 12 = old town, 7 = community facilities, 18 = specific volumetric order, 20a = detached buildings, 22a = industrial; ~59% of stores fall in 13"),
 "pgm_label_points": ("PGM map labels for street width and building volume", "one label", "label_type (street_width / volumetric), label, geom", ""),
 # ---------------- raw: population ----------------
 "pop_2026_pad_base": ("Registered population per census section (2026-01-01)", "one census section", "seccio_censal, habitants_n", "valor = population"),
 "pop_2026_pad_base_by_barri": ("Registered population per barri", "one barri", "codi_barri, total_poblacio", ""),
 "pop_2026_pads_edat_1": ("Population by single year of age per census section", "census section x age", "seccio_censal, edat_1, habitants_n", "Long table, 105k rows. 10,323 cells (9.8%) are NULL = source marker '..' = cell below 5 people withheld (statistical secrecy). Published cells sum to 1,704,260 vs the official population 1,729,963 (-1.49%); the withheld cells hold 1-4 people each (implied mean 2.45). 25.6% of the 65+ cells are withheld (ages 93-100 almost all): never treat NULL as 0 silently"),
 "pop_2026_pad_16niv_educa_sexe": ("Population by education level x sex per census section", "census section x level x sex", "seccio_censal, niv_educa_esta, sexe, habitants_n", "Long table. 1,576 of 12,591 cells (12.5%) are NULL = '..' = cell below 5 withheld (statistical secrecy): sums and shares over published cells are biased low"),
 "pop_2026_pad_dom18": ("Households by number of members under 18", "census section x group", "seccio_censal, dom_00_18, llars_n", "Long table; dom = household"),
 "pop_2026_pad_dom_mdbas_edat_1864": ("Households by number of members aged 18-64", "census section x group", "seccio_censal, dom_18_64, llars_n", "Long table"),
 "pop_2026_pad_dom_mdbas_edat_6599": ("Households by number of members aged 65+", "census section x group", "seccio_censal, dom_65_99, llars_n", "Long table"),
 "pop_2025_pad_def_mdbas": ("Deaths per census section in 2025 (Padro = Municipal Register of Inhabitants; def = defuncions; confirmed by the Open Data BCN dataset title 'Deaths')", "one census section", "seccio_censal, defuncions_n, aeb",
                            "1049 of 1068 sections have a value (total 14,489); 19 are NULL (source marker '..'). The smallest published value is 5 and there is no spike at 5, so values below 5 look WITHHELD (not rounded up) - inferred from the data, the dataset text does not say so. The total therefore understates the true city total slightly"),
 "pop_2025_pad_nai_mdbas": ("Births per census section in 2025 (Padro = Municipal Register of Inhabitants; nai = naixements; confirmed by the Open Data BCN dataset title 'Births')", "one census section", "seccio_censal, naixements_n, aeb",
                            "1065 of 1068 sections present, 1002 with a value (total 10,804); 63 are NULL ('..') and 3 sections are absent. Smallest published value is 5, no spike at 5: values below 5 look withheld (inferred). Coarse indicator only"),
 "pop_age_groups_by_barri": ("Your barri age groups. For each band: _count = people; _pct_of_unit_pop = % of the barri population; _pct_of_city_group = % of the city's people of that age band who live here; _location_quotient = _pct_of_unit_pop / city share (above 1 = more concentrated than the city)", "one barri", "codi_barri, pop_total, age_*_count, age_*_pct_of_unit_pop, age_*_location_quotient", "WARNING: built from the incomplete published age cells (see pop_2026_pads_edat_1): pop_total is below the official population and the 65+ group is understated by roughly 6%. Definitions verified on a real row. Use ana.pop_age_bands_barri | SUPERSEDED: use ana.pop_age_bands_barri (shares and location quotients on reconciled bands)"),
 "pop_age_groups_by_seccio": ("Same as above at census-section level", "one census section", "seccio_censal, pop_total, age_*_pct_of_unit_pop", "WARNING: pop_total is the sum of PUBLISHED age cells, not the official population: lower than raw.pop_2026_pad_base in all 1068 sections (mean -1.68%, max -9.5%); 65+ understated by roughly 6% overall. Use ana.pop_age_bands_section | SUPERSEDED: use ana.pop_age_bands_section (age_*_location_quotient recomputed on reconciled bands; 129 sections differed by > 0.05 for 65+)"),
 "pop_educa_superior_by_barri": ("Your barri share of people with higher education", "one barri", "codi_barri, pct_alta_educa", "Same level-6 problem as the section table. Use ana.pop_education_section | SUPERSEDED: use ana.pop_education_barri (level 5 only)"),
 "pop_educa_superior_by_seccio": ("Your census-section share of people with higher education", "one census section", "seccio_censal, total_16plus, total_alta_educa, pct_alta_educa", "WARNING: total_alta_educa = level 5 + level 6, but level 6 means 'No consta' (not available), so it is slightly overstated (mean 38.97% vs 38.49% corrected). Use ana.pop_education_section | SUPERSEDED: use ana.pop_education_section.tertiary_share_pct"),
 # ---------------- raw: other ----------------
 "rel_religious_facilities": ("Religious facilities register", "facility x one contact entry", "register_id, nom, lat, lon", "Several rows per facility: count DISTINCT register_id"),
 "store_supermarkets_official": ("[STORE MASTER LIST] 964 supermarkets (701 in the city + 263 outside), from official websites and OSM", "one store",
                                 "ensenya, nom, store_type, lat, lon, municipi, codi_barri",
                                 "The 263 outside stores only cover the corners of the city's bounding box, not a full buffer; Mercadona, Caprabo, Lidl, Aldi, Carrefour come from OSM and may miss stores; the Dia website now returns 403 (cannot refresh)"),
 # ---------------- raw: tourism ----------------
 "tou_2017_huts_illa": ("2017 tourist flats, beds, residents and dwellings per city block", "one block", "hut_casos, hut_places, habitants, num_vivend, geom", ""),
 "tou_2019_turisme_allotjament": ("2019 tourist-accommodation surface layer", "one polygon", "dn, geom", "Single field dn with unverified meaning: confirm before use"),
 "tou_hotels": ("Hotel register (stars in secondary_filters_name)", "hotel x one contact entry", "register_id, nom, secondary_filters_name, lat, lon", "Several rows per hotel: count DISTINCT register_id"),
 "tou_hut_comunicacio_2026_1t": ("Tourist-flat (HUT) register, 2026 Q1 edition", "one tourist flat", "n_expedient, codi_barri, numero_places, lat, lon", ""),
 "tou_hut_comunicacio_opendata": ("Tourist-flat (HUT) register, earlier edition", "one tourist flat", "n_expedient, codi_barri, numero_places, lat, lon", "Differs by 5 rows from the 2026 Q1 edition"),
 # ---------------- raw: traffic ----------------
 "trf_aforament_desc_2025": ("Traffic counters: motor traffic, ring roads, bicycles", "one counter", "id_aforament, desc_tipus_aforament, lat, lon", "Ring-road (Rondes) counters belong to no district: codi_districte is NULL"),
 "trf_aforament_detall_2025": ("Average daily traffic (IMD = Intensitat Mitjana Diaria, vehicles per day) per counter, month and day type", "counter x month x day type", "id_aforament, mes, desc_tipus_dia, imd_vehicles_per_day", "'Mesura no disponible' (no measurement) converted to NULL"),
 "trf_motor_2025": ("Published motorization index (vehicles per 1000 residents) per census section and vehicle type", "census section x vehicle type", "seccio_censal, tipus_vehicle, index_motoritzacio_per_1000_hab", "Only 183 of 1068 sections have a value (17%, reason unknown). Recomputed for all sections in ana.motorization_section (reproduces the published values: correlation 0.996)"),
 "trf_parc_vehicles": ("Registered vehicles per census section and vehicle type", "census section x vehicle type", "seccio_censal, tipologia_parc, nombre_vehicles", "Long table; nom_districte = 'No consta' means unknown district"),
 "trf_vehicles_evolucio": ("Total registered vehicles per census section in 2025 (only one year despite the name)", "one census section", "seccio_censal, total", "One row has an unknown section (NC)"),
 "trf_osm_roads": ("OSM road segments and class (motorway ... residential)", "one road segment", "osm_id, highway, nom, lanes, maxspeed, geom", "Raw OSM: lanes and maxspeed are text"),
 # ---------------- raw: transit ----------------
 "trn_parades": ("Bus stops", "one bus stop", "id_parada, codi_parada, nom_parada, municipi, geom", "id_districte is NOT a district code (values 621-630): never use it as a district"),
 "trn_corresp_parades": ("Stop - route correspondences", "stop x route", "codi_parada, codi_linia, geom", ""),
 "trn_linies_bus": ("Bus route geometries", "one route", "codi_linia, geom", ""),
 "trn_estacions_metro": ("Metro stations", "one station", "id_estacio, nom_estacio, geom", ""),
 "trn_accessos": ("Metro station entrances", "one entrance", "id_acces, id_estacio, geom", ""),
 "trn_intercs": ("Transport interchanges", "one interchange", "codi_interc, geom", ""),
 "trn_barcelona_transit_stations": ("FGC, Rodalies and tram stations (OSM + Renfe open data)", "one station", "nom, network, lines, lat, lon", ""),
}

tabs = Q("""select t.table_schema, t.table_name, coalesce(m.source_file,''), coalesce(m.language,''), coalesce(m.geom_type,''),
                   (select count(*) from information_schema.columns c where c.table_schema=t.table_schema and c.table_name=t.table_name)
            from information_schema.tables t left join meta.tables m on m.table_schema=t.table_schema and m.table_name=t.table_name
            where t.table_schema in ('raw','ana','meta','gis') order by 1,2""")
rows = []
for s, t, src, lang, gt, ncol in tabs:
    n = conn.execute(f'select count(*) from {s}."{t}"').fetchone()[0]
    cols = [c for (c,) in Q("select column_name from information_schema.columns where table_schema=%s and table_name=%s", (s, t))]
    if not gt and "geom" in cols: gt = conn.execute(f"select coalesce(max(geometrytype(geom)),'') from {s}.\"{t}\"").fetchone()[0]
    tr = ""
    if "any_" in cols:
        a, b = conn.execute(f'select min(any_), max(any_) from {s}."{t}"').fetchone(); tr = f"{a}-{b}" if a != b else f"{a}"
    else:
        for dc in ("data_referencia", "data_revisio", "date", "dia", "feed_start_date"):
            if dc in cols:
                a, b = conn.execute(f'select min("{dc}"), max("{dc}") from {s}."{t}"').fetchone(); tr = f"{a} - {b}"; break
    pref = t.split("_")[0]
    cat = {"gis": "Visualisation layer (QGIS / dashboard; not for modelling)", "ana": "Derived", "meta": "Metadata (catalog)"}.get(s, CAT.get(pref, "Other"))
    if s == "ana" and t.startswith("gtfs"): cat = "Derived: transit service"
    if s == "ana" and t.startswith("dim"): cat = "Derived: lookup / dimension"
    if s == "ana" and t.startswith("py_"): cat = "Derived: store analysis"
    content, unit, keys, notes = D.get(t, ("(no description)", "", "", ""))
    level = "census section" if "seccio_censal" in cols else ("barri" if "codi_barri" in cols else ("district" if "codi_districte" in cols else ""))
    rows.append({"category": cat, "schema": s, "table": f"{s}.{t}", "content": content, "one_row_is": unit, "rows": n, "columns": ncol, "geometry": gt or "",
                 "time_range": tr, "joinable_admin_unit": level, "key_columns": keys, "notes": notes,
                 "table_language": {"ca": "Catalan", "en": "English", "es": "Spanish"}.get(lang, ""), "source_file": src})
cat_df = pd.DataFrame(rows)
order = ["Visualisation layer (QGIS / dashboard; not for modelling)", "Supermarket stores", "Derived: store analysis", "Derived: lookup / dimension", "Derived: transit service", "Population", "Income", "Housing, land use & rentals",
         "Cadastre & built form", "Commercial census (every ground-floor premise)", "Commercial facilities & census layers", "Traffic, vehicles & roads",
         "Public transport stops & lines", "Public transport timetable (TMB GTFS)", "Urban planning (PGM)", "Administrative units / boundaries", "Tourism", "Other facilities",
         "Store opening-history clues", "Metadata (catalog)"]
cat_df["_o"] = cat_df["category"].map({c: i for i, c in enumerate(order)}).fillna(99); cat_df = cat_df.sort_values(["_o", "table"]).drop(columns="_o")

cols_df = pd.DataFrame(Q("""select table_schema||'.'||table_name, column_name, data_type, ordinal_position from information_schema.columns
                            where table_schema in ('raw','ana','meta','gis') order by 1, 4"""), columns=["table", "column", "data_type", "pos"]).drop(columns="pos")
skipped = pd.DataFrame(Q("select source_file, reason from meta.skipped_files order by 1"), columns=["file", "reason"]); skipped.insert(0, "status", "copied, not imported by design")
not_copied = pd.DataFrame([
    ("not copied", "export_vis/ (16 files)", "QGIS web exports and age-group maps: outputs, not data"), ("not copied", "jpg/, svg/, *.docx", "Images and documents, not data"),
    ("not copied", "tempor/ (22 files)", "QGIS temporary layers: per-brand store splits, old supermarket counts, sumHOTEL...: intermediate or outdated"),
    ("not copied", "new/SC_CX.geojson", "Your wide census-section join built in QGIS; all source tables are in the database and it can be rebuilt with SQL"),
    ("not copied", "zip/BCN_UNITATS_ADM.zip, zip/*hut*.zip", "Duplicates of data already imported"),
    ("copied, not imported", "csv/Commercial/layers/layers_overview.xlsx", "Layer documentation"), ("copied, not imported", "csv/Demographie/useless/ (2 files)", "Marked as useless by you"),
    ("copied, not imported", "geojson/*.qmd (10 files)", "QGIS style metadata, not data")], columns=["status", "file", "reason"])
glossary = pd.DataFrame([
    ("codi_districte / nom_districte", "District code (1-10) / name", "Codi_Districte, CDISTRI, addresses_district_id, district_code, DISTRICTE ..."),
    ("codi_barri / nom_barri", "Barri code (1-73) / name", "Codi_Barri, CBARRI, BARRI, addresses_neighborhood_id, neighborhood_code ..."),
    ("seccio_censal", "Census section = district x 1000 + section in district (1001-10237)", "Seccio_Censal, SEC_CENS, codi_seccio_censal; within-district originals kept in seccio_censal_orig"),
    ("any_", "Year ('any' is an SQL reserved word, hence the underscore)", "Any, year"), ("data_revisio", "Review / update date", "Data_Revisio, DATA (2016), ULTIMA_VISITA (2014), review_date"),
    ("total_poblacio", "Population", "Total_Poblacio, population"), ("municipi / codi_municipi", "Municipality name / code", "poblacio, nom_poblacio, ciudad, addresses_town, municipality, id_poblacio"),
    ("codi_postal", "Postal code (text, keeps the leading 0)", "cp, addresses_zip_code"), ("nom_via", "Street name", "carrer, addresses_road_name, N_CARRER (2016), CARRCADAST (2014)"),
    ("num_policia_inicial / _final", "House number", "numero, addresses_start/end_street_number, NUM_POLICI, DOORNUM"),
    ("adreca", "Full address", "address, calle"), ("nom", "Entity name", "name"), ("ensenya", "Store banner / brand", "brand"),
    ("nom_local / nom_activitat / nom_grup_activitat / nom_sector_activitat", "Census: premise name / activity / activity group / sector", "N_LOCAL, N_ACT, N_GRUPACT, N_SECTOR (2016); NOM, BCN3, BCN2, BCN1 (2014)"),
    ("id_bcn_2016", "2016 premise id, links 2016 / 2019 / 2022 / 2024", "ID_BCN (2016)"), ("lat / lon", "Longitude / latitude (EPSG:4326)", "Latitud, Longitud, latitude, longitude"),
    ("x_utm_etrs89 / y_utm_etrs89", "Metric coordinates (EPSG:25831)", "X_UTM_ETRS89, X_ETRS89, X_UTM, geo_epgs_25831_x"), ("geom", "Geometry column, always EPSG:25831", "geometry"),
    ("sn_*", "Census yes/no flags as boolean, true = yes", "0/1 (2016), inverted 0/1 (2019), Si/No (2022/2024)")], columns=["harmonised_name", "meaning", "original_names_examples"])
readme = pd.DataFrame([
    ("Database", "PostgreSQL 18.6 + PostGIS 3.6.2, database supermarket_bcn, port 5432"),
    ("Schemas", "raw = imported source data (never edited); ana = tables we derive; meta = catalog and audit"),
    ("Table names", "<theme prefix>_<file name>, lowercase; 'pad' in a name = Padro (Municipal Register of Inhabitants), 'mdbas' = municipi/districte/barri/AEB/seccio levels; prefixes: pop population, inc income, hou housing, cad cadastre, cen census, com commercial, trf traffic, trn transit stops/lines, gtfs timetable, pgm planning, adm administrative, tou tourism, hist history clues, store stores, rel other"),
    ("Column names", "Lowercase ascii snake_case; shared concepts use one Catalan name everywhere (see 'harmonised_names'); other columns keep the source language; GTFS keeps the international standard English names; raw OSM tags kept as-is"),
    ("Coordinates", "Every geom column is EPSG:25831 (metres); lat/lon are WGS84 degrees; the 2014 census only has ED50 coordinates (EPSG:23031)"),
    ("Withheld small cells", "Padro tables (pop_2025_pad_def, pop_2025_pad_nai, pop_2026_pads_edat_1, pop_2026_pad_16niv_educa_sexe) use the marker '..' (loaded as NULL) for cells below 5 people: statistical secrecy. Withheld cells hold 1-4 people; never read NULL as 0 or as missing-at-random"),
    ("Type rules", "Codes / ids / postal codes / phone numbers are text; district, barri, census-section codes and years are integers; dates are date; yes/no flags are boolean"),
    ("Rebuild", "Run clean_catalog.py -> import_all.py -> audit_types.py; all rules live in bcn_naming.py; never edit tables by hand"),
    ("Most used tables", "ana.py_stores_model_table_city, ana.dim_neighborhood, raw.pop_2026_pad_base, raw.inc_2022_renda_disponible_llars_per_persona, ana.gtfs_stop_service"),
    ("Generated", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))], columns=["item", "description"])

out = Path("docs/data_catalog_supermarket_bcn.xlsx"); out.parent.mkdir(exist_ok=True)
with pd.ExcelWriter(out, engine="openpyxl") as w:
    readme.to_excel(w, sheet_name="readme", index=False); cat_df.to_excel(w, sheet_name="tables", index=False)
    glossary.to_excel(w, sheet_name="harmonised_names", index=False); pd.concat([skipped, not_copied]).to_excel(w, sheet_name="not_imported", index=False)
    cols_df.to_excel(w, sheet_name="all_columns", index=False)
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
wb = load_workbook(out)
widths = {"readme": [18, 120], "tables": [30, 7, 42, 60, 24, 10, 8, 16, 22, 16, 55, 70, 10, 60], "harmonised_names": [42, 45, 80], "not_imported": [26, 60, 80], "all_columns": [50, 34, 26]}
for ws in wb.worksheets:
    for i, wd in enumerate(widths.get(ws.title, []), start=1): ws.column_dimensions[ws.cell(1, i).column_letter].width = wd
    for c in ws[1]: c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496"); c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
    for row in ws.iter_rows(min_row=2):
        for c in row: c.alignment = Alignment(vertical="top", wrap_text=True)
wb.save(out)
missing = [r["table"] for r in rows if r["content"] == "(no description)"]
print("written", out, "| tables:", len(cat_df), "| columns:", len(cols_df), "| without description:", missing)
