-- Income and inequality per barri, aggregated correctly from the census sections (replaces raw.inc_renda_gini_by_barri).
--   income: POPULATION-WEIGHTED mean of the section values (EUR per person; the source has only sections). The old table used the simple mean of the
--           sections, which gives a small section the same weight as a large one (differences up to ~780 EUR).
--   Gini:   a barri Gini cannot be computed from section Ginis (it needs the household incomes). We keep the population-weighted MEAN of the section Ginis
--           (= typical inequality inside a section of the barri) plus the lowest / highest section value, and name it so.
--   between-section spread of income: coefficient of variation of the section incomes (population-weighted), a rough sign of inequality BETWEEN sections.
-- Income: 2022 (raw.inc_2022_renda_disponible_llars_per_persona), Gini: 2023 atlas, weights: Padro 2026.
{{ config(post_hook=primary_key('codi_barri')) }}
WITH s AS (
    SELECT l.codi_barri, p.habitants_n AS w, r.renda_disponible_eur_per_persona AS inc, g.index_gini AS gini
    FROM {{ source('raw', 'inc_2022_renda_disponible_llars_per_persona') }} r
    JOIN {{ source('raw', 'inc_2023_atles_renda_index_gini') }} g USING (seccio_censal)
    JOIN {{ source('raw', 'pop_2026_pad_base') }} p USING (seccio_censal)
    JOIN {{ source('raw', 'adm_census_section_lookup') }} l USING (seccio_censal)),
m AS (SELECT codi_barri, sum(w * inc) / sum(w) AS inc_pw FROM s GROUP BY 1)
SELECT s.codi_barri, count(*) AS sections_n, sum(s.w) AS population_n,
       round(m.inc_pw::numeric, 0)::integer                                     AS disposable_income_eur_per_person,
       round(avg(s.inc)::numeric, 0)::integer                                   AS disposable_income_simple_mean_eur_per_person,
       round((sum(s.w * s.gini) / sum(s.w))::numeric, 2)                        AS mean_section_gini_0_100,
       round(min(s.gini)::numeric, 2)                                           AS min_section_gini_0_100,
       round(max(s.gini)::numeric, 2)                                           AS max_section_gini_0_100,
       round((100 * sqrt(sum(s.w * (s.inc - m.inc_pw) ^ 2) / sum(s.w)) / m.inc_pw)::numeric, 2) AS income_between_sections_cv_pct
FROM s JOIN m USING (codi_barri)
GROUP BY s.codi_barri, m.inc_pw
