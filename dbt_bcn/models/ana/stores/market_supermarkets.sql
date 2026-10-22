-- Municipal markets and supermarkets: one row per municipal market (raw.com_mercats_municipals_clean, 43 markets, 39 of them food markets).
--   food_market = false for the flower market, the Sunday book market and the two Encants flea / clothes markets.
--   chain stores at the market (within 50 m / 100 m of the market point = inside the market building or at its door), within 300 m, nearest chain store;
--   chain openings 2016-2024 within 300 m;
--   FRESH-FOOD SHOPS around the market: active premises of the four fresh activities that exist unchanged in every edition 2016-2024
--   (Carn i Porc, Fruites i verdures, Ous i aus, Peix i marisc), in a RING 100-400 m from the market point: the market's own stalls are census
--   premises too (the Boqueria alone has ~270), so everything within 100 m is left out. 2014 is not used (other activity coding);
--   bread is not used (bakery-cafe chains make it jump in 2024).
{{ config(post_hook=primary_key('nom_mercat')) }}
WITH m AS (SELECT nom_mercat, nom_barri, nom_districte,
                  nom_mercat !~* 'flors|dominical|encants' AS food_market,
                  ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831)::geometry(Point, 25831) AS geom
           FROM {{ source('raw', 'com_mercats_municipals_clean') }} WHERE lon IS NOT NULL),
p AS (SELECT * FROM {{ ref('store_points') }} WHERE in_city),
f AS NOT MATERIALIZED (
    SELECT census_year, geom AS g FROM {{ ref('int_census_premises') }}
    WHERE census_year >= 2016 AND nom_principal_activitat = 'Actiu'
      AND nom_activitat IN ('Carn i Porc', 'Fruites i verdures', 'Ous i aus', 'Peix i marisc'))
SELECT m.nom_mercat, m.nom_barri, m.nom_districte, m.food_market,
       u.seccio_censal, u.codi_barri,
       (SELECT count(*) FROM p WHERE ST_DWithin(p.geom, m.geom, 50))                                   AS chain_stores_50m_n,
       (SELECT string_agg(p.ensenya, ', ' ORDER BY p.ensenya) FROM p WHERE ST_DWithin(p.geom, m.geom, 50)) AS chain_stores_50m,
       (SELECT count(*) FROM p WHERE ST_DWithin(p.geom, m.geom, 100))                                  AS chain_stores_100m_n,
       (SELECT count(*) FROM p WHERE ST_DWithin(p.geom, m.geom, 300))                                  AS chain_stores_300m_n,
       (SELECT round(min(ST_Distance(p.geom, m.geom))::numeric, 0) FROM p WHERE ST_DWithin(p.geom, m.geom, 2000)) AS nearest_chain_store_m,
       (SELECT count(*) FROM p WHERE p.first_seen_census_year >= 2016 AND NOT coalesce(p.clarel_conversion, false) AND ST_DWithin(p.geom, m.geom, 300)) AS chain_openings_2016_2024_300m_n,
       (SELECT count(*) FROM f WHERE f.census_year = 2016 AND ST_DWithin(f.g, m.geom, 400) AND NOT ST_DWithin(f.g, m.geom, 100)) AS fresh_shops_ring_100_400m_2016_n,
       (SELECT count(*) FROM f WHERE f.census_year = 2019 AND ST_DWithin(f.g, m.geom, 400) AND NOT ST_DWithin(f.g, m.geom, 100)) AS fresh_shops_ring_100_400m_2019_n,
       (SELECT count(*) FROM f WHERE f.census_year = 2022 AND ST_DWithin(f.g, m.geom, 400) AND NOT ST_DWithin(f.g, m.geom, 100)) AS fresh_shops_ring_100_400m_2022_n,
       (SELECT count(*) FROM f WHERE f.census_year = 2024 AND ST_DWithin(f.g, m.geom, 400) AND NOT ST_DWithin(f.g, m.geom, 100)) AS fresh_shops_ring_100_400m_2024_n,
       m.geom
FROM m
LEFT JOIN LATERAL (SELECT seccio_censal, codi_barri FROM {{ source('raw', 'adm_units_polygons') }} a
                   WHERE a.tipus_ua = 'SEC_CENS' AND ST_DWithin(a.geom, m.geom, 1) LIMIT 1) u ON true
