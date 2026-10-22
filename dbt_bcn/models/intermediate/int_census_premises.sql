-- All ground-floor premises of the five commercial census editions as EPSG:25831 points, one row per premise and edition.
-- 2014 coordinates are ED50 (EPSG:23031); 2014 has no nom_principal_activitat (active = sector <> 'LOCAL BUIT'); id_global exists only 2022 / 2024.
-- Shared by the store-list validation, the Clarel exclusion, openings, closures and the event-study panels (formerly repeated in 5 SQL files).
-- geom typed as geometry(Point, 25831) so QGIS / PostGIS know the geometry type and CRS of every derived table
{{ config(indexes=[{'columns': ['geom'], 'type': 'gist'}, {'columns': ['census_year']}], post_hook=analyze_this()) }}
SELECT census_year, id_global, nom_local, nom_activitat, nom_grup_activitat, nom_sector_activitat, nom_principal_activitat, geom::geometry(Point, 25831) AS geom
FROM (
SELECT 2014 AS census_year, NULL::text AS id_global, nom_local, nom_activitat, nom_grup_activitat, nom_sector_activitat, NULL::text AS nom_principal_activitat,
       ST_Transform(ST_SetSRID(ST_MakePoint(x_ed50, y_ed50), 23031), 25831) AS geom
FROM {{ source('raw', 'cen_census_2014') }} WHERE x_ed50 IS NOT NULL
UNION ALL
SELECT 2016, NULL, nom_local, nom_activitat, nom_grup_activitat, nom_sector_activitat, nom_principal_activitat, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831)
FROM {{ source('raw', 'cen_census_2016') }} WHERE lon IS NOT NULL
UNION ALL
SELECT 2019, NULL, nom_local, nom_activitat, nom_grup_activitat, nom_sector_activitat, nom_principal_activitat, geom
FROM {{ source('raw', 'cen_census_2019') }}
UNION ALL
SELECT 2022, id_global, nom_local, nom_activitat, nom_grup_activitat, nom_sector_activitat, nom_principal_activitat, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831)
FROM {{ source('raw', 'cen_census_2022') }} WHERE lon IS NOT NULL
UNION ALL
SELECT 2024, id_global, nom_local, nom_activitat, nom_grup_activitat, nom_sector_activitat, nom_principal_activitat, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831)
FROM {{ source('raw', 'cen_census_2024') }} WHERE lon IS NOT NULL
) u
