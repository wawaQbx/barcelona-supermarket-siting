-- VISUALISATION LAYER (QGIS + dashboard): a curated copy of ana tables. Do NOT use for modelling; models read ana.
-- One row per store (city stores + stores outside the city within 2 km, in_city = false): position, chain, format, opening history,
-- validation evidence and building; chain colour from seeds/chain_colours.csv (the same colour on every map and chart). lon / lat (WGS84) added for tools that cannot read EPSG:25831 (Tableau, Power BI).
{{ config(post_hook=primary_key('store_id'), indexes=[{'columns': ['geom'], 'type': 'gist'}]) }}
SELECT p.store_id, p.ensenya, p.brand_group, cc.chain_label, cc.colour_hex AS chain_colour_hex, cc.sort_order AS chain_sort_order, p.format_group, p.store_type, p.point_source, p.in_city,
       p.first_seen_census_year,
       CASE WHEN o.opening_type IS NOT NULL THEN o.opening_type WHEN p.first_seen_census_year = 2014 THEN 'open_in_2014' END AS opening_type,
       -- display labels for the dashboard (decomposition tree, legends)
       CASE p.store_type WHEN 'supermarket' THEN 'Supermarket' WHEN 'convenience' THEN 'Convenience store' WHEN 'hypermarket' THEN 'Hypermarket' END AS store_type_label,
       CASE coalesce(o.opening_type, CASE WHEN p.first_seen_census_year = 2014 THEN 'open_in_2014' END)
            WHEN 'open_in_2014' THEN 'Open by 2014' WHEN 'new_site' THEN 'New site'
            WHEN 'takeover_of_food_premise' THEN 'Replaced a grocery'
            WHEN 'clarel_conversion' THEN 'Replaced a grocery'   -- 1 store: a Clarel drugstore of the Dia group turned into a Dia (same group, counted with the replacements)
            ELSE CASE WHEN p.in_city THEN 'Not dated' ELSE 'Outside the city' END END AS opening_type_label,
       -- opening period = between which two censuses the store first appears (page 03 decomposition tree)
       CASE p.first_seen_census_year WHEN 2014 THEN 'By 2014' WHEN 2016 THEN '2015-2016' WHEN 2019 THEN '2017-2019'
            WHEN 2022 THEN '2020-2022' WHEN 2024 THEN '2023-2024' ELSE CASE WHEN p.in_city THEN 'Not dated' ELSE 'Outside the city' END END AS opening_period,
       CASE p.first_seen_census_year WHEN 2014 THEN 1 WHEN 2016 THEN 2 WHEN 2019 THEN 3 WHEN 2022 THEN 4 WHEN 2024 THEN 5 ELSE CASE WHEN p.in_city THEN 6 ELSE 7 END END AS opening_period_order,   -- sort key only
       -- what a store that "replaced a grocery" replaced (previous census occupant of the site; page 03). Same group = a rebranding inside
       -- one company (Simply -> Mi Alcampo, Dia Market -> Dia, Charter -> Consum); regional / franchise brands = grocery banners outside the 10 chains.
       CASE WHEN o.opening_type = 'clarel_conversion' THEN 'Clarel (Dia group drugstore)' ELSE o.previous_food_premise_name END AS replaced_premise_name,
       CASE WHEN o.opening_type NOT IN ('takeover_of_food_premise', 'clarel_conversion') OR o.opening_type IS NULL THEN NULL
            WHEN o.opening_type = 'clarel_conversion' THEN 'Same group (Clarel)'
            WHEN (p.brand_group = 'Alcampo' AND o.previous_food_premise_name ~* 'simply|sabeco|alcampo')
              OR (p.brand_group = 'Dia' AND o.previous_food_premise_name ~* '^d[ií]a\M|d[ií]a market')
              OR (p.brand_group = 'Consum_Charter' AND o.previous_food_premise_name ~* 'charter|\mconsum\M')
              OR (p.brand_group = 'BonPreu_Esclat' AND o.previous_food_premise_name ~* 'bon ?preu|esclat')
              OR (p.brand_group = 'Carrefour' AND o.previous_food_premise_name ~* 'carrefour')
              OR (p.brand_group = 'Condis' AND o.previous_food_premise_name ~* 'condis')
              OR (p.brand_group = 'Caprabo' AND o.previous_food_premise_name ~* 'caprabo')     THEN 'Same group (Clarel)'
            WHEN o.previous_food_premise_name ~* 'condis|caprabo|mercadona|\mlidl|\maldi\M|carrefour|alcampo|simply|sabeco|^d[ií]a\M|d[ií]a market|charter|\mconsum\M|bon ?preu|esclat'
                 THEN 'Major chain'
            WHEN o.previous_food_premise_name ~* 'coaliment|\msuma\M|covir[aá]n|\mspar\M|veritas|bon ?[aà]rea|superestalvi|\munico\M|distop|keisy|plusfresc|ametller|supercor|eroski|froiz|\mmas\M|tot d.avui'
                 THEN 'Smaller brand'
            ELSE 'Independent shop' END AS replaced_premise_type,
       -- marker colour by opening type (page 03 map; Azure Map takes the colour from a field): new sites in the neutral accent, old stores muted
       CASE coalesce(o.opening_type, CASE WHEN p.first_seen_census_year = 2014 THEN 'open_in_2014' END)
            WHEN 'open_in_2014' THEN '#B3A895' WHEN 'new_site' THEN '#C79A5B'
            WHEN 'takeover_of_food_premise' THEN '#7A5C3E' WHEN 'clarel_conversion' THEN '#7A5C3E' ELSE '#D9D2C4' END AS opening_colour_hex,
       -- size of the building the store occupies (cadastre footprint): small ground floors vs large plates (page 02)
       CASE WHEN b.footprint_area_m2 IS NULL THEN 'No match' WHEN b.footprint_area_m2 < 500 THEN 'Small (< 500 m2)'
            WHEN b.footprint_area_m2 < 1500 THEN 'Medium (500-1,500 m2)' ELSE 'Large (> 1,500 m2)' END AS building_size_class,
       CASE WHEN b.footprint_area_m2 IS NULL THEN 4 WHEN b.footprint_area_m2 < 500 THEN 1 WHEN b.footprint_area_m2 < 1500 THEN 2 ELSE 3 END AS building_size_order,
       v.evidence AS validation_evidence, p.coord_corrected,
       b.year_of_construction AS building_year_of_construction, b.footprint_area_m2 AS building_footprint_area_m2,
       coalesce(b.seccio_censal, ns.seccio_censal) AS seccio_censal, coalesce(b.codi_barri, ns.codi_barri) AS codi_barri, n.nom_barri, d.nom_districte,
       -- spacing of the networks: straight-line distance to the nearest store of the SAME chain and of ANY OTHER chain (stores outside the city count as neighbours)
       round(own.d::numeric, 0) AS dist_nearest_same_chain_m, round(rival.d::numeric, 0) AS dist_nearest_other_chain_m,
       ST_X(ST_Transform(p.geom, 4326)) AS lon, ST_Y(ST_Transform(p.geom, 4326)) AS lat,
       p.geom
FROM {{ ref('store_points') }} p
LEFT JOIN {{ ref('chain_colours') }} cc ON cc.brand_group = p.brand_group   -- fixed chain colours (seeds/chain_colours.csv)
LEFT JOIN LATERAL (SELECT ST_Distance(q.geom, p.geom) AS d FROM {{ ref('store_points') }} q
                   WHERE q.brand_group = p.brand_group AND q.store_id <> p.store_id ORDER BY q.geom <-> p.geom LIMIT 1) own ON true
LEFT JOIN LATERAL (SELECT ST_Distance(q.geom, p.geom) AS d FROM {{ ref('store_points') }} q
                   WHERE q.brand_group <> p.brand_group ORDER BY q.geom <-> p.geom LIMIT 1) rival ON true
LEFT JOIN {{ ref('store_openings') }} o USING (store_id)
LEFT JOIN {{ ref('store_list_validation') }} v USING (store_id)
LEFT JOIN {{ ref('site_buildings') }} b ON b.site_id = 'store_' || p.store_id
-- city stores a few metres outside every section polygon (on the boundary line): nearest section within 50 m
LEFT JOIN LATERAL (SELECT u.seccio_censal, u.codi_barri, u.codi_districte FROM {{ source('raw', 'adm_units_polygons') }} u
                   WHERE p.in_city AND b.seccio_censal IS NULL AND u.tipus_ua = 'SEC_CENS' AND ST_DWithin(u.geom, p.geom, 50)
                   ORDER BY u.geom <-> p.geom LIMIT 1) ns ON true
LEFT JOIN {{ source('ana', 'dim_neighborhood') }} n ON n.codi_barri = coalesce(b.codi_barri, ns.codi_barri)
LEFT JOIN {{ source('ana', 'dim_district') }} d ON d.codi_districte = coalesce(b.codi_districte, ns.codi_districte)
