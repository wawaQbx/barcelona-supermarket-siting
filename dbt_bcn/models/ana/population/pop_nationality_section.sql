-- Population by nationality group per census section, 1 January 2015 and 2026, reconciled with the OFFICIAL total (same method as pop_age_bands_section).
-- Source: Padro, nationality group x sex (raw.pop_padro_nationality_2015_2026; 1 Spain, 2 rest of EU, 3 rest of the world, 4 not available).
-- Cells below 5 people are withheld ('..' -> NULL): per section, withheld_total = official population - published cells (exact), spread over the groups
-- in proportion to their number of withheld cells (each withheld cell holds 1-4 people).
-- Official totals: 2026 raw.pop_2026_pad_base, 2015 raw.pop_padro_population_history.
{{ config(post_hook=primary_key('seccio_censal')) }}
WITH cells AS (
    SELECT extract(year FROM data_referencia)::int AS yr, seccio_censal, nacionalitat_g::int AS grp, habitants_n
    FROM {{ source('raw', 'pop_padro_nationality_2015_2026') }}),
grp AS (
    SELECT yr, seccio_censal, grp, coalesce(sum(habitants_n), 0) AS published, count(*) FILTER (WHERE habitants_n IS NULL) AS n_withheld
    FROM cells GROUP BY 1, 2, 3),
official AS (
    SELECT 2026 AS yr, seccio_censal, habitants_n AS pop_official FROM {{ source('raw', 'pop_2026_pad_base') }}
    UNION ALL
    SELECT 2015, seccio_censal, max(habitants_n) FROM {{ source('raw', 'pop_padro_population_history') }} WHERE data_referencia = '2015-01-01' GROUP BY 2),
tot AS (
    SELECT g.yr, g.seccio_censal, o.pop_official, sum(g.published) AS pop_published, sum(g.n_withheld) AS n_withheld
    FROM grp g JOIN official o USING (yr, seccio_censal) GROUP BY 1, 2, 3),
est AS (    -- estimated people per group = published + share of the withheld remainder
    SELECT g.yr, g.seccio_censal, g.grp, t.pop_official, t.n_withheld AS n_withheld_cells_section,
           g.published + CASE WHEN t.n_withheld > 0 THEN (t.pop_official - t.pop_published)::numeric * g.n_withheld / t.n_withheld ELSE 0 END AS people
    FROM grp g JOIN tot t USING (yr, seccio_censal)),
wide AS (
    SELECT seccio_censal,
           max(pop_official) FILTER (WHERE yr = 2015) AS population_2015_n, max(pop_official) FILTER (WHERE yr = 2026) AS population_2026_n,
           sum(people) FILTER (WHERE yr = 2015 AND grp IN (2, 3)) AS foreign_2015, sum(people) FILTER (WHERE yr = 2015 AND grp = 3) AS non_eu_2015,
           sum(people) FILTER (WHERE yr = 2026 AND grp IN (2, 3)) AS foreign_2026, sum(people) FILTER (WHERE yr = 2026 AND grp = 3) AS non_eu_2026,
           sum(people) FILTER (WHERE yr = 2026 AND grp = 4) AS unknown_2026,
           max(n_withheld_cells_section) FILTER (WHERE yr = 2026) AS n_withheld_cells_2026
    FROM est GROUP BY 1)
SELECT w.seccio_censal, l.codi_barri, l.codi_districte, w.population_2015_n, w.population_2026_n,
       round(w.foreign_2026, 1) AS foreign_2026_estimated_n, round(w.non_eu_2026, 1) AS foreign_non_eu_2026_estimated_n,
       round(100 * w.foreign_2026 / w.population_2026_n, 2) AS share_foreign_2026_pct,
       round(100 * w.non_eu_2026 / w.population_2026_n, 2)  AS share_foreign_non_eu_2026_pct,
       round(100 * w.foreign_2015 / w.population_2015_n, 2) AS share_foreign_2015_pct,
       round(100 * w.non_eu_2015 / w.population_2015_n, 2)  AS share_foreign_non_eu_2015_pct,
       round(100 * w.foreign_2026 / w.population_2026_n - 100 * w.foreign_2015 / w.population_2015_n, 2) AS share_foreign_change_2015_2026_pp,
       round(100 * w.unknown_2026 / w.population_2026_n, 2) AS share_nationality_unknown_2026_pct,
       w.n_withheld_cells_2026::int AS n_withheld_cells_2026
FROM wide w LEFT JOIN {{ source('raw', 'adm_census_section_lookup') }} l USING (seccio_censal)
