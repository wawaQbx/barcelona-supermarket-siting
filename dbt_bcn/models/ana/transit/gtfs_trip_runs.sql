-- departures of each trip: 1, or for headway-based trips (gtfs_frequencies) the number of runs in the window
{{ config(post_hook=primary_key('trip_id')) }}
SELECT t.trip_id, t.route_id, t.service_id,
       coalesce((SELECT sum(ceil((split_part(f.end_time, ':', 1)::int * 3600 + split_part(f.end_time, ':', 2)::int * 60 + split_part(f.end_time, ':', 3)::int
                              - split_part(f.start_time, ':', 1)::int * 3600 - split_part(f.start_time, ':', 2)::int * 60 - split_part(f.start_time, ':', 3)::int)
                             / f.headway_secs::numeric))
                 FROM {{ source('raw', 'gtfs_frequencies') }} f WHERE f.trip_id = t.trip_id), 1)::int AS runs
FROM {{ source('raw', 'gtfs_trips') }} t
