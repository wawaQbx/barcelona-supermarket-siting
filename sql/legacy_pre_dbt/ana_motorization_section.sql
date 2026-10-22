-- =====================================================================================================
-- ana.motorization_section : vehicles per 1000 residents for EVERY census section (the published index covers only 17% of sections).
-- Vehicle counts (raw.trf_parc_vehicles) are complete; population = raw.pop_2026_pad_base.
-- Validation: for the 183 sections where Open Data BCN publishes the index, vehicles / population * 1000 reproduces it
--             (correlation 0.996, mean ratio 1.000, range 0.94-1.06).
-- =====================================================================================================
DROP TABLE IF EXISTS ana.motorization_section CASCADE;
CREATE TABLE ana.motorization_section AS
WITH v AS (
    SELECT seccio_censal,
           sum(nombre_vehicles) FILTER (WHERE tipologia_parc = 'Turismes')        AS cars_n,
           sum(nombre_vehicles) FILTER (WHERE tipologia_parc = 'Motos')           AS motorcycles_n,
           sum(nombre_vehicles) FILTER (WHERE tipologia_parc = 'Ciclomotors')     AS mopeds_n,
           sum(nombre_vehicles) FILTER (WHERE tipologia_parc = 'Furgonetes')      AS vans_n,
           sum(nombre_vehicles) FILTER (WHERE tipologia_parc = 'Camions')         AS trucks_n,
           sum(nombre_vehicles) FILTER (WHERE tipologia_parc = 'Altres vehicles') AS other_vehicles_n,
           sum(nombre_vehicles) AS all_vehicles_n
    FROM raw.trf_parc_vehicles WHERE seccio_censal IS NOT NULL GROUP BY 1)
SELECT p.seccio_censal, l.codi_barri, l.codi_districte, p.habitants_n AS population_n,
       coalesce(v.cars_n, 0) AS cars_n, coalesce(v.motorcycles_n, 0) AS motorcycles_n, coalesce(v.mopeds_n, 0) AS mopeds_n, coalesce(v.vans_n, 0) AS vans_n,
       coalesce(v.trucks_n, 0) AS trucks_n, coalesce(v.other_vehicles_n, 0) AS other_vehicles_n, coalesce(v.all_vehicles_n, 0) AS all_vehicles_n,
       round(1000.0 * coalesce(v.cars_n, 0) / p.habitants_n, 1)        AS cars_per_1000_hab,
       round(1000.0 * coalesce(v.motorcycles_n, 0) / p.habitants_n, 1) AS motorcycles_per_1000_hab,
       round(1000.0 * (coalesce(v.mopeds_n, 0) + coalesce(v.motorcycles_n, 0)) / p.habitants_n, 1) AS two_wheelers_per_1000_hab,
       round(1000.0 * (coalesce(v.vans_n, 0) + coalesce(v.trucks_n, 0)) / p.habitants_n, 1) AS vans_trucks_per_1000_hab,
       round(1000.0 * coalesce(v.all_vehicles_n, 0) / p.habitants_n, 1) AS all_vehicles_per_1000_hab,
       m.index_motoritzacio_per_1000_hab AS cars_index_published_per_1000_hab,
       (1000.0 * coalesce(v.cars_n, 0) / p.habitants_n) > 600 AS fleet_distorted      -- company fleets registered in a tiny residential population (port, Zona Franca)
FROM raw.pop_2026_pad_base p
LEFT JOIN v USING (seccio_censal)
LEFT JOIN raw.adm_census_section_lookup l USING (seccio_censal)
LEFT JOIN raw.trf_motor_2025 m ON m.seccio_censal = p.seccio_censal AND m.tipus_vehicle = 'Turismes';
ALTER TABLE ana.motorization_section ADD PRIMARY KEY (seccio_censal);
COMMENT ON TABLE ana.motorization_section IS 'Vehicles per 1000 residents for all 1068 census sections, recomputed from registered vehicles / population (published index covers 17% only). Built by sql/ana_motorization_section.sql';
