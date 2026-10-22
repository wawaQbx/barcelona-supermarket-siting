-- Predictors measured BEFORE the 2016-2024 openings (time ordering against reverse causality).
--   population, density, 65+ share, tertiary education: Padro 1 January 2015 (fetch_history.py; same 1068 section codes, year-to-year corr >= 0.976)
--   income: 2015 disposable income per person;  ground-floor premises: 2014 commercial census (ED50 points joined to sections)
-- 65+ share is reconciled like pop_age_bands_section: withheld five-year cells (< 5 people) get the exact section remainder,
-- spread by number of withheld cells.
{{ config(post_hook=primary_key('seccio_censal')) }}
WITH geo AS (SELECT seccio_censal, geom, ST_Area(geom) / 10000.0 AS area_ha FROM {{ source('raw', 'adm_units_polygons') }} WHERE tipus_ua = 'SEC_CENS'),
pop AS (SELECT seccio_censal,
               max(habitants_n) FILTER (WHERE data_referencia = '2015-01-01') AS pop_2015,
               max(habitants_n) FILTER (WHERE data_referencia = '2026-01-01') AS pop_2026
        FROM {{ source('raw', 'pop_padro_population_history') }} GROUP BY 1),
age AS (SELECT seccio_censal,
               coalesce(sum(habitants_n) FILTER (WHERE edat_q >= 13), 0) AS pub_65,  coalesce(sum(habitants_n), 0) AS pub_all,
               count(*) FILTER (WHERE habitants_n IS NULL AND edat_q >= 13) AS nw_65, count(*) FILTER (WHERE habitants_n IS NULL) AS nw_all
        FROM {{ source('raw', 'pop_padro_age5_2015') }} GROUP BY 1),
edu AS (SELECT seccio_censal,
               sum(habitants_n) FILTER (WHERE niv_educa_esta = 5) AS tertiary, sum(habitants_n) FILTER (WHERE niv_educa_esta BETWEEN 1 AND 5) AS known
        FROM {{ source('raw', 'pop_padro_education_2015') }} GROUP BY 1),
inc AS (SELECT seccio_censal, renda_disponible_eur_per_persona AS income_2015 FROM {{ source('raw', 'inc_income_history') }} WHERE any_ = 2015),
c14 AS (SELECT g.seccio_censal,
               count(c.*) FILTER (WHERE c.nom_sector_activitat <> 'LOCAL BUIT')        AS premises_active_2014_n,
               count(c.*) FILTER (WHERE c.nom_sector_activitat = 'LOCAL BUIT')         AS premises_vacant_2014_n,
               count(c.*) FILTER (WHERE c.nom_sector_activitat = 'COMERÇ AL DETALL')   AS premises_retail_2014_n
        FROM geo g LEFT JOIN (SELECT nom_sector_activitat, geom AS gp FROM {{ ref('int_census_premises') }} WHERE census_year = 2014) c ON ST_Intersects(g.geom, c.gp)
        GROUP BY 1)
SELECT g.seccio_censal, round(g.area_ha::numeric, 2) AS area_ha,
       p.pop_2015 AS population_2015_n, p.pop_2026 AS population_2026_n,
       round((100.0 * (p.pop_2026 - p.pop_2015) / p.pop_2015)::numeric, 2) AS population_growth_2015_2026_pct,
       round((p.pop_2015 / g.area_ha)::numeric, 1) AS population_per_ha_2015,
       round((100.0 * (a.pub_65 + CASE WHEN a.nw_all > 0 THEN (p.pop_2015 - a.pub_all) * a.nw_65::numeric / a.nw_all ELSE 0 END) / p.pop_2015)::numeric, 2) AS share_age_65plus_2015_pct,
       round((100.0 * e.tertiary / nullif(e.known, 0))::numeric, 2) AS share_tertiary_education_2015_pct,
       i.income_2015 AS disposable_income_2015_eur_per_person,
       c.premises_active_2014_n, c.premises_vacant_2014_n, c.premises_retail_2014_n,
       round((100.0 * c.premises_vacant_2014_n / nullif(c.premises_active_2014_n + c.premises_vacant_2014_n, 0))::numeric, 2) AS vacant_share_2014_pct
FROM geo g LEFT JOIN pop p USING (seccio_censal) LEFT JOIN age a USING (seccio_censal) LEFT JOIN edu e USING (seccio_censal)
LEFT JOIN inc i USING (seccio_censal) LEFT JOIN c14 c USING (seccio_censal)
