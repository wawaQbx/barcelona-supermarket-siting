-- Store points BEFORE the census checks (step 1 of ana.store_points):
--   (a) the official store list minus hand-documented removals (store_removals_manual.csv), coordinates corrected to the census premise where check_store_addresses.py found the chain at the address;
--   (b) Dia outside the city: the Dia site returns 403, so OSM Dia shops outside the city within 2 km that are not within 150 m of a listed Dia
--       (2026-10: 24 OSM Dia in that ring, 20 already listed, 4 added; OSM covers 39% of city Dia, 86% match an official store, 14% are closed);
--   (c) RING stores (edge effect): stores outside the city within 2 km (fetch_ring_stores.py + fetch_ring_osm.py), kept only when no listed store
--       of the same chain is within 100 m, and only one of several ring copies of one store (official + OSM).
-- store_id: numbered in a fixed order (chain, address, position), so it is the same after every rebuild.
-- in_city = assigned to a barri in the source, or on a section polygon (a few points sit on the boundary line / a few metres off).
{{ config(indexes=[{'columns': ['geom'], 'type': 'gist'}], post_hook=analyze_this()) }}
WITH sections AS (SELECT geom FROM {{ source('raw', 'adm_units_polygons') }} WHERE tipus_ua = 'SEC_CENS'),
official AS (
    SELECT (row_number() OVER (ORDER BY s.ensenya, s.adreca, s.lat, s.lon))::text AS store_id, 'official_list'::text AS point_source, (s.codi_barri IS NOT NULL) AS has_barri, s.ensenya, s.store_type,
           CASE WHEN s.ensenya IN ('Consum','Charter') THEN 'Consum_Charter'
                WHEN s.ensenya IN ('Bon Preu','Esclat') THEN 'BonPreu_Esclat'
                WHEN s.ensenya IN ('Alcampo','Mi Alcampo') THEN 'Alcampo'
                WHEN s.ensenya LIKE 'Carrefour%' THEN 'Carrefour'
                ELSE s.ensenya END AS brand_group,
           ST_Transform(ST_SetSRID(ST_MakePoint(coalesce(k.census_lon, s.lon), coalesce(k.census_lat, s.lat)), 4326), 25831) AS geom,
           (k.census_lon IS NOT NULL) AS coord_corrected, k.coord_offset_m AS coord_correction_m
    FROM {{ source('raw', 'store_supermarkets_official') }} s
    LEFT JOIN {{ source('raw', 'store_coordinate_corrections') }} k
           ON k.ensenya = s.ensenya AND k.adreca = s.adreca AND abs(k.lat - s.lat) < 1e-7 AND abs(k.lon - s.lon) < 1e-7
    WHERE s.lon IS NOT NULL AND s.lat IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM {{ source('raw', 'store_removals_manual') }} m   -- closed / listed twice / wrong coordinates (evidence in the file)
                      WHERE m.ensenya = s.ensenya
                        AND (m.adreca = s.adreca OR (m.lat IS NOT NULL AND abs(m.lat - s.lat) < 5e-5 AND abs(m.lon - s.lon) < 5e-5)))),
osm_dia AS (
    SELECT 'osm_' || o.osm_id AS store_id, 'osm_supplement'::text AS point_source, false AS has_barri, 'Dia'::text AS ensenya, 'supermarket'::text AS store_type,
           'Dia'::text AS brand_group, o.geom, NULL::boolean AS coord_corrected, NULL::double precision AS coord_correction_m
    FROM {{ source('raw', 'hist_osm_shops') }} o
    WHERE (o.ensenya ILIKE 'dia%' OR o.nom ILIKE 'dia %' OR o.nom ILIKE '%supermercados dia%')
      AND NOT EXISTS (SELECT 1 FROM sections u WHERE ST_Intersects(u.geom, o.geom))
      AND EXISTS (SELECT 1 FROM sections u WHERE ST_DWithin(u.geom, o.geom, 2000))
      AND NOT EXISTS (SELECT 1 FROM official p WHERE p.brand_group = 'Dia' AND ST_DWithin(p.geom, o.geom, 150))),
listed AS (SELECT * FROM official UNION ALL SELECT * FROM osm_dia),
ring_all AS (
    SELECT 'ring_' || row_number() OVER (ORDER BY r.ensenya, r.lat, r.lon) AS store_id, 'ring_' || CASE WHEN r.source ILIKE '%osm%' THEN 'osm' ELSE 'official' END AS point_source, false AS has_barri,
           r.ensenya, coalesce(r.store_type, 'supermarket') AS store_type,
           CASE WHEN r.ensenya IN ('Consum','Charter') THEN 'Consum_Charter' WHEN r.ensenya IN ('Bon Preu','Esclat') THEN 'BonPreu_Esclat'
                WHEN r.ensenya IN ('Alcampo','Mi Alcampo') THEN 'Alcampo' WHEN r.ensenya LIKE 'Carrefour%' THEN 'Carrefour' ELSE r.ensenya END AS brand_group,
           ST_Transform(ST_SetSRID(ST_MakePoint(r.lon, r.lat), 4326), 25831) AS geom, NULL::boolean AS coord_corrected, NULL::double precision AS coord_correction_m
    FROM (SELECT DISTINCT ON (ensenya, round(lat::numeric, 4), round(lon::numeric, 4)) * FROM {{ source('raw', 'store_ring_stores_2km') }} WHERE lat IS NOT NULL
          ORDER BY ensenya, round(lat::numeric, 4), round(lon::numeric, 4), source, lat, lon) r
    WHERE NOT EXISTS (SELECT 1 FROM sections u WHERE ST_DWithin(u.geom, ST_Transform(ST_SetSRID(ST_MakePoint(r.lon, r.lat), 4326), 25831), 1))
      AND EXISTS (SELECT 1 FROM sections u WHERE ST_DWithin(u.geom, ST_Transform(ST_SetSRID(ST_MakePoint(r.lon, r.lat), 4326), 25831), 2000))),
ring_new AS (   -- not a store that is already listed
    SELECT a.* FROM ring_all a
    WHERE NOT EXISTS (SELECT 1 FROM listed b WHERE a.brand_group = b.brand_group AND ST_DWithin(a.geom, b.geom, 100))),
ring AS (       -- one ring copy per store: drop a copy when another copy with a smaller store_id (text order) is within 100 m
    SELECT a.* FROM ring_new a
    WHERE NOT EXISTS (SELECT 1 FROM ring_new b WHERE a.brand_group = b.brand_group AND a.store_id > b.store_id AND ST_DWithin(a.geom, b.geom, 100))),
pts AS (SELECT * FROM listed UNION ALL SELECT * FROM ring)
SELECT p.store_id, p.point_source, p.has_barri, p.ensenya, p.store_type, p.brand_group, p.geom::geometry(Point, 25831) AS geom,   -- typed for QGIS
       p.coord_corrected, p.coord_correction_m,
       (p.has_barri OR EXISTS (SELECT 1 FROM sections u WHERE ST_DWithin(u.geom, p.geom, 1))) AS in_city
FROM pts p
