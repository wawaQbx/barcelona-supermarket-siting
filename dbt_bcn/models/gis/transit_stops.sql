-- VISUALISATION LAYER (QGIS + dashboard): TMB stops and stations with their service level. Do NOT use for modelling; models read ana.gtfs_stop_service.
-- One row per bus stop / metro station (platforms rolled up to the station); departures on the representative days of ana.gtfs_service_day.
{{ config(post_hook=primary_key('stop_id'), indexes=[{'columns': ['geom'], 'type': 'gist'}]) }}
SELECT t.stop_id, t.nom, CASE WHEN t.modes ~ 'metro' THEN 'metro' WHEN t.modes ~ 'funicular' THEN 'funicular' ELSE 'bus' END AS stop_kind, t.modes, t.n_routes,
       t.departures_weekday, t.departures_weekday_7_9h, t.departures_saturday, t.departures_sunday,
       t.codi_barri, n.nom_barri, t.codi_districte, t.lon, t.lat, t.geom
FROM {{ ref('gtfs_stop_service') }} t
LEFT JOIN {{ source('ana', 'dim_neighborhood') }} n ON n.codi_barri = t.codi_barri
