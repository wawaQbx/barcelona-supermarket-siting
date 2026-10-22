-- =====================================================================================================
-- ana.store_site_premises_panel : BEFORE / AFTER design (event study) around each city store.
-- For every dated city store and every census edition (2014, 2016, 2019, 2022, 2024): ACTIVE ground-floor premises within 150 m,
-- excluding the store's own premise (anything within 20 m).
-- Active = 2014: sector <> 'LOCAL BUIT'; 2016-2024: nom_principal_activitat = 'Actiu'. Vacancy is not used: its categories change between editions
-- (2016 / 2019 have 11-13k 'Sense informació' premises). Level differences between editions are absorbed by edition fixed effects in the model.
-- =====================================================================================================
DROP TABLE IF EXISTS ana.store_site_premises_panel CASCADE;
CREATE TEMP TABLE tmp_active_premises AS
WITH act AS (
    SELECT 2014 AS census_year, ST_Transform(ST_SetSRID(ST_MakePoint(x_ed50, y_ed50), 23031), 25831) AS g FROM raw.cen_census_2014 WHERE x_ed50 IS NOT NULL AND nom_sector_activitat <> 'LOCAL BUIT'
    UNION ALL SELECT 2016, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) FROM raw.cen_census_2016 WHERE lon IS NOT NULL AND nom_principal_activitat = 'Actiu'
    UNION ALL SELECT 2019, geom FROM raw.cen_census_2019 WHERE nom_principal_activitat = 'Actiu'
    UNION ALL SELECT 2022, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) FROM raw.cen_census_2022 WHERE lon IS NOT NULL AND nom_principal_activitat = 'Actiu'
    UNION ALL SELECT 2024, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) FROM raw.cen_census_2024 WHERE lon IS NOT NULL AND nom_principal_activitat = 'Actiu')
SELECT * FROM act;
CREATE INDEX ON tmp_active_premises USING gist (g);
CREATE TABLE ana.store_site_premises_panel AS
WITH s AS (SELECT p.store_id, p.brand_group, p.first_seen_census_year, coalesce(o.opening_type, 'legacy_2014') AS opening_type, p.geom
      FROM ana.store_points p LEFT JOIN ana.store_openings o USING (store_id)
      WHERE p.in_city AND p.first_seen_census_year IS NOT NULL),
y AS (SELECT unnest(ARRAY[2014, 2016, 2019, 2022, 2024]) AS census_year)
SELECT s.store_id, s.brand_group, s.first_seen_census_year, s.opening_type, y.census_year,
       (SELECT count(*) FROM tmp_active_premises a WHERE a.census_year = y.census_year AND ST_DWithin(a.g, s.geom, 150) AND NOT ST_DWithin(a.g, s.geom, 20)) AS active_premises_150m_n
FROM s CROSS JOIN y;
CREATE INDEX ON ana.store_site_premises_panel (store_id);
COMMENT ON TABLE ana.store_site_premises_panel IS 'Event-study panel: active ground-floor premises within 150 m (own premise excluded) around each dated city store in each census edition. Built by sql/ana_time_site_panel.sql';

-- =====================================================================================================
-- ana.section_metro_l10 : NATURAL EXPERIMENT. L10 Sud opened Collblanc-Foc on 8 Sep 2018 (stations Foc and Foneria inside the city;
-- Provencana, Ciutat de la Justicia in L'Hospitalet; Zona Franca 2020 and the port stations 2021 serve almost no residents).
-- Treated = census sections within 500 m of Foc or Foneria that had NO metro station within 500 m before (other lines' stations).
-- Openings: pre = first seen 2016 (opened 2014-2016), post = first seen 2019-2024 (opened 2017-2024; the 2019 census straddles the opening).
-- =====================================================================================================
DROP TABLE IF EXISTS ana.section_metro_l10 CASCADE;
CREATE TABLE ana.section_metro_l10 AS
WITH geo AS (SELECT seccio_censal, codi_barri, codi_districte, geom FROM raw.adm_units_polygons WHERE tipus_ua = 'SEC_CENS'),
newst AS (SELECT geom FROM ana.gtfs_stop_service WHERE location_type = 1 AND nom IN ('Foc', 'Foneria')),
oldst AS (SELECT geom FROM ana.gtfs_stop_service WHERE location_type = 1 AND modes ~ 'metro'
            AND nom NOT IN ('Foc', 'Foneria', 'Provençana', 'Ciutat de la Justícia', 'Zona Franca', 'Port Comercial | La Factoria', 'Ecoparc', 'ZAL | Riu Vell',
                            'Mercabarna', 'Parc Logístic', 'Fira', 'Europa | Fira', 'Can Tries | Gornal', 'Torrassa', 'Amadeu Torner', 'Aeroport T1', 'Aeroport T2',
                            'Les Moreres', 'El Prat Estació', 'Cèntric', 'Parc Nou', 'Mas Blau', 'Can Zam', 'Singuerlín', 'Església Major', 'Fondo')),
o AS (SELECT seccio_censal, sum(n_openings_2016_2024 - n_openings_clarel) AS n_open,
             0 AS dummy FROM ana.store_openings_section WHERE brand_group = 'ALL' GROUP BY 1)
SELECT g.seccio_censal, g.codi_barri, g.codi_districte,
       EXISTS (SELECT 1 FROM newst n WHERE ST_DWithin(g.geom, n.geom, 500)) AS near_new_l10_station,
       EXISTS (SELECT 1 FROM oldst x WHERE ST_DWithin(g.geom, x.geom, 500)) AS had_metro_500m_before,
       (SELECT count(*) FROM ana.store_openings s WHERE s.opening_type <> 'clarel_conversion' AND s.first_seen_census_year = 2016 AND ST_Intersects(g.geom, s.geom)) AS openings_pre_2014_2016_n,
       (SELECT count(*) FROM ana.store_openings s WHERE s.opening_type <> 'clarel_conversion' AND s.first_seen_census_year >= 2019 AND ST_Intersects(g.geom, s.geom)) AS openings_post_2017_2024_n
FROM geo g;
ALTER TABLE ana.section_metro_l10 ADD COLUMN treated boolean;
UPDATE ana.section_metro_l10 SET treated = near_new_l10_station AND NOT had_metro_500m_before;
ALTER TABLE ana.section_metro_l10 ADD PRIMARY KEY (seccio_censal);
COMMENT ON TABLE ana.section_metro_l10 IS 'Natural experiment: sections that gained metro access with L10 Sud (Foc / Foneria, Sep 2018) vs. the rest; supermarket openings before / after. Built by sql/ana_time_site_panel.sql';
