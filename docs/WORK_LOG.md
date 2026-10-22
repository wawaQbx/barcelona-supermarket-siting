# Work log (chronological record of the working sessions, for the final summary)

Kept up to date during the work; one entry per step that changed data, code, results or decisions. Details of results: MODEL_RESULTS.md;
decisions and data-quality findings: PROJECT_REPORT.md.

## Phase 1 - data collection and database (2026-10-09 .. 10-12)
- Goal set: explain the siting of supermarket chains in Barcelona with PostgreSQL / PostGIS, SQL, QGIS, Python models, later a dashboard.
- Store list: 964 stores of 16 banners from the chains' official locators (Dia gzipped JSON, Consum / Charter HTML, Bon Preu / Esclat JSON, Condis ...);
  analysis limited to the city (701 city stores at first), stores outside the city kept for the edge effect. Floor area NOT scraped (user rule: only if
  exact for every store).
- Database supermarket_bcn: schemas raw (imported, never edited), ana (derived), meta (catalog, audit). Pipeline clean_catalog.py -> import_all.py ->
  audit_types.py; all naming / type rules in bcn_naming.py (shared concepts in Catalan, units in column names, codes as text, EPSG:25831).
- Data traps found: 2019 census yes/no flags inverted, 2014 census coordinates in ED50, Padro cells < 5 withheld, QGIS age / education tables biased,
  published motorisation index covers 17% of sections.
- Opening dates: no chain publishes them -> first appearance in the 5 commercial censuses (2014-2024).

## Phase 2 - siting models v1-v6 and food access (2026-10-13)
- Edge effect plan A (stores inside the unit / within X m, with and without outside stores); ring of outside stores collected (2 km).
- Models: Poisson with ln(population) offset, barri-clustered errors, NB / Moran checks, format split, own vs other chains, time ordering (2015
  predictors), event study around new sites, L10 metro and pacified-streets natural experiments, case-control of store buildings (cadastre INSPIRE),
  conditional-logit site choice, out-of-time prediction, ML with spatial CV.
- Store-list corrections: 57 "Dia Market" entries are Clarel drugstores (excluded), 51 Condis / Consum coordinates corrected by address, 79 missing
  chain stores added from the 2024 census (city stores 723); automatic validation against the censuses.
- Food access: walking network + slope (Copernicus DEM, Tobler), older pace; low-income food deserts (top 3 = Institut Metropoli's Torre Baro,
  Vallbona, Baro de Viver); why no store opens there (catchment far below existing stores).

## Phase 3 - learning mode (2026-10-14)
- User felt they had not used PostgreSQL / PostGIS / dbt themselves: step-by-step worked examples per tool (DBeaver, SQL, PostGIS, indexes, dbt, QGIS);
  dbt installed (.venv-dbt, dbt-core 1.12, dbt.cmd disables the dbt State login); user built the chain_summary dbt model.

## Phase 4 - 2026-10-15 (this session)
1. Migration of the 13 sql/ana_*.sql scripts to dbt: 25 models in dbt_bcn/models/ana + helper tables in dbt_int (replace TEMP tables), primary keys as
   post-hooks, type harmonisation as on-run-end macro, 49 tests; verified against a backup (23 / 25 identical, 2 differed only in tie-breaks, now
   deterministic); section_pacified_streets 448 s -> 2 s, store_list_validation 59 s -> 1 s; import_all runs dbt build; old SQL archived.
2. Store ids made stable across rebuilds (ordered numbering); stale food-access figure in MODEL_RESULTS corrected (3.8% beyond 500 m, not 4.2%).
3. Dashboard scope discussed: one central question (where chains open, why, who is left out), 4 pages + overview + methods; flashy Tableau-style not
   required; Tableau Public vs Power BI compared (user later chose Power BI).
4. Extra data (easy + important only): Padro nationality 2015 + 2026, Inside Airbnb 2026-09 (host data not kept), tourist flats 2026 / 2017, hotels,
   municipal markets. New dbt models pop_nationality_section, section_tourism, section_airbnb_reviews_year, market_supermarkets; analyze_tourism_markets.py (v7).
   Noise / air skipped (raster only, off-topic).
5. Robustness of v7 at the user's request (stepwise controls, alternative measures and outcomes, per-dwelling offset, matched controls): tourist grocery
   demand is served by independent supermarkets, not chains; fewer chain stores where non-EU residents are many (0.82-0.88 per SD), not replaced by
   independents; 30 of 39 food markets have a chain store within 100 m (municipal policy, confirmed by Nacio Digital 2026-08); fresh shops near markets
   fell less than around matched places. Earlier claims corrected (tourism "no effect" was only true for chains; "independents fill the gap" refuted;
   the first market trend was wrong because market stalls and the 2016 coding were counted).
6. QGIS: connection settings explained; derived point geometries typed geometry(Point, 25831) so QGIS reads them; DB-connected new project instead of the
   old file-based barcelona_super.qgz.
7. Audit of the tables the user had derived in QGIS: user's "PQ" = age location quotient (LQ), recomputed on reconciled age bands; barri income
   (population-weighted), barri Gini (only mean of section Ginis possible), barri cadastral value (area-weighted), education, traditional food shops
   (+ fish, poultry) corrected as dbt models; old raw tables marked SUPERSEDED in the catalogs.
8. gis schema (visualisation layers, not for modelling): section_indicators (108 columns), barri_indicators (78), stores, markets, transit_stops,
   traffic_counters; built at the end of build_food_access.py; DASHBOARD_DESIGN.md with pages, column groups and a color / classification guide;
   Swiss-style wireframes of the 6 pages shown in chat.
9. Opening dates completed: stores not dated by census_panel.py (census supplement + address-corrected coordinates) dated by chain-name match within 60 m
   (agrees 98.4%); dated 508 -> 639 (88%), openings 276 -> 352; all models re-run (MODEL_RESULTS section 26: Carrefour non-EU time-order result gone,
   Condis openings follow 2017 tourist flats, site choice away from own stores stronger).
10. Fixes found while building gis: NULL building-era shares (should be 0), integer types in pop_education_barri, traffic counters without barri.
11. Full rebuild from the source files + new check_quality.py (17 checks + dbt tests + independent re-verification): all OK. Fixed on the way: syntax
    error in build_food_access.py, row-order dependence of cross-validation / holdout / sampled site choice (now reproducible), 3 missing primary keys.
12. Power BI started: Windows 11 Home China is single-language -> Store version of Power BI showed Chinese; fixed by moving English to the top of the
    preferred-language list. Connected to PostgreSQL (Import, Basic, Organizational, no encryption: server ssl = off); loaded gis.stores,
    gis.section_indicators, gis.markets via Transform data; geom columns removed; queries renamed stores / sections / markets.
13. Power Query explained to the user: Applied steps Source (connect, list of all tables) -> Navigation (pick gis.stores) -> Removed columns (geom);
    M code in Advanced Editor; query folding (steps translated to SQL and run by PostgreSQL). Load vs Transform data vs Create explained; only the tables
    of the current page are imported, the others added per page (model coefficients and other CSV results come from docs/).
14. User rule: keep this log updated continuously and before any context compaction (logged in memory).
15. Power BI model: sections import first failed (user had applied "Remove Errors" instead of removing the geom column -> 0 rows; fixed);
    stores 996 / sections 1068 / markets 43 rows confirmed; relationship stores[seccio_censal] *:1 sections[seccio_censal], single direction, active.
    Explained to the user: card display options, cross-filter Single vs Both (worked example: Lidl filter -> city population 1,729,963 vs 44,982 in the
    28 sections with a Lidl), one active relationship per table pair (ambiguity; USERELATIONSHIP or role-playing copies), markets to be linked through
    gis.barri_indicators (star schema) on page 3.
16. Power BI page 1 started: Azure Map with stores (lat / lon, legend brand_group, in_city filter). Map settings explained (style, geocoding culture =
    address parsing only, boundaries / buildings off, auto zoom off, style picker off). Selection (lasso) is disabled by a tenant admin switch that a
    personal Microsoft account cannot change (not related to the Organizational privacy level, which only governs combining data sources in Power Query).
    Azure Map has no per-category color list -> new dbt seed gis.chain_colors (seeds/chain_colors.csv: brand_group, chain_label, color_hex,
    sort_order) joined to gis.stores (chain_color_hex, chain_label, chain_sort_order); map color via fx -> Field value.
17. Page 1 first version built by the user (Azure map, chain slicer, bar chart); counts verified (723 city stores, per chain identical to the DB).
    User feedback: not pretty, default titles clutter, slicer duplicates the bar chart. gis.stores now gives the one boundary-line store its nearest
    section / district (0 city stores without district). Theme file dashboard/theme_supermarket_bcn.json (chain colors, Segoe UI, no default titles /
    borders / shadows, page background #F3F2EF). Page 1 redesign proposed: header with question + finding, KPI cards, bar chart as the chain filter,
    district slicer instead of the chain slicer, map legend and basemap labels off.
18. Page 1 work (2026-10-15 evening): district slicer moved to sections[nom_districte] (filter flows sections -> stores, so district stores and
    district population match; (Blank) = the 273 stores outside the city without a section, excluded by a visual-level filter); DAX measures written:
    Stores, Population ('sections' must be quoted: name clashes with a DAX keyword), Stores per 10k residents, ... (city) with REMOVEFILTERS,
    diff vs city, arrow text (UNICHAR 9650 / 9660), color (blue #4E79A7 above / orange #F28E2B below / grey), Stores share of city (percentage format).
    Card (new) with reference labels ("Share of city 11.9%", "vs city 4.2 ▲ 0.2"); counts checked against the DB (Sarria-Sant Gervasi 67 / 4.38,
    Sants-Montjuic 86 / 4.39, Sant Andreu 63 / 3.98). Explained: Filters pane levels, measure vs column (rates must be recomputed, not summed),
    Measure tools formatting, theme vs manual formatting, page / visual background colors (#F3F2EF page, #FFFFFF cards).
    Open for next session: one-line SVG KPI option (measure code given, not built yet), page alignment with exact coordinates (table in chat:
    slicer 1016/28/240x44, cards 24/88/1232x88, map 24/192/760x504, bars 800/192/456x504), map labels off, header text box, choose a gallery theme,
    then pages 2-4 (model coefficients CSV, openings, markets via gis.barri_indicators star schema, food access) and boundary GeoJSON test.
    User: expected 2 days, now estimates about a week; ended the day here.
19. 2026-10-16: page 1 extensions chosen by the user: stores per 10k residents by district (Gracia 5.4 ... Horta-Guinardo 3.2, city 4.2) and KPI
    "96.2% of residents within 500 m of a chain store". Other candidates computed: chain format mix (Carrefour 30 of 38 convenience, Alcampo 5
    hypermarkets), densest / sparsest barris (Dreta de l'Eixample 6.8, Barri Gotic 1.1 per 10k). Choropleth maps: export_dashboard_boundaries.py
    writes simplified WGS84 GeoJSON (sections 0.59 MB, barris 0.14 MB, keys + names only) to dashboard/boundaries/; options in Power BI: Azure Map
    reference layer (GeoJSON) or Shape map (preview, needs TopoJSON; no converter installed locally - mapshaper.org suggested).
20. Page 1 more charts: heat matrix rejected by the user (prefers map heat). gis.stores gained dist_nearest_same_chain_m / dist_nearest_other_chain_m
    (straight line, ring stores count as neighbours). Medians: own chain 266 m (Condis) .. 871 m (Lidl), nearest rival 89-166 m for every chain ->
    chains space their own stores and sit next to rivals (matches the v3 model). Proposed chart: clustered bar own vs rival distance per chain;
    Azure Map heat map layer; walking bands 96.2 / 2.9 / 0.9 % (optional). KPI "Residents within 500 m" showed 1.0 -> needs Percentage format.
21. 2026-10-16: user flagged the edge effect of the 500 m / food-access figures. Checked: chain stores outside the city were already targets (273 ring
    stores, network ~1 km beyond the city) -> 96.2% unaffected. Fresh shops / markets / independent supermarkets were city-census only -> added outside
    the city from OSM (fetch_ring_food_osm.py, raw.com_osm_food_shops_box; OSM completeness vs census: markets 95%, supermarkets 57%, fresh 10-23%)
    + edge_outside_food_uncertain flag (63 sections). While checking, found two real bugs in build_food_access.py: false slopes of the surface model
    (7,044 edges > 30%, Tobler speed collapsing; now capped at 30%, sensitivity 25-40% gives the same result) and buildings beyond the 60 min cutoff
    silently dropped (1,519 dwellings; now set to the cutoff). Low-income food deserts 11 -> 5 (Torre Baro, Vallbona, Baro de Viver, Marina de Port,
    Sant Genis); 65+ beyond 10 min 10,650 -> 7,730. MODEL_RESULTS sections 23 + 27, PROJECT_REPORT, DASHBOARD_DESIGN, catalogs updated; quality check OK.
22. Fresh-food definition made explicit (user question: do independent supermarkets sell meat / vegetables?): many "independents" are regional chains that
    sell fresh food. Three definitions computed in build_food_access.py (fresh = middle MAIN, fresh_strict, fresh_broad); food deserts middle 4 (Torre Baro,
    Vallbona, Sant Genis, Marina de Port), range strict 5 / broad 1; Torre Baro in all; Baro de Viver only under strict (depends on a Supercor 250 m away
    and BonArea / Sorli across the boundary; press reports fit strict). 60-min search cutoff explained (computational limit, not an analysis threshold).
    MODEL_RESULTS section 28, gis flags _strict / _broad, DASHBOARD_DESIGN KPI updated.
23. User asked why the vulnerable indicator only used chain stores and ignored slope: it was a leftover of the first version. Now the same slope-aware
    10-min test as the food deserts: vulnerable_low_access (fresh food, middle definition) = 2 sections (Sarria, Pedralbes); vulnerable_low_access_chain
    (full chain supermarket) = 5 (+ Vall d'Hebron 7101, Vallcarca 6010, Can Baro 7021); distance-only version (7) retired. MODEL_RESULTS section 29.
24. Power BI page 1 (cards, reference label "incl. independent shops"): the earlier 98.7% was a minutes-based estimate, not comparable with the
    96.2% chain coverage (network distance 500 m). build_food_access.py now also computes the network distance to ANY supermarket-class shop:
    gis.section_indicators share_dwellings_beyond_500m_any_supermarket_pct / residents_beyond_500m_any_supermarket_est. City: 1.4% beyond 500 m
    -> 98.6% within 500 m incl. independents (chains only 96.2%, unchanged). Other food-access results unchanged (deserts 4, range 5/1; vulnerable 2/5).
    Page 1 advice: title + one-line conclusion text box; non-bar visuals (scatter own vs rival spacing, treemap chain share, heat-map layer).
25. Counting rule fixed with the user (consistency): pages 00-03 = chain stores only, no independent-shop reference values; page 04 (food access)
    = all food shops. The 98.6% "incl. independents" reference label dropped from page 1 (column kept in gis for page 04). DASHBOARD_DESIGN updated.
26. Page 1 review: heat-map layer dropped (723 stores merge into one blob = built-up area, no information; population-relative density will come
    as a section choropleth); map needed the in_city filter (273 outside stores shown). Layout frame: make_layout_backgrounds.py draws the page grid
    as a canvas-background PNG (dashboard/layout/page01_layout.png, 1280x720, margin 24, gap 16, 4 KPI cards aligned with 3 columns).
27. Swiss style theme (user request; user builds the layout without the background template): dashboard/theme_supermarket_bcn.json rewritten -
    Arial everywhere (textClasses + explicit fontFamily for axes, legends, labels, card value / label / reference title / value / detail, slicer),
    black #111111 / grey #6B6B6B, white page, no visual backgrounds, borders, shadows or rounded card tiles; red #E2001A as "bad" accent.
    Cause of the mixed card fonts: card reference-label values have their own font property (base theme default Segoe UI Semibold) that the
    global text classes do not reach. Theme checked against Microsoft reportThemeSchema-2.159 (all properties valid). The user's "Reset to default"
    removed the reference labels; backup of the last saved report (11:46, labels intact): D:\Power BI\Pro\supermarket_bcn_backup_2026-10-16_1146.pbix.
28. Theme revised on user request: serif font Cambria everywhere (lining figures; Georgia has old-style figures that jump in KPI numbers and axes,
    so Georgia only for the hand-formatted title text box), colors kept, page beige #F5F1E8 (wallpaper #E9E4D8), cards white with a thin warm-grey
    outline #E3DDD0 and 6 px corners, gridlines #E3DDD0. Button slicer (advancedSlicerVisual) styled by state from the theme: default white / grey
    text / light outline, hover darker outline, selected = dark text bold + dark outline + 3 px dark bar underneath (#2B2B2B, no fill change, no
    clash with chain colors). Validated again against reportThemeSchema-2.159.
29. Cards toned down (user: white too loud): theme card fill #EDE7DA (one step darker than the page #F5F1E8), no outline, divider #DCD4C4.
    Page-1 key findings drafted and checked in the DB: Condis 259 = Caprabo + Dia + Consum (260); Horta-Guinardo lowest density 3.2 per 10k
    (city 4.2) and 11.2% of residents beyond 500 m = 20,420 of 64,983 (31%) of the city's uncovered residents; Eixample 0.1%; spacing 89-166 m
    to a rival vs 266-871 m to own chain.
30. Theme: visual titles regular italic (bold off, italic on), user preference.
31. Theme: visual titles 11 -> 13 pt; card reference area fill #EDE7DA -> #F0EBE1 (lighter; callout area stays white = two-tone card the user liked).
32. Page-1 key findings finalised (whole city): crowd rivals / space own stores (89-166 vs 266-871 m); hillside districts thinner
    (Horta-Guinardo 3.2 per 10k, 11.2% beyond 500 m; Sarria-Sant Gervasi 6.5%; Eixample 0.1%); chain formats (median building footprint
    Mercadona 1,765 / Lidl 1,242 vs Condis 475 / Dia 544 m2). User question Sant Marti / Poblenou: Sant Marti 14.6% of residents but 20% of
    Mercadona (9/45, ~1.4x) - and Condis also over-represented (18.5%); Caprabo 10.7, Dia 11.9, Consum 6.8, Aldi 0 under. Mercadona there on
    large plates (ex-industrial / new blocks: 1,373-4,958 m2, one 1889 building of 1,672 m2), consistent with the footprint / larger-section
    effects in MODEL_RESULTS (not a separate test for Sant Marti).
33. Sant Marti check (user asked for evidence; scratch sm_check.py): the "few small ground-floor premises" explanation mostly FAILS.
    Premises per 1k residents SM 31.0 vs rest 36.6, and city-wide Caprabo+Dia+Consum rise with premises density (0.82 -> 2.04 per 10k), but the
    premises mix explains only 38.0 -> 36.3 expected stores vs 26 observed; Poblenou / Parc i Llacuna have the most premises yet few of them.
    Poisson vs population share 14.6%: Caprabo+Dia+Consum 26 vs 38 (p = 0.03), Condis 48 vs 38 (p = 0.06), Mercadona 9 vs 6.6 (p = 0.22, NOT
    significant - earlier "Mercadona over-represented" overstated), all small formats together 74 vs 76 (p = 0.45). Reading: Condis holds the
    small-format niche in Sant Marti (31 of its 48 stores opened 2016-2024, 65% vs 55% elsewhere); why (pre-emption, franchise network) not testable here.
34. Sant Marti research (web + DB): Condis in Sant Marti 25 new sites + 6 takeovers; 23 of 48 first seen in the 2022 / 2024 census (48% vs 21%
    elsewhere) = a recent burst. Context from press: Sant Marti suspended licences for autoserveis / supermarkets up to 300 m2 and convenience
    stores from Dec 2023 (moratorium), Pla d'Usos approved 19 Dec 2025 (one food self-service / convenience shop of the same activity within 200 m;
    initial proposal 100 m) - Condis' network was largely in place before the freeze; new entries since are large formats (Aldi Mercat del
    Poblenou Dec 2024 >1,000 m2 replacing a Mercadona closed Mar 2024; Lidl Guipuscoa 183 Sep 2026, 1,300 m2). Condis: 688 shops, 527 franchised,
    >85% of franchises in Barcelona province (foodretail.es). DATA GAP found: the Aldi at Placa de la Unio 25 (Dec 2024) is missing - Aldi list
    comes from OSM; Lidl Guipuscoa (Sep 2026) also after the snapshot. Aldi / OSM-sourced chains need an audit against official locators.
35. STORE LIST AUDIT (user: "all supplements now"). Official locators: Mercadona data.js (dated 2026-10-16, with opening dates) and Aldi store
    finder (__NEXT_DATA__) -> fetch_official_locators.py -> data_catalog/01_stores/official_locators/store_official_locators.csv (raw.store_official_locators).
    Lidl / Carrefour locators behind bot protection (not bypassed), Caprabo has no public locator: checked against current OSM (Overpass 2026-10-16):
    Lidl 28 = 28, Carrefour 7 and Caprabo 29 of ours not in OSM (Caprabo mostly census-2024 additions), no new OSM stores beyond 80 m except
    the Aldi at Bac de Roda 178 (ex-Lidl site). Findings: Mercadona city 45 -> 40 (5 closed: Mercat del Poblenou Mar 2024, Placa Fort Pienc
    [2 points, one census duplicate] -> Aldi end 2025, Trinitat Vella, Sant Andreu); Aldi city 23 -> 27 (+ Placa de la Unio 25 Dec 2024,
    Sardenya 350, Rossello 188, Bac de Roda 178 Jun 2026); Lidl Bac de Roda dropped (store_closures_manual.csv with evidence). dbt store_points:
    drop listed / supplement stores of locator chains with no locator store within 150 m; add locator stores missing (city + 2 km ring,
    point_source official_locator); manual closures within 30 m. Reference date of the store list is now mixed: other chains scraped ~2026-06,
    Mercadona / Aldi 2026-10-16. Full rebuild started.
36. Rebuild after the audit: dbt 107 PASS, gis 19 PASS, check_quality OK (after fixing an untyped geometry from the locator additions), models and
    boundaries re-exported. City stores 721 (Mercadona 40, Aldi 27, Lidl 27). MODEL_RESULTS section 30 (changes), PROJECT_REPORT, DASHBOARD_DESIGN updated.
    Press: Fort Pienc Mercadona -> Aldi (Nov 2025, "transfer agreement" / could not remodel); both Mercadona closures were in municipal markets.
    Power BI needs Home -> Refresh. Key findings card numbers re-checked: Mercadona building median 1,867 m2, Lidl 1,271, Condis 475, Dia 544;
    spacing rival 89-166 m vs own 266-871 m unchanged.
37. Second audit round (user: "are the latest data perfectly verified?" + "avoid one store counted as several points"):
    - Re-scraped Condis / Consum-Charter / Bon Preu-Esclat (refresh_store_list.py, address match because Condis coordinates are 150-250 m off):
      Consum and Bon Preu unchanged; Condis city -5 (Alt de Pedrell 64, Guitard 36, Llenguadoc 90, Poesia 9, Cantabria 73) +1 (Marti Alsina 29),
      ring changes too. Dia now 403 (not bypassed) -> June list kept; Alcampo locator via Selenium hangs -> June list kept.
    - Bug in check_store_addresses.py: partial street-name match ("emilia llorca martin" ~ "marti") moved a Barceloneta Condis 4.1 km onto
      another Condis in Gracia. Fixed: partial match only for whole words of >= 8 characters; corrections capped at 1,000 m.
    - One store = one point: data_catalog/01_stores/store_removals_manual.csv (closed / duplicate / wrong_coordinates, with evidence), applied in
      int_store_points_base by chain + address or chain + point: Lidl Bac de Roda (-> Aldi), Carrefour Express Balmes 62 (-> Mi Alcampo, census),
      Condis Torrent de l'Olla 180 = Asturies 66-68 corner, Mi Alcampo = Alcampo Travessera de Dalt 78, Alcampo Sant Quirze hypermarket geocoded
      into la Guineueta, Mi Alcampo Muntaner geocoded outside the city (already in via census). New check_quality check "one store = one point"
      (same chain < 40 m, two chains < 10 m); reviewed and kept: Condis / Dia Badalona Sant Salvador 32-34 (both locators, outside the city).
    - Census history 2014-2024 (name-matched premises): Caprabo / Dia / Consum under-represented in Sant Marti in EVERY edition (6-13% vs 14.6%
      of residents) -> long-standing, before the Dec 2023 licence freeze and before Condis' growth there (14 -> 43 premises).
38. Census supplement restricted to Caprabo / Lidl / Carrefour (store_points): for chains with official lists the census-only points were the same store
    again (Condis offsets 150-250 m) or closed since 2024 -> 41 points removed. Final city stores 678 (Condis 237, Caprabo 103, Dia 73, Consum 69,
    Mercadona 40, Carrefour 37, Bon Preu 36, Lidl 28, Alcampo 28, Aldi 27); 3.9 per 10k; 95.8% within 500 m; vulnerable 3 / 7; deserts 4 (1-5).
    Rebuild OK (dbt 107 + 19 PASS, check_quality OK incl. "one store = one point"). MODEL_RESULTS s30 rewritten, PROJECT_REPORT, DASHBOARD_DESIGN updated.
39. Closed stores documented in store_removals_manual are no longer brought back by the census supplement (the Lidl at Bac de Roda had come back). Final city stores 677 (Lidl 27). Rebuild OK, check_quality OK.
40. Power BI card fix by file edit (user could not find the label-level title in the UI): backup D:\Power BI\Pro\supermarket_bcn_backup_before_card_fix_1953.pbix; in Report/definition/.../05277d954e29ac58e454/visual.json the two referenceLabelTitle entries of 'sections.Stores per 10k residents' set show=false (label-level custom title 'vs city 4.2' had overridden the card-level switch). Zip test OK. The city value now comes from the measure Stores per 10k vs city text (& '  vs city ' & [Stores per 10k residents (city)]).
41. Dashboard page 02 data: load_model_outputs.py (after analyze_siting) loads docs/model_v4_blocks*.csv into ana.py_model_v4_coefficients / _fit and
    builds gis.model_drivers (dbt, models/gis/after_models, tag after_models; build_food_access now excludes that tag): 105 rows = 7 groups x 15
    predictors with rate ratio, 95% CI, effect class, log ratio, labels (new seed factor_labels) and chain colors. export_dashboard_boundaries.py
    also writes TopoJSON (Shape map). check_quality OK. Rebuild order: ... analyze_siting -> load_model_outputs -> analyze_tourism_markets.
    Page-02 findings (after the audit): all chains - active shops 1.40, 65+ 1.28, degree 1.25, newer buildings 0.87, commercial floor 1.15;
    Condis degree 1.43 / shops 1.33; Dia shops 1.58 only; Caprabo shops 2.22 + income 1.79; Mercadona commercial floor 2.08, fewer cars 0.50,
    65+ 1.80, newer buildings 0.56; Consum degree 3.22, farther from centre 1.79; Bon Preu nothing significant. No effect for any chain:
    population density, built density, main roads, pedestrian streets, property value, road traffic.
42. gis.model_drivers: evidence_strength (strong p<0.01 / weak 0.01-0.05 / none) - 105 tests, ~5 false positives expected at 5%; 12 strong, 10 weak. Mercadona cars 0.50 (p 0.04) = weak, appears only with income held constant (MODEL_RESULTS s22).
43. factor_labels.factor_short (<= 11 characters) for the page-02 x axis; carried into gis.model_drivers.
44. evidence_strength redefined with Benjamini-Hochberg FDR over the 105 tests (q_value_bh in load_model_outputs.py): strong = q<0.05 (9), weak = p<0.05 only (13), none (83). Strong: all chains shops 1.40 / 65+ 1.28 / commercial floor 1.15; Condis shops 1.33 / 65+ 1.30; Caprabo shops 2.22; Dia shops 1.58; Mercadona commercial floor 2.08; Consum degree 3.22. CI width shrinks with stores (Condis 231 narrow, Bon Preu 36 / Mercadona 38 wide).
45. gis.model_drivers.chain_order_by_stores (button order by modelled stores: All 664, Condis 231, Caprabo 100, Dia 73, Consum 69, Mercadona 38, Bon Preu 36).
46. Theme: button-slicer accent bar removed in every state (could not be switched off in the format pane because it came from the theme); selected outline kept at 1 px (user: only remove the accent bar).
47. factor_short: one word where the axis wrapped (Main roads -> Roads, Prop. value -> Price, Comm. space -> Commercial); full names stay in factor_label (tooltips).
48. One comparison color rule for the dashboard (DASHBOARD_DESIGN): blue above / red below / white equal; reference lines grey; page-02 map as index vs the average barri (Map index measure), matrix gradient and card arrow colors aligned.
49. Comparison fills raised to the chain-palette saturation: #5B8DB8 / #D9675E (text and arrows stay #2F6497 / #B04A33).
50. gis.stores: store_type_label / opening_type_label (display labels for the decomposition tree).
51. gis.stores: building_size_class / building_size_order (cadastre footprint <500 / 500-1500 / >1500 m2) for a page-02 100% stacked bar; decomposition tree moved to page 03 (opening history).
52. Page-02 text pass: chart titles carry the findings (no Key findings box), subtitles only say how to read; building_size_class 'No building match' -> 'No match'.
53. Page 03 data: gis.chain_census_premises (dbt) = chain stores per census edition 2014-2024 from sign names, premises of one chain within 50 m merged (ST_ClusterDBSCAN; one store = one point). City total 422 (2014) -> 662 (2024), +240 (+57%); Condis +135 (56% of the net growth), Dia -30; Alcampo incl. Simply / Sabeco. Census 2024 counts differ from the store list (e.g. Mercadona 48 vs 40: closures after the fieldwork).
54. CORRECTION chain_census_premises: sign-name matching alone counted travel agencies, car parks, stock rooms, offices, a music school, a gym and food co-operatives. Now food-retail class per edition (2014 ALIMENTACIO, 2016 Resta alimentacio, 2019+ Autoservei / Supermercat, hypermarkets all years), co-operatives excluded, 50 m merge. City 405 (2014) -> 639 (2024), +234 (+58%); Condis 91 -> 227 (+136 = 58% of net growth), Dia 106 -> 76 (-30); Condis passed Dia between 2014 and 2016 (91/106 -> 124/115). 2014/2016 classes differ from 2019+: trend also holds 2019-2024 (Condis 161 -> 227, Dia 109 -> 76).
55. Page-03 data checks: excluded but shop-like signs = a handful per edition (e.g. Condis filed as fruit / fish shop 2014 / 2019: 4 in all editions), 2024 merges within 50 m = 6 pairs (same corner or a fish counter of the same store). Residual uncertainty documented: 2014 / 2016 class wider than 2019+, franchisees under their own sign not counted, census vs store-list dates differ.
56. Uncertainties of page 03 tested: (1) class change 2014/2016 vs 2019+: in 2019-2024 99.4% of chain-named retail premises are in the supermarket class, and 419 of the 2016 chain premises in 'Resta alimentacio' linked by id_bcn_2016 are 'Autoservei / Supermercat' in 2019 (3 became stock rooms) -> chain counts are comparable across editions. (2) chain stores recorded under another / no sign in 2024 (store_list_validation 'other_supermarket'): 27 of the store list (~4%), 8 of them 'SN' (no sign recorded) -> census counts may be up to ~4% low, same rule every edition. (3) census (2024 fieldwork) vs store list (2026) are different dates: labelled, not subtracted.
57. Theme: plotArea transparency 100 for all visuals (scatter plot area was tinted; the pane only offers an image there).
58. opening_type_label: takeover of a food premise + the single Clarel conversion -> 'Took over an existing shop' (105).
59. Neutral accent color added to the dashboard palette: ochre #C79A5B / #EFE3CF (decomposition tree); warm greys for size classes.
60. gis.stores.opening_color_hex (Azure Map marker color by opening type: open by 2014 #D6CFC2, new site #C79A5B, takeover #7A5C3E, not dated #ECE7DD).
61. gis.stores.opening_period (+ _order): census interval in which a city store first appears (By 2014 / 2015-2016 / 2017-2019 / 2020-2022 / 2023-2024 / Not dated) for the page-03 tree.
    opening_type_label 'New site 2016-2024' -> 'New site' (the period is its own column now).
62. opening_period_order: 1-6 (7 = outside the city) instead of the 9999 placeholder for undated stores.
63. store_openings takeover definition corrected (2014 'QUOTIDIA NO ALIMENTARI' pharmacies / drugstores and specialised food shops next door were counted): takeover = replaced a supermarket / grocery (supermarket class per edition). New site 238, replaced a grocery 88 (+1 Clarel). gis label 'Replaced a grocery'. Full rebuild OK (dbt 110 + 21 PASS, check_quality OK, models re-run). MODEL_RESULTS note added.
64. Map colors: open by 2014 #D6CFC2 -> #B3A895, not dated #ECE7DD -> #D9D2C4 (too faint on the grey base map).
65. gis.stores.replaced_premise_name / replaced_premise_type (page 03 donut): of the 89 stores that replaced a grocery, the previous occupant was an independent grocery 48, a regional / franchise banner 21 (Coaliment, Suma, Coviran, Spar ...), another of the 10 chains 14 (9 of them Dia / Dia Market), the same company rebranding 6 (Simply -> Mi Alcampo ...).
66. Dating by earliest evidence (store_points: LEAST of census_panel and brand-pattern year) - renamed stores are no longer openings; Dia pattern accepts 'Día'. Rebuild OK. Page 03 numbers now: census 408 -> 639 (+231, +57%), Condis +136 (59%), Dia -33; openings new site 238 / replaced 85 / Clarel 1; donut 50 / 21 / 14 / 1.
67. Takeover check by the user (areas / plausibility): Lidl -> Condis (Gracia) genuine; Mercadona -> Condis (Diagonal Mar) wrong (Mercadona still trades 13 m away) -> rule: previous chain still within 40 m today = new site; Caprabo -> Aldi (Fabra i Puig) genuine but the OSM Caprabo was stale -> store_removals_manual. City stores 676. Full rebuild OK.
68. One-pass audit of all takeovers (user: stop finding errors one by one): 18 of 84 were neighbours (previous grocery still trading) -> rule 'previous grocery gone when the chain appears'; no rebrand left; sensitivity 15/20/29% for 15/25/40 m. Final new site 258, replaced 65, Clarel 1; donut 36 / 16 / 13 / 1. Audit table data/store_openings_audit.csv. Full rebuild + check_quality OK.
69. replaced_premise_type labels shortened: Independent grocery / Regional / franchise brand / Another chain / Same group (Clarel).
70. replaced_premise_type labels: Independent / Regional / franchise / Another chain / Same group (Clarel) (legend width).
71. replaced_premise_type final labels: Independent grocery / Regional / franchise brand / Another of the 10 chains / Same group (Clarel); legend on the right.
72. replaced_premise_type by size, not by franchise (the major chains franchise too): Independent shop 36 / Smaller brand 16 / Major chain 13 / Same group (Clarel) 1.
73. Page 04 data verified (no nulls, totals consistent; 91% of dwellings within 5 min of fresh food at older pace). gis.section_indicators: seccio_key (text, Shape map), fresh_access_class / _order / _color (median older-pace minutes to fresh food: <5, 5-10, 10-15, 15+; red ramp), access_flag (low-income food desert / strict only / older-car-less).
74. Spelling unified to 'color' (user): seed chain_colors.csv (gis.chain_colors, old gis.chain_colours dropped), columns chain_color_hex / opening_color_hex / fresh_access_color / color_hex, docs and scripts; raw data files untouched. Rebuild + check_quality OK. Power BI fx bindings to the old column names must be re-selected.
75. Spelling change reverted at the user's request (Power BI bindings use the old names): back to colour everywhere (chain_colours seed, *_colour_hex, fresh_access_colour); openpyxl calls in make_catalog.py kept as color / fgColor. Rebuild + check_quality OK.
76. access_flag shortened (Food desert / Food desert (strict def.) / Older / no car, far) + access_flag_order for the page-04 table.
77. gis.section_indicators.access_group (scatter legend: Food desert / Older / no car, far / Other sections; strict-only shown as other because the x axis uses the main definition). Quadrant check: bottom-right = the 4 food deserts only.
78. Food-desert threshold kept at 50% (no international standard; the cut was set before seeing the results, so it is not moved to take in one section). Sensitivity: 40% -> 5 sections (+ Torre Baro 8108), 33% (USDA low-access share) -> 6 (+ Baro de Viver 9007), 7,282 / 8,628 residents vs 5,011. Goes to the page-05 method notes.
79. Page 04 scatter dropped (few coloured points, two different concepts, age / cars already on page 02). Replaced by residents over 10 min from fresh food (older pace) by income quarter: gis.section_indicators.residents_fresh_over_10min_est, income_quarter / income_quarter_order (ntile 4). Lowest 25% 10,470 (2.2%), 25-50% 4,062 (0.9%), 50-75% 4,090 (1.0%), highest 25% 14,307 (3.5%); the 4 food deserts are all in the lowest quarter, the 3 older / no car sections all in the highest.
80. Definitions checked against sources: Institut Metropoli (ex-IERMB, renamed 2023) food desert = low availability of fresh healthy food within a 5-min walk in low-income areas (betevé); 400 m radius cited for Vallbona / Torre Baro / Baro de Viver (Nacio Digital, 2026-03-24, 2025 metropolitan food-environment map). No share-of-population or income cut published there: our 50% / q25 / 10 min older pace (~7 min adult) is our own operationalisation. USDA (Food Access Research Atlas): low income = poverty >= 20% or median family income <= 80% of state / metro median; low access = >= 500 people or >= 33% beyond 1 mile urban / 10 miles rural (also 0.5 / 20 mile variants). food_desert_viability.py re-run with the current store list (reference p10 / median residents within 400 m: 11,206 / 19,503; food-desert areas 1,073-3,887, below 99% of existing stores).
81. gis.food_desert_viability (page 04 'why no store opens'): food_desert_viability.py now profiles exactly the flagged sections of the page-04 table (8: 4 food deserts, Baro de Viver strict, Sarria / Pedralbes / Font d'en Fargues) and writes ana.py_food_desert_viability, then builds the dbt model (after_models folder; source added). Residents within 400 m: food deserts 1,073-3,887 vs existing chain stores p10 11,206 / median 19,503 (below 99% of stores); Font d'en Fargues 13,553 (20th percentile) = the exception. Catalogs (EN + ZH) rebuilt; check_quality OK. DASHBOARD_DESIGN page 04 row updated.
82. Fresh-food error found while comparing the definitions: the "Supercor" 250 m from Baro de Viver is a Repsol petrol-station shop (census fuel premise 7 m, OSM Repsol Pg Santa Coloma 71); all other city Supercors are Supercor Exprés (convenience). build_food_access.py: Supercor removed from FRESH_SUPER_RX, supermarket-class premises within 20 m of a fuel premise excluded. Main food deserts 4 -> 5 (+ Baro de Viver 9006, 6,333 residents) = strict; broad 1; 65+ far 7,005. 'Food desert (strict def.)' category now empty. Income quarters: lowest 11,415 (2.4%). Homes within 5 min 91.0% (unchanged). Threshold sensitivity: 40% -> 6, 33% -> 7. Viability, catalogs, MODEL_RESULTS 28, DASHBOARD_DESIGN updated.
83. Page-04 viability bar chart: 400 m is a STRAIGHT-LINE radius around the dwelling-weighted section centre (store centre for the reference), not walking distance - stated in the chart subtitle. Constant lines must use Average of the p10 / median columns (Sum over 8 rows pushed the axis to 0.2M). Title: "Residents within 400 m of each section's centre"; subtitle explains the dashed lines.
84. Page 04 income chart rebuilt in Power BI (by Claude via screen control, user's request): Line and stacked column - columns Residents 65+ far / Residents under 65 far (measures), line Cars per 1000 far (residents-far-weighted cars per 1,000; lowest quarter 294, highest 407), tooltip Share over 10 min pct. DAX in this model needs quoted table names ('sections'[col]). Final colours (user: match the warm dashboard style; Datawrapper: warm hues + one blue complement): 65+ #9C6B30, under 65 #E2CFA6, line slate #3E5C76 linear 2 px; labels only on the line + totals (units None, no background); both y-axes hidden, secondary range fixed 0-600 so the line labels clear the bar totals. Title "Residents over 10 min from fresh food, and their car ownership, by income quarter".
85. Same chart, user's choice: all data / total labels removed, both y-axes back to default ticks (secondary range auto, starts near 250).
86. Page 04 viability bar chart: fx colour (access_flag_colour, purple) removed, bars set to ochre #9C6B30 to match the income chart.
87. Page 04 palette rebalanced (user: no all-ochre, page must be harmonious): map terracotta ramp unchanged (warm); viability bars deep teal #2F6F62; combo 65+ slate #3E5C76, under 65 light slate #B9C6D2, line mustard #C2A23A (teal and mustard reused from the page-03 donut). Cool charts balance the warm map; the warm line echoes it.
88. Page 04 layout (canvas 1920x1080): right column X 884 W 996 for all three visuals - table Y 65 H 248, bar chart Y 330 H 270, combo Y 620 H 420; table header Barri renamed Neighbourhood. No Key findings box (user).
89. Page 04 switchable map (user approved, pbix backed up as supermarket_bcn_backup_before_page4_views_2026-10-19_1942.pbix): dbt gis.section_access_views (1068 sections x 3 views: walk to fresh food / walk to a chain supermarket, older pace min, classes 5/10/15; climb home from the nearest chain supermarket m, classes 5/10/20; same red ramp; dwellings_n for a 100% bar of homes by map class). Homes by class - fresh 92.5/5.9/1.0/0.6, chain 82.8/14.1/2.1/1.0, climb 96.8/1.7/0.9/0.7. The unbuilt fresh_access_bands draft removed. Catalogs rebuilt, check_quality OK.
90. Page 04 in Power BI (screen control, user approved): gis.section_access_views imported (relationship seccio_censal -> sections, many-to-one, both directions; auto nom_barri links deleted); class_label sorted by class_order (class_label_order rejected by Power BI), view_name by view_order; page-2 button slicer copied (not synced) and bound to view_name, single select + force selection; map Location/Legend switched to the new table, 8 class colours = map red ramp; tooltips Neighbourhood / Residents / Median (min or m) / Residents 65+ over 10 min / Independent supermarkets; dynamic title measure [Map title]; layout slicer X30 Y132 W802 H48, map Y190 H740. NOT done yet: 100% summary bar of homes by class under the map (Y 940), right-column layout, save (Ctrl+S).
91. Page 04 summary bar (Power BI): 100% stacked bar X30 Y930 W802 H140, Y view_name (labels off), X dwellings_n as percent of grand total ("Share of homes"), legend class_label (legend off - the map legend applies), minute-class colours = map ramp, labels = percent of total, 1 decimal, dark; min category height 60 px; title "Share of homes in each map class". Still to do: colours of the 4 metre classes (climb view) in this bar, right-column layout check, Ctrl+S.
92. Summary bar: metre-class colours (climb view) set to the map ramp; all three views now use the same 4-step ramp in map and bar. Remaining: Ctrl+S by the user.
93. Page 05 data (dbt): seed chain_list_sources (list source + reference date per chain), gis.store_list_steps (waterfall, signed stores_change computed from the pipeline: 698 listed in the city, -6 by hand, -57 Clarel, -4 closed per locator, +38 census 2024, +7 locators = 676), gis.store_sources (stores per chain, source, date, share confirmed by the 2024 census within 60 m: 567/676 = 84%; Aldi 59%). check_quality: seed added to NO_PK_OK, PK on store_list_steps; RESULT OK.
94. Page 05 redesigned (user: >= 5 charts, new chart types; treemap already used): dbt gis.store_validation_funnel (676 -> 614 any supermarket at the spot in a census -> 587 chain name in a census -> 567 in 2024), gis.food_desert_sensitivity (thresholds 25-75% x strict/main/broad: main = 5 for 45-70%, broad = 1, strict = main from 40%), gis.store_source_by_chain (stacked bar), store_sources + census_2024_premises_n (scatter list 2026 vs census 2024; Aldi 27 vs 17). Catalogs rebuilt, check_quality OK. Planned visuals: waterfall, funnel, stacked bar, line, scatter, table + footnote.
95. Page 05 setup in Power BI (Claude, user asked): pbix backed up (supermarket_bcn_backup_before_page5_2026-10-20_1344.pbix); 5 tables were already loaded, auto relationships to store_sources (stores, chain_years, store_source_by_chain via brand_group) deleted; sort-by columns set (step_label, stage_label, chain_label x2, source_label, definition); new page 'Page 5' with title 'How was the store list built and checked?' (Georgia 32 as page 04). Next: the 6 visuals.
96. Page 05: waterfall dropped (already used on page 03, little information). dbt model / table gis.store_list_steps removed; store-list cleaning goes into the page footnote (698 listed, 57 Clarel drugstores of the Dia group listed as Dia, 10 closed or duplicate, +45 from the 2024 census and locators = 676). Page 05 = funnel, stacked bar, line, scatter, table. Catalogs rebuilt, check_quality run.
97. Page 05 re-planned after a content audit (richness / duplication / fit): funnel and stacked bar dropped (one number, duplicates; models store_validation_funnel / store_source_by_chain and tables removed). Page 05 = line (food_desert_sensitivity), scatter (store list vs census 2024), bar (new gis.osm_completeness: OSM recall of 2024 census food premises in the city, 50 m, market stalls excluded - markets 95%, supermarkets 61%, greengrocers 33%, fishmongers 25%, butchers 23%; replaces the earlier ad-hoc 57% / 10-23% in build_food_access, catalog, MODEL_RESULTS), table (store_sources + added_from_census_2024_n / added_from_locator_n). Title: 'How reliable are these results?'.
98. Page 05 step 0 done in Power BI (Claude): unused tables store_list_steps / store_source_by_chain / store_validation_funnel deleted from the model, data refreshed (store_sources has added_from_* columns), gis.osm_completeness imported (no auto relationship), category_label sorted by category_order, page title 'How reliable are these results?' (Georgia 32). Saved 14:13.
99. Page 05 built in Power BI (Claude): line (Strict slate #3E5C76 2px, Main red #D9675E 6px, Broad mustard #C2A23A dashed; linear; subtitle), bar (OSM completeness, subtitle), scatter (store list vs 2024 census, log axes 10-300, ratio line grey dashed = all chains 676/639, teal markers, labels, subtitle), table (7 columns, Fixed order, totals off, subtitle; seed list_source labels shortened). Subtitle wrap on all. Saved. Left: footnote text box, line-chart constant line label 'Threshold used', table cell shading bar for selected bar (bar chart shows a highlighted bar - clear selection).
100. Tourism re-check on the audited list (analyze_tourism_markets.py re-run, docs/model_v7_* overwritten; old copies in scratchpad): independent mini-markets with tourism robust (1.16-1.22/SD); chains n.s. with HUT beds; chains with Airbnb 1.15/SD p=0.01 only with rent proxy / district FE (was p=0.06) - weak; convenience formats pooled vs Airbnb 1.28-1.73 robust, vs HUT n.s.; Condis openings vs 2017 HUT 1.28 p=0.006 unchanged. MODEL_RESULTS section 25 note added.
101. Page 05 table labels shortened in seed chain_list_sources: list_source Locator / OSM + census / OSM + locator, reference_date as month (2026-10, 2026-06); meanings in seeds.yml. User asked Claude to stop screen control (instructions only).
102. Page 05: store_sources.unconfirmed_n (stores on no official locator and not in the 2024 census: Caprabo 14, Carrefour 8, Lidl 4 = 26 of 676), replacing Confirmed (%) in the table (user). New gis.model_fit (cross-validated AUC of siting model v4 per chain: all 0.64, chains 0.58-0.66) for a proposed extra page-05 chart. check_quality OK.
103. Power BI (Claude, user asked): refresh error 'cyclic reference' on barris - M code was correct (Source -> Navigation -> remove geom); Close & Apply + full refresh then succeeded. Page 05 table: Confirmed (%) replaced by Unconfirmed (unconfirmed_n), new title 'Store list by chain: source, date, stores added and stores unconfirmed' + subtitle. Saved.
104. Page 05: model-fit column chart added (gis.model_fit imported, auto relation to model_drivers deleted, chain_label sorted; X 490 Y 131 W 440 H 440; slate bars, labels, Y 0.4-1, grey dashed 'Chance' line at 0.5; title + subtitle); line chart narrowed to W 440. Table selection cleared. Saved.
105. food_desert_sensitivity definition labels shortened (Strict: 10 chains, markets, fresh shops / Main: + regional chains selling fresh food / Broad: + all mini-markets).
106. Page 05 (Claude, user asked): table column widths reset by removing/re-adding + Census / + Locator / Unconfirmed (renamed, sorted by Chain); line chart series colours restored after the label change (Strict #3E5C76 2px, Main #D9675E 6px, Broad #C2A23A dashed). Saved.
107. osm_completeness labels shortened: Markets / Supermarkets, mini-markets / Greengrocers / Butchers (incl. poultry) / Fishmongers.
108. Labels: osm_completeness 'Grocery stores' (supermarket-class premises incl. mini-markets); chain_list_sources Locator -> Official, OSM + locator -> OSM + official.
109. store_sources: from_official_n / from_osm_n (+ added_from_census_2024_n) = stores_n, for the page-05 table (user: one column per origin). Mercadona / Aldi counted as Official (every store checked against the locator).
110. Page 05 table rebuilt in Power BI (Claude, user asked): Chain | Stores | Official | OSM | Census | Unconfirmed | As of; Source and + Locator columns removed; title 'Store list by chain: where each store comes from' + subtitle. Saved.
111. GitHub preparation (user asked; no commit / push yet): 38 exploratory or one-off scripts (diagnose*, test_*, probe_*, patch_*, main.py ...) and 8 logs moved to archive/ (git-ignored, kept locally); new README.md (portfolio overview: findings, dashboard, pipeline diagram, store audit, limitations, data sources + licences, reproduce, layout); old README -> docs/DATABASE_GUIDE.md (701 -> 676 fixed); .gitignore (envs, dbt target/logs, raw / clean / scraped data, root csv/geojson, pbix, archive, ZH catalog; store_removals_manual.csv published); requirements.txt + dbt_bcn/requirements.txt; scraper.py Alcampo Woosmap key -> env ALCAMPO_WOOSMAP_KEY; scrape_transit.py hard-coded path -> script folder; docs/img/ for page screenshots. git init (main), dry run: 183 files, 2.6 MB. check_quality OK.
112. Screenshots of pages 01-05 in docs/img (PNG), README dashboard section with images, copyright notice + LICENSE (all rights reserved, user's choice). Initial local commit 380ff9e (188 files). Push pending: gh CLI not installed; user to create the empty GitHub repo.
113. Pushed to https://github.com/wawaQbx/barcelona-supermarket-siting (branch main, commit 380ff9e).
