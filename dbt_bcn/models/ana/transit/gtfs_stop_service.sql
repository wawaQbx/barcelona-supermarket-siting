-- How much public-transport service each TMB stop / station gets on the representative days (gtfs_service_day).
-- Platforms (location_type 0 with a parent) are rolled up to their station; headway trips expanded (gtfs_trip_runs).
-- pre_hook: indexes on the big raw timetable (1.68 M rows) + fresh statistics, so the joins below are fast.
{{ config(
    pre_hook=["CREATE INDEX IF NOT EXISTS gtfs_stop_times_trip_idx ON {{ source('raw', 'gtfs_stop_times') }} (trip_id, stop_sequence)",
              "CREATE INDEX IF NOT EXISTS gtfs_stop_times_stop_idx ON {{ source('raw', 'gtfs_stop_times') }} (stop_id)",
              "CREATE INDEX IF NOT EXISTS gtfs_trips_service_idx ON {{ source('raw', 'gtfs_trips') }} (service_id)",
              "ANALYZE {{ source('raw', 'gtfs_stop_times') }}", "ANALYZE {{ source('raw', 'gtfs_trips') }}"],
    indexes=[{'columns': ['geom'], 'type': 'gist'}],
    post_hook=primary_key('stop_id')) }}
WITH visits AS (
    SELECT coalesce(s.parent_station, s.stop_id) AS stop_key,
           sd.tipus_dia, tr.route_id, r.route_type, tr.runs,
           split_part(st.departure_time, ':', 1)::int AS hora                 -- GTFS hours can exceed 24 (after midnight)
    FROM {{ source('raw', 'gtfs_stop_times') }} st
    JOIN {{ ref('gtfs_trip_runs') }} tr ON tr.trip_id = st.trip_id
    JOIN {{ ref('gtfs_service_day') }} sd ON sd.service_id = tr.service_id
    JOIN {{ source('raw', 'gtfs_stops') }} s ON s.stop_id = st.stop_id
    JOIN {{ source('raw', 'gtfs_routes') }} r ON r.route_id = tr.route_id
),
agg AS (
    SELECT stop_key,
           sum(runs) FILTER (WHERE tipus_dia = 'weekday')                           AS departures_weekday,
           sum(runs) FILTER (WHERE tipus_dia = 'weekday' AND hora BETWEEN 7 AND 8)  AS departures_weekday_7_9h,
           sum(runs) FILTER (WHERE tipus_dia = 'saturday')                          AS departures_saturday,
           sum(runs) FILTER (WHERE tipus_dia = 'sunday')                            AS departures_sunday,
           count(DISTINCT route_id)                                                  AS n_routes,
           string_agg(DISTINCT CASE route_type WHEN 1 THEN 'metro' WHEN 3 THEN 'bus' WHEN 7 THEN 'funicular' ELSE route_type::text END, ',') AS modes
    FROM visits GROUP BY stop_key
),
stops AS (
    SELECT s.stop_id, s.stop_name AS nom, s.location_type, a.modes, a.n_routes,
           coalesce(a.departures_weekday, 0)      AS departures_weekday,
           coalesce(a.departures_weekday_7_9h, 0) AS departures_weekday_7_9h,
           coalesce(a.departures_saturday, 0)     AS departures_saturday,
           coalesce(a.departures_sunday, 0)       AS departures_sunday,
           s.stop_lat AS lat, s.stop_lon AS lon,
           st_transform(st_setsrid(st_makepoint(s.stop_lon, s.stop_lat), 4326), 25831)::geometry(Point, 25831) AS geom
    FROM {{ source('raw', 'gtfs_stops') }} s
    JOIN agg a ON a.stop_key = s.stop_id
)
-- administrative units: the barri polygon that contains the stop (NULL outside the city)
SELECT st.*, u.codi_barri::integer AS codi_barri, u.codi_districte::integer AS codi_districte
FROM stops st
LEFT JOIN LATERAL (SELECT b.codi_barri, n.codi_districte
                   FROM {{ source('raw', 'adm_units_polygons') }} b
                   JOIN {{ source('ana', 'dim_neighborhood') }} n ON n.codi_barri = b.codi_barri
                   WHERE b.elem_descr ILIKE 'L%mit de barri' AND st_within(st.geom, b.geom) LIMIT 1) u ON true
