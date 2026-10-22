-- one row per store and group it belongs to (chain, format group, ALL), used to count stores per group
{{ config(indexes=[{'columns': ['grp']}]) }}
SELECT store_id, brand_group AS grp FROM {{ ref('store_points') }} UNION ALL
SELECT store_id, format_group FROM {{ ref('store_points') }} WHERE format_group IS NOT NULL UNION ALL
SELECT store_id, 'ALL' FROM {{ ref('store_points') }}
