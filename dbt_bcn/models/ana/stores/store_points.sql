-- All stores used by the analyses as EPSG:25831 points (one row per store):
--   int_store_points_base (official list + OSM Dia outside the city + ring stores)  minus  store_points_excluded (Clarel drugstores)
--   plus COMPLETION (2026-10-13): chain supermarkets recorded by the 2024 commercial census (municipal field survey) but missing from the store list
--   (no store of the same chain within 150 m), point_source = 'census_2024_supplement' - since the 2026-10-16 audit only for Caprabo, Lidl and Carrefour (see below).
-- LOCATOR AUDIT (2026-10-16): OSM lagged behind openings and closures, so for the two OSM-sourced chains that publish their store list
--   (fetch_official_locators.py: Mercadona, Aldi) a listed or census-supplement store with no locator store of the chain within 150 m is dropped
--   (closed: e.g. the Mercadona of the Mercat del Poblenou, March 2024), and a locator store with no listed store within 150 m is added
--   (point_source = 'official_locator', city + 2 km ring). Hand-documented removals (store_removals_manual) are applied in int_store_points_base.
-- format_group: the user's store_type in the official list (Alcampo hypermarkets vs Mi Alcampo; Carrefour convenience vs supermarket).
-- Opening timeline (city stores only): first census edition in which the store appears (2014 = already open in 2014), Clarel -> Dia conversions.
--   1st source: census_panel.py (ana.py_stores_opening_era_city, matched on the ORIGINAL list coordinates within 1 m);
--   2nd source, for stores it does not date (the census-2024 supplement, and stores whose coordinates were corrected by address, which no longer match
--   within 1 m): the earliest census edition with a premise of the same chain name within 60 m (same rule as store_list_validation; the two sources agree
--   for 500 of the 508 stores dated by both). first_seen_source says which one was used.
{{ config(indexes=[{'columns': ['geom'], 'type': 'gist'}], post_hook=primary_key('store_id')) }}
WITH kept AS (
    SELECT b.* FROM {{ ref('int_store_points_base') }} b
    WHERE NOT EXISTS (SELECT 1 FROM {{ ref('store_points_excluded') }} x WHERE x.store_id = b.store_id)),
census AS (
    SELECT x.id_global, x.nom_local, x.geom AS g,
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
    FROM {{ ref('int_census_premises') }} x
    WHERE x.census_year = 2024 AND x.nom_activitat = 'Autoservei / Supermercat' AND x.nom_principal_activitat = 'Actiu'),
supplement AS (
    SELECT 'cen24_' || c.id_global AS store_id, 'census_2024_supplement'::text AS point_source, true AS has_barri, c.ensenya,
           CASE WHEN c.nom_local ~* 'express|city|go\M' THEN 'convenience' ELSE 'supermarket' END AS store_type, c.brand_group, c.g AS geom,
           NULL::boolean AS coord_corrected, NULL::double precision AS coord_correction_m,
           true AS in_city                                             -- the census covers only the city
    FROM census c
    WHERE c.brand_group IN ('Caprabo', 'Lidl', 'Carrefour')   -- AUDIT 2026-10-16: only chains whose list is OSM without an official locator. For chains with an
          -- official current list (Condis, Consum / Charter, Bon Preu / Esclat, Dia, Alcampo, Mercadona, Aldi) a census-only premise was either the SAME store
          -- (locator coordinates 150-250 m off, e.g. Condis Carreras i Candi 101, Gran Via 940 / 1176) or a store closed since the 2024 fieldwork
          -- (e.g. Condis Alt de Pedrell, Cantabria 73, Poesia 9): one store counted twice, or a closed store counted. The official list wins.
      AND NOT EXISTS (SELECT 1 FROM kept p WHERE p.brand_group = c.brand_group AND ST_DWithin(p.geom, c.g, 150))
      AND NOT EXISTS (SELECT 1 FROM {{ source('raw', 'store_removals_manual') }} m   -- a documented closure is not brought back by the 2024 census
                      WHERE m.reason_type = 'closed' AND m.lat IS NOT NULL AND c.brand_group = CASE WHEN m.ensenya LIKE 'Carrefour%' THEN 'Carrefour' ELSE m.ensenya END
                        AND ST_DWithin(ST_Transform(ST_SetSRID(ST_MakePoint(m.lon, m.lat), 4326), 25831), c.g, 50))),
sections AS (SELECT geom FROM {{ source('raw', 'adm_units_polygons') }} WHERE tipus_ua = 'SEC_CENS'),
locator AS (
    SELECT l.ensenya, l.store_code, ST_Transform(ST_SetSRID(ST_MakePoint(l.lon, l.lat), 4326), 25831) AS g FROM {{ source('raw', 'store_official_locators') }} l),
listed AS (   -- listed + census supplement, minus closed stores
    SELECT a.* FROM (SELECT * FROM kept UNION ALL SELECT * FROM supplement) a
    WHERE NOT (a.brand_group IN (SELECT DISTINCT ensenya FROM locator)
               AND NOT EXISTS (SELECT 1 FROM locator l WHERE l.ensenya = a.brand_group AND ST_DWithin(l.g, a.geom, 150)))
),
added AS (    -- locator stores missing from the list (city + 2 km ring)
    SELECT 'loc_' || lower(l.ensenya) || '_' || l.store_code AS store_id, 'official_locator'::text AS point_source, false AS has_barri, l.ensenya,
           'supermarket'::text AS store_type, l.ensenya AS brand_group, l.g::geometry(Point, 25831) AS geom, NULL::boolean AS coord_corrected, NULL::double precision AS coord_correction_m,
           EXISTS (SELECT 1 FROM sections u WHERE ST_DWithin(u.geom, l.g, 1)) AS in_city
    FROM locator l
    WHERE EXISTS (SELECT 1 FROM sections u WHERE ST_DWithin(u.geom, l.g, 2000))
      AND NOT EXISTS (SELECT 1 FROM listed p WHERE p.brand_group = l.ensenya AND ST_DWithin(p.geom, l.g, 150))),
pts AS (SELECT * FROM listed UNION ALL SELECT * FROM added),
rx AS (SELECT * FROM {{ brand_patterns() }}),
seen AS (   -- earliest census edition with a premise of the chain's name within 60 m
    SELECT p.store_id, min(c.census_year) AS first_year
    FROM pts p JOIN rx USING (brand_group) JOIN {{ ref('int_census_premises') }} c ON ST_DWithin(c.geom, p.geom, 60) AND c.nom_local ~* rx.pattern
    WHERE p.in_city GROUP BY 1)
SELECT p.*,
       CASE WHEN p.brand_group = 'Alcampo'   AND p.store_type = 'hypermarket' THEN 'Alcampo_hypermarket'
            WHEN p.brand_group = 'Alcampo'                                    THEN 'Alcampo_MiAlcampo'
            WHEN p.brand_group = 'Carrefour' AND p.store_type = 'convenience' THEN 'Carrefour_convenience'
            WHEN p.brand_group = 'Carrefour'                                  THEN 'Carrefour_supermarket' END AS format_group,
       -- EARLIEST EVIDENCE (2026-10-19): census_panel.py matches the exact banner, so a renamed store (Dia Market -> Dia, Simply -> Mi Alcampo,
       -- Charter -> Consum, Esclat -> Bon Preu) looked like a new store; the chain-name rule (brand_patterns, includes the old banners) is taken
       -- whenever it finds the chain EARLIER at the site.
       LEAST(o.first_seen_census_year, s.first_year)::integer AS first_seen_census_year,
       CASE WHEN o.first_seen_census_year IS NOT NULL AND (s.first_year IS NULL OR o.first_seen_census_year <= s.first_year) THEN o.opening_era
            ELSE CASE s.first_year WHEN 2014 THEN '<=2014' WHEN 2016 THEN '2015-2016' WHEN 2019 THEN '2017-2019' WHEN 2022 THEN '2020-2022' WHEN 2024 THEN '2023-2024'
                                   ELSE CASE WHEN p.in_city THEN 'no census match' END END END::text AS opening_era,
       (o.first_banner = 'Clarel (legacy)') AS clarel_conversion,
       CASE WHEN o.first_seen_census_year IS NOT NULL AND (s.first_year IS NULL OR o.first_seen_census_year <= s.first_year) THEN 'census_panel'
            WHEN s.first_year IS NOT NULL THEN 'census_name_match' END AS first_seen_source
FROM pts p
LEFT JOIN LATERAL (SELECT e.first_seen_census_year, e.opening_era, e.first_banner FROM {{ source('ana', 'py_stores_opening_era_city') }} e
                   WHERE p.in_city AND e.ensenya = p.ensenya
                     AND ST_DWithin(p.geom, ST_Transform(ST_SetSRID(ST_MakePoint(e.lon, e.lat), 4326), 25831), 1)
                   LIMIT 1) o ON true
LEFT JOIN seen s USING (store_id)
