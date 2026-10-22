-- Services running on each representative day (TMB GTFS, valid 2026-06-12 .. 2026-12-31):
-- weekday Wed 2026-10-14 (avoids the 12-Oct holiday), Saturday 2026-10-17, Sunday 2026-10-18.
-- regular weekly services (gtfs_calendar) + services added for that exact date (gtfs_calendar_dates, type 1)
-- - services removed for that date (type 2; none in this feed, kept for correctness)
WITH dies(dia, tipus_dia) AS (
    VALUES (date '2026-10-14', 'weekday'), (date '2026-10-17', 'saturday'), (date '2026-10-18', 'sunday')
),
regular AS (
    SELECT d.dia, d.tipus_dia, c.service_id
    FROM dies d
    JOIN {{ source('raw', 'gtfs_calendar') }} c ON d.dia BETWEEN c.start_date AND c.end_date
    WHERE (extract(isodow FROM d.dia) = 1 AND c.monday = 1) OR (extract(isodow FROM d.dia) = 2 AND c.tuesday = 1)
       OR (extract(isodow FROM d.dia) = 3 AND c.wednesday = 1) OR (extract(isodow FROM d.dia) = 4 AND c.thursday = 1)
       OR (extract(isodow FROM d.dia) = 5 AND c.friday = 1) OR (extract(isodow FROM d.dia) = 6 AND c.saturday = 1)
       OR (extract(isodow FROM d.dia) = 7 AND c.sunday = 1)
),
added AS (
    SELECT d.dia, d.tipus_dia, cd.service_id FROM dies d
    JOIN {{ source('raw', 'gtfs_calendar_dates') }} cd ON cd.date = d.dia AND cd.exception_type = 1
),
removed AS (
    SELECT d.dia, cd.service_id FROM dies d
    JOIN {{ source('raw', 'gtfs_calendar_dates') }} cd ON cd.date = d.dia AND cd.exception_type = 2
)
SELECT DISTINCT a.dia, a.tipus_dia, a.service_id
FROM (SELECT * FROM regular UNION SELECT * FROM added) a
WHERE NOT EXISTS (SELECT 1 FROM removed r WHERE r.dia = a.dia AND r.service_id = a.service_id)
