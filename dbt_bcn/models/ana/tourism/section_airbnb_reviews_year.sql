-- Airbnb reviews per census section and year (2010-2026) = proxy of tourist activity over time.
-- Built from the review dates of the listings online on 2026-09-17 (Inside Airbnb): listings removed earlier are missing (survivorship bias),
-- so early years are under-counted; use it for differences BETWEEN sections, not for city totals over time.
{{ config(post_hook=primary_key('seccio_censal, review_year')) }}
WITH sec AS (SELECT seccio_censal, geom FROM {{ source('raw', 'adm_units_polygons') }} WHERE tipus_ua = 'SEC_CENS'),
lst AS (SELECT l.listing_id, s.seccio_censal
        FROM {{ source('raw', 'tou_airbnb_listings_2026_09') }} l
        JOIN sec s ON ST_Intersects(s.geom, ST_Transform(ST_SetSRID(ST_MakePoint(l.lon, l.lat), 4326), 25831))
        WHERE l.lon IS NOT NULL),
rev AS (SELECT lst.seccio_censal, r.any_ AS review_year, sum(r.reviews_n) AS reviews_n
        FROM {{ source('raw', 'tou_airbnb_reviews_per_year') }} r JOIN lst USING (listing_id) GROUP BY 1, 2)
SELECT s.seccio_censal, y.review_year::int AS review_year, coalesce(rev.reviews_n, 0) AS airbnb_reviews_n
FROM sec s CROSS JOIN generate_series(2010, 2026) AS y(review_year)
LEFT JOIN rev ON rev.seccio_censal = s.seccio_censal AND rev.review_year = y.review_year
