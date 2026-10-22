-- Substitution: which shops change around a new supermarket. Active premises by TYPE (int_active_premises_typed) within 150 m
-- (own premise = anything within 20 m excluded) of every dated city store, every census edition.
WITH s AS (SELECT p.store_id, p.brand_group, p.first_seen_census_year, coalesce(o.opening_type, 'legacy_2014') AS opening_type, p.geom
           FROM {{ ref('store_points') }} p LEFT JOIN {{ ref('store_openings') }} o USING (store_id) WHERE p.in_city AND p.first_seen_census_year IS NOT NULL)
SELECT s.store_id, s.brand_group, s.first_seen_census_year, s.opening_type, t.census_year, t.ptype, count(t.*) AS premises_150m_n
FROM s JOIN {{ ref('int_active_premises_typed') }} t ON ST_DWithin(t.g, s.geom, 150) AND NOT ST_DWithin(t.g, s.geom, 20)
GROUP BY 1, 2, 3, 4, 5, 6
