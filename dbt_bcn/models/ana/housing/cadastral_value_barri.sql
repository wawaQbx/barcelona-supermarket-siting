-- Cadastral value per m2 by barri, weighted by floor area: total cadastral value / total floor area of the sections (raw.hou_2026_loc_hab_valors).
-- Replaces raw.hou_2026_valor_cadastral_by_barri, the SIMPLE mean of the section unit values (a small section counted as much as a large one;
-- differences up to ~140 EUR/m2). Floor area = total value / unit value of each section.
{{ config(post_hook=primary_key('codi_barri')) }}
WITH v AS (
    SELECT seccio_censal, codi_barri,
           max(valors) FILTER (WHERE desc_valors = 'Valor_cadastral_total_€')        AS total_eur,
           max(valors) FILTER (WHERE desc_valors = 'Valor_cadastral_unitari_€/m2')   AS unit_eur_m2,
           max(valors) FILTER (WHERE desc_valors = 'Valor_sòl_total_€')              AS land_total_eur
    FROM {{ source('raw', 'hou_2026_loc_hab_valors') }} GROUP BY 1, 2)
SELECT codi_barri, count(*) AS sections_n,
       round(sum(total_eur / nullif(unit_eur_m2, 0))::numeric, 0)                        AS floor_area_m2,
       round((sum(total_eur) / sum(total_eur / nullif(unit_eur_m2, 0)))::numeric, 2)     AS cadastral_value_eur_per_m2,
       round(avg(unit_eur_m2)::numeric, 2)                                               AS cadastral_value_simple_mean_eur_per_m2,
       round((100 * sum(land_total_eur) / sum(total_eur))::numeric, 2)                   AS land_share_of_value_pct
FROM v GROUP BY 1
