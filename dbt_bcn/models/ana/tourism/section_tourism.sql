-- Tourist accommodation per census section:
--   HUT 2026 = licensed tourist flats (raw.tou_hut_comunicacio_2026_1t, 2026 Q1; numero_places = beds)
--   HUT 2017 per city block (raw.tou_2017_huts_illa: hut_casos, hut_places; block assigned by a point on its surface) = baseline before most 2019-2024 openings
--   hotels (raw.tou_hotels, Open Data BCN equipment list, 446 hotels; no beds / stars in the open data)
--   Airbnb (raw.tou_airbnb_listings_2026_09, Inside Airbnb 2026-09-17): all listings, entire homes, reviews in the last 12 months (activity proxy)
-- Every point is assigned once to the section polygon that contains it; densities per 100 residents (Padro 2026).
{{ config(post_hook=primary_key('seccio_censal')) }}
WITH sec AS (SELECT seccio_censal, codi_barri, codi_districte, geom FROM {{ source('raw', 'adm_units_polygons') }} WHERE tipus_ua = 'SEC_CENS'),
pts AS (
    SELECT 'hut' AS src, 1::numeric AS flats, numero_places::numeric AS beds, NULL::text AS room_type, NULL::numeric AS reviews_ltm,
           ST_Transform(ST_SetSRID(ST_MakePoint(longitud_x, latitud_y), 4326), 25831) AS g
    FROM {{ source('raw', 'tou_hut_comunicacio_2026_1t') }} WHERE longitud_x IS NOT NULL
    UNION ALL
    SELECT 'hut2017', hut_casos, hut_places, NULL, NULL, ST_PointOnSurface(geom) FROM {{ source('raw', 'tou_2017_huts_illa') }}
    UNION ALL
    SELECT 'hotel', NULL, NULL, NULL, NULL, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) FROM {{ source('raw', 'tou_hotels') }} WHERE lon IS NOT NULL
    UNION ALL
    SELECT 'airbnb', NULL, NULL, room_type, number_of_reviews_ltm, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831)
    FROM {{ source('raw', 'tou_airbnb_listings_2026_09') }} WHERE lon IS NOT NULL),
agg AS (
    SELECT s.seccio_censal,
           count(*) FILTER (WHERE p.src = 'hut')                                   AS hut_flats_n,
           coalesce(sum(p.beds) FILTER (WHERE p.src = 'hut'), 0)                   AS hut_beds_n,
           coalesce(sum(p.flats) FILTER (WHERE p.src = 'hut2017'), 0)              AS hut_flats_2017_n,
           coalesce(sum(p.beds) FILTER (WHERE p.src = 'hut2017'), 0)               AS hut_beds_2017_n,
           count(*) FILTER (WHERE p.src = 'hotel')                                 AS hotels_n,
           count(*) FILTER (WHERE p.src = 'airbnb')                                AS airbnb_listings_n,
           count(*) FILTER (WHERE p.src = 'airbnb' AND p.room_type = 'Entire home/apt') AS airbnb_entire_homes_n,
           coalesce(sum(p.reviews_ltm) FILTER (WHERE p.src = 'airbnb'), 0)         AS airbnb_reviews_last_12m_n
    FROM sec s LEFT JOIN pts p ON ST_Intersects(s.geom, p.g)
    GROUP BY 1)
SELECT s.seccio_censal, s.codi_barri, s.codi_districte, pop.habitants_n AS population_n,
       a.hut_flats_n, a.hut_beds_n, a.hut_flats_2017_n, a.hut_beds_2017_n, a.hotels_n, a.airbnb_listings_n, a.airbnb_entire_homes_n, a.airbnb_reviews_last_12m_n,
       round(100.0 * a.hut_beds_n / nullif(pop.habitants_n, 0), 2)        AS hut_beds_per_100_residents,
       round(100.0 * a.hut_beds_2017_n / nullif(pop.habitants_n, 0), 2)   AS hut_beds_2017_per_100_residents,
       round(100.0 * a.airbnb_listings_n / nullif(pop.habitants_n, 0), 2) AS airbnb_listings_per_100_residents
FROM sec s JOIN agg a USING (seccio_censal)
LEFT JOIN {{ source('raw', 'pop_2026_pad_base') }} pop USING (seccio_censal)
