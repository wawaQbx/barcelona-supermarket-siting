-- Age bands per barri: sum of the reconciled section estimates (pop_age_bands_section), shares and location quotients
{{ config(post_hook=primary_key('codi_barri')) }}
SELECT codi_barri, sum(pop_official_n) AS pop_official_n, sum(n_withheld_cells) AS n_withheld_cells,
       round(sum(age_0_17_estimated_n), 1) AS age_0_17_estimated_n, round(sum(age_18_24_estimated_n), 1) AS age_18_24_estimated_n, round(sum(age_25_44_estimated_n), 1) AS age_25_44_estimated_n,
       round(sum(age_45_64_estimated_n), 1) AS age_45_64_estimated_n, round(sum(age_65plus_estimated_n), 1) AS age_65plus_estimated_n,
       round(100 * sum(age_65plus_estimated_n) / sum(pop_official_n), 2) AS share_65plus_pct, round(100 * sum(age_0_17_estimated_n) / sum(pop_official_n), 2) AS share_0_17_pct,
       round(100 * sum(age_18_24_estimated_n) / sum(pop_official_n), 2) AS share_18_24_pct, round(100 * sum(age_25_44_estimated_n) / sum(pop_official_n), 2) AS share_25_44_pct,
       round(100 * sum(age_45_64_estimated_n) / sum(pop_official_n), 2) AS share_45_64_pct,
       -- location quotient per barri (replaces raw.pop_age_groups_by_barri, built from the incomplete published cells)
       round((sum(age_0_17_estimated_n) / sum(pop_official_n)) / (sum(sum(age_0_17_estimated_n)) OVER () / sum(sum(pop_official_n)) OVER ()), 3) AS age_0_17_location_quotient,
       round((sum(age_18_24_estimated_n) / sum(pop_official_n)) / (sum(sum(age_18_24_estimated_n)) OVER () / sum(sum(pop_official_n)) OVER ()), 3) AS age_18_24_location_quotient,
       round((sum(age_25_44_estimated_n) / sum(pop_official_n)) / (sum(sum(age_25_44_estimated_n)) OVER () / sum(sum(pop_official_n)) OVER ()), 3) AS age_25_44_location_quotient,
       round((sum(age_45_64_estimated_n) / sum(pop_official_n)) / (sum(sum(age_45_64_estimated_n)) OVER () / sum(sum(pop_official_n)) OVER ()), 3) AS age_45_64_location_quotient,
       round((sum(age_65plus_estimated_n) / sum(pop_official_n)) / (sum(sum(age_65plus_estimated_n)) OVER () / sum(sum(pop_official_n)) OVER ()), 3) AS age_65plus_location_quotient
FROM {{ ref('pop_age_bands_section') }} WHERE codi_barri IS NOT NULL GROUP BY 1
