-- Educational attainment per census section (both sexes added), with the correct definition of "tertiary".
-- Official levels (Open Data BCN pad-dimensions): 1 no studies, 2 primary, 3 lower secondary, 4 upper secondary / mid-level vocational,
--   5 TERTIARY (university, higher vocational CFGS), 6 'No consta' = NOT AVAILABLE.
-- Level 5 cells are never withheld; withheld cells ('..', below 5 people) occur only in levels 1 and 6, so the tertiary share is robust.
-- raw.pop_educa_superior_by_* (QGIS tables) counted level 6 (unknown) as higher education, which overstates it.
-- Tertiary share: point estimate over published cells; bounds assume every withheld cell holds 4 people (lower share) or 1 person (upper share).
{{ config(post_hook=primary_key('seccio_censal')) }}
WITH lev AS (
    SELECT s.seccio_censal, l.codi_barri, l.codi_districte,
           sum(habitants_n) FILTER (WHERE niv_educa_esta = '1') AS n_no_studies_published,
           sum(habitants_n) FILTER (WHERE niv_educa_esta = '2') AS n_primary,
           sum(habitants_n) FILTER (WHERE niv_educa_esta = '3') AS n_lower_secondary,
           sum(habitants_n) FILTER (WHERE niv_educa_esta = '4') AS n_upper_secondary,
           sum(habitants_n) FILTER (WHERE niv_educa_esta = '5') AS n_tertiary,
           sum(habitants_n) FILTER (WHERE niv_educa_esta = '6') AS n_unknown_published,
           count(*) FILTER (WHERE habitants_n IS NULL) AS n_withheld_cells,
           count(*) FILTER (WHERE habitants_n IS NULL AND niv_educa_esta IN ('2','3','4','5')) AS n_withheld_cells_levels_2_to_5
    FROM {{ source('raw', 'pop_2026_pad_16niv_educa_sexe') }} s LEFT JOIN {{ source('raw', 'adm_census_section_lookup') }} l USING (seccio_censal)
    GROUP BY s.seccio_censal, l.codi_barri, l.codi_districte),
known AS (
    SELECT lev.*, (coalesce(n_no_studies_published, 0) + n_primary + n_lower_secondary + n_upper_secondary + n_tertiary)::numeric AS pop_16plus_known_level_n
    FROM lev)
SELECT k.*,
       round(100.0 * n_tertiary / pop_16plus_known_level_n, 2)                          AS tertiary_share_pct,
       round(100.0 * n_tertiary / (pop_16plus_known_level_n + 4 * n_withheld_cells), 2) AS tertiary_share_lower_bound_pct,
       round(100.0 * n_tertiary / (pop_16plus_known_level_n + 1 * n_withheld_cells), 2) AS tertiary_share_upper_bound_pct,
       n_withheld_cells > 0                                                             AS has_withheld_cells
FROM known k
