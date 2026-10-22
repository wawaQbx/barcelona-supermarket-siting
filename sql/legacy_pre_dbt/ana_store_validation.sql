-- =====================================================================================================
-- ana.store_list_validation : is every city store in the store list a real supermarket at that place? (checked against the commercial censuses)
-- evidence, strongest first:
--   brand_in_2024      a premise with the chain's name within 60 m in the 2024 census
--   brand_earlier_only the chain's name within 60 m only in 2014-2022 (closed, renamed or moved since; or opened after the 2024 fieldwork)
--   other_supermarket  no chain name, but a supermarket-class premise (Autoservei / Supermercat) within 30 m in 2024 (franchisee under its own sign)
--   no_evidence        none of the above: suspicious entry (wrong coordinates, other store type, opened after 2024, or not a supermarket)
-- nearest_2024_* = the closest premise of the 2024 census, to judge the no_evidence cases.
-- Address-based checks and coordinate corrections: check_store_addresses.py. Runs after ana_store_counts.sql (Clarel drugstores already excluded).
-- =====================================================================================================
DROP TABLE IF EXISTS ana.store_list_validation CASCADE;
DROP TABLE IF EXISTS tmp_census_points;
CREATE TEMP TABLE tmp_census_points AS
SELECT 2014 AS y, nom_local, NULL::text AS nom_activitat, ST_Transform(ST_SetSRID(ST_MakePoint(x_ed50, y_ed50), 23031), 25831) AS g FROM raw.cen_census_2014 WHERE x_ed50 IS NOT NULL
UNION ALL SELECT 2016, nom_local, nom_activitat, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) FROM raw.cen_census_2016 WHERE lon IS NOT NULL
UNION ALL SELECT 2019, nom_local, nom_activitat, geom FROM raw.cen_census_2019
UNION ALL SELECT 2022, nom_local, nom_activitat, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) FROM raw.cen_census_2022 WHERE lon IS NOT NULL
UNION ALL SELECT 2024, nom_local, nom_activitat, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) FROM raw.cen_census_2024 WHERE lon IS NOT NULL;
CREATE INDEX ON tmp_census_points USING gist (g);
ANALYZE tmp_census_points;

CREATE TABLE ana.store_list_validation AS
WITH rx AS (SELECT * FROM (VALUES
        ('Condis', 'condis'), ('Dia', '^(dia\M|dia %|dia market|supermercados dia|la plaza de dia)'), ('Caprabo', 'caprabo'), ('Mercadona', 'mercadona'),
        ('Consum_Charter', 'charter|\mconsum\M'), ('BonPreu_Esclat', 'bon ?preu|esclat'), ('Lidl', '\mlidl'), ('Aldi', '\maldi\M'),
        ('Carrefour', 'carrefour'), ('Alcampo', 'alcampo|simply|sabeco')) v(brand_group, pattern)),
s AS (SELECT p.store_id, p.ensenya, p.brand_group, p.store_type, p.point_source, p.coord_corrected, p.geom, r.pattern
      FROM ana.store_points p JOIN rx r USING (brand_group) WHERE p.in_city),
near AS (SELECT s.store_id, c.y, c.nom_local, c.nom_activitat, ST_Distance(c.g, s.geom) AS d, (c.nom_local ~* s.pattern) AS is_brand
         FROM s JOIN tmp_census_points c ON ST_DWithin(c.g, s.geom, 60))
SELECT s.store_id, s.ensenya, s.brand_group, s.store_type, s.point_source, s.coord_corrected,
       (SELECT min(d) FROM near n WHERE n.store_id = s.store_id AND n.y = 2024 AND n.is_brand)::numeric(6, 1) AS dist_brand_2024_m,
       (SELECT string_agg(DISTINCT n.y::text, ',') FROM near n WHERE n.store_id = s.store_id AND n.is_brand) AS brand_seen_in_census,
       (SELECT min(d) FROM near n WHERE n.store_id = s.store_id AND n.y = 2024 AND n.nom_activitat = 'Autoservei / Supermercat' AND n.d <= 30)::numeric(6, 1) AS dist_any_supermarket_2024_m,
       nn.nom_local AS nearest_2024_name, nn.nom_activitat AS nearest_2024_activity, nn.d::numeric(6, 1) AS nearest_2024_m
FROM s
LEFT JOIN LATERAL (SELECT c.nom_local, c.nom_activitat, ST_Distance(c.g, s.geom) AS d FROM tmp_census_points c WHERE c.y = 2024 ORDER BY c.g <-> s.geom LIMIT 1) nn ON true;
ALTER TABLE ana.store_list_validation ADD COLUMN evidence text;
UPDATE ana.store_list_validation SET evidence = CASE
    WHEN dist_brand_2024_m IS NOT NULL THEN 'brand_in_2024'
    WHEN brand_seen_in_census IS NOT NULL THEN 'brand_earlier_only'
    WHEN dist_any_supermarket_2024_m IS NOT NULL THEN 'other_supermarket'
    ELSE 'no_evidence' END;
ALTER TABLE ana.store_list_validation ADD PRIMARY KEY (store_id);
COMMENT ON TABLE ana.store_list_validation IS 'Validation of every city store of the store list against the commercial censuses (brand name within 60 m, other supermarket premise within 30 m, nearest 2024 premise). Built by sql/ana_store_validation.sql';
