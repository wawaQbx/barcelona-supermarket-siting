-- Educational attainment per barri: sums of the section counts of pop_education_section; tertiary = level 5 only (level 6 'No consta' = not available).
-- Replaces raw.pop_educa_superior_by_barri, which counted level 6 as higher education.
{{ config(post_hook=primary_key('codi_barri')) }}
SELECT codi_barri,
       sum(pop_16plus_known_level_n)::integer AS pop_16plus_known_level_n, sum(n_tertiary)::integer AS n_tertiary, sum(n_unknown_published)::integer AS n_unknown_published,
       sum(n_withheld_cells)::integer AS n_withheld_cells,
       round(100.0 * sum(n_tertiary) / sum(pop_16plus_known_level_n), 2)                                  AS tertiary_share_pct,
       round(100.0 * sum(n_tertiary) / (sum(pop_16plus_known_level_n) + 4 * sum(n_withheld_cells)), 2)    AS tertiary_share_lower_bound_pct,
       round(100.0 * sum(n_tertiary) / (sum(pop_16plus_known_level_n) + 1 * sum(n_withheld_cells)), 2)    AS tertiary_share_upper_bound_pct
FROM {{ ref('pop_education_section') }}
WHERE codi_barri IS NOT NULL
GROUP BY 1
