-- counts of store openings 2016-2024 per census section and group (chain, format, ALL), by opening type
{{ config(post_hook=primary_key('seccio_censal, brand_group')) }}
WITH units AS (SELECT seccio_censal, geom FROM {{ source('raw', 'adm_units_polygons') }} WHERE tipus_ua = 'SEC_CENS'),
o AS (SELECT m.grp, s.* FROM {{ ref('store_openings') }} s JOIN {{ ref('store_group_membership') }} m USING (store_id))
SELECT u.seccio_censal, g.grp AS brand_group,
       count(o.store_id)                                                     AS n_openings_2016_2024,
       count(o.store_id) FILTER (WHERE o.opening_type = 'new_site')          AS n_openings_new_site,
       count(o.store_id) FILTER (WHERE o.opening_type = 'takeover_of_food_premise') AS n_openings_takeover,
       count(o.store_id) FILTER (WHERE o.opening_type = 'clarel_conversion') AS n_openings_clarel
FROM units u CROSS JOIN (SELECT DISTINCT grp FROM {{ ref('store_group_membership') }}) g
LEFT JOIN o ON o.grp = g.grp AND ST_Intersects(u.geom, o.geom)
GROUP BY 1, 2
