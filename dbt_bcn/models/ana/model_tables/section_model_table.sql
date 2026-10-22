-- ONE ROW PER CENSUS SECTION (1068) = the base table for the siting regressions.
-- Outcomes: store counts per brand group (store_counts_section) under the two edge-effect definitions.
-- Predictors: demand (population, density, age, education, income), mobility (vehicles, public-transport departures),
--             commerce (ground-floor premises of the 2024 census), housing / tourism, cadastral value, position.
-- Corrected tables are used for age, education and motorization (see PROJECT_REPORT section 5).
{{ config(post_hook=primary_key('seccio_censal')) }}
WITH geo AS (
    SELECT seccio_censal, codi_barri, codi_districte, geom, ST_Area(geom) / 10000.0 AS area_ha, ST_PointOnSurface(geom) AS pt
    FROM {{ source('raw', 'adm_units_polygons') }} WHERE tipus_ua = 'SEC_CENS'),
transit AS (
    SELECT g.seccio_censal,
           count(s.stop_id)                           AS transit_stops_300m_n,
           coalesce(sum(s.departures_weekday), 0)     AS transit_departures_weekday_300m_n
    FROM geo g LEFT JOIN {{ ref('gtfs_stop_service') }} s ON ST_DWithin(g.geom, s.geom, 300) GROUP BY 1),
cen AS (
    SELECT seccio_censal,
           count(*) FILTER (WHERE nom_principal_activitat = 'Actiu')                                                    AS premises_active_n,
           count(*) FILTER (WHERE nom_sector_activitat ILIKE 'Locals buits%')                                           AS premises_vacant_n,
           count(*) FILTER (WHERE nom_sector_activitat ILIKE 'Comer_ al detall%')                                       AS premises_retail_n,
           count(*) FILTER (WHERE nom_grup_activitat ILIKE 'Quotidi_ alimentari' AND nom_activitat <> 'Autoservei / Supermercat') AS premises_daily_food_other_n,
           count(*) FILTER (WHERE nom_grup_activitat ILIKE 'Restaurants%')                                              AS premises_restaurants_bars_n,
           count(*) FILTER (WHERE nom_activitat = 'Autoservei / Supermercat')                                           AS premises_supermarket_census2024_n
    FROM {{ source('raw', 'cen_census_2024') }} GROUP BY 1),
-- cadastre (2026): building age, built floor area, floor area of ground-floor premises
cad AS (
    SELECT g.seccio_censal, e.bldg_mean_age_years, f.built_floor_m2
    FROM geo g
    LEFT JOIN (SELECT seccio_censal, avg(edat_mitjana_anys) AS bldg_mean_age_years FROM {{ source('raw', 'cad_edif_edat') }} GROUP BY 1) e USING (seccio_censal)
    LEFT JOIN (SELECT seccio_censal, sum(superficie_m2) AS built_floor_m2 FROM {{ source('raw', 'cad_finques_sup') }} WHERE desc_sup = 'Superfície_construïda' GROUP BY 1) f USING (seccio_censal)),
-- note: raw.cad_edif_sup 'Superfície_locals' is the floor area of ALL cadastral units (~90% of built area), not shops; commercial floor area comes from hou_2026_us_desti
-- road network (OSM): length of main roads and of pedestrian streets inside the section + 50 m (index join, one intersection per road piece)
road_pieces AS MATERIALIZED (
    SELECT g.seccio_censal, r.highway, ST_Length(ST_Intersection(r.geom, ST_Buffer(g.geom, 50, 2))) AS len
    FROM geo g JOIN {{ source('raw', 'trf_osm_roads') }} r ON ST_DWithin(r.geom, g.geom, 50)
    WHERE r.highway ~ '^(trunk|primary|secondary|motorway)(_link)?$' OR r.highway IN ('pedestrian', 'living_street')),
roads AS (
    SELECT seccio_censal,
           sum(len) FILTER (WHERE highway ~ '^(trunk|primary|secondary)(_link)?$') AS main_road_len_m,
           sum(len) FILTER (WHERE highway IN ('pedestrian', 'living_street'))      AS pedestrian_street_len_m,
           sum(len) FILTER (WHERE highway ~ '^motorway')                            AS motorway_len_m
    FROM road_pieces GROUP BY 1),
-- building construction period (cadastre, number of buildings; no building of an era = 0%, not NULL) and PGM zoning (share of section area; only keys whose meaning is verified)
era AS (
    SELECT seccio_censal, sum(nombre) AS bldg_total,
           sum(nombre) FILTER (WHERE any_construccio IN ('<1901', '1901-1940'))                         AS b_pre1941,
           sum(nombre) FILTER (WHERE any_construccio IN ('1951-1960', '1961-1970', '1971-1980'))        AS b_1951_1980,
           sum(nombre) FILTER (WHERE any_construccio IN ('1991-2000', '2001-2010', '2011-2020', '2021-2030')) AS b_post1990
    FROM {{ source('raw', 'cad_edif_any') }} GROUP BY 1),
pgm_pieces AS MATERIALIZED (
    SELECT g.seccio_censal, substring(z.clau from '^[0-9]+') AS fam, ST_Area(ST_Intersection(z.geom, g.geom)) AS a
    FROM geo g JOIN {{ source('raw', 'pgm_qualif_polygons') }} z ON ST_Intersects(z.geom, g.geom)
    WHERE substring(z.clau from '^[0-9]+') IN ('12', '13', '15', '18', '20', '22')),
pgm AS (
    SELECT seccio_censal,
           sum(a) FILTER (WHERE fam = '12') AS a12, sum(a) FILTER (WHERE fam = '13') AS a13, sum(a) FILTER (WHERE fam = '15') AS a15,
           sum(a) FILTER (WHERE fam = '18') AS a18, sum(a) FILTER (WHERE fam = '20') AS a20, sum(a) FILTER (WHERE fam = '22') AS a22
    FROM pgm_pieces GROUP BY 1),
-- traffic counts (2025): highest mean working-day traffic of the counting stations within 300 m
imd AS (
    SELECT g.seccio_censal, max(st.imd) AS imd_max_300m_vehicles_per_day
    FROM geo g JOIN (SELECT d.id_aforament, ST_Transform(ST_SetSRID(ST_MakePoint(d.lon, d.lat), 4326), 25831) AS geom, avg(x.imd_vehicles_per_day) AS imd
                     FROM {{ source('raw', 'trf_aforament_desc_2025') }} d JOIN {{ source('raw', 'trf_aforament_detall_2025') }} x USING (id_aforament)
                     WHERE x.desc_tipus_dia = 'laborables' GROUP BY 1, 2) st ON ST_DWithin(g.geom, st.geom, 300)
    GROUP BY 1)
SELECT g.seccio_censal, g.codi_barri, g.codi_districte, round(g.area_ha::numeric, 2) AS area_ha,
       ST_X(g.pt) AS x_utm25831_m, ST_Y(g.pt) AS y_utm25831_m,
       round(ST_Distance(g.pt, ST_Transform(ST_SetSRID(ST_MakePoint(2.1700, 41.3870), 4326), 25831))::numeric, 0) AS dist_placa_catalunya_m,
       a.pop_official_n AS population_n,
       round((a.pop_official_n / g.area_ha)::numeric, 1) AS population_per_ha,
       a.share_0_17_pct AS share_age_0_17_pct, a.share_18_24_pct AS share_age_18_24_pct, a.share_25_44_pct AS share_age_25_44_pct, a.share_45_64_pct AS share_age_45_64_pct, a.share_65plus_pct AS share_age_65plus_pct,
       e.tertiary_share_pct AS share_tertiary_education_pct,
       i.renda_disponible_eur_per_persona AS disposable_income_eur_per_person,
       gi.index_gini AS gini_index_0_100,
       m.cars_per_1000_hab AS cars_per_1000_residents, m.fleet_distorted AS cars_fleet_distorted,
       h.habitatges_n AS dwellings_n, h.locals_comercials_per_100_habitatges AS commercial_premises_per_100_dwellings,
       h.turisme_hostaleria_per_100_habitatges AS tourism_hospitality_per_100_dwellings,
       c.valor_cadastral_eur_per_m2 AS cadastral_value_eur_per_m2,
       t.transit_stops_300m_n, t.transit_departures_weekday_300m_n,
       coalesce(ce.premises_active_n, 0) AS premises_active_n, coalesce(ce.premises_vacant_n, 0) AS premises_vacant_n, coalesce(ce.premises_retail_n, 0) AS premises_retail_n, coalesce(ce.premises_daily_food_other_n, 0) AS premises_daily_food_other_n, coalesce(ce.premises_restaurants_bars_n, 0) AS premises_restaurants_bars_n, coalesce(ce.premises_supermarket_census2024_n, 0) AS premises_supermarket_census2024_n,
       round(cd.bldg_mean_age_years::numeric, 1) AS bldg_mean_age_years, round((cd.built_floor_m2 / (g.area_ha * 10000))::numeric, 3) AS floor_area_ratio,
       round(h.locals_comercials_m2::numeric, 0) AS commercial_floor_m2, round((100.0 * h.locals_comercials_m2 / nullif(cd.built_floor_m2, 0))::numeric, 2) AS commercial_floor_share_pct,
       round(coalesce(rd.main_road_len_m, 0)::numeric, 0) AS main_road_len_50m_m, round(coalesce(rd.pedestrian_street_len_m, 0)::numeric, 0) AS pedestrian_street_len_50m_m,
       round(coalesce(rd.motorway_len_m, 0)::numeric, 0) AS motorway_len_50m_m, round(im.imd_max_300m_vehicles_per_day::numeric, 0) AS imd_max_300m_vehicles_per_day,
       round((100.0 * coalesce(er.b_pre1941, 0) / nullif(er.bldg_total, 0))::numeric, 2) AS bldg_share_pre1941_pct,
       round((100.0 * coalesce(er.b_1951_1980, 0) / nullif(er.bldg_total, 0))::numeric, 2) AS bldg_share_1951_1980_pct,
       round((100.0 * coalesce(er.b_post1990, 0) / nullif(er.bldg_total, 0))::numeric, 2) AS bldg_share_post1990_pct,
       round((100.0 * coalesce(pg.a12, 0) / (g.area_ha * 10000))::numeric, 2) AS pgm_share_12_old_town_pct,
       round((100.0 * coalesce(pg.a13, 0) / (g.area_ha * 10000))::numeric, 2) AS pgm_share_13_densification_pct,
       round((100.0 * coalesce(pg.a15, 0) / (g.area_ha * 10000))::numeric, 2) AS pgm_share_15_conservation_pct,
       round((100.0 * coalesce(pg.a18, 0) / (g.area_ha * 10000))::numeric, 2) AS pgm_share_18_specific_volume_pct,
       round((100.0 * coalesce(pg.a20, 0) / (g.area_ha * 10000))::numeric, 2) AS pgm_share_20_detached_pct,
       round((100.0 * coalesce(pg.a22, 0) / (g.area_ha * 10000))::numeric, 2) AS pgm_share_22_industrial_pct
FROM geo g
LEFT JOIN {{ ref('pop_age_bands_section') }} a USING (seccio_censal)
LEFT JOIN {{ ref('pop_education_section') }} e USING (seccio_censal)
LEFT JOIN {{ source('raw', 'inc_2022_renda_disponible_llars_per_persona') }} i USING (seccio_censal)
LEFT JOIN {{ source('raw', 'inc_2023_atles_renda_index_gini') }} gi USING (seccio_censal)
LEFT JOIN {{ ref('motorization_section') }} m USING (seccio_censal)
LEFT JOIN {{ source('raw', 'hou_2026_us_desti_by_seccio') }} h USING (seccio_censal)
LEFT JOIN {{ source('raw', 'hou_2026_valor_cadastral_by_seccio') }} c USING (seccio_censal)
LEFT JOIN transit t USING (seccio_censal)
LEFT JOIN cen ce USING (seccio_censal)
LEFT JOIN cad cd USING (seccio_censal)
LEFT JOIN roads rd USING (seccio_censal)
LEFT JOIN imd im USING (seccio_censal)
LEFT JOIN era er USING (seccio_censal)
LEFT JOIN pgm pg USING (seccio_censal)
