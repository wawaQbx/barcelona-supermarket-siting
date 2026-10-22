-- VISUALISATION LAYER (dashboard page 03 "Change 2014-2024"): chain premises in each edition of the municipal commercial census (city only),
-- recognised by the sign name (macro brand_patterns, same rule as the store dating). One row per chain x census year (2014, 2016, 2019, 2022, 2024).
-- Active food-retail premises only (see the filter below). Alcampo includes its predecessor signs Simply / Sabeco.
-- ONE STORE = ONE POINT: premises of the same chain within 50 m of each other in the same edition (a store recorded twice, store + car park /
-- stock room) are merged into one store (ST_ClusterDBSCAN, eps 50 m).
-- These counts come from the census field survey, not from the store list: the 2024 numbers differ slightly from gis.stores (stores opened after
-- the 2024 fieldwork, franchisees under their own sign, signs the regular expression misses).
{{ config(post_hook=primary_key('brand_group, census_year')) }}
WITH rx AS (SELECT * FROM {{ brand_patterns() }}),
raw_p AS (
    SELECT c.census_year, rx.brand_group, c.geom
    FROM {{ ref('int_census_premises') }} c JOIN rx ON c.nom_local ~* rx.pattern
    WHERE (c.nom_principal_activitat = 'Actiu' OR c.census_year = 2014)
      -- FOOD RETAIL ONLY (checked 2026-10-18): the sign name alone also matches travel agencies (Carrefour Viatges), car parks, stock rooms,
      -- offices, a music school (Esclat), a gym (Simply Gym) and food co-operatives ("cooperativa de consum"). The supermarket class differs by edition:
      AND (   (c.census_year = 2014 AND c.nom_activitat = 'ALIMENTACIÓ')
           OR (c.census_year = 2016 AND c.nom_activitat = 'Resta alimentació')        -- 2016 has no supermarket class
           OR (c.census_year >= 2019 AND c.nom_activitat = 'Autoservei / Supermercat')
           OR c.nom_activitat ILIKE 'Grans magatzems i hipermercats')
      AND c.nom_local !~* 'cooperativa'),
clustered AS (
    SELECT census_year, brand_group, ST_ClusterDBSCAN(geom, 50, 1) OVER (PARTITION BY census_year, brand_group) AS cluster_id FROM raw_p),
p AS (SELECT DISTINCT census_year, brand_group, cluster_id FROM clustered),
grid AS (SELECT b.brand_group, y.census_year FROM (SELECT DISTINCT brand_group FROM rx) b CROSS JOIN (SELECT DISTINCT census_year FROM {{ ref('int_census_premises') }}) y)
SELECT g.brand_group, k.chain_label, k.colour_hex AS chain_colour_hex, k.sort_order AS chain_sort_order, g.census_year,
       make_date(g.census_year, 1, 1) AS census_date,      -- a date axis for line / ribbon charts
       count(p.cluster_id)::integer AS stores_n   -- census premises merged within 50 m
FROM grid g
LEFT JOIN p USING (brand_group, census_year)
LEFT JOIN {{ ref('chain_colours') }} k USING (brand_group)
GROUP BY g.brand_group, k.chain_label, k.colour_hex, k.sort_order, g.census_year
