-- Traditional (fresh) food shops of the 2024 commercial census, active premises: bakeries, butchers, greengrocers, FISHMONGERS and POULTRY / EGG shops.
-- Replaces raw.com_layer2_alimentacio_tradicional, which left out fish (Peix i marisc, 437 shops) and poultry / eggs (Ous i aus, 260).
-- These five activities are coded identically in the 2016-2024 censuses (2016 has no supermarket class, see market_supermarkets).
{{ config(indexes=[{'columns': ['geom'], 'type': 'gist'}]) }}
SELECT x.id_global AS premise_id, x.nom_local, x.nom_activitat,
       CASE x.nom_activitat WHEN 'Pa, pastisseria i làctics' THEN 'bakery_dairy' WHEN 'Carn i Porc' THEN 'butcher' WHEN 'Fruites i verdures' THEN 'greengrocer'
                            WHEN 'Peix i marisc' THEN 'fishmonger' WHEN 'Ous i aus' THEN 'poultry_eggs' END AS fresh_category,
       u.seccio_censal, u.codi_barri, u.codi_districte, x.geom
FROM {{ ref('int_census_premises') }} x
LEFT JOIN LATERAL (SELECT seccio_censal, codi_barri, codi_districte FROM {{ source('raw', 'adm_units_polygons') }} a
                   WHERE a.tipus_ua = 'SEC_CENS' AND ST_DWithin(a.geom, x.geom, 1) LIMIT 1) u ON true
WHERE x.census_year = 2024 AND x.nom_principal_activitat = 'Actiu'
  AND x.nom_activitat IN ('Pa, pastisseria i làctics', 'Carn i Porc', 'Fruites i verdures', 'Peix i marisc', 'Ous i aus')
