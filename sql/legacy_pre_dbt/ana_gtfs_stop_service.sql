-- =====================================================================================================
-- ana.gtfs_stop_service : how much public-transport service each TMB stop / station gets on a typical day
-- Source: raw.gtfs_* (TMB GTFS, valid 2026-06-12 .. 2026-12-31). Re-run after every import (import_all.py calls it).
-- Representative days: weekday Wed 2026-10-14 (avoids the 12-Oct holiday), Saturday 2026-10-17, Sunday 2026-10-18.
-- =====================================================================================================

-- 0) indexes for the big timetable (1.68 M rows)
CREATE INDEX IF NOT EXISTS gtfs_stop_times_trip_idx ON raw.gtfs_stop_times (trip_id, stop_sequence);
CREATE INDEX IF NOT EXISTS gtfs_stop_times_stop_idx ON raw.gtfs_stop_times (stop_id);
CREATE INDEX IF NOT EXISTS gtfs_trips_service_idx ON raw.gtfs_trips (service_id);
ANALYZE raw.gtfs_stop_times; ANALYZE raw.gtfs_trips;

-- 1) services running on each representative day
--    regular weekly services (gtfs_calendar) + services added for that exact date (gtfs_calendar_dates, type 1)
--    - services removed for that date (type 2; none in this feed, kept for correctness)
DROP TABLE IF EXISTS ana.gtfs_service_day;
CREATE TABLE ana.gtfs_service_day AS
WITH dies(dia, tipus_dia) AS (
    VALUES (date '2026-10-14', 'weekday'), (date '2026-10-17', 'saturday'), (date '2026-10-18', 'sunday')
),
regular AS (
    SELECT d.dia, d.tipus_dia, c.service_id
    FROM dies d
    JOIN raw.gtfs_calendar c ON d.dia BETWEEN c.start_date AND c.end_date
    WHERE (extract(isodow FROM d.dia) = 1 AND c.monday = 1) OR (extract(isodow FROM d.dia) = 2 AND c.tuesday = 1)
       OR (extract(isodow FROM d.dia) = 3 AND c.wednesday = 1) OR (extract(isodow FROM d.dia) = 4 AND c.thursday = 1)
       OR (extract(isodow FROM d.dia) = 5 AND c.friday = 1) OR (extract(isodow FROM d.dia) = 6 AND c.saturday = 1)
       OR (extract(isodow FROM d.dia) = 7 AND c.sunday = 1)
),
added AS (
    SELECT d.dia, d.tipus_dia, cd.service_id FROM dies d
    JOIN raw.gtfs_calendar_dates cd ON cd.date = d.dia AND cd.exception_type = 1
),
removed AS (
    SELECT d.dia, cd.service_id FROM dies d
    JOIN raw.gtfs_calendar_dates cd ON cd.date = d.dia AND cd.exception_type = 2
)
SELECT DISTINCT a.dia, a.tipus_dia, a.service_id
FROM (SELECT * FROM regular UNION SELECT * FROM added) a
WHERE NOT EXISTS (SELECT 1 FROM removed r WHERE r.dia = a.dia AND r.service_id = a.service_id);

-- 2) departures of each trip: 1, or for headway-based trips (gtfs_frequencies) the number of runs in the window
DROP TABLE IF EXISTS ana.gtfs_trip_runs;
CREATE TABLE ana.gtfs_trip_runs AS
SELECT t.trip_id, t.route_id, t.service_id,
       coalesce((SELECT sum(ceil((split_part(f.end_time, ':', 1)::int * 3600 + split_part(f.end_time, ':', 2)::int * 60 + split_part(f.end_time, ':', 3)::int
                              - split_part(f.start_time, ':', 1)::int * 3600 - split_part(f.start_time, ':', 2)::int * 60 - split_part(f.start_time, ':', 3)::int)
                             / f.headway_secs::numeric))
                 FROM raw.gtfs_frequencies f WHERE f.trip_id = t.trip_id), 1)::int AS runs
FROM raw.gtfs_trips t;

-- 3) stop visits per day; platforms (location_type 0 with a parent) are rolled up to their station
DROP TABLE IF EXISTS ana.gtfs_stop_service;
CREATE TABLE ana.gtfs_stop_service AS
WITH visits AS (
    SELECT coalesce(s.parent_station, s.stop_id) AS stop_key,
           sd.tipus_dia, tr.route_id, r.route_type, tr.runs,
           split_part(st.departure_time, ':', 1)::int AS hora                 -- GTFS hours can exceed 24 (after midnight)
    FROM raw.gtfs_stop_times st
    JOIN ana.gtfs_trip_runs tr ON tr.trip_id = st.trip_id
    JOIN ana.gtfs_service_day sd ON sd.service_id = tr.service_id
    JOIN raw.gtfs_stops s ON s.stop_id = st.stop_id
    JOIN raw.gtfs_routes r ON r.route_id = tr.route_id
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
)
SELECT s.stop_id, s.stop_name AS nom, s.location_type, a.modes, a.n_routes,
       coalesce(a.departures_weekday, 0)      AS departures_weekday,
       coalesce(a.departures_weekday_7_9h, 0) AS departures_weekday_7_9h,
       coalesce(a.departures_saturday, 0)     AS departures_saturday,
       coalesce(a.departures_sunday, 0)       AS departures_sunday,
       s.stop_lat AS lat, s.stop_lon AS lon,
       st_transform(st_setsrid(st_makepoint(s.stop_lon, s.stop_lat), 4326), 25831)::geometry(Point, 25831) AS geom
FROM raw.gtfs_stops s
JOIN agg a ON a.stop_key = s.stop_id;

-- 4) attach the administrative units (point in barri polygon)
ALTER TABLE ana.gtfs_stop_service ADD COLUMN codi_barri integer, ADD COLUMN codi_districte integer;
UPDATE ana.gtfs_stop_service g
SET codi_barri = b.codi_barri, codi_districte = n.codi_districte
FROM raw.adm_units_polygons b
JOIN ana.dim_neighborhood n ON n.codi_barri = b.codi_barri
WHERE b.elem_descr ILIKE 'L%mit de barri' AND st_within(g.geom, b.geom);

CREATE INDEX ON ana.gtfs_stop_service USING gist (geom);
ALTER TABLE ana.gtfs_stop_service ADD PRIMARY KEY (stop_id);
COMMENT ON TABLE ana.gtfs_stop_service IS 'Departures per TMB stop/station on representative days (weekday 2026-10-14, Sat 10-17, Sun 10-18); platforms rolled up to parent station; headway trips expanded. Built by sql/ana_gtfs_stop_service.sql';
