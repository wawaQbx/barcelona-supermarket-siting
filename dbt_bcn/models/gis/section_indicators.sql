-- VISUALISATION LAYER (QGIS + dashboard): a curated copy of ana tables. Do NOT use for modelling; models read ana.
-- One row per census section (1068): boundary + every indicator worth mapping, grouped by theme (column groups in docs/DASHBOARD_DESIGN.md).
-- Counts that depend on the section size also come as densities (per ha / per 10k residents) for fair maps.
-- Built after build_food_access.py (needs ana.py_section_food_access): tag after_python.
{% set chains = ['ALL', 'Condis', 'Dia', 'Caprabo', 'Mercadona', 'Consum_Charter', 'BonPreu_Esclat', 'Lidl', 'Aldi', 'Carrefour', 'Alcampo'] %}
{{ config(post_hook=primary_key('seccio_censal'), indexes=[{'columns': ['geom'], 'type': 'gist'}]) }}
WITH sec AS (SELECT seccio_censal, geom FROM {{ source('raw', 'adm_units_polygons') }} WHERE tipus_ua = 'SEC_CENS'),
counts AS (
    SELECT seccio_censal,
{%- for ch in chains %}
           max(n_inside) FILTER (WHERE brand_group = '{{ ch }}') AS stores_{{ ch | lower }}_n,
{%- endfor %}
           max(n_all_within_500m) FILTER (WHERE brand_group = 'ALL') AS stores_within_500m_n,
           max(n_ring_500m) FILTER (WHERE brand_group = 'ALL')       AS stores_ring_500m_n
    FROM {{ ref('store_counts_section') }} GROUP BY 1),
openings AS (
    SELECT seccio_censal, n_openings_2016_2024 - n_openings_clarel AS openings_2016_2024_n, n_openings_new_site AS openings_new_site_n,
           n_openings_takeover AS openings_takeover_n
    FROM {{ ref('store_openings_section') }} WHERE brand_group = 'ALL'),
metro AS (  -- metro stations (incl. funicular-metro interchange) around the section
    SELECT s.seccio_censal,
           count(*) FILTER (WHERE ST_DWithin(s.geom, t.geom, 500)) AS metro_stations_500m_n,
           round(min(ST_Distance(s.geom, t.geom))::numeric, 0)     AS dist_nearest_metro_station_m
    FROM sec s JOIN {{ ref('gtfs_stop_service') }} t ON t.location_type = 1 AND t.modes ~ 'metro' AND ST_DWithin(s.geom, t.geom, 5000)
    GROUP BY 1),
indep AS (  -- independent supermarket-class shops 2024 (no chain store within 50 m)
    SELECT s.seccio_censal, count(*) AS independent_supermarkets_2024_n
    FROM sec s JOIN {{ ref('int_census_premises') }} c ON ST_Intersects(s.geom, c.geom)
    WHERE c.census_year = 2024 AND c.nom_activitat = 'Autoservei / Supermercat' AND c.nom_principal_activitat = 'Actiu'
      AND NOT EXISTS (SELECT 1 FROM {{ ref('store_points') }} p WHERE p.in_city AND ST_DWithin(p.geom, c.geom, 50))
    GROUP BY 1)
SELECT s.seccio_censal, m.codi_barri, n.nom_barri, m.codi_districte, d.nom_districte,
       -- context and denominators
       m.area_ha, m.population_n, m.population_per_ha, m.dwellings_n, m.dist_placa_catalunya_m,
       -- population
       m.share_age_0_17_pct, m.share_age_18_24_pct, m.share_age_25_44_pct, m.share_age_45_64_pct, m.share_age_65plus_pct,
       a.age_0_17_location_quotient, a.age_18_24_location_quotient, a.age_25_44_location_quotient, a.age_45_64_location_quotient, a.age_65plus_location_quotient,
       m.share_tertiary_education_pct,
       f.share_foreign_2026_pct AS share_foreign_pct, f.share_foreign_non_eu_2026_pct AS share_foreign_non_eu_pct, f.share_foreign_change_2015_2026_pp,
       b.population_2015_n, b.population_growth_2015_2026_pct,
       -- income and property
       m.disposable_income_eur_per_person, b.disposable_income_2015_eur_per_person, m.gini_index_0_100, m.cadastral_value_eur_per_m2,
       -- buildings and planning (cadastre, PGM zoning)
       m.bldg_mean_age_years, m.bldg_share_pre1941_pct, m.bldg_share_1951_1980_pct, m.bldg_share_post1990_pct, m.floor_area_ratio, m.commercial_floor_share_pct,
       m.pgm_share_12_old_town_pct, m.pgm_share_13_densification_pct, m.pgm_share_15_conservation_pct, m.pgm_share_18_specific_volume_pct,
       m.pgm_share_20_detached_pct, m.pgm_share_22_industrial_pct,
       -- transport and streets
       CASE WHEN m.cars_fleet_distorted THEN NULL ELSE m.cars_per_1000_residents END AS cars_per_1000_residents,   -- NULL where company fleets distort it
       m.transit_stops_300m_n, m.transit_departures_weekday_300m_n,
       coalesce(mt.metro_stations_500m_n, 0) AS metro_stations_500m_n, mt.dist_nearest_metro_station_m,
       m.main_road_len_50m_m, m.motorway_len_50m_m, m.pedestrian_street_len_50m_m, w.pedestrian_priority_len_m,
       round((w.pedestrian_priority_len_m / m.area_ha)::numeric, 1) AS pedestrian_priority_m_per_ha,
       m.imd_max_300m_vehicles_per_day, ps.treated_pacified_street AS near_pacified_street_2020, l10.treated AS new_metro_access_l10_2018,
       -- commerce (2024 commercial census, ground-floor premises)
       m.premises_active_n, round((m.premises_active_n / m.area_ha)::numeric, 1) AS premises_active_per_ha,
       m.premises_vacant_n, round((100.0 * m.premises_vacant_n / nullif(m.premises_active_n + m.premises_vacant_n, 0))::numeric, 2) AS premises_vacant_share_pct,
       m.premises_retail_n, m.premises_daily_food_other_n, m.premises_restaurants_bars_n, m.premises_supermarket_census2024_n,
       coalesce(i.independent_supermarkets_2024_n, 0) AS independent_supermarkets_2024_n,
       m.commercial_premises_per_100_dwellings, b.premises_active_2014_n,
       -- tourism
       t.hut_beds_n, t.hut_beds_per_100_residents, t.hut_beds_2017_per_100_residents, t.hotels_n, t.airbnb_listings_n,
       t.airbnb_listings_per_100_residents, t.airbnb_reviews_last_12m_n, m.tourism_hospitality_per_100_dwellings,
       -- chain stores (inside the section; within 500 m incl. stores outside the city; ring = within 500 m but outside the section)
{%- for ch in chains %}
       coalesce(c.stores_{{ ch | lower }}_n, 0) AS stores_{{ ch | lower }}_n,
{%- endfor %}
       round(10000.0 * coalesce(c.stores_all_n, 0) / nullif(m.population_n, 0), 2) AS stores_per_10k_residents,
       coalesce(c.stores_within_500m_n, 0) AS stores_within_500m_n, coalesce(c.stores_ring_500m_n, 0) AS stores_ring_500m_n,
       -- openings 2016-2024 (Clarel conversions excluded)
       coalesce(o.openings_2016_2024_n, 0) AS openings_2016_2024_n, coalesce(o.openings_new_site_n, 0) AS openings_new_site_n,
       coalesce(o.openings_takeover_n, 0) AS openings_takeover_n,
       -- food access (walking network, slope-aware minutes; older pace = 70% of adult speed)
       fa.median_walk_to_supermarket_m, fa.share_dwellings_beyond_500m_pct, fa.share_dwellings_beyond_800m_pct,
       fa.share_dwellings_beyond_500m_any_supermarket_pct, fa.residents_beyond_500m_any_supermarket_est,   -- chains + independent supermarket-class shops
       fa.median_minutes_chain, fa.median_minutes_any_supermarket, fa.median_minutes_market, fa.median_minutes_fresh_food,
       fa.median_minutes_chain_older, fa.median_minutes_fresh_older, fa.share_dwellings_fresh_over_10min_older_pct,
       fa.median_climb_home_from_supermarket_m, fa.residents_beyond_500m_est, fa.residents_65plus_beyond_500m_est, fa.residents_65plus_fresh_over_10min_est,
       fa.vulnerable_low_access, fa.vulnerable_low_access_chain, fa.food_desert_low_income,
       fa.food_desert_low_income_strict, fa.food_desert_low_income_broad,   -- range of the food-desert flag (main = middle definition of fresh food)
       fa.edge_outside_food_uncertain,   -- city-edge section next to a built-up area: shops across the boundary are under-recorded (OSM)
       -- dashboard page 04 helpers
       s.seccio_censal::text AS seccio_key,                                   -- text key for the Power BI Shape map (TopoJSON keys are text)
       CASE WHEN fa.median_minutes_fresh_older < 5 THEN 'Under 5 min' WHEN fa.median_minutes_fresh_older < 10 THEN '5-10 min'
            WHEN fa.median_minutes_fresh_older < 15 THEN '10-15 min' ELSE '15 min or more' END AS fresh_access_class,
       CASE WHEN fa.median_minutes_fresh_older < 5 THEN 1 WHEN fa.median_minutes_fresh_older < 10 THEN 2
            WHEN fa.median_minutes_fresh_older < 15 THEN 3 ELSE 4 END AS fresh_access_order,
       CASE WHEN fa.median_minutes_fresh_older < 5 THEN '#EFE6D8' WHEN fa.median_minutes_fresh_older < 10 THEN '#E3A99C'
            WHEN fa.median_minutes_fresh_older < 15 THEN '#D9675E' ELSE '#9E3B33' END AS fresh_access_colour,   -- red ramp = worse access (comparison rule)
       CASE WHEN fa.food_desert_low_income THEN 'Food desert'
            WHEN fa.food_desert_low_income_strict THEN 'Food desert (strict def.)'
            WHEN fa.vulnerable_low_access THEN 'Older / no car, far' END AS access_flag,
       CASE WHEN fa.food_desert_low_income THEN 1 WHEN fa.food_desert_low_income_strict THEN 2 WHEN fa.vulnerable_low_access THEN 3 END AS access_flag_order,
       -- scatter legend: same groups, the strict-only food desert shown with the other sections (the scatter x axis uses the MAIN definition)
       CASE WHEN fa.food_desert_low_income THEN 'Food desert' WHEN fa.vulnerable_low_access THEN 'Older / no car, far' ELSE 'Other sections' END AS access_group,
       -- far from fresh food by income quarter (replaces the scatter): residents estimated from the share of dwellings over 10 min (older pace)
       round(m.population_n * fa.share_dwellings_fresh_over_10min_older_pct / 100.0) AS residents_fresh_over_10min_est,
       ntile(4) OVER (ORDER BY m.disposable_income_eur_per_person) AS income_quarter_order,   -- 1 = lowest income (same cut as the food-desert q25 flag)
       (ARRAY['Lowest 25%', '25-50%', '50-75%', 'Highest 25%'])[ntile(4) OVER (ORDER BY m.disposable_income_eur_per_person)] AS income_quarter,
       s.geom
FROM sec s
JOIN {{ ref('section_model_table') }} m USING (seccio_censal)
LEFT JOIN {{ source('ana', 'dim_neighborhood') }} n ON n.codi_barri = m.codi_barri
LEFT JOIN {{ source('ana', 'dim_district') }} d ON d.codi_districte = m.codi_districte
LEFT JOIN {{ ref('pop_age_bands_section') }} a USING (seccio_censal)
LEFT JOIN {{ ref('pop_nationality_section') }} f USING (seccio_censal)
LEFT JOIN {{ ref('section_baseline_2015') }} b USING (seccio_censal)
LEFT JOIN {{ ref('section_walkability') }} w USING (seccio_censal)
LEFT JOIN {{ ref('section_pacified_streets') }} ps USING (seccio_censal)
LEFT JOIN {{ ref('section_metro_l10') }} l10 USING (seccio_censal)
LEFT JOIN {{ ref('section_tourism') }} t USING (seccio_censal)
LEFT JOIN counts c USING (seccio_censal)
LEFT JOIN openings o USING (seccio_censal)
LEFT JOIN metro mt USING (seccio_censal)
LEFT JOIN indep i USING (seccio_censal)
LEFT JOIN {{ source('ana', 'py_section_food_access') }} fa USING (seccio_censal)
