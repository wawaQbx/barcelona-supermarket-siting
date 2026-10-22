-- VISUALISATION LAYER (dashboard page 05): number of low-income food-desert sections for share-of-homes thresholds 25-75% (main = 50%) and the
-- three definitions of fresh food (strict / main / broad), same rule as build_food_access.py: share of homes > 10 min (older pace) >= threshold
-- and income per person <= the city's lower quartile.
{{ config(post_hook=primary_key('definition_order, threshold_pct')) }}
WITH f AS (SELECT * FROM {{ source('ana', 'py_section_food_access') }}),
q AS (SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY disposable_income_eur_per_person) AS q25 FROM f),
t AS (SELECT generate_series(25, 75, 5) AS threshold_pct),
d AS (
    SELECT 1 AS definition_order, 'Strict: 10 chains, markets, fresh shops' AS definition, seccio_censal, share_dwellings_fresh_strict_over_10min_older_pct AS share, disposable_income_eur_per_person AS inc FROM f
    UNION ALL SELECT 2, 'Main: + regional chains selling fresh food', seccio_censal, share_dwellings_fresh_over_10min_older_pct, disposable_income_eur_per_person FROM f
    UNION ALL SELECT 3, 'Broad: + all mini-markets', seccio_censal, share_dwellings_fresh_broad_over_10min_older_pct, disposable_income_eur_per_person FROM f)
SELECT d.definition_order, d.definition, t.threshold_pct,
       count(*) FILTER (WHERE d.share >= t.threshold_pct AND d.inc <= q.q25)::int AS food_desert_sections_n
FROM d CROSS JOIN t CROSS JOIN q
GROUP BY d.definition_order, d.definition, t.threshold_pct
