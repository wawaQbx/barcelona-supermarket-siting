-- VISUALISATION LAYER (dashboard page 02 "Why there"): what kind of place each chain chooses, from the siting model v4
-- (Poisson, ln(population) offset = stores per resident, errors clustered by barri; analyze_siting.py -> load_model_outputs.py).
-- One row per chain group x predictor: rate ratio per SD with 95% interval, plus display labels (seed factor_labels) and chain colour (seed chain_colours).
-- Rate ratio 1.30 = one standard deviation more of the factor goes with 30% more stores per resident, the other factors held equal. Correlation, not causation.
-- Chains with fewer stores (Lidl, Aldi, Carrefour, Alcampo) are not modelled at this level (too few stores for 15 predictors).
{{ config(post_hook=primary_key('brand_group, factor_code')) }}
SELECT c.brand_group,
       CASE WHEN c.brand_group = 'ALL' THEN 'All chains' ELSE k.chain_label END AS chain_label,
       CASE WHEN c.brand_group = 'ALL' THEN '#5C5C5C' ELSE k.colour_hex END AS chain_colour_hex,
       CASE WHEN c.brand_group = 'ALL' THEN 0 ELSE k.sort_order END AS chain_sort_order,
       f.stores_n,
       dense_rank() OVER (ORDER BY f.stores_n DESC)::integer AS chain_order_by_stores,   -- button order on page 02: All chains (664) first, then Condis, Caprabo ...
       c.factor_code, l.factor_label, l.factor_short, l.factor_block, l.factor_order, l.unit_note,
       round(c.rate_ratio_per_sd::numeric, 3) AS rate_ratio_per_sd,
       round(c.ci95_low::numeric, 3) AS ci95_low, round(c.ci95_high::numeric, 3) AS ci95_high,
       round(c.p_value::numeric, 4) AS p_value,
       (c.ci95_low > 1 OR c.ci95_high < 1) AS significant_95,
       CASE WHEN c.ci95_low > 1 THEN 'more stores' WHEN c.ci95_high < 1 THEN 'fewer stores' ELSE 'no clear effect' END AS effect_class,
       round((100 * (c.rate_ratio_per_sd - 1))::numeric, 0) AS effect_pct_per_sd,
       -- 105 tests (7 groups x 15 factors): about 5 would pass p < 0.05 by chance alone. Benjamini-Hochberg q value (load_model_outputs.py):
       -- strong = q < 0.05 (survives the correction), weak = p < 0.05 but not q < 0.05 (could be chance), none = p >= 0.05
       round(c.q_value_bh::numeric, 4) AS q_value_bh,
       CASE WHEN c.q_value_bh < 0.05 THEN 'strong' WHEN c.p_value < 0.05 THEN 'weak' ELSE 'none' END AS evidence_strength,
       round(ln(c.rate_ratio_per_sd)::numeric, 3) AS log_rate_ratio       -- symmetric scale for the heat-map colours (0 = no effect)
FROM {{ source('ana', 'py_model_v4_coefficients') }} c
JOIN {{ ref('factor_labels') }} l USING (factor_code)
JOIN {{ source('ana', 'py_model_v4_fit') }} f USING (brand_group)
LEFT JOIN {{ ref('chain_colours') }} k USING (brand_group)
