-- Population by 5 age bands per census section, reconciled with the OFFICIAL total.
-- Problem: raw.pop_2026_pads_edat_1 withholds every single-age cell below 5 people (marker '..' -> NULL). Summing the published cells
--          under-counts the population (1,704,260 vs 1,729,963 official) and mostly loses very old / very young cells.
-- Method:  per section, withheld_total = official population (raw.pop_2026_pad_base) - sum of published cells (exact, not a guess).
--          It is spread over the age bands in proportion to the number of withheld cells each band has (each withheld cell holds 1-4 people).
-- Use this table for age structure; do NOT use raw.pop_age_groups_by_* (built from the incomplete cells).
{{ config(post_hook=primary_key('seccio_censal')) }}
WITH cells AS (
    SELECT seccio_censal,
           CASE WHEN edat_1::int <= 17 THEN '0_17' WHEN edat_1::int <= 24 THEN '18_24' WHEN edat_1::int <= 44 THEN '25_44'
                WHEN edat_1::int <= 64 THEN '45_64' ELSE '65plus' END AS band,
           habitants_n
    FROM {{ source('raw', 'pop_2026_pads_edat_1') }}),
band AS (
    SELECT seccio_censal, band, coalesce(sum(habitants_n), 0) AS published, count(*) FILTER (WHERE habitants_n IS NULL) AS n_withheld
    FROM cells GROUP BY 1, 2),
tot AS (
    SELECT b.seccio_censal, p.habitants_n AS pop_official_n, sum(b.published) AS pop_published_n, sum(b.n_withheld) AS n_withheld_cells
    FROM band b JOIN {{ source('raw', 'pop_2026_pad_base') }} p USING (seccio_censal) GROUP BY 1, 2),
wide AS (
    SELECT b.seccio_censal,
           sum(published) FILTER (WHERE band = '0_17') AS pub_0_17,   sum(published) FILTER (WHERE band = '18_24') AS pub_18_24,
           sum(published) FILTER (WHERE band = '25_44') AS pub_25_44, sum(published) FILTER (WHERE band = '45_64') AS pub_45_64,
           sum(published) FILTER (WHERE band = '65plus') AS pub_65plus,
           sum(n_withheld) FILTER (WHERE band = '0_17') AS nw_0_17,   sum(n_withheld) FILTER (WHERE band = '18_24') AS nw_18_24,
           sum(n_withheld) FILTER (WHERE band = '25_44') AS nw_25_44, sum(n_withheld) FILTER (WHERE band = '45_64') AS nw_45_64,
           sum(n_withheld) FILTER (WHERE band = '65plus') AS nw_65plus
    FROM band b GROUP BY 1),
est AS (
    SELECT w.*, t.pop_official_n, t.pop_published_n, t.n_withheld_cells,
           (t.pop_official_n - t.pop_published_n) AS withheld_total
    FROM wide w JOIN tot t USING (seccio_censal)),
bands AS (
    SELECT e.seccio_censal, l.codi_barri, l.codi_districte,
           e.pop_official_n, e.pop_published_n::int AS pop_published_n, e.withheld_total::int AS withheld_total_estimated_n, e.n_withheld_cells::int AS n_withheld_cells,
           (e.n_withheld_cells > 0) AS has_withheld_cells,
           -- sanity check: every withheld cell must hold 1-4 people
           CASE WHEN e.n_withheld_cells = 0 THEN e.withheld_total = 0
                ELSE e.withheld_total::numeric / e.n_withheld_cells BETWEEN 1 AND 4 END AS reconciles,
           e.pub_0_17::int AS age_0_17_published_n, e.pub_18_24::int AS age_18_24_published_n, e.pub_25_44::int AS age_25_44_published_n,
           e.pub_45_64::int AS age_45_64_published_n, e.pub_65plus::int AS age_65plus_published_n,
           round(e.pub_0_17   + CASE WHEN e.n_withheld_cells > 0 THEN e.withheld_total * e.nw_0_17   / e.n_withheld_cells ELSE 0 END, 2) AS age_0_17_estimated_n,
           round(e.pub_18_24  + CASE WHEN e.n_withheld_cells > 0 THEN e.withheld_total * e.nw_18_24  / e.n_withheld_cells ELSE 0 END, 2) AS age_18_24_estimated_n,
           round(e.pub_25_44  + CASE WHEN e.n_withheld_cells > 0 THEN e.withheld_total * e.nw_25_44  / e.n_withheld_cells ELSE 0 END, 2) AS age_25_44_estimated_n,
           round(e.pub_45_64  + CASE WHEN e.n_withheld_cells > 0 THEN e.withheld_total * e.nw_45_64  / e.n_withheld_cells ELSE 0 END, 2) AS age_45_64_estimated_n,
           round(e.pub_65plus + CASE WHEN e.n_withheld_cells > 0 THEN e.withheld_total * e.nw_65plus / e.n_withheld_cells ELSE 0 END, 2) AS age_65plus_estimated_n
    FROM est e LEFT JOIN {{ source('raw', 'adm_census_section_lookup') }} l USING (seccio_censal))
SELECT b.*,
       round(100 * age_0_17_estimated_n / pop_official_n, 2)   AS share_0_17_pct,  round(100 * age_18_24_estimated_n / pop_official_n, 2) AS share_18_24_pct,
       round(100 * age_25_44_estimated_n / pop_official_n, 2)  AS share_25_44_pct, round(100 * age_45_64_estimated_n / pop_official_n, 2) AS share_45_64_pct,
       round(100 * age_65plus_estimated_n / pop_official_n, 2) AS share_65plus_pct,
       -- LOCATION QUOTIENT (the user's LQ, recomputed on the reconciled bands): share of the band here / share of the band in the whole city;
       -- 1 = city average, 1.5 = 50% more concentrated, 0.6 = 40% less. Replaces raw.pop_age_groups_by_seccio, which used the incomplete published cells.
       round((age_0_17_estimated_n / pop_official_n) / (sum(age_0_17_estimated_n) OVER () / sum(pop_official_n) OVER ()), 3) AS age_0_17_location_quotient,
       round((age_18_24_estimated_n / pop_official_n) / (sum(age_18_24_estimated_n) OVER () / sum(pop_official_n) OVER ()), 3) AS age_18_24_location_quotient,
       round((age_25_44_estimated_n / pop_official_n) / (sum(age_25_44_estimated_n) OVER () / sum(pop_official_n) OVER ()), 3) AS age_25_44_location_quotient,
       round((age_45_64_estimated_n / pop_official_n) / (sum(age_45_64_estimated_n) OVER () / sum(pop_official_n) OVER ()), 3) AS age_45_64_location_quotient,
       round((age_65plus_estimated_n / pop_official_n) / (sum(age_65plus_estimated_n) OVER () / sum(pop_official_n) OVER ()), 3) AS age_65plus_location_quotient
FROM bands b
