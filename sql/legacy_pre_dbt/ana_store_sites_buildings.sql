-- =====================================================================================================
-- The BUILDING of each store and of comparable sites (Spanish cadastre INSPIRE buildings, raw.cad_inspire_buildings).
-- ana.site_buildings : one row per site, sites = (a) every city store, (b) every other ACTIVE ground-floor premise of the 2024 census (controls:
--   places where a shop exists but no supermarket; premises within 30 m of a store are excluded).
-- A point is matched to the building footprint that contains it, otherwise the nearest footprint within 15 m (census points often sit on the facade line).
-- Case-control design: compare store buildings with control buildings IN THE SAME BARRI (barri fixed effects in analyze_siting.py).
-- =====================================================================================================
DROP TABLE IF EXISTS ana.site_buildings CASCADE;
CREATE TABLE ana.site_buildings AS
WITH sites AS (
    SELECT 'store_' || p.store_id AS site_id, 'store' AS site_type, p.store_id, p.brand_group, p.format_group, p.first_seen_census_year,
           o.opening_type, p.geom
    FROM ana.store_points p LEFT JOIN ana.store_openings o USING (store_id) WHERE p.in_city
    UNION ALL
    SELECT 'premise_' || c.id_global, 'control_premise', NULL, NULL, NULL, NULL, NULL, c.g
    FROM (SELECT id_global, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) AS g FROM raw.cen_census_2024
          WHERE lon IS NOT NULL AND nom_principal_activitat = 'Actiu' AND nom_activitat <> 'Autoservei / Supermercat') c
    WHERE NOT EXISTS (SELECT 1 FROM ana.store_points s WHERE s.in_city AND ST_DWithin(s.geom, c.g, 30)))
SELECT s.site_id, s.site_type, s.store_id, s.brand_group, s.format_group, s.first_seen_census_year, s.opening_type,
       u.seccio_censal, u.codi_barri, u.codi_districte,
       b.referencia_cadastral, round(b.dist::numeric, 1) AS dist_to_building_m,
       b.year_of_construction, b.current_use, b.building_units_n, b.dwellings_n, b.gross_floor_area_m2, b.footprint_area_m2,
       b.floors_above_ground_max, b.floors_below_ground_max, s.geom
FROM sites s
LEFT JOIN LATERAL (SELECT x.*, ST_Distance(x.geom, s.geom) AS dist FROM raw.cad_inspire_buildings x
                   WHERE ST_DWithin(x.geom, s.geom, 15) ORDER BY x.geom <-> s.geom LIMIT 1) b ON true
LEFT JOIN LATERAL (SELECT seccio_censal, codi_barri, codi_districte FROM raw.adm_units_polygons a
                   WHERE a.tipus_ua = 'SEC_CENS' AND ST_DWithin(a.geom, s.geom, 1) LIMIT 1) u ON true;
CREATE INDEX ON ana.site_buildings (site_type);
COMMENT ON TABLE ana.site_buildings IS 'Building (cadastre INSPIRE) of every city store and of every other active ground-floor premise 2024 (controls): year of construction, use, floors, footprint, units. Built by sql/ana_store_sites_buildings.sql';
