-- VISUALISATION LAYER (QGIS + dashboard): traffic counting stations 2025 with their mean daily traffic (IMD). Do NOT use for modelling.
-- imd = mean vehicles per day over the months of 2025, by type of day as published (laborables = working days, dissabte = Saturday, diumenge = Sunday).
{{ config(post_hook=primary_key('id_aforament'), indexes=[{'columns': ['geom'], 'type': 'gist'}]) }}
SELECT d.id_aforament, d.desc_aforament, d.desc_tipus_aforament, d.num_carrils AS lanes_n, coalesce(d.codi_barri, b.codi_barri) AS codi_barri, n.nom_barri,
       round(avg(x.imd_vehicles_per_day) FILTER (WHERE x.desc_tipus_dia = 'laborables')::numeric, 0) AS imd_working_day_vehicles_per_day,
       round(avg(x.imd_vehicles_per_day) FILTER (WHERE x.desc_tipus_dia = 'dissabte')::numeric, 0)   AS imd_saturday_vehicles_per_day,
       round(avg(x.imd_vehicles_per_day) FILTER (WHERE x.desc_tipus_dia = 'diumenge')::numeric, 0)   AS imd_sunday_vehicles_per_day,
       d.lon, d.lat, ST_Transform(ST_SetSRID(ST_MakePoint(d.lon, d.lat), 4326), 25831)::geometry(Point, 25831) AS geom
FROM {{ source('raw', 'trf_aforament_desc_2025') }} d
JOIN {{ source('raw', 'trf_aforament_detall_2025') }} x USING (id_aforament)
-- 62 stations have no barri code in the source: taken from the barri polygon that contains the point (NULL outside the city)
LEFT JOIN LATERAL (SELECT u.codi_barri FROM {{ source('raw', 'adm_units_polygons') }} u WHERE u.tipus_ua = 'BARRI'
                   AND ST_Intersects(u.geom, ST_Transform(ST_SetSRID(ST_MakePoint(d.lon, d.lat), 4326), 25831)) LIMIT 1) b ON true
LEFT JOIN {{ source('ana', 'dim_neighborhood') }} n ON n.codi_barri = coalesce(d.codi_barri, b.codi_barri)
WHERE d.lon IS NOT NULL
GROUP BY d.id_aforament, d.desc_aforament, d.desc_tipus_aforament, d.num_carrils, coalesce(d.codi_barri, b.codi_barri), n.nom_barri, d.lon, d.lat
