-- Natural experiment: pacified streets (Eixample "eixos verds", from 2020 Q3). Sections within 30 m of a pacified street vs the rest;
-- active premises 2016-2024 and supermarket openings before / after.
{{ config(post_hook=primary_key('seccio_censal')) }}
WITH geo AS (SELECT seccio_censal, codi_barri, codi_districte, geom FROM {{ source('raw', 'adm_units_polygons') }} WHERE tipus_ua = 'SEC_CENS'),
pac AS (SELECT ST_Union(geom) AS g FROM {{ source('raw', 'trf_streets_pacified_2020_2022') }} WHERE any_ = 2020 AND trimestre = 3),
t AS NOT MATERIALIZED (SELECT * FROM {{ ref('int_active_premises_typed') }})   -- NOT MATERIALIZED: keep the spatial index usable
SELECT g.seccio_censal, g.codi_barri, g.codi_districte, ST_DWithin(g.geom, pac.g, 30) AS treated_pacified_street,
       (SELECT count(*) FROM t WHERE t.census_year = 2016 AND ST_Intersects(g.geom, t.g)) AS active_premises_2016_n,
       (SELECT count(*) FROM t WHERE t.census_year = 2019 AND ST_Intersects(g.geom, t.g)) AS active_premises_2019_n,
       (SELECT count(*) FROM t WHERE t.census_year = 2022 AND ST_Intersects(g.geom, t.g)) AS active_premises_2022_n,
       (SELECT count(*) FROM t WHERE t.census_year = 2024 AND ST_Intersects(g.geom, t.g)) AS active_premises_2024_n,
       (SELECT count(*) FROM t WHERE t.census_year = 2019 AND t.ptype = 'restaurants_bars' AND ST_Intersects(g.geom, t.g)) AS restaurants_2019_n,
       (SELECT count(*) FROM t WHERE t.census_year = 2024 AND t.ptype = 'restaurants_bars' AND ST_Intersects(g.geom, t.g)) AS restaurants_2024_n,
       (SELECT count(*) FROM {{ ref('store_openings') }} s WHERE s.opening_type <> 'clarel_conversion' AND s.first_seen_census_year IN (2016, 2019) AND ST_Intersects(g.geom, s.geom)) AS openings_2014_2019_n,
       (SELECT count(*) FROM {{ ref('store_openings') }} s WHERE s.opening_type <> 'clarel_conversion' AND s.first_seen_census_year IN (2022, 2024) AND ST_Intersects(g.geom, s.geom)) AS openings_2020_2024_n
FROM geo g, pac
