-- VISUALISATION LAYER (dashboard page 05): how well the siting model (v4, analyze_siting.py) tells sections with a store of the chain from sections
-- without one: cross-validated AUC (0.5 = chance, 1 = perfect), per chain group. Source: ana.py_model_v4_fit (load_model_outputs.py).
{{ config(post_hook=primary_key('brand_group')) }}
SELECT f.brand_group,
       CASE WHEN f.brand_group = 'ALL' THEN 'All chains' ELSE k.chain_label END AS chain_label,
       CASE WHEN f.brand_group = 'ALL' THEN 0 ELSE k.sort_order END AS chain_sort_order,
       f.stores_n::int AS stores_n,
       round(f.cv_auc_base::numeric, 2) AS cv_auc
FROM {{ source('ana', 'py_model_v4_fit') }} f
LEFT JOIN {{ ref('chain_colours') }} k ON k.brand_group = f.brand_group
