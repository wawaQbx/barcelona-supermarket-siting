-- BEFORE / AFTER design (event study) around each city store.
-- For every dated city store and every census edition (2014, 2016, 2019, 2022, 2024): ACTIVE ground-floor premises within 150 m,
-- excluding the store's own premise (anything within 20 m).
-- Active = 2014: sector <> 'LOCAL BUIT'; 2016-2024: nom_principal_activitat = 'Actiu'. Vacancy is not used: its categories change between editions
-- (2016 / 2019 have 11-13k 'Sense informació' premises). Level differences between editions are absorbed by edition fixed effects in the model.
{{ config(indexes=[{'columns': ['store_id']}]) }}
WITH s AS (SELECT p.store_id, p.brand_group, p.first_seen_census_year, coalesce(o.opening_type, 'legacy_2014') AS opening_type, p.geom
      FROM {{ ref('store_points') }} p LEFT JOIN {{ ref('store_openings') }} o USING (store_id)
      WHERE p.in_city AND p.first_seen_census_year IS NOT NULL),
y AS (SELECT unnest(ARRAY[2014, 2016, 2019, 2022, 2024]) AS census_year)
SELECT s.store_id, s.brand_group, s.first_seen_census_year, s.opening_type, y.census_year,
       (SELECT count(*) FROM {{ ref('int_active_premises_typed') }} a
        WHERE a.census_year = y.census_year AND ST_DWithin(a.g, s.geom, 150) AND NOT ST_DWithin(a.g, s.geom, 20)) AS active_premises_150m_n
FROM s CROSS JOIN y
