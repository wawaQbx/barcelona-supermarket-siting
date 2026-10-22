-- ONE ROW PER BARRI (73): the section predictors of section_model_table aggregated (rates are population-weighted; cars exclude fleet-distorted sections)
{{ config(post_hook=primary_key('codi_barri')) }}
SELECT s.codi_barri, count(*) AS sections_n, round(sum(s.area_ha)::numeric, 1) AS area_ha, sum(s.population_n) AS population_n,
       round((sum(s.population_n) / sum(s.area_ha))::numeric, 1) AS population_per_ha,
       round((sum(s.population_n * s.share_age_65plus_pct) / sum(s.population_n))::numeric, 2) AS share_age_65plus_pct,
       round((sum(s.population_n * s.share_age_0_17_pct) / sum(s.population_n))::numeric, 2) AS share_age_0_17_pct,
       round((sum(s.population_n * s.share_tertiary_education_pct) / sum(s.population_n))::numeric, 2) AS share_tertiary_education_pct,
       round((sum(s.population_n * s.disposable_income_eur_per_person) / sum(s.population_n))::numeric, 0)::integer AS disposable_income_eur_per_person,
       round((1000.0 * sum(m.cars_n) FILTER (WHERE NOT m.fleet_distorted) / sum(s.population_n) FILTER (WHERE NOT m.fleet_distorted))::numeric, 1) AS cars_per_1000_residents,
       sum(s.dwellings_n) AS dwellings_n,
       round((100.0 * sum(s.premises_retail_n) / nullif(sum(s.premises_active_n), 0))::numeric, 2) AS retail_share_of_active_premises_pct,
       sum(s.premises_active_n)::bigint AS premises_active_n, sum(s.premises_vacant_n)::bigint AS premises_vacant_n,
       sum(s.premises_daily_food_other_n)::bigint AS premises_daily_food_other_n, sum(s.premises_restaurants_bars_n)::bigint AS premises_restaurants_bars_n,
       sum(s.transit_departures_weekday_300m_n) / count(*) AS transit_departures_weekday_300m_mean_n
FROM {{ ref('section_model_table') }} s JOIN {{ ref('motorization_section') }} m USING (seccio_censal)
GROUP BY 1
