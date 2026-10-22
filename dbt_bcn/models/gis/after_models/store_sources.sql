-- VISUALISATION LAYER (dashboard page 05): one row per chain - city stores, where the list comes from, its reference date, and the share of stores
-- confirmed by the 2024 commercial census (a premise with the chain's name within 60 m: ana.store_list_validation, evidence = brand_in_2024).
{{ config(post_hook=primary_key('brand_group')) }}
SELECT c.brand_group, k.chain_label, k.sort_order AS chain_sort_order,
       count(*)::int AS stores_n,
       count(*) FILTER (WHERE s.list_source IN ('Official', 'OSM + official'))::int AS from_official_n,   -- on the chain's official locator (OSM lists of Mercadona / Aldi checked store by store)
       count(*) FILTER (WHERE s.list_source = 'OSM + census' AND c.point_source <> 'census_2024_supplement')::int AS from_osm_n,   -- OpenStreetMap only (no usable official list)
       count(*) FILTER (WHERE c.point_source = 'census_2024_supplement')::int AS added_from_census_2024_n,   -- not in the store list, recorded by the census
       count(*) FILTER (WHERE c.point_source = 'official_locator')::int AS added_from_locator_n,             -- not in the store list, on the official locator
       s.list_source, s.reference_date,
       round((100.0 * count(*) FILTER (WHERE v.evidence = 'brand_in_2024') / count(*))::numeric, 1) AS confirmed_by_census_2024_pct,
       count(*) FILTER (WHERE s.list_source = 'OSM + census' AND v.evidence <> 'brand_in_2024')::int AS unconfirmed_n,   -- on no official locator and not in the 2024 census (chains without a usable official list)
       max(cp.stores_n) AS census_2024_premises_n   -- chain premises in the 2024 commercial census (gis.chain_census_premises)
FROM {{ ref('store_points') }} c
JOIN {{ ref('store_list_validation') }} v USING (store_id)
JOIN {{ ref('chain_colours') }} k ON k.brand_group = c.brand_group
JOIN {{ ref('chain_list_sources') }} s ON s.brand_group = c.brand_group
LEFT JOIN {{ ref('chain_census_premises') }} cp ON cp.brand_group = c.brand_group AND cp.census_year = 2024
WHERE c.in_city
GROUP BY c.brand_group, k.chain_label, k.sort_order, s.list_source, s.reference_date
