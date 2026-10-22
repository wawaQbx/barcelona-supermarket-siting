-- VISUALISATION LAYER (dashboard page 04): why no supermarket opens in the flagged food-access sections.
-- One row per flagged section (same sections as the page-04 table): residents and spending power within 400 m of the section's dwelling-weighted
-- centre, compared with the same measure around every existing city chain store (p10 / p25 / median as columns, for reference lines).
-- Source: ana.py_food_desert_viability (food_desert_viability.py, after build_food_access.py).
{{ config(post_hook=primary_key('seccio_censal')) }}
SELECT v.seccio_censal, s.nom_barri, s.nom_districte,
       s.nom_barri || ' (' || v.seccio_censal || ')' AS area_label,
       s.access_flag, s.access_flag_order,
       CASE s.access_flag_order WHEN 1 THEN '#5E3C99' WHEN 2 THEN '#B2A3D1' ELSE '#2E8B9A' END AS access_flag_colour,
       round(v.residents_400m_n)::int AS residents_400m_n,   -- estimate (dwellings x persons per dwelling), shown as whole people
       v.spending_400m_meur, v.income_400m_eur_per_person, v.elev_range_400m_m,
       v.vacant_premises_400m_n, v.big_buildings_with_shops_400m_n, v.nearest_chain_store_m,
       v.share_existing_stores_fewer_residents_pct,
       v.existing_stores_residents_400m_p10, v.existing_stores_residents_400m_p25, v.existing_stores_residents_400m_median
FROM {{ source('ana', 'py_food_desert_viability') }} v
JOIN {{ ref('section_indicators') }} s USING (seccio_censal)
