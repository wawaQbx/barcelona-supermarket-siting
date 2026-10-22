-- =====================================================================================================
-- v6 dynamics: (1) which shops change around a new supermarket (substitution), (2) supermarket closures, (3) pacified streets natural experiment,
-- (4) pedestrian-priority streets per section. Runs after ana_time_site_panel.sql (needs ana.store_points / store_openings / site_buildings).
-- =====================================================================================================

-- ---------- (1) active premises by TYPE around every dated store site, every census edition ----------
-- types comparable across editions: daily_food_other = "Quotidia alimentari" without supermarkets; other_retail = the other retail groups;
-- restaurants_bars = "Restaurants, bars i hotels" (2016+ only: 2014 put restaurants inside SERVEIS); services_other = the rest of the active premises.
DROP TABLE IF EXISTS tmp_premises_typed;
CREATE TEMP TABLE tmp_premises_typed AS
SELECT 2014 AS census_year, ST_Transform(ST_SetSRID(ST_MakePoint(x_ed50, y_ed50), 23031), 25831) AS g,
       CASE WHEN nom_grup_activitat = 'QUOTIDIÀ ALIMENTARI' THEN 'daily_food_other'
            WHEN nom_grup_activitat IN ('EQUIPAMENT PERSONAL', 'PARAMENT DE LA LLAR', 'OCI I CULTURA', 'QUOTIDIÀ NO ALIMENTARI', 'AUTOMOCIÓ') THEN 'other_retail'
            ELSE 'services_other' END AS ptype
FROM raw.cen_census_2014 WHERE x_ed50 IS NOT NULL AND nom_sector_activitat <> 'LOCAL BUIT'
UNION ALL
SELECT y, g, CASE WHEN grp = 'Quotidià alimentari' AND act IS DISTINCT FROM 'Autoservei / Supermercat' THEN 'daily_food_other'
                  WHEN grp = 'Quotidià alimentari' THEN 'supermarket_class'
                  WHEN grp IN ('Equipament personal', 'Parament de la llar', 'Oci i cultura', 'Quotidià no alimentari', 'Automoció') THEN 'other_retail'
                  WHEN grp LIKE 'Restaurants%' THEN 'restaurants_bars' ELSE 'services_other' END
FROM (SELECT 2016 AS y, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) AS g, nom_grup_activitat AS grp, nom_activitat AS act FROM raw.cen_census_2016 WHERE lon IS NOT NULL AND nom_principal_activitat = 'Actiu'
      UNION ALL SELECT 2019, geom, nom_grup_activitat, nom_activitat FROM raw.cen_census_2019 WHERE nom_principal_activitat = 'Actiu'
      UNION ALL SELECT 2022, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831), nom_grup_activitat, nom_activitat FROM raw.cen_census_2022 WHERE lon IS NOT NULL AND nom_principal_activitat = 'Actiu'
      UNION ALL SELECT 2024, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831), nom_grup_activitat, nom_activitat FROM raw.cen_census_2024 WHERE lon IS NOT NULL AND nom_principal_activitat = 'Actiu') x;
CREATE INDEX ON tmp_premises_typed USING gist (g);

DROP TABLE IF EXISTS ana.store_site_premises_by_type CASCADE;
CREATE TABLE ana.store_site_premises_by_type AS
WITH s AS (SELECT p.store_id, p.brand_group, p.first_seen_census_year, coalesce(o.opening_type, 'legacy_2014') AS opening_type, p.geom
           FROM ana.store_points p LEFT JOIN ana.store_openings o USING (store_id) WHERE p.in_city AND p.first_seen_census_year IS NOT NULL)
SELECT s.store_id, s.brand_group, s.first_seen_census_year, s.opening_type, t.census_year, t.ptype, count(t.*) AS premises_150m_n
FROM s JOIN tmp_premises_typed t ON ST_DWithin(t.g, s.geom, 150) AND NOT ST_DWithin(t.g, s.geom, 20)
GROUP BY 1, 2, 3, 4, 5, 6;
COMMENT ON TABLE ana.store_site_premises_by_type IS 'Event-study panel by premise type (daily food, other retail, restaurants 2016+, services) within 150 m of each dated city store. Built by sql/ana_time_dynamics.sql';

-- ---------- (2) supermarket closures: supermarket-class premises of the 2019 and 2022 censuses that are gone in the next edition ----------
DROP TABLE IF EXISTS ana.supermarket_premises_closures CASCADE;
CREATE TABLE ana.supermarket_premises_closures AS
WITH sup AS (
    SELECT 2019 AS census_year, 2022 AS next_year, nom_local, geom AS g FROM raw.cen_census_2019 WHERE nom_activitat = 'Autoservei / Supermercat' AND nom_principal_activitat = 'Actiu'
    UNION ALL SELECT 2022, 2024, nom_local, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) FROM raw.cen_census_2022
      WHERE nom_activitat = 'Autoservei / Supermercat' AND nom_principal_activitat = 'Actiu' AND lon IS NOT NULL),
nxt AS (SELECT census_year, g FROM tmp_premises_typed WHERE ptype = 'supermarket_class')
SELECT (row_number() OVER ())::text AS premise_id, s.census_year, s.next_year, s.nom_local,
       CASE WHEN s.nom_local ~* 'mercadona' THEN 'Mercadona' WHEN s.nom_local ~* '\mlidl' THEN 'Lidl' WHEN s.nom_local ~* '\maldi\M' THEN 'Aldi'
            WHEN s.nom_local ~* '^(dia\M|dia %|dia market|supermercados dia)' THEN 'Dia' WHEN s.nom_local ~* 'caprabo' THEN 'Caprabo' WHEN s.nom_local ~* 'condis' THEN 'Condis'
            WHEN s.nom_local ~* 'charter|\mconsum\M' THEN 'Consum_Charter' WHEN s.nom_local ~* 'bon ?preu|esclat' THEN 'BonPreu_Esclat'
            WHEN s.nom_local ~* 'carrefour' THEN 'Carrefour' WHEN s.nom_local ~* 'alcampo|simply|sabeco' THEN 'Alcampo'
            ELSE 'independent_or_other' END AS brand_group,
       NOT EXISTS (SELECT 1 FROM nxt WHERE nxt.census_year = s.next_year AND ST_DWithin(nxt.g, s.g, 20)) AS closed_by_next_census,
       u.seccio_censal, u.codi_barri,
       (SELECT count(*) FROM sup o WHERE o.census_year = s.census_year AND ST_DWithin(o.g, s.g, 300) AND NOT ST_DWithin(o.g, s.g, 20)) AS supermarkets_300m_n,
       (SELECT count(*) FROM ana.store_points p WHERE p.first_seen_census_year = s.next_year AND ST_DWithin(p.geom, s.g, 300)) AS chain_openings_300m_next_n,
       b.year_of_construction, b.footprint_area_m2, s.g AS geom
FROM sup s
LEFT JOIN LATERAL (SELECT seccio_censal, codi_barri FROM raw.adm_units_polygons a WHERE a.tipus_ua = 'SEC_CENS' AND ST_DWithin(a.geom, s.g, 1) LIMIT 1) u ON true
LEFT JOIN LATERAL (SELECT year_of_construction, footprint_area_m2 FROM raw.cad_inspire_buildings x WHERE ST_DWithin(x.geom, s.g, 15) ORDER BY x.geom <-> s.g LIMIT 1) b ON true;
COMMENT ON TABLE ana.supermarket_premises_closures IS 'Supermarket-class premises of the 2019 and 2022 censuses, chain from the sign name, closed = no supermarket premise within 20 m in the next census. Built by sql/ana_time_dynamics.sql';

-- ---------- (3) pacified streets (Eixample "eixos verds", from 2020 Q3) natural experiment ----------
DROP TABLE IF EXISTS ana.section_pacified_streets CASCADE;
CREATE TABLE ana.section_pacified_streets AS
WITH geo AS (SELECT seccio_censal, codi_barri, codi_districte, geom FROM raw.adm_units_polygons WHERE tipus_ua = 'SEC_CENS'),
pac AS (SELECT ST_Union(geom) AS g FROM raw.trf_streets_pacified_2020_2022 WHERE any_ = 2020 AND trimestre = 3)
SELECT g.seccio_censal, g.codi_barri, g.codi_districte, ST_DWithin(g.geom, pac.g, 30) AS treated_pacified_street,
       (SELECT count(*) FROM tmp_premises_typed t WHERE t.census_year = 2016 AND ST_Intersects(g.geom, t.g)) AS active_premises_2016_n,
       (SELECT count(*) FROM tmp_premises_typed t WHERE t.census_year = 2019 AND ST_Intersects(g.geom, t.g)) AS active_premises_2019_n,
       (SELECT count(*) FROM tmp_premises_typed t WHERE t.census_year = 2022 AND ST_Intersects(g.geom, t.g)) AS active_premises_2022_n,
       (SELECT count(*) FROM tmp_premises_typed t WHERE t.census_year = 2024 AND ST_Intersects(g.geom, t.g)) AS active_premises_2024_n,
       (SELECT count(*) FROM tmp_premises_typed t WHERE t.census_year = 2019 AND t.ptype = 'restaurants_bars' AND ST_Intersects(g.geom, t.g)) AS restaurants_2019_n,
       (SELECT count(*) FROM tmp_premises_typed t WHERE t.census_year = 2024 AND t.ptype = 'restaurants_bars' AND ST_Intersects(g.geom, t.g)) AS restaurants_2024_n,
       (SELECT count(*) FROM ana.store_openings s WHERE s.opening_type <> 'clarel_conversion' AND s.first_seen_census_year IN (2016, 2019) AND ST_Intersects(g.geom, s.geom)) AS openings_2014_2019_n,
       (SELECT count(*) FROM ana.store_openings s WHERE s.opening_type <> 'clarel_conversion' AND s.first_seen_census_year IN (2022, 2024) AND ST_Intersects(g.geom, s.geom)) AS openings_2020_2024_n
FROM geo g, pac;
ALTER TABLE ana.section_pacified_streets ADD PRIMARY KEY (seccio_censal);
COMMENT ON TABLE ana.section_pacified_streets IS 'Natural experiment: sections within 30 m of the pacified streets of 2020 Q3 vs the rest; active premises 2016-2024 and supermarket openings before / after. Built by sql/ana_time_dynamics.sql';

-- ---------- (4) pedestrian-priority streets per section (current layer) ----------
DROP TABLE IF EXISTS ana.section_walkability CASCADE;
CREATE TABLE ana.section_walkability AS
SELECT g.seccio_censal, coalesce(sum(ST_Length(ST_Intersection(p.geom, ST_Buffer(g.geom, 25)))), 0)::numeric(12, 1) AS pedestrian_priority_len_m
FROM raw.adm_units_polygons g LEFT JOIN raw.trf_streets_pedestrian_priority_2023_2026 p ON p.any_ IS NULL AND ST_DWithin(p.geom, g.geom, 25)
WHERE g.tipus_ua = 'SEC_CENS' GROUP BY 1;
ALTER TABLE ana.section_walkability ADD PRIMARY KEY (seccio_censal);
COMMENT ON TABLE ana.section_walkability IS 'Length of pedestrian-priority single-platform streets inside each section (+25 m). Built by sql/ana_time_dynamics.sql';
