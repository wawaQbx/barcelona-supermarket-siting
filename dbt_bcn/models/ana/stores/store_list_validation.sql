-- Is every city store in the store list a real supermarket at that place? (checked against the commercial censuses)
-- evidence, strongest first:
--   brand_in_2024      a premise with the chain's name within 60 m in the 2024 census
--   brand_earlier_only the chain's name within 60 m only in 2014-2022 (closed, renamed or moved since; or opened after the 2024 fieldwork)
--   other_supermarket  no chain name, but a supermarket-class premise (Autoservei / Supermercat) within 30 m in 2024 (franchisee under its own sign)
--   no_evidence        none of the above: suspicious entry (wrong coordinates, other store type, opened after 2024, or not a supermarket)
-- nearest_2024_* = the closest premise of the 2024 census, to judge the no_evidence cases.
-- Address-based checks and coordinate corrections: check_store_addresses.py. Clarel drugstores are already excluded (store_points_excluded).
{{ config(post_hook=primary_key('store_id')) }}
WITH rx AS (SELECT * FROM {{ brand_patterns() }}),   -- macros/brand_patterns.sql
s AS (SELECT p.store_id, p.ensenya, p.brand_group, p.store_type, p.point_source, p.coord_corrected, p.geom, r.pattern
      FROM {{ ref('store_points') }} p JOIN rx r USING (brand_group) WHERE p.in_city),
near AS (SELECT s.store_id, c.census_year AS y, c.nom_local, c.nom_activitat, ST_Distance(c.geom, s.geom) AS d, (c.nom_local ~* s.pattern) AS is_brand
         FROM s JOIN {{ ref('int_census_premises') }} c ON ST_DWithin(c.geom, s.geom, 60)),
ev AS (       -- one pass over the census matches (faster than three correlated subqueries per store)
    SELECT store_id,
           min(d) FILTER (WHERE y = 2024 AND is_brand)                                                    AS dist_brand_2024,
           string_agg(DISTINCT y::text, ',' ORDER BY y::text) FILTER (WHERE is_brand)                     AS brand_seen_in_census,
           min(d) FILTER (WHERE y = 2024 AND nom_activitat = 'Autoservei / Supermercat' AND d <= 30)      AS dist_any_supermarket_2024
    FROM near GROUP BY store_id),
v AS (
    SELECT s.store_id, s.ensenya, s.brand_group, s.store_type, s.point_source, s.coord_corrected,
           ev.dist_brand_2024::numeric(6, 1) AS dist_brand_2024_m, ev.brand_seen_in_census, ev.dist_any_supermarket_2024::numeric(6, 1) AS dist_any_supermarket_2024_m,
           nn.nom_local AS nearest_2024_name, nn.nom_activitat AS nearest_2024_activity, nn.d::numeric(6, 1) AS nearest_2024_m
    FROM s
    LEFT JOIN ev USING (store_id)
    LEFT JOIN LATERAL (SELECT c.nom_local, c.nom_activitat, ST_Distance(c.geom, s.geom) AS d FROM {{ ref('int_census_premises') }} c
                       WHERE c.census_year = 2024 ORDER BY c.geom <-> s.geom, c.nom_local, c.nom_activitat LIMIT 1) nn ON true)   -- ties (several premises at one point): alphabetical
SELECT v.*,
       CASE WHEN dist_brand_2024_m IS NOT NULL THEN 'brand_in_2024'
            WHEN brand_seen_in_census IS NOT NULL THEN 'brand_earlier_only'
            WHEN dist_any_supermarket_2024_m IS NOT NULL THEN 'other_supermarket'
            ELSE 'no_evidence' END AS evidence
FROM v
