-- VISUALISATION LAYER (QGIS + dashboard): a curated copy of ana tables. Do NOT use for modelling; models read ana.
-- One row per barri (73): boundary + the indicators of gis.section_indicators aggregated correctly:
--   counts are summed; densities and shares are recomputed from the sums (stores per 10k residents, premises per ha, vacant share ...);
--   age shares / LQ, education, income, foreign residents, cadastral value come from their own barri models (ana.*_barri, reconciled);
--   other section-level rates (transit exposure, building age, minutes of walk, tourism per resident ...) are POPULATION-WEIGHTED means of the sections
--   (= what the average resident of the barri experiences).
{% set chains = ['ALL', 'Condis', 'Dia', 'Caprabo', 'Mercadona', 'Consum_Charter', 'BonPreu_Esclat', 'Lidl', 'Aldi', 'Carrefour', 'Alcampo'] %}
{% set pw = ['share_foreign_change_2015_2026_pp', 'bldg_mean_age_years', 'bldg_share_pre1941_pct', 'bldg_share_1951_1980_pct', 'bldg_share_post1990_pct',
             'transit_departures_weekday_300m_n', 'dist_nearest_metro_station_m', 'imd_max_300m_vehicles_per_day',
             'median_walk_to_supermarket_m', 'median_minutes_chain', 'median_minutes_market', 'median_minutes_fresh_food', 'median_minutes_fresh_older',
             'share_dwellings_beyond_500m_pct', 'share_dwellings_fresh_over_10min_older_pct', 'median_climb_home_from_supermarket_m'] %}
{{ config(post_hook=primary_key('codi_barri'), indexes=[{'columns': ['geom'], 'type': 'gist'}]) }}
WITH counts AS (
    SELECT codi_barri,
{%- for ch in chains %}
           max(n_inside) FILTER (WHERE brand_group = '{{ ch }}') AS stores_{{ ch | lower }}_n{{ "," if not loop.last }}
{%- endfor %}
    FROM {{ ref('store_counts_barri') }} GROUP BY 1),
sec AS (
    SELECT codi_barri, sum(area_ha) AS area_ha, sum(dwellings_n) AS dwellings_n, sum(population_2015_n) AS population_2015_n,
{%- for v in pw %}
           sum(population_n * {{ v }}) / nullif(sum(population_n) FILTER (WHERE {{ v }} IS NOT NULL), 0) AS {{ v }},
{%- endfor %}
           sum(premises_active_n) AS premises_active_n, sum(premises_vacant_n) AS premises_vacant_n, sum(premises_daily_food_other_n) AS premises_daily_food_other_n,
           sum(premises_restaurants_bars_n) AS premises_restaurants_bars_n, sum(independent_supermarkets_2024_n) AS independent_supermarkets_2024_n,
           sum(pedestrian_priority_len_m) AS pedestrian_priority_len_m, sum(main_road_len_50m_m) AS main_road_len_50m_m,
           sum(hut_beds_n) AS hut_beds_n, sum(hotels_n) AS hotels_n, sum(airbnb_listings_n) AS airbnb_listings_n, sum(airbnb_reviews_last_12m_n) AS airbnb_reviews_last_12m_n,
           sum(openings_2016_2024_n) AS openings_2016_2024_n, sum(openings_new_site_n) AS openings_new_site_n, sum(openings_takeover_n) AS openings_takeover_n,
           sum(residents_beyond_500m_est) AS residents_beyond_500m_est, sum(residents_65plus_fresh_over_10min_est) AS residents_65plus_fresh_over_10min_est,
           count(*) FILTER (WHERE vulnerable_low_access) AS vulnerable_sections_n, count(*) FILTER (WHERE food_desert_low_income) AS food_desert_sections_n
    FROM {{ ref('section_indicators') }} GROUP BY 1),
nat AS (
    SELECT codi_barri, 100 * sum(foreign_2026_estimated_n) / sum(population_2026_n) AS share_foreign_pct,
           100 * sum(foreign_non_eu_2026_estimated_n) / sum(population_2026_n) AS share_foreign_non_eu_pct
    FROM {{ ref('pop_nationality_section') }} WHERE codi_barri IS NOT NULL GROUP BY 1),
metro AS (SELECT codi_barri, count(*) AS metro_stations_n FROM {{ ref('gtfs_stop_service') }} WHERE location_type = 1 AND modes ~ 'metro' GROUP BY 1)
SELECT b.codi_barri, n.nom_barri, n.codi_districte, d.nom_districte,
       -- context
       b.area_ha, b.population_n, b.population_per_ha, s.dwellings_n,
       -- population
       a.share_0_17_pct AS share_age_0_17_pct, a.share_18_24_pct AS share_age_18_24_pct, a.share_25_44_pct AS share_age_25_44_pct,
       a.share_45_64_pct AS share_age_45_64_pct, a.share_65plus_pct AS share_age_65plus_pct,
       a.age_0_17_location_quotient, a.age_18_24_location_quotient, a.age_25_44_location_quotient, a.age_45_64_location_quotient, a.age_65plus_location_quotient,
       e.tertiary_share_pct AS share_tertiary_education_pct,
       round(nat.share_foreign_pct::numeric, 2) AS share_foreign_pct, round(nat.share_foreign_non_eu_pct::numeric, 2) AS share_foreign_non_eu_pct,
       round(s.share_foreign_change_2015_2026_pp::numeric, 2) AS share_foreign_change_2015_2026_pp,
       s.population_2015_n, round((100.0 * (b.population_n - s.population_2015_n) / nullif(s.population_2015_n, 0))::numeric, 2) AS population_growth_2015_2026_pct,
       -- income and property
       i.disposable_income_eur_per_person, i.mean_section_gini_0_100, i.income_between_sections_cv_pct, cv.cadastral_value_eur_per_m2,
       -- buildings
       round(s.bldg_mean_age_years::numeric, 1) AS bldg_mean_age_years, round(s.bldg_share_pre1941_pct::numeric, 2) AS bldg_share_pre1941_pct,
       round(s.bldg_share_1951_1980_pct::numeric, 2) AS bldg_share_1951_1980_pct, round(s.bldg_share_post1990_pct::numeric, 2) AS bldg_share_post1990_pct,
       -- transport and streets
       b.cars_per_1000_residents, round(s.transit_departures_weekday_300m_n::numeric, 0) AS transit_departures_weekday_300m_n,
       coalesce(mt.metro_stations_n, 0) AS metro_stations_n, round(s.dist_nearest_metro_station_m::numeric, 0) AS dist_nearest_metro_station_m,
       round(s.imd_max_300m_vehicles_per_day::numeric, 0) AS imd_max_300m_vehicles_per_day,
       round((s.pedestrian_priority_len_m / s.area_ha)::numeric, 1) AS pedestrian_priority_m_per_ha, round((s.main_road_len_50m_m / s.area_ha)::numeric, 1) AS main_road_m_per_ha,
       -- commerce
       s.premises_active_n, round((s.premises_active_n / s.area_ha)::numeric, 1) AS premises_active_per_ha,
       round((100.0 * s.premises_vacant_n / nullif(s.premises_active_n + s.premises_vacant_n, 0))::numeric, 2) AS premises_vacant_share_pct,
       s.premises_daily_food_other_n, s.premises_restaurants_bars_n, s.independent_supermarkets_2024_n,
       -- tourism
       s.hut_beds_n, round((100.0 * s.hut_beds_n / b.population_n)::numeric, 2) AS hut_beds_per_100_residents, s.hotels_n,
       s.airbnb_listings_n, round((100.0 * s.airbnb_listings_n / b.population_n)::numeric, 2) AS airbnb_listings_per_100_residents, s.airbnb_reviews_last_12m_n,
       -- chain stores and openings
{%- for ch in chains %}
       coalesce(c.stores_{{ ch | lower }}_n, 0) AS stores_{{ ch | lower }}_n,
{%- endfor %}
       round(10000.0 * coalesce(c.stores_all_n, 0) / nullif(b.population_n, 0), 2) AS stores_per_10k_residents,
       s.openings_2016_2024_n, s.openings_new_site_n, s.openings_takeover_n,
       -- food access
       round(s.median_walk_to_supermarket_m::numeric, 0) AS median_walk_to_supermarket_m, round(s.median_minutes_chain::numeric, 1) AS median_minutes_chain,
       round(s.median_minutes_market::numeric, 1) AS median_minutes_market, round(s.median_minutes_fresh_food::numeric, 1) AS median_minutes_fresh_food,
       round(s.median_minutes_fresh_older::numeric, 1) AS median_minutes_fresh_older, round(s.median_climb_home_from_supermarket_m::numeric, 1) AS median_climb_home_from_supermarket_m,
       s.residents_beyond_500m_est, round((100.0 * s.residents_beyond_500m_est / b.population_n)::numeric, 2) AS share_residents_beyond_500m_pct,
       s.residents_65plus_fresh_over_10min_est, s.vulnerable_sections_n, s.food_desert_sections_n,
       u.geom
FROM {{ source('raw', 'adm_units_polygons') }} u
JOIN {{ ref('barri_model_table') }} b ON b.codi_barri = u.codi_barri
LEFT JOIN {{ source('ana', 'dim_neighborhood') }} n ON n.codi_barri = b.codi_barri
LEFT JOIN {{ source('ana', 'dim_district') }} d ON d.codi_districte = n.codi_districte
LEFT JOIN {{ ref('pop_age_bands_barri') }} a ON a.codi_barri = b.codi_barri
LEFT JOIN {{ ref('pop_education_barri') }} e ON e.codi_barri = b.codi_barri
LEFT JOIN {{ ref('income_barri') }} i ON i.codi_barri = b.codi_barri
LEFT JOIN {{ ref('cadastral_value_barri') }} cv ON cv.codi_barri = b.codi_barri
LEFT JOIN nat ON nat.codi_barri = b.codi_barri
LEFT JOIN metro mt ON mt.codi_barri = b.codi_barri
LEFT JOIN counts c ON c.codi_barri = b.codi_barri
LEFT JOIN sec s ON s.codi_barri = b.codi_barri
WHERE u.tipus_ua = 'BARRI'
