-- Supermarket closures: supermarket-class premises of the 2019 and 2022 censuses (chain from the sign name);
-- closed = no supermarket-class premise within 20 m in the next census edition.
{{ config(post_hook=primary_key('premise_id')) }}
WITH sup AS (
    SELECT census_year, CASE census_year WHEN 2019 THEN 2022 ELSE 2024 END AS next_year, nom_local, geom AS g
    FROM {{ ref('int_census_premises') }}
    WHERE census_year IN (2019, 2022) AND nom_activitat = 'Autoservei / Supermercat' AND nom_principal_activitat = 'Actiu'),
nxt AS (SELECT census_year, g FROM {{ ref('int_active_premises_typed') }} WHERE ptype = 'supermarket_class')
-- premise_id: deterministic numbering (edition, then position, then name)
SELECT (row_number() OVER (ORDER BY s.census_year, ST_X(s.g), ST_Y(s.g), s.nom_local))::text AS premise_id, s.census_year, s.next_year, s.nom_local,
       CASE WHEN s.nom_local ~* 'mercadona' THEN 'Mercadona' WHEN s.nom_local ~* '\mlidl' THEN 'Lidl' WHEN s.nom_local ~* '\maldi\M' THEN 'Aldi'
            WHEN s.nom_local ~* '^(dia\M|dia %|dia market|supermercados dia)' THEN 'Dia' WHEN s.nom_local ~* 'caprabo' THEN 'Caprabo' WHEN s.nom_local ~* 'condis' THEN 'Condis'
            WHEN s.nom_local ~* 'charter|\mconsum\M' THEN 'Consum_Charter' WHEN s.nom_local ~* 'bon ?preu|esclat' THEN 'BonPreu_Esclat'
            WHEN s.nom_local ~* 'carrefour' THEN 'Carrefour' WHEN s.nom_local ~* 'alcampo|simply|sabeco' THEN 'Alcampo'
            ELSE 'independent_or_other' END AS brand_group,
       NOT EXISTS (SELECT 1 FROM nxt WHERE nxt.census_year = s.next_year AND ST_DWithin(nxt.g, s.g, 20)) AS closed_by_next_census,
       u.seccio_censal, u.codi_barri,
       (SELECT count(*) FROM sup o WHERE o.census_year = s.census_year AND ST_DWithin(o.g, s.g, 300) AND NOT ST_DWithin(o.g, s.g, 20)) AS supermarkets_300m_n,
       (SELECT count(*) FROM {{ ref('store_points') }} p WHERE p.first_seen_census_year = s.next_year AND ST_DWithin(p.geom, s.g, 300)) AS chain_openings_300m_next_n,
       b.year_of_construction, b.footprint_area_m2, s.g AS geom
FROM sup s
LEFT JOIN LATERAL (SELECT seccio_censal, codi_barri FROM {{ source('raw', 'adm_units_polygons') }} a WHERE a.tipus_ua = 'SEC_CENS' AND ST_DWithin(a.geom, s.g, 1) LIMIT 1) u ON true
LEFT JOIN LATERAL (SELECT year_of_construction, footprint_area_m2 FROM {{ source('raw', 'cad_inspire_buildings') }} x WHERE ST_DWithin(x.geom, s.g, 15) ORDER BY x.geom <-> s.g LIMIT 1) b ON true
