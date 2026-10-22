-- City stores first seen in a census AFTER 2014 (first_seen_census_year 2016-2024), with what stood at the site in the PREVIOUS census edition.
-- "First seen" = a premise with the same brand name within 60 m (census_panel.py), so a "new" store can be
--   (a) a NEW SITE (no food retail premise within 25 m in the previous edition), or
--   (b) a TAKEOVER: it replaced a supermarket / grocery self-service that was within 25 m in the previous census and is gone when the chain appears (e.g. Simply -> Mi Alcampo, Dia Market -> Condis, independent -> Condis franchise).
-- "Supermarket / grocery" = the supermarket class of each edition, the same rule as gis.chain_census_premises: 2014 'ALIMENTACIÓ',
-- 2016 'Resta alimentació' (no supermarket class that year), 2019+ 'Autoservei / Supermercat', and hypermarkets.
-- CORRECTED 2026-10-19: the earlier rule matched any activity or group containing "alimentari", which also took the 2014 group
-- "QUOTIDIÀ NO ALIMENTARI" (pharmacies, drugstores), and any specialised food shop within 25 m (a bakery next door is not a takeover).
{{ config(post_hook=primary_key('store_id')) }}
WITH food AS (
    SELECT census_year AS yr, geom AS g, nom_local, nom_activitat FROM {{ ref('int_census_premises') }}
    WHERE census_year <= 2022
      AND (   (census_year = 2014 AND nom_activitat = 'ALIMENTACIÓ')
           OR (census_year = 2016 AND nom_activitat = 'Resta alimentació')
           OR (census_year >= 2019 AND nom_activitat = 'Autoservei / Supermercat')
           OR nom_activitat ILIKE 'Grans magatzems i hipermercats')),
prev AS (SELECT 2016 AS yr, 2014 AS prev_yr UNION ALL SELECT 2019, 2016 UNION ALL SELECT 2022, 2019 UNION ALL SELECT 2024, 2022),
-- NEIGHBOUR, NOT TAKEOVER (2026-10-19): when the previous occupant was one of the 10 chains and that chain still has a store within 40 m today,
-- the new store opened next to it (e.g. a Condis beside the Mercadona of Diagonal Mar, whose census point moved 90 m in 2022): new site.
rx AS (SELECT * FROM {{ brand_patterns() }})
SELECT p.store_id, p.ensenya, p.brand_group, p.format_group, p.store_type, p.first_seen_census_year, p.opening_era, p.clarel_conversion, pv.prev_yr AS previous_census_year,
       f.nom_local AS previous_food_premise_name, f.nom_activitat AS previous_food_premise_activity,
       CASE WHEN p.clarel_conversion THEN 'clarel_conversion'
            WHEN f.nom_local IS NOT NULL AND NOT EXISTS (
                     SELECT 1 FROM rx JOIN {{ ref('store_points') }} q ON q.brand_group = rx.brand_group
                     WHERE f.nom_local ~* rx.pattern AND q.store_id <> p.store_id AND ST_DWithin(q.geom, p.geom, 40)) THEN 'takeover_of_food_premise'
            ELSE 'new_site' END AS opening_type,
       p.geom
FROM {{ ref('store_points') }} p
JOIN prev pv ON pv.yr = p.first_seen_census_year
-- the previous grocery must have GONE by the census in which the chain store appears (its sign not within 30 m then): otherwise the chain opened
-- NEXT TO it (18 of 84 "takeovers" were neighbours before this rule, 2026-10-19 audit, data/store_openings_audit.csv)
LEFT JOIN LATERAL (SELECT f0.nom_local, f0.nom_activitat FROM food f0
                   WHERE f0.yr = pv.prev_yr AND ST_DWithin(f0.g, p.geom, 25)
                     AND NOT EXISTS (SELECT 1 FROM {{ ref('int_census_premises') }} f1
                                     WHERE f1.census_year = pv.yr AND upper(f1.nom_local) = upper(f0.nom_local) AND ST_DWithin(f1.geom, f0.g, 30))
                   ORDER BY ST_Distance(f0.g, p.geom) LIMIT 1) f ON true
WHERE p.in_city AND p.first_seen_census_year >= 2016
