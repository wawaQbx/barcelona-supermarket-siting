-- Store counts per barri and group (same definitions as store_counts_section; ring = within 1000 m outside the barri)
{{ config(post_hook=primary_key('codi_barri, brand_group')) }}
WITH units AS (SELECT codi_barri, geom FROM {{ source('raw', 'adm_units_polygons') }} WHERE tipus_ua = 'BARRI'),
groups AS (SELECT DISTINCT grp FROM {{ ref('store_group_membership') }}),
sp AS (SELECT m.grp, p.* FROM {{ ref('store_group_membership') }} m JOIN {{ ref('store_points') }} p USING (store_id))
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
GROUP BY u.codi_barri, g.grp
