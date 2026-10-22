-- =====================================================================================================
-- ana.store_openings : city stores first seen in a census AFTER 2014 (first_seen_census_year 2016-2024), with what stood at the site
-- in the PREVIOUS census edition. "First seen" = a premise with the same brand name within 60 m (census_panel.py), so a "new" store can be
--   (a) a NEW SITE (no food retail premise within 25 m in the previous edition), or
--   (b) a TAKEOVER / REBRANDING of an existing food shop or supermarket (e.g. Simply -> Mi Alcampo, Clarel -> Dia, independent -> Condis franchise).
-- 2014 / 2016 have no separate supermarket class, so "food retail" = activity names with alimentaci / supermercat / autoservei / hipermercat.
-- =====================================================================================================
DROP TABLE IF EXISTS ana.store_openings CASCADE;
CREATE TABLE ana.store_openings AS
WITH food AS (
    SELECT 2014 AS yr, ST_Transform(ST_SetSRID(ST_MakePoint(x_ed50, y_ed50), 23031), 25831) AS g, nom_local, nom_activitat FROM raw.cen_census_2014
      WHERE x_ed50 IS NOT NULL AND (nom_activitat ~* 'alimentaci|supermerc|autoserv|hipermerc' OR nom_grup_activitat ~* 'alimentari')
    UNION ALL SELECT 2016, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831), nom_local, nom_activitat FROM raw.cen_census_2016
      WHERE lon IS NOT NULL AND (nom_activitat ~* 'alimentaci|supermerc|autoserv|hipermerc')
    UNION ALL SELECT 2019, geom, nom_local, nom_activitat FROM raw.cen_census_2019
      WHERE nom_activitat ~* 'alimentaci|supermerc|autoserv|hipermerc'
    UNION ALL SELECT 2022, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831), nom_local, nom_activitat FROM raw.cen_census_2022
      WHERE lon IS NOT NULL AND nom_activitat ~* 'alimentaci|supermerc|autoserv|hipermerc'),
prev AS (SELECT 2016 AS yr, 2014 AS prev_yr UNION ALL SELECT 2019, 2016 UNION ALL SELECT 2022, 2019 UNION ALL SELECT 2024, 2022)
SELECT p.store_id, p.ensenya, p.brand_group, p.format_group, p.store_type, p.first_seen_census_year, p.opening_era, p.clarel_conversion, pv.prev_yr AS previous_census_year,
       f.nom_local AS previous_food_premise_name, f.nom_activitat AS previous_food_premise_activity,
       CASE WHEN p.clarel_conversion THEN 'clarel_conversion'
            WHEN f.nom_local IS NOT NULL THEN 'takeover_of_food_premise'
            ELSE 'new_site' END AS opening_type,
       p.geom
FROM ana.store_points p
JOIN prev pv ON pv.yr = p.first_seen_census_year
LEFT JOIN LATERAL (SELECT nom_local, nom_activitat FROM food WHERE food.yr = pv.prev_yr AND ST_DWithin(food.g, p.geom, 25)
                   ORDER BY ST_Distance(food.g, p.geom) LIMIT 1) f ON true
WHERE p.in_city AND p.first_seen_census_year >= 2016;
ALTER TABLE ana.store_openings ADD PRIMARY KEY (store_id);
COMMENT ON TABLE ana.store_openings IS 'City stores first seen 2016-2024 with opening_type: new_site / takeover_of_food_premise (food shop within 25 m in the previous census) / clarel_conversion. Built by sql/ana_store_openings.sql';

-- counts of openings per census section and group (chain, format, ALL)
DROP TABLE IF EXISTS ana.store_openings_section CASCADE;
CREATE TABLE ana.store_openings_section AS
WITH units AS (SELECT seccio_censal, geom FROM raw.adm_units_polygons WHERE tipus_ua = 'SEC_CENS'),
o AS (SELECT m.grp, s.* FROM ana.store_openings s JOIN ana.store_group_membership m USING (store_id))
SELECT u.seccio_censal, g.grp AS brand_group,
       count(o.store_id)                                                     AS n_openings_2016_2024,
       count(o.store_id) FILTER (WHERE o.opening_type = 'new_site')          AS n_openings_new_site,
       count(o.store_id) FILTER (WHERE o.opening_type = 'takeover_of_food_premise') AS n_openings_takeover,
       count(o.store_id) FILTER (WHERE o.opening_type = 'clarel_conversion') AS n_openings_clarel
FROM units u CROSS JOIN (SELECT DISTINCT grp FROM ana.store_group_membership) g
LEFT JOIN o ON o.grp = g.grp AND ST_Intersects(u.geom, o.geom)
GROUP BY 1, 2;
ALTER TABLE ana.store_openings_section ADD PRIMARY KEY (seccio_censal, brand_group);
COMMENT ON TABLE ana.store_openings_section IS 'Store openings 2016-2024 per census section and group, by opening type. Built by sql/ana_store_openings.sql';
