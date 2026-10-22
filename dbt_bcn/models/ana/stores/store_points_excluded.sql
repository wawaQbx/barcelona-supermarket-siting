-- DATA CORRECTION (2026-10-13): 57 'Dia Market' entries of the Dia store locator are Clarel drugstores (Dia group brand until 2023), not supermarkets:
-- no Dia-named premise within 60 m in any census edition, but a Clarel premise within 60 m in 2024 (56 of 57); the nearest 2024 premise is a drugstore, bar,
-- dry-cleaner ... and only once a supermarket. They are listed here and left out of ana.store_points, every count and every model.
WITH dia AS (SELECT geom AS g FROM {{ ref('int_census_premises') }} WHERE nom_local ~* '^(dia\M|dia %|dia market|supermercados dia|la plaza de dia)'),
clarel24 AS (SELECT geom AS g FROM {{ ref('int_census_premises') }} WHERE census_year = 2024 AND nom_local ~* 'clarel')
SELECT p.*, 'likely Clarel drugstore listed in the Dia locator'::text AS exclusion_reason
FROM {{ ref('int_store_points_base') }} p
WHERE p.brand_group = 'Dia' AND p.point_source = 'official_list'
  AND NOT EXISTS (SELECT 1 FROM dia WHERE ST_DWithin(dia.g, p.geom, 60))
  AND EXISTS (SELECT 1 FROM clarel24 c WHERE ST_DWithin(c.g, p.geom, 60))
