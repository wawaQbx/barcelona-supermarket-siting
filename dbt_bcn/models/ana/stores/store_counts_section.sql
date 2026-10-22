-- Store counts per census section and group (chain, format group, ALL), two definitions for the edge effect:
--   n_inside        : stores whose point lies inside the section (also split by opening period)
--   n_city_within_X : stores inside the CITY within X m of the section polygon (inside the section counts, distance 0)
--   n_all_within_X  : same, but stores outside the city (ring stores, OSM Dia) also count
--   n_ring_X        : within X m but OUTSIDE the section (competition: the store being explained is never counted in its own predictor)
-- X = 250, 500, 1000, 2000 m (2000 m for hypermarkets).
{{ config(post_hook=primary_key('seccio_censal, brand_group')) }}
WITH units AS (SELECT seccio_censal, geom FROM {{ source('raw', 'adm_units_polygons') }} WHERE tipus_ua = 'SEC_CENS'),
groups AS (SELECT DISTINCT grp FROM {{ ref('store_group_membership') }}),
sp AS (SELECT m.grp, p.* FROM {{ ref('store_group_membership') }} m JOIN {{ ref('store_points') }} p USING (store_id))
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
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 500)  AND NOT ST_Intersects(u.geom, p.geom))        AS n_ring_500m,
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 2000) AND NOT ST_Intersects(u.geom, p.geom))        AS n_ring_2000m,
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 500)  AND NOT ST_Intersects(u.geom, p.geom) AND p.first_seen_census_year = 2014) AS n_ring_500m_legacy_2014,
  count(p.store_id) FILTER (WHERE ST_DWithin(u.geom, p.geom, 2000) AND NOT ST_Intersects(u.geom, p.geom) AND p.first_seen_census_year = 2014) AS n_ring_2000m_legacy_2014
FROM units u CROSS JOIN groups g
LEFT JOIN sp p ON p.grp = g.grp AND ST_DWithin(u.geom, p.geom, 2000)
GROUP BY u.seccio_censal, g.grp
