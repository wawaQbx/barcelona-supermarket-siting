-- ACTIVE premises of every census edition with a type that is comparable across editions:
--   daily_food_other = "Quotidia alimentari" without supermarkets; supermarket_class = Autoservei / Supermercat (2016+);
--   other_retail = the other retail groups; restaurants_bars = "Restaurants, bars i hotels" (2016+ only: 2014 put restaurants inside SERVEIS);
--   services_other = the rest. Active = 2014: sector <> 'LOCAL BUIT'; 2016-2024: nom_principal_activitat = 'Actiu'.
{{ config(indexes=[{'columns': ['g'], 'type': 'gist'}], post_hook=analyze_this()) }}
SELECT census_year, geom AS g,
       CASE WHEN census_year = 2014 THEN
                CASE WHEN nom_grup_activitat = 'QUOTIDIÀ ALIMENTARI' THEN 'daily_food_other'
                     WHEN nom_grup_activitat IN ('EQUIPAMENT PERSONAL', 'PARAMENT DE LA LLAR', 'OCI I CULTURA', 'QUOTIDIÀ NO ALIMENTARI', 'AUTOMOCIÓ') THEN 'other_retail'
                     ELSE 'services_other' END
            WHEN nom_grup_activitat = 'Quotidià alimentari' AND nom_activitat IS DISTINCT FROM 'Autoservei / Supermercat' THEN 'daily_food_other'
            WHEN nom_grup_activitat = 'Quotidià alimentari' THEN 'supermarket_class'
            WHEN nom_grup_activitat IN ('Equipament personal', 'Parament de la llar', 'Oci i cultura', 'Quotidià no alimentari', 'Automoció') THEN 'other_retail'
            WHEN nom_grup_activitat LIKE 'Restaurants%' THEN 'restaurants_bars'
            ELSE 'services_other' END AS ptype
FROM {{ ref('int_census_premises') }}
WHERE (census_year = 2014 AND nom_sector_activitat <> 'LOCAL BUIT') OR (census_year > 2014 AND nom_principal_activitat = 'Actiu')
