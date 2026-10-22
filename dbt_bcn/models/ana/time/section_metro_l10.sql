-- NATURAL EXPERIMENT. L10 Sud opened Collblanc-Foc on 8 Sep 2018 (stations Foc and Foneria inside the city;
-- Provencana, Ciutat de la Justicia in L'Hospitalet; Zona Franca 2020 and the port stations 2021 serve almost no residents).
-- Treated = census sections within 500 m of Foc or Foneria that had NO metro station within 500 m before (other lines' stations).
-- Openings: pre = first seen 2016 (opened 2014-2016), post = first seen 2019-2024 (opened 2017-2024; the 2019 census straddles the opening).
{{ config(post_hook=primary_key('seccio_censal')) }}
WITH geo AS (SELECT seccio_censal, codi_barri, codi_districte, geom FROM {{ source('raw', 'adm_units_polygons') }} WHERE tipus_ua = 'SEC_CENS'),
newst AS (SELECT geom FROM {{ ref('gtfs_stop_service') }} WHERE location_type = 1 AND nom IN ('Foc', 'Foneria')),
oldst AS (SELECT geom FROM {{ ref('gtfs_stop_service') }} WHERE location_type = 1 AND modes ~ 'metro'
            AND nom NOT IN ('Foc', 'Foneria', 'Provençana', 'Ciutat de la Justícia', 'Zona Franca', 'Port Comercial | La Factoria', 'Ecoparc', 'ZAL | Riu Vell',
                            'Mercabarna', 'Parc Logístic', 'Fira', 'Europa | Fira', 'Can Tries | Gornal', 'Torrassa', 'Amadeu Torner', 'Aeroport T1', 'Aeroport T2',
                            'Les Moreres', 'El Prat Estació', 'Cèntric', 'Parc Nou', 'Mas Blau', 'Can Zam', 'Singuerlín', 'Església Major', 'Fondo')),
sec AS (
    SELECT g.seccio_censal, g.codi_barri, g.codi_districte,
           EXISTS (SELECT 1 FROM newst n WHERE ST_DWithin(g.geom, n.geom, 500)) AS near_new_l10_station,
           EXISTS (SELECT 1 FROM oldst x WHERE ST_DWithin(g.geom, x.geom, 500)) AS had_metro_500m_before,
           (SELECT count(*) FROM {{ ref('store_openings') }} s WHERE s.opening_type <> 'clarel_conversion' AND s.first_seen_census_year = 2016 AND ST_Intersects(g.geom, s.geom)) AS openings_pre_2014_2016_n,
           (SELECT count(*) FROM {{ ref('store_openings') }} s WHERE s.opening_type <> 'clarel_conversion' AND s.first_seen_census_year >= 2019 AND ST_Intersects(g.geom, s.geom)) AS openings_post_2017_2024_n
    FROM geo g)
SELECT sec.*, near_new_l10_station AND NOT had_metro_500m_before AS treated
FROM sec
