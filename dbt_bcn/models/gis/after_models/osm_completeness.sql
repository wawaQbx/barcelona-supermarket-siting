-- VISUALISATION LAYER (dashboard page 05): how complete OpenStreetMap is for food shops, checked INSIDE the city against the 2024 commercial
-- census (a municipal field survey of every ground-floor premise). Outside the city only OSM is available (build_food_access.py), so this is the
-- likely under-recording of shops across the city boundary. A census premise counts as found when an OSM object of the matching category is
-- within 50 m (municipal markets: within 150 m of the market). Stalls inside municipal markets are left out (OSM maps the market, not its stalls).
{{ config(post_hook=primary_key('category_order')) }}
WITH osm AS (
    SELECT food_category, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) AS g
    FROM {{ source('raw', 'com_osm_food_shops_box') }} WHERE lon IS NOT NULL),
cen AS (
    SELECT CASE nom_activitat WHEN 'Autoservei / Supermercat' THEN 2 WHEN 'Fruites i verdures' THEN 3
                WHEN 'Carn i Porc' THEN 4 WHEN 'Ous i aus' THEN 4 WHEN 'Peix i marisc' THEN 5 END AS category_order,
           ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) AS g
    FROM {{ source('raw', 'cen_census_2024') }}
    WHERE nom_principal_activitat = 'Actiu' AND lon IS NOT NULL AND NOT coalesce(sn_mercat, false)
      AND nom_activitat IN ('Autoservei / Supermercat', 'Fruites i verdures', 'Carn i Porc', 'Ous i aus', 'Peix i marisc')),
cat AS (
    SELECT * FROM (VALUES (1, 'Markets', ARRAY['market']), (2, 'Grocery stores', ARRAY['supermarket', 'convenience']),
                          (3, 'Greengrocers', ARRAY['greengrocer']), (4, 'Butchers', ARRAY['butcher']),
                          (5, 'Fishmongers', ARRAY['fishmonger'])) v(category_order, category_label, osm_categories)),
shops AS (
    SELECT c.category_order, count(*) AS census_n,
           count(*) FILTER (WHERE EXISTS (SELECT 1 FROM osm o WHERE o.food_category = ANY (k.osm_categories) AND ST_DWithin(o.g, c.g, 50))) AS found_n
    FROM cen c JOIN cat k USING (category_order) GROUP BY 1),
mkts AS (
    SELECT 1 AS category_order, count(*) AS census_n,
           count(*) FILTER (WHERE EXISTS (SELECT 1 FROM osm o WHERE o.food_category = 'market' AND ST_DWithin(o.g, m.geom, 150))) AS found_n
    FROM {{ ref('markets') }} m WHERE m.food_market)
SELECT k.category_order, k.category_label, x.census_n::int AS census_premises_n, x.found_n::int AS found_in_osm_n,
       round((100.0 * x.found_n / x.census_n)::numeric, 1) AS found_in_osm_pct
FROM cat k JOIN (SELECT * FROM shops UNION ALL SELECT * FROM mkts) x USING (category_order)
