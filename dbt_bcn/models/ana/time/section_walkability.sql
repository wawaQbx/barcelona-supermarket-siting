-- Length of pedestrian-priority single-platform streets inside each census section (+25 m), current layer
{{ config(post_hook=primary_key('seccio_censal')) }}
SELECT g.seccio_censal, coalesce(sum(ST_Length(ST_Intersection(p.geom, ST_Buffer(g.geom, 25)))), 0)::numeric(12, 1) AS pedestrian_priority_len_m
FROM {{ source('raw', 'adm_units_polygons') }} g
LEFT JOIN {{ source('raw', 'trf_streets_pedestrian_priority_2023_2026') }} p ON p.any_ IS NULL AND ST_DWithin(p.geom, g.geom, 25)
WHERE g.tipus_ua = 'SEC_CENS' GROUP BY 1
