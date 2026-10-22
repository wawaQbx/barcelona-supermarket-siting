-- =====================================================================================================
-- Store counts per analysis unit (census section and barri), two definitions for the edge effect:
--   n_inside        : stores whose point lies inside the unit
--   n_city_within_X : stores inside the CITY within X m of the unit polygon (inside the unit counts, distance 0)
--   n_all_within_X  : same, but stores outside the city (the 263 stores of the bounding box) also count
-- X = 250, 500, 1000 m (2000 m for hypermarkets). Brand groups merge banners of one chain.
-- Source: raw.store_supermarkets_official (964 stores; lon/lat WGS84 -> EPSG:25831). Dia / Mercadona etc. outside the city are incomplete (see PROJECT_REPORT).
-- =====================================================================================================
DROP TABLE IF EXISTS ana.store_points CASCADE;
CREATE TABLE ana.store_points AS
SELECT (row_number() OVER ())::text AS store_id, 'official_list'::text AS point_source, (s.codi_barri IS NOT NULL) AS has_barri, s.ensenya, s.store_type,
       CASE WHEN s.ensenya IN ('Consum','Charter') THEN 'Consum_Charter'
            WHEN s.ensenya IN ('Bon Preu','Esclat') THEN 'BonPreu_Esclat'
            WHEN s.ensenya IN ('Alcampo','Mi Alcampo') THEN 'Alcampo'
            WHEN s.ensenya LIKE 'Carrefour%' THEN 'Carrefour'
            ELSE s.ensenya END AS brand_group,
       -- coordinates corrected to the census premise when the address check found the same chain at the store's address (check_store_addresses.py)
       ST_Transform(ST_SetSRID(ST_MakePoint(coalesce(k.census_lon, s.lon), coalesce(k.census_lat, s.lat)), 4326), 25831) AS geom,
       (k.census_lon IS NOT NULL) AS coord_corrected, k.coord_offset_m AS coord_correction_m
FROM raw.store_supermarkets_official s
LEFT JOIN raw.store_coordinate_corrections k ON k.ensenya = s.ensenya AND k.adreca = s.adreca AND abs(k.lat - s.lat) < 1e-7 AND abs(k.lon - s.lon) < 1e-7
WHERE s.lon IS NOT NULL AND s.lat IS NOT NULL;
CREATE INDEX ON ana.store_points USING gist (geom);
-- Dia outside the city: the Dia site now returns 403, so OSM Dia shops outside the city within 2 km that are not within 150 m of a listed Dia are added
-- (2026-10: 24 OSM Dia in that ring, 20 already listed, 4 added). Checked in the city: OSM covers 39% of Dia, 86% of OSM Dia match an official store
-- (median 15 m), 14% are closed stores still in OSM - so about 0.5 of the 4 added may be closed.
INSERT INTO ana.store_points (store_id, point_source, has_barri, ensenya, store_type, brand_group, geom)
SELECT 'osm_' || o.osm_id, 'osm_supplement', false, 'Dia', 'supermarket', 'Dia', o.geom
FROM raw.hist_osm_shops o
WHERE (o.ensenya ILIKE 'dia%' OR o.nom ILIKE 'dia %' OR o.nom ILIKE '%supermercados dia%')
  AND NOT EXISTS (SELECT 1 FROM raw.adm_units_polygons u WHERE u.tipus_ua = 'SEC_CENS' AND ST_Intersects(u.geom, o.geom))
  AND EXISTS (SELECT 1 FROM raw.adm_units_polygons u WHERE u.tipus_ua = 'SEC_CENS' AND ST_DWithin(u.geom, o.geom, 2000))
  AND NOT EXISTS (SELECT 1 FROM ana.store_points p WHERE p.brand_group = 'Dia' AND ST_DWithin(p.geom, o.geom, 150));
-- RING stores (edge effect): stores outside the city within 2 km of it, collected by fetch_ring_stores.py + fetch_ring_osm.py (official locators of Condis,
-- Bon Preu / Esclat, Consum / Charter, Alcampo; OSM for Mercadona, Caprabo, Lidl, Aldi, Carrefour, Dia). Added only when no listed store of the same chain is within 100 m.
INSERT INTO ana.store_points (store_id, point_source, has_barri, ensenya, store_type, brand_group, geom)
SELECT 'ring_' || row_number() OVER (), 'ring_' || CASE WHEN r.source ILIKE '%osm%' THEN 'osm' ELSE 'official' END, false, r.ensenya, coalesce(r.store_type, 'supermarket'),
       CASE WHEN r.ensenya IN ('Consum','Charter') THEN 'Consum_Charter' WHEN r.ensenya IN ('Bon Preu','Esclat') THEN 'BonPreu_Esclat'
            WHEN r.ensenya IN ('Alcampo','Mi Alcampo') THEN 'Alcampo' WHEN r.ensenya LIKE 'Carrefour%' THEN 'Carrefour' ELSE r.ensenya END,
       ST_Transform(ST_SetSRID(ST_MakePoint(r.lon, r.lat), 4326), 25831)
FROM (SELECT DISTINCT ON (ensenya, round(lat::numeric, 4), round(lon::numeric, 4)) * FROM raw.store_ring_stores_2km WHERE lat IS NOT NULL) r
WHERE NOT EXISTS (SELECT 1 FROM raw.adm_units_polygons u WHERE u.tipus_ua = 'SEC_CENS' AND ST_DWithin(u.geom, ST_Transform(ST_SetSRID(ST_MakePoint(r.lon, r.lat), 4326), 25831), 1))
  AND EXISTS (SELECT 1 FROM raw.adm_units_polygons u WHERE u.tipus_ua = 'SEC_CENS' AND ST_DWithin(u.geom, ST_Transform(ST_SetSRID(ST_MakePoint(r.lon, r.lat), 4326), 25831), 2000));
DELETE FROM ana.store_points a USING ana.store_points b
WHERE a.point_source LIKE 'ring_%' AND b.point_source NOT LIKE 'ring_%' AND a.brand_group = b.brand_group AND ST_DWithin(a.geom, b.geom, 100);
DELETE FROM ana.store_points a USING ana.store_points b       -- duplicates inside the ring list itself (official + OSM copies of one store)
WHERE a.point_source LIKE 'ring_%' AND b.point_source LIKE 'ring_%' AND a.brand_group = b.brand_group AND a.store_id > b.store_id AND ST_DWithin(a.geom, b.geom, 100);
ALTER TABLE ana.store_points ADD COLUMN in_city boolean;
-- in the city = assigned to a barri in the source, or on a section polygon (a few points sit on the boundary line / a few metres off)
UPDATE ana.store_points p SET in_city = has_barri OR EXISTS (SELECT 1 FROM raw.adm_units_polygons u WHERE u.tipus_ua = 'SEC_CENS' AND ST_DWithin(u.geom, p.geom, 1));
COMMENT ON TABLE ana.store_points IS 'All 964 listed stores + OSM Dia supplement outside the city (point_source) as EPSG:25831 points with brand_group and in_city flag. Built by sql/ana_store_counts.sql';

-- DATA CORRECTION (2026-10-13): 57 'Dia Market' entries of the Dia store locator are Clarel drugstores (Dia group brand until 2023), not supermarkets:
-- no Dia-named premise within 60 m in any census edition, but a Clarel premise within 60 m in 2024 (56 of 57); the nearest 2024 premise is a drugstore, bar,
-- dry-cleaner ... and only once a supermarket. They are moved to ana.store_points_excluded and left out of every count and model.
DROP TABLE IF EXISTS ana.store_points_excluded CASCADE;
CREATE TABLE ana.store_points_excluded AS
WITH cen AS (
    SELECT nom_local, ST_Transform(ST_SetSRID(ST_MakePoint(x_ed50, y_ed50), 23031), 25831) AS g FROM raw.cen_census_2014 WHERE x_ed50 IS NOT NULL
    UNION ALL SELECT nom_local, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) FROM raw.cen_census_2016 WHERE lon IS NOT NULL
    UNION ALL SELECT nom_local, geom FROM raw.cen_census_2019
    UNION ALL SELECT nom_local, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) FROM raw.cen_census_2022 WHERE lon IS NOT NULL
    UNION ALL SELECT nom_local, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) FROM raw.cen_census_2024 WHERE lon IS NOT NULL),
dia AS (SELECT g FROM cen WHERE nom_local ~* '^(dia\M|dia %|dia market|supermercados dia|la plaza de dia)'),
clarel24 AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) AS g FROM raw.cen_census_2024 WHERE lon IS NOT NULL AND nom_local ~* 'clarel')
SELECT p.*, 'likely Clarel drugstore listed in the Dia locator'::text AS exclusion_reason
FROM ana.store_points p
WHERE p.brand_group = 'Dia' AND p.point_source = 'official_list'
  AND NOT EXISTS (SELECT 1 FROM dia WHERE ST_DWithin(dia.g, p.geom, 60))
  AND EXISTS (SELECT 1 FROM clarel24 c WHERE ST_DWithin(c.g, p.geom, 60));
DELETE FROM ana.store_points p USING ana.store_points_excluded x WHERE p.store_id = x.store_id;
COMMENT ON TABLE ana.store_points_excluded IS 'Store-list entries excluded from all analyses (57 Clarel drugstores listed as Dia Market by the Dia locator). Built by sql/ana_store_counts.sql';

-- COMPLETION (2026-10-13): chain supermarkets recorded by the 2024 commercial census (municipal field survey) but missing from the store list
-- (no store of the same chain within 150 m): mostly OSM-sourced chains (Caprabo 28, Condis 18, Dia 11, Carrefour 9 ...). Added as point_source = 'census_2024_supplement'.
INSERT INTO ana.store_points (store_id, point_source, has_barri, ensenya, store_type, brand_group, geom)
SELECT 'cen24_' || c.id_global, 'census_2024_supplement', true, c.ensenya,
       CASE WHEN c.nom_local ~* 'express|city|go\M' THEN 'convenience' ELSE 'supermarket' END, c.brand_group, c.g
FROM (SELECT x.id_global, x.nom_local, ST_Transform(ST_SetSRID(ST_MakePoint(x.lon, x.lat), 4326), 25831) AS g,
             CASE WHEN x.nom_local ~* 'condis' THEN 'Condis' WHEN x.nom_local ~* '^(dia\M|dia %|dia market|supermercados dia|la plaza de dia)' THEN 'Dia'
                  WHEN x.nom_local ~* 'caprabo' THEN 'Caprabo' WHEN x.nom_local ~* 'mercadona' THEN 'Mercadona' WHEN x.nom_local ~* 'charter' THEN 'Charter'
                  WHEN x.nom_local ~* '\mconsum\M' THEN 'Consum' WHEN x.nom_local ~* 'esclat' THEN 'Esclat' WHEN x.nom_local ~* 'bon ?preu' THEN 'Bon Preu'
                  WHEN x.nom_local ~* '\mlidl' THEN 'Lidl' WHEN x.nom_local ~* '\maldi\M' THEN 'Aldi' WHEN x.nom_local ~* 'carrefour express' THEN 'Carrefour Express'
                  WHEN x.nom_local ~* 'carrefour market' THEN 'Carrefour Market' WHEN x.nom_local ~* 'carrefour' THEN 'Carrefour'
                  WHEN x.nom_local ~* 'alcampo' THEN 'Mi Alcampo' END AS ensenya,
             CASE WHEN x.nom_local ~* 'condis' THEN 'Condis' WHEN x.nom_local ~* '^(dia\M|dia %|dia market|supermercados dia|la plaza de dia)' THEN 'Dia'
                  WHEN x.nom_local ~* 'caprabo' THEN 'Caprabo' WHEN x.nom_local ~* 'mercadona' THEN 'Mercadona' WHEN x.nom_local ~* 'charter|\mconsum\M' THEN 'Consum_Charter'
                  WHEN x.nom_local ~* 'esclat|bon ?preu' THEN 'BonPreu_Esclat' WHEN x.nom_local ~* '\mlidl' THEN 'Lidl' WHEN x.nom_local ~* '\maldi\M' THEN 'Aldi'
                  WHEN x.nom_local ~* 'carrefour' THEN 'Carrefour' WHEN x.nom_local ~* 'alcampo' THEN 'Alcampo' END AS brand_group
      FROM raw.cen_census_2024 x
      WHERE x.lon IS NOT NULL AND x.nom_activitat = 'Autoservei / Supermercat' AND x.nom_principal_activitat = 'Actiu') c
WHERE c.brand_group IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM ana.store_points p WHERE p.brand_group = c.brand_group AND ST_DWithin(p.geom, c.g, 150));
UPDATE ana.store_points SET in_city = true WHERE point_source = 'census_2024_supplement';   -- the census covers only the city

-- format split (the user's store_type in the official list): Alcampo hypermarkets vs Mi Alcampo; Carrefour convenience (Express / small Market) vs supermarket
ALTER TABLE ana.store_points ADD COLUMN format_group text;
UPDATE ana.store_points SET format_group = CASE
    WHEN brand_group = 'Alcampo'   AND store_type = 'hypermarket' THEN 'Alcampo_hypermarket'
    WHEN brand_group = 'Alcampo'                                  THEN 'Alcampo_MiAlcampo'
    WHEN brand_group = 'Carrefour' AND store_type = 'convenience' THEN 'Carrefour_convenience'
    WHEN brand_group = 'Carrefour'                                THEN 'Carrefour_supermarket' END;
-- opening timeline (city stores only): first census edition in which the store appears (2014 = already open in 2014), Clarel -> Dia conversions
ALTER TABLE ana.store_points ADD COLUMN first_seen_census_year integer, ADD COLUMN opening_era text, ADD COLUMN clarel_conversion boolean;
UPDATE ana.store_points p SET first_seen_census_year = o.first_seen_census_year, opening_era = o.opening_era, clarel_conversion = (o.first_banner = 'Clarel (legacy)')
FROM ana.py_stores_opening_era_city o
WHERE p.in_city AND o.ensenya = p.ensenya
  AND ST_DWithin(p.geom, ST_Transform(ST_SetSRID(ST_MakePoint(o.lon, o.lat), 4326), 25831), 1);
-- one row per store and group it belongs to (chain, format, ALL)
DROP TABLE IF EXISTS ana.store_group_membership CASCADE;
CREATE TABLE ana.store_group_membership AS
SELECT store_id, brand_group AS grp FROM ana.store_points UNION ALL
SELECT store_id, format_group FROM ana.store_points WHERE format_group IS NOT NULL UNION ALL
SELECT store_id, 'ALL' FROM ana.store_points;
CREATE INDEX ON ana.store_group_membership (grp);
COMMENT ON TABLE ana.store_group_membership IS 'Store -> group (chain, format group, ALL), used to count stores per group. Built by sql/ana_store_counts.sql';

DROP TABLE IF EXISTS ana.store_counts_section CASCADE;
CREATE TABLE ana.store_counts_section AS
WITH units AS (SELECT seccio_censal, geom FROM raw.adm_units_polygons WHERE tipus_ua = 'SEC_CENS'),
groups AS (SELECT DISTINCT grp FROM ana.store_group_membership),
sp AS (SELECT m.grp, p.* FROM ana.store_group_membership m JOIN ana.store_points p USING (store_id))
SELECT u.seccio_censal, g.grp AS brand_group,
  count(p.store_id) FILTER (WHERE p.in_city AND ST_Intersects(u.geom, p.geom))                                   AS n_inside,
  -- by opening period (city stores): opened after the 2014 census (first seen 2016-2024) / already open in 2014 / no dating evidence
  count(p.store_id) FILTER (WHERE p.in_city AND ST_Intersects(u.geom, p.geom) AND p.first_seen_census_year >= 2016) AS n_inside_new_2016_2024,
  count(p.store_id) FILTER (WHERE p.in_city AND ST_Intersects(u.geom, p.geom) AND p.first_seen_census_year >= 2016 AND NOT coalesce(p.clarel_conversion, false)) AS n_inside_new_excl_clarel,
  count(p.store_id) FILTER (WHERE p.in_city AND ST_Intersects(u.geom, p.geom) AND p.first_seen_census_year = 2014) AS n_inside_legacy_2014,
  count(p.store_id) FILTER (WHERE p.in_city AND ST_Intersects(u.geom, p.geom) AND p.first_seen_census_year IS NULL) AS n_inside_undated,
  count(p.store_id) FILTER (WHERE p.in_city AND ST_DWithin(u.geom, p.geom, 250))                                 AS n_city_within_250m,
  count(p.store_id) FILTER (WHERE p.in_city AND ST_DWithin(u.geom, p.geom, 500))                                 AS n_city_within_500m,
  count(p.store_id) FILTER (WHERE p.in_city AND ST_DWithin(u.geom, p.geom, 1000))                                AS n_city_within_1000m,
  count(p.store_id) FILTER (WHERE p.in_city AND ST_DWithin(u.geom, p.geom, 2000))                                AS n_city_within_2000m,
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 250))                                               AS n_all_within_250m,
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 500))                                               AS n_all_within_500m,
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 1000))                                              AS n_all_within_1000m,
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 2000))                                              AS n_all_within_2000m,
  -- RING = within X m but outside the section (used for competition, so the store being explained is never counted in its own predictor)
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 500)  AND NOT ST_Intersects(u.geom, p.geom))        AS n_ring_500m,
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 2000) AND NOT ST_Intersects(u.geom, p.geom))        AS n_ring_2000m,
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 500)  AND NOT ST_Intersects(u.geom, p.geom) AND p.first_seen_census_year = 2014) AS n_ring_500m_legacy_2014,
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 2000) AND NOT ST_Intersects(u.geom, p.geom) AND p.first_seen_census_year = 2014) AS n_ring_2000m_legacy_2014
FROM units u CROSS JOIN groups g
LEFT JOIN sp p ON p.grp = g.grp AND ST_DWithin(u.geom, p.geom, 2000)
GROUP BY u.seccio_censal, g.grp;
ALTER TABLE ana.store_counts_section ADD PRIMARY KEY (seccio_censal, brand_group);
COMMENT ON TABLE ana.store_counts_section IS 'Stores per census section and group (chain, format group, ALL): inside the section (also split by opening period), ring counts outside the section (competition), and within 250/500/1000/2000 m of its boundary (n_city_* = city stores only; n_all_* = also stores outside the city). Built by sql/ana_store_counts.sql';

DROP TABLE IF EXISTS ana.store_counts_barri CASCADE;
CREATE TABLE ana.store_counts_barri AS
WITH units AS (SELECT codi_barri, geom FROM raw.adm_units_polygons WHERE tipus_ua = 'BARRI'),
groups AS (SELECT DISTINCT grp FROM ana.store_group_membership),
sp AS (SELECT m.grp, p.* FROM ana.store_group_membership m JOIN ana.store_points p USING (store_id))
SELECT u.codi_barri, g.grp AS brand_group,
  count(p.store_id) FILTER (WHERE p.in_city AND ST_Intersects(u.geom, p.geom))      AS n_inside,
  count(p.store_id) FILTER (WHERE p.in_city AND ST_Intersects(u.geom, p.geom) AND p.first_seen_census_year >= 2016) AS n_inside_new_2016_2024,
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 1000) AND NOT ST_Intersects(u.geom, p.geom)) AS n_ring_1000m,
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 1000) AND NOT ST_Intersects(u.geom, p.geom) AND p.first_seen_census_year = 2014) AS n_ring_1000m_legacy_2014,
  count(p.store_id) FILTER (WHERE p.in_city AND ST_DWithin(u.geom, p.geom, 500))    AS n_city_within_500m,
  count(p.store_id) FILTER (WHERE p.in_city AND ST_DWithin(u.geom, p.geom, 1000))   AS n_city_within_1000m,
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 500))                  AS n_all_within_500m,
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 1000))                 AS n_all_within_1000m
FROM units u CROSS JOIN groups g
LEFT JOIN sp p ON p.grp = g.grp AND ST_DWithin(u.geom, p.geom, 1000)
GROUP BY u.codi_barri, g.grp;
ALTER TABLE ana.store_counts_barri ADD PRIMARY KEY (codi_barri, brand_group);
COMMENT ON TABLE ana.store_counts_barri IS 'Stores per barri and brand group (inside; within 500/1000 m, city-only and all). Built by sql/ana_store_counts.sql';
