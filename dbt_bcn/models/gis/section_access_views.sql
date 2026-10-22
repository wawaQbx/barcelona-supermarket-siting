-- VISUALISATION LAYER (dashboard page 04): the page-04 map as a switchable map (button slicer on view_name, Shape map Legend = class_label).
-- One row per census section x view. Views: walking minutes at older pace (70% of adult speed, slope-aware) to fresh food and to a chain
-- supermarket - same 5 / 10 / 15 min classes, 10 min = the food-desert threshold - and the net climb home from the nearest chain supermarket
-- (home elevation minus store elevation, median of the section's homes; negative = downhill home). The same 4-step red ramp is used in every view
-- (class 1 = easy, 4 = hard). dwellings_n / population_n let a 100% bar of homes by class summarise the map for the selected view.
-- Built after build_food_access.py: tag after_python.
{{ config(post_hook=primary_key('seccio_censal, view_order')) }}
WITH s AS (
    SELECT seccio_censal, seccio_key, nom_barri, nom_districte, dwellings_n, population_n,
           median_minutes_fresh_older, median_minutes_chain_older, median_climb_home_from_supermarket_m
    FROM {{ ref('section_indicators') }}),
v AS (
    SELECT seccio_censal, 1 AS view_order, 'Walk to fresh food (min)' AS view_name, median_minutes_fresh_older AS value,
           CASE WHEN median_minutes_fresh_older < 5 THEN 1 WHEN median_minutes_fresh_older < 10 THEN 2
                WHEN median_minutes_fresh_older < 15 THEN 3 ELSE 4 END AS class_order FROM s
    UNION ALL
    SELECT seccio_censal, 2, 'Walk to a chain supermarket (min)', median_minutes_chain_older,
           CASE WHEN median_minutes_chain_older < 5 THEN 1 WHEN median_minutes_chain_older < 10 THEN 2
                WHEN median_minutes_chain_older < 15 THEN 3 ELSE 4 END FROM s
    UNION ALL
    SELECT seccio_censal, 3, 'Climb home from a supermarket (m)', median_climb_home_from_supermarket_m,
           CASE WHEN median_climb_home_from_supermarket_m < 5 THEN 1 WHEN median_climb_home_from_supermarket_m < 10 THEN 2
                WHEN median_climb_home_from_supermarket_m < 20 THEN 3 ELSE 4 END FROM s)
SELECT v.seccio_censal, s.seccio_key, s.nom_barri, s.nom_districte, v.view_order, v.view_name,
       round(v.value::numeric, 1) AS value, v.class_order,
       CASE WHEN v.view_order < 3 THEN (ARRAY['Under 5 min', '5-10 min', '10-15 min', '15 min or more'])[v.class_order]
            ELSE (ARRAY['Under 5 m', '5-10 m', '10-20 m', '20 m or more'])[v.class_order] END AS class_label,
       CASE WHEN v.view_order < 3 THEN v.class_order ELSE 4 + v.class_order END AS class_label_order,   -- one sort key per label (Power BI Sort by column): min labels 1-4, m labels 5-8
       (ARRAY['#EFE6D8', '#E3A99C', '#D9675E', '#9E3B33'])[v.class_order] AS class_colour,   -- same ramp as fresh_access_colour
       s.dwellings_n, s.population_n
FROM v JOIN s USING (seccio_censal)
