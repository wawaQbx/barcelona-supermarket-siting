# Dashboard design

Central question: **where do the supermarket chains of Barcelona open, why there, and who is left out?**
Six pages, 16:9 canvas (1280 x 720). Every page: title bar with the question it answers + page navigation; maps on the left (2/3), supporting charts on the right.
Counting rule (one standard per question, never mixed on a page): pages 00-03 count **chain stores only** (10 chain groups) - store numbers,
densities, the 500 m coverage (96.2%), spacing. Page 04 asks whether residents can buy fresh food, so it counts every food shop (chains, markets,
greengrocers, butchers, fishmongers, fresh-selling independents; definitions in MODEL_RESULTS section 28). Independent shops appear on pages 00-03
at most as one footnote line, never as a KPI or reference value.
One fixed colour per chain on every page; sequential colours for indicator maps; diverging colours centred on 1 for location quotients.

Data: the visualisation layers of schema `gis` (dbt models in `dbt_bcn/models/gis`, curated copies of `ana` tables - not for modelling) plus small
non-spatial tables taken from `docs/model_*.csv`. Findings and their robustness: `docs/MODEL_RESULTS.md`.

## Pages

| Page | Question | Visuals | Data |
|---|---|---|---|
| 00 Overview | What is this? | 4 KPI cards (676 stores, 10 chains, 72,000 residents > 500 m, 5 low-income food deserts (range 1-5)); store thumbnail map; 4 navigation cards with one finding each | gis.stores, gis.section_indicators |
| 01 Where they are | Where are the chains? | Filters (chain, format, district, show 2 km ring); main map: stores coloured by chain over sections shaded by stores per 10k residents; bar chart stores per chain; heat matrix district x chain | gis.stores, gis.section_indicators (stores_*_n, stores_per_10k_residents) |
| 02 Why there | What kind of place does each chain choose? | Chain filter; forest plot of rate ratios with 95% intervals; map of one chosen indicator (incl. age LQ) with the chain's stores; heat matrix chain x indicator; card "factors with no effect" (tourism for chains, L10 metro, pacified streets, competition) | model rate ratios (docs/model_v4_blocks_coefficients.csv, model_v7_*), gis.section_indicators |
| 03 Change 2014-2024 | Who expanded, how, and what happened around markets? | Line chart census premises per chain 2014-2024; map of openings coloured by opening type; stacked bars new site / takeover / Clarel conversion; market panel (30 of 39 food markets with a chain store within 100 m; fresh shops around markets vs matched places) | ana.store_openings, gis.stores, gis.markets, docs/model_v7_robust_markets_*.csv |
| 04 Who is left out | Who has poor walking access to food, and why does no store open there? | Shape map of median older-pace minutes to fresh food (where); column chart of residents over 10 min by income quarter (who: U shape); table of the flagged sections (which); bar chart of residents within 400 m of each flagged section vs existing chain stores, p10 / median reference lines (why). Scatter dropped 2026-10-19 | gis.section_indicators, gis.food_desert_viability |
| 05 Data and methods | Can the numbers be trusted? | Pipeline diagram (raw data -> PostgreSQL / PostGIS -> dbt -> Python models -> dashboard); validation cards (57 Clarel removed, 51 coordinates corrected, 79 stores added); sources; limitations | text |

## Columns of the gis layers

Rule: everything that is worth mapping is in the layer; left out are only intermediate and quality-check columns (published vs estimated cells,
bounds, reconciliation flags), duplicate outcome definitions (within 250 / 1000 / 2000 m, city-only vs all) and model-only transformations (logs).
Variables whose effect was tested and NOT found (tourism for chains, pacified streets, L10 metro) are in the layers for context maps, but the dashboard
shows them under "factors with no effect", never as drivers. Counts that grow with the section size also come as densities (per ha, per 10k residents).

`gis.section_indicators` (1068 sections, 108 columns), by group:

| Group | Columns | Page |
|---|---|---|
| Identity | seccio_censal, codi_barri, nom_barri, codi_districte, nom_districte, geom | all |
| Context | area_ha, population_n, population_per_ha, dwellings_n, dist_placa_catalunya_m | all |
| Population | share_age_*_pct (5 bands), age_*_location_quotient (5), share_tertiary_education_pct, share_foreign_pct, share_foreign_non_eu_pct, share_foreign_change_2015_2026_pp, population_2015_n, population_growth_2015_2026_pct | 02 |
| Income and property | disposable_income_eur_per_person (2022), disposable_income_2015_eur_per_person, gini_index_0_100, cadastral_value_eur_per_m2 | 02, 04 |
| Buildings and planning | bldg_mean_age_years, bldg_share_pre1941 / 1951_1980 / post1990_pct, floor_area_ratio, commercial_floor_share_pct, pgm_share_12 / 13 / 15 / 18 / 20 / 22_*_pct | 02 |
| Transport and streets | cars_per_1000_residents, transit_stops_300m_n, transit_departures_weekday_300m_n, metro_stations_500m_n, dist_nearest_metro_station_m, main_road_len_50m_m, motorway_len_50m_m, pedestrian_street_len_50m_m, pedestrian_priority_len_m, pedestrian_priority_m_per_ha, imd_max_300m_vehicles_per_day, near_pacified_street_2020, new_metro_access_l10_2018 | 02 |
| Commerce (2024 census) | premises_active_n, premises_active_per_ha, premises_vacant_n, premises_vacant_share_pct, premises_retail_n, premises_daily_food_other_n, premises_restaurants_bars_n, premises_supermarket_census2024_n, independent_supermarkets_2024_n, commercial_premises_per_100_dwellings, premises_active_2014_n | 02, 03 |
| Tourism | hut_beds_n, hut_beds_per_100_residents, hut_beds_2017_per_100_residents, hotels_n, airbnb_listings_n, airbnb_listings_per_100_residents, airbnb_reviews_last_12m_n, tourism_hospitality_per_100_dwellings | 02 |
| Chain stores | stores_all_n ... stores_alcampo_n (inside the section), stores_per_10k_residents, stores_within_500m_n (incl. outside the city), stores_ring_500m_n (within 500 m, outside the section) | 01, 02 |
| Openings 2016-2024 | openings_2016_2024_n, openings_new_site_n, openings_takeover_n | 03 |
| Food access | median_walk_to_supermarket_m, share_dwellings_beyond_500m_pct / 800m_pct, median_minutes_chain / any_supermarket / market / fresh_food, median_minutes_chain_older / fresh_older, share_dwellings_fresh_over_10min_older_pct, median_climb_home_from_supermarket_m, residents_beyond_500m_est, residents_65plus_beyond_500m_est, residents_65plus_fresh_over_10min_est, vulnerable_low_access, food_desert_low_income | 04 |

NULLs that are meant: cars_per_1000_residents (13 sections where company fleets distort it), imd_max_300m_vehicles_per_day (58 sections without a counting
station within 300 m), bldg_mean_age_years (13 sections without cadastre age), premises_vacant_share_pct (1 section without premises), median_minutes_market (2).

`gis.barri_indicators` (73 barris, 78 columns): the same groups; counts summed, densities and shares recomputed from the sums, age / education / income /
foreign residents / cadastral value from their barri models, the other rates population-weighted means of the sections; plus metro_stations_n,
main_road_m_per_ha, mean_section_gini_0_100, income_between_sections_cv_pct, vulnerable_sections_n, food_desert_sections_n.
Point layers: `gis.stores` (996), `gis.markets` (43), `gis.transit_stops` (2734 stops / stations, departures weekday / 7-9 h / Saturday / Sunday),
`gis.traffic_counters` (881 stations, mean vehicles per day on working days / Saturday / Sunday). All point layers carry lon / lat (WGS84) for BI tools.

## Colour and classification guide (QGIS and dashboard)

**Comparison colours (one rule on every page, 2026-10-17):** blue = above the reference / more stores, red = below / fewer, white = equal.
Text and arrows `#2F6497` / `#B04A33` / `#6B6B6B`; fills (matrix, choropleth) `#5B8DB8` / `#D9675E` / `#FFFFFF` (same saturation as the Tableau 10 chain colours, slightly different hue from Condis / Dia). Reference lines (city average,
"1 = no effect") are dark grey dashed `#6B6B6B`, never red. Neutral accent for charts that show neither a chain nor a comparison (decomposition tree, single-measure bars): ochre `#C79A5B` on `#EFE3CF`; categorical size classes use warm greys `#E3DDD0` / `#B8B0A0` / `#4A4A4A`. Choropleths of factors show the barri relative to the average barri (index, 1 = average,
diverging 0.5-1.5) so they read like the model matrix (rate ratio, 1 = no effect) and the KPI cards (vs city).

Palettes are ColourBrewer / Tableau 10 (colour-blind safe, available in QGIS, Tableau and Power BI themes).

| Kind of indicator | Examples | Colour ramp | Classes | Breaks |
|---|---|---|---|---|
| Location quotient | age_*_location_quotient | diverging RdBu, inverted (blue = below city, red = above), white middle class | 6 | manual: 0.8 / 0.95 / 1.05 / 1.25 / 1.5 |
| Change (can be negative) | population_growth_2015_2026_pct, share_foreign_change_2015_2026_pp | diverging PuOr centred on 0 | 6 | manual, symmetric: growth -10 / -2 / 2 / 10 / 20 %; change -5 / -1 / 1 / 5 / 10 pp |
| Shares in % | share_age_65plus_pct, share_tertiary_education_pct, share_foreign_*_pct, bldg_share_*, pgm_share_*, premises_vacant_share_pct | sequential Blues (one hue) | 5 | quantiles (equal count): ranks the sections, robust to outliers |
| Densities and rates | population_per_ha, premises_active_per_ha, stores_per_10k_residents, transit_departures_weekday_300m_n, pedestrian_priority_m_per_ha | sequential YlGnBu | 5 | quantiles |
| Skewed rates with many zeros | hut_beds_per_100_residents, airbnb_listings_per_100_residents, independent_supermarkets_2024_n | sequential YlOrRd; zero = light grey own class | 1 + 5 | 0, then quantiles of the non-zero values |
| Money | disposable_income_eur_per_person, cadastral_value_eur_per_m2 | sequential Greens | 5 | quantiles (city quintiles) |
| Distance / time (higher = worse) | median_walk_to_supermarket_m, median_minutes_*_older | sequential YlOrRd (dark = far) | 5 | manual at meaningful thresholds: metres 250 / 500 / 800 / 1500; minutes 5 / 10 / 15 / 30 |
| Share of homes beyond a threshold | share_dwellings_beyond_500m_pct, share_dwellings_fresh_over_10min_older_pct | sequential Reds; 0 = no fill | 5 | manual: 0 / 10 / 25 / 50 / 100 |
| Yes / no flags | food_desert_low_income, vulnerable_low_access, near_pacified_street_2020, new_metro_access_l10_2018 | true = solid red (#C0392B) or thick outline over the base map; false = no fill | 2 | - |
| Counts per unit (size-dependent) | stores_*_n, openings_*_n, residents_*_est, hut_beds_n | do NOT shade polygons by raw counts: graduated symbols (circles at the centroid, area proportional to the count) or use the matching rate | - | - |
| Chains (points) | brand_group | categorical, fixed for every page: Condis #4E79A7, Dia #E15759, Caprabo #F28E2B, Mercadona #59A14F, Consum_Charter #76B7B2, BonPreu_Esclat #EDC948, Lidl #B07AA1, Aldi #FF9DA7, Carrefour #9C755F, Alcampo #BAB0AC | 10 | - |
| Opening type (points) | opening_type | new_site #59A14F, takeover_of_food_premise #F28E2B, clarel_conversion #BAB0AC, open_in_2014 #4E79A7, not dated: hollow grey | 4 + 1 | - |
| Service level (points) | transit_stops.departures_weekday, traffic_counters.imd_working_day_vehicles_per_day | one colour (metro dark, bus light), symbol size by value | 5 | quantiles of the values |

Why these methods: quantiles give every class the same number of sections (good for "where is high / low" maps, robust to one extreme value such as the
18-24 LQ of 3.42 in section 3040, student residences); manual breaks are used where a threshold has a meaning (LQ = 1, 500 m, 10 minutes);
equal intervals and Jenks natural breaks are avoided for skewed data, because one outlier pushes almost all sections into the lowest class.

## Build

`gis` is rebuilt at the end of `build_food_access.py` (`dbt build --select tag:after_python`), because it reads ana.py_section_food_access.
Export for Tableau / Power BI (WGS84, simplified boundaries) is a separate step, to be written once the tool is chosen.
