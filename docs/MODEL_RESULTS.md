# Siting models - results (v1 and v2, 2026-10-13)

> **Note (2026-10-15):** the opening dates were completed (section 26: 639 instead of 508 dated city stores, 352 instead of 276 openings 2016-2024).
> All `docs/model_*.csv` files hold the re-run results; numbers quoted in sections 9-25 that depend on openings are the earlier values unless updated - section 26 lists what changed.

Script: `analyze_siting.py` (reads `ana.section_model_table`, `ana.barri_model_table`, `ana.store_counts_section`, `ana.store_counts_barri`).
Outputs: `docs/model_summary.csv` (fit per brand x unit x definition), `docs/model_coefficients_section.csv`, `docs/model_coefficients_barri.csv`.
This is a **first, exploratory pass**: it answers "which definition and unit to use" and gives a first reading of the drivers. It is not the final model.

## 1. Set-up (decisions taken 2026-10-13)

| Decision | Choice |
|---|---|
| Edge effect | Plan A: two outcome definitions now (stores inside the unit; stores within X m of the unit, with and without stores outside the city), compare; the outside ring is to be completed later |
| Outside ring | **1 km** for all chains, 2 km for hypermarkets (3 km is not needed: the largest distance used is 1000 m, 2000 m for hypermarkets) |
| Thresholds | 250 / 500 / 1000 m (2000 m hypermarkets) for sections; 500 / 1000 m for barris |
| Missing Dia outside the city | Both: the gap is stated, and OSM was tried: 24 OSM Dia shops in the 2 km ring, 20 already listed, **4 added** (`point_source = osm_supplement`). See section 5 for the quality check of OSM Dia |
| Unit | Both: 1068 census sections and 73 barris |

Model: Poisson GLM of the store count, robust (HC1) standard errors, predictors standardised (a rate ratio is the effect of +1 standard deviation).
Presence (count > 0) is also scored with a 5-fold cross-validated logistic regression (AUC).
Predictors: ln population density, % aged 65+, % tertiary education, ln disposable income, cars per 1000 residents, ln weekday public-transport departures within 300 m,
ln active ground-floor premises (2024 census), ln area, distance to Placa Catalunya (sections only).
13 sections with company-fleet-distorted vehicle counts are excluded (1055 sections used); one barri without a valid car rate is excluded (72 barris).

## 2. Main results

**Edge effect is small for the coefficients.** Adding the stores outside the city changes the 500 m counts of 83 sections (168 at 1000 m, 36 at 250 m),
but the coefficient vectors with and without them correlate 0.97-1.00 for every chain; at most one predictor changes significance per chain.
The choice of the outcome definition (inside vs. within 500 m) matters far more than the outside stores.

**Section, stores inside (the sharpest test of "where exactly"):** fit is weak (deviance explained 10% for all chains, 2-15% per chain; presence AUC 0.50-0.69).
Exact store position inside a 3.6 ha section is driven mostly by things not in the data (available ground-floor premises, rents, company strategy).
Still, consistent signals across chains:

* **Commercial street fabric** (number of active ground-floor premises) is the most frequent driver: positive for all chains, significant for 6 of 10 (Dia 1.75, Caprabo 2.13, Carrefour 2.02 per SD).
* **Population density** (Mercadona 3.29, Bon Preu 3.20, Consum 2.57, Dia 2.14) and **share of residents 65+** (Mercadona 1.86, Bon Preu 1.60, Caprabo / Consum 1.46) are positive;
  Alcampo is the exception (65+ share 0.42).
* Income has no effect once education and the other variables are in; Consum / Charter is the only chain with a clear social profile (more tertiary education 2.86, lower income 0.51).
* Aldi follows public transport (2.35); Mercadona and Bon Preu favour larger sections (space for a bigger store).

**Section, stores within 500 m (catchment view):** fit is better (deviance explained 3-38%), but the counts of neighbouring sections overlap,
so p-values are too optimistic here. The pattern: fewer stores where car ownership is high (all chains), more in older and better-educated areas
and in commercial streets, and for most chains more towards the centre (Carrefour 0.52, Aldi 0.64 per SD of distance).

**Barri, stores inside:** high deviance explained (90% for all chains) because the store count simply grows with population and area; with only 72 barris and 9 predictors,
the per-chain estimates are unstable (rate ratios up to 9.9) and should not be read individually.

## 3. Recommendation after v1

1. Keep the **census section** as the main unit (enough units, close to a walking catchment); use the barri only for description and robustness.
2. Outcome: use both definitions: inside (location) and within 500 m (catchment); the outside-city stores can stay in (they barely change results).
3. Next model improvements: negative-binomial (overdispersion), standard errors clustered by barri (spatial dependence), competition variables
   (other chains within 500 m), and the ground-floor premises vacancy and rent variables.
4. Completing the 1 km outside ring is useful mainly for sections at the city edge; it is not urgent given the stability shown above.

## 4. Caveats

Correlation, not causation. Store lists from OSM (Mercadona, Caprabo, Lidl, Aldi, Carrefour) may miss stores. Counts within X m overlap between neighbouring sections.

## 5. Quality of the OSM Dia data (checked against the official list and the commercial census)

* Inside the city OSM has 51 Dia shops vs. 130 in the official list: **coverage 39%**.
* 44 of the 51 (86%) are within 150 m of an official Dia (37 within 50 m; median offset 15 m): positions are good.
* The 7 without an official match (14%) are **stale**: none is a Dia in the 2024 census; 4 were "DIA MARKET" in the 2019 / 2022 census (closed since), 3 have no Dia premise at all.
  None of them has an OSM `check_date`.
* The 4 shops added outside the city (Santa Coloma de Gramenet area; the city census cannot check them): 1 has a 2026-04 `check_date`, 3 come from one 2020-era OSM edit
  without check date. Expected error from the in-city rate: about 0.5 of the 4 may be closed. Effect on the models: they touch the 500 m counts of a few edge sections only.

## 6. v2: clustered errors, competition, vacancy, spatial check (`docs/model_v2_*.csv`)

Changes: outcome = stores inside the unit; Poisson with standard errors **clustered by barri** (sections) or district (barris), 95% intervals reported;
new predictors: **competition** = ln(1 + stores of the other chains within 500 m; 1000 m for barris) and **vacant ground-floor share**.

* **Over-dispersion:** a negative-binomial fit gives alpha ~ 0 for every chain except Alcampo, so Poisson is adequate (inside counts are almost all 0 or 1).
* **Spatial autocorrelation of residuals:** Moran's I (neighbours within 500 m) between -0.03 and 0.00 for all chains: no remaining spatial clustering, the section results are not inflated by it.
* **Fit:** McFadden pseudo-R2 0.02-0.13 per chain at section level; presence AUC 0.57-0.71, **Lidl 0.40 (no predictive power)**.
* **Competition:** not significant for 9 of 10 chains; Alcampo 0.60 (avoids areas with many other chains), Aldi 1.71 (p = 0.06, tends to cluster near others).
* **Stable after clustering:** density (Mercadona 3.72, Bon Preu 3.51, Consum 2.50, Caprabo 2.22, Dia 2.09), 65+ share (Mercadona 1.83, Bon Preu 1.56, Consum 1.49, Caprabo 1.45),
  active premises (Dia 1.79, Caprabo 1.99, Carrefour 1.93, Condis 1.41), transit (Aldi 2.22, Dia 1.24), larger sections for Mercadona (5.19) and Bon Preu (2.76); Mercadona avoids streets with many vacant premises (0.72).
* **Weakened after clustering:** Consum / Charter income 0.54 (95% CI 0.26-1.10, p = 0.09): the "lower income" part is no longer significant; the education effect stays (2.73, CI 1.28-5.83).
  Education and income correlate 0.86 across sections, so the two coefficients are hard to separate. Descriptively, Consum stores per 100 sections are 4.2 where education is far below what income predicts
  and 9.1 / 6.8 in the two upper quarters: Consum favours **educated, middle-income** areas (e.g. Sant Pere / Santa Caterina / la Ribera, Vila de Gracia, Sagrada Familia) rather than the richest ones.
* Alcampo (Mi Alcampo + hypermarkets mixed, 28 stores) gives extreme, unstable estimates; split the formats before interpreting it.
* Barri level (72 units, clustered by 10 districts): too few units for 10 predictors; estimates such as Carrefour 7.5 or Bon Preu income 5.9 are not reliable.

Next: split Alcampo / Carrefour by format; brand-specific competition (own chain vs. others); compare 2016 -> 2024 openings (new stores only) to separate location choice from history.

## 7. v3: format split, own vs. other chains, openings 2016-2024 (`docs/model_v3_*.csv`)

**Format split** (the user's `store_type` in the official list): Alcampo hypermarkets 5 city stores / Mi Alcampo 25; Carrefour convenience 21 / supermarket 8.
Groups with fewer than 15 stores are not modelled (hypermarkets, Carrefour supermarkets): too few events for 9 predictors.
Mi Alcampo avoids older areas (65+ share 0.52) and large sections (0.24): a small urban format in dense, younger streets. Carrefour convenience follows commercial streets (active premises 1.91).

**Competition split.** Ring = stores within 500 m but outside the section (2000 m for hypermarkets), so the store being explained is never in its own predictor.
In 13 of 14 chain models the OWN-chain rate ratio is below 1 and the OTHER-chains ratio mostly above 1:
chains **space out their own stores** (avoid cannibalisation) and **locate near rivals** (shared shopping streets).
Significant: Lidl own 0.35; Aldi own 0.44 / others 2.27; Dia own 0.69 / others 1.34; Condis (2014 network) own 0.69 / others 1.59; Consum (2014 network) own 0.64 / others 2.51.

**Openings.** 344 city stores were first seen after the 2014 census: 252 new sites, 92 takeovers of a food premise (5 former DIA MARKET, Suma, Coaliment, Simply ...),
57 Clarel -> Dia conversions (excluded from the opening models: the site choice was made for Clarel). Predictors of competition use the network that existed in 2014.
* Openings are less predictable than the existing network (all chains: pseudo-R2 0.03 vs 0.06, AUC 0.59 vs 0.66); the one robust driver is commercial street fabric (1.34).
* Mercadona is the clearest recent strategy: dense (5.27), older (2.34), large sections with room for a big store (7.64); same on new sites only.
* Consum new openings: lower-income areas (0.44) away from other chains (0.70), the opposite of its 2014 network (near rivals 2.51).
* Dia's opening model is based on 15 stores; Lidl, Aldi, Bon Preu, Carrefour formats have too few openings to model.
* Several models have fewer than 10 events per variable: treat single coefficients as indicative; trust signs repeated across chains.

Caveats: only stores still open today are seen (closures 2014-2024 are invisible: survivorship); predictors are measured 2022-2026, after many openings;
"first seen" depends on the brand name in the census (hypermarkets inside shopping centres may be dated late).

## 8. Correction: section area and density are almost the same variable (checked 2026-10-13)

Census sections are drawn to hold a similar number of residents (median 1,532; 90% between 1,077 and 2,293), so a large section is a thinly populated one:
corr(ln area, ln density) = -0.95, VIF 15.0 (area) and 14.3 (density). With both in the model, "density at fixed area" really means "more residents",
and the two coefficients are hard to separate. A re-specification with **ln(population) as offset** (= stores per resident) and density only
fits as well (AIC within +-8) and changes the reading:

| Chain | density, v1-v3 spec (with area) | density, per-resident spec (offset ln population) |
|---|---|---|
| ALL | 1.56 | 1.06 (n.s.) |
| Dia | 2.14 | 1.60 (p < 0.001) |
| Consum / Charter | 2.57 | 1.68 (p = 0.01) |
| Bon Preu / Esclat | 3.20 | 1.32 (n.s.) |
| Mercadona | 3.29 | **0.78** (p = 0.05) |

So per resident, Dia and Consum prefer dense sections, while Mercadona prefers **less dense, larger** sections (space for a big store); the earlier
"Mercadona favours dense areas" reading came from the collinear pair and is withdrawn. Next model round: use the offset specification throughout.
Also: the largest sections (3025 la Marina del Prat Vermell 1,424 ha, 5001 802 ha) are mostly port, Collserola or parks, so total area is a poor measure of
where people live; a built-up / residential area would be better.

## 9. v4: cadastre and traffic, time ordering, before / after, natural experiment (`docs/model_v4_*.csv`)

Specification from here on: ln(population) as offset (stores per resident), area dropped (section 8). Errors clustered by barri.

**Cadastre and traffic blocks** (joint Wald test of each block, model also contains the base predictors):

| Group | Cadastre block p | Traffic block p | AIC change | AUC base -> full |
|---|---|---|---|---|
| ALL | < 0.001 | 0.59 | -7 | 0.64 -> 0.64 |
| Condis | 0.015 | 0.07 | -3 | 0.57 -> 0.58 |
| Caprabo | 0.006 | 0.85 | +4 | 0.67 -> 0.67 |
| Mercadona | < 0.001 | 0.24 | **-18** | **0.62 -> 0.73** |
| Dia, Consum, Bon Preu | 0.10-0.21 | 0.33-0.64 | +7 to +8 | no gain |

* Cadastre matters: stores sit where the **ground-floor commercial floor share** is higher (all 1.16, Mercadona 1.97, Consum 1.26), in **newer buildings**
  (all 0.89, Mercadona 0.58, Condis 0.82) and where **cadastral value is lower** (all 0.80, Dia 0.60, Caprabo 0.49): space and cost of the premises.
* Traffic (main-road length, pedestrian streets, counted traffic) adds nothing once the base variables are in. Motorway length was dropped:
  only 17 sections have one and Caprabo / Bon Preu have no store there (complete separation gave rate ratios of 0.02).

**Time ordering.** Openings 2016-2024 (Clarel conversions excluded) explained with predictors measured BEFORE them
(`ana.section_baseline_2015`: Padro 2015, income 2015, 2014 census, 2014 network) instead of 2022-2026 values:

| Openings, all chains | 2022-2026 predictors | 2014-2015 predictors |
|---|---|---|
| active premises | 1.28 (p = 0.001) | 1.08 (p = 0.31) |
| 65+ share | 1.16 (p = 0.04) | 0.93 (p = 0.23) |
| tertiary share | 1.38 (p = 0.01) | 1.01 (p = 0.97) |
| AIC | 1335 | 1341 |

Most associations of the openings with today's neighbourhood **disappear when the neighbourhood is measured before the opening**:
they partly describe what happened after the stores arrived (reverse causality, see the event study) or neighbourhood change since 2015.
Consum's "lower income" effect (0.26) also vanishes (1.02). Mercadona's time-ordered model has 18 openings for 10 predictors (EPV < 2): not interpretable.

**Before / after (event study).** Active premises within 150 m of each store site (own premise excluded), site and edition fixed effects,
reference = last census before the store appears; controls = 243 sites of stores already open in 2014:

| New sites (201) | change vs. reference |
|---|---|
| 2+ censuses before (pre-trend) | -1.2% (CI -6.9 to +4.9) |
| census of opening | **+5.1%** (p = 0.03) |
| next census | **+9.1%** (p = 0.007) |
| 2+ censuses after | **+11.9%** (p = 0.01) |

No pre-trend (supermarkets did not pick streets that were already growing), then commerce around a new site grows by about 12%:
**a new supermarket attracts other shops**: the "active premises" predictor is partly an effect of the stores. Takeovers of existing food shops (86 sites) show no change
(-/+ 2%, all n.s.), as expected when no new anchor arrives.

**Natural experiment (L10 Sud, Foc / Foneria, opened 8 Sep 2018).** 17 sections gained metro access within 500 m.
Openings: treated 0 before (2014-2016) -> 4 after (2017-2024); comparable sections without metro (87): 3 -> 15.
Difference in differences +0.025 openings per section-year, **randomisation p = 0.43** (0.21 against all sections): no detectable effect.
The ratio estimate is not usable (zero openings before in the treated group). With 17 sections the design can only detect very large effects; it is reported for completeness.

Overall reading after v4: what reliably predicts where supermarkets are is the supply of suitable, affordable ground-floor space (commercial floor share, newer buildings,
lower cadastral value) and spacing from the own chain; neighbourhood demographics measured before the openings say little about where new stores went,
and part of the "commercial street" association is created by the supermarkets themselves.

## 10. Why are buildings newer? (`docs/model_v4_building_origin.csv`)

"Newer" is relative: the newest tenth of sections still has a mean building age of ~40 years (la Verneda, el Besos, la Marina de Port, Sant Andreu, Navas =
1960s-80s planned housing estates; Diagonal Mar / Poblenou = 2000s redevelopment). Mean age is unrelated to population growth 2015-2026 (corr 0.04).
New section columns: building shares by period (cadastre: before 1941 / 1951-1980 / after 1990) and PGM zoning shares (verified keys 12 old town,
13 densification, 15 conservation, 18 specific volume = planned estates, 20 detached, 22 industrial incl. 22@).

Three specifications (all with the base predictors, commercial floor share and cadastral value): A mean age only; B construction period + zoning + population growth
2007-2026 instead of mean age; C both.

* Once period and zoning are in (C), the mean-age effect weakens: all chains 0.89 (p = 0.02) -> 0.94 (n.s.); Mercadona 0.55 (p = 0.005) -> 0.72 (n.s.).
  "Newer buildings" is mostly a summary of **when and under which plan** the area was built, not an effect of its own.
* No single period / zoning variable replaces it robustly, and A has the lowest AIC for most chains: mean age is the most economical summary; the detailed
  variables are too correlated with each other to separate with 41 Mercadona stores.
* What survives every specification: **commercial floor share** (all 1.14, Mercadona 1.93, Condis 1.14) and **lower cadastral value** (all 0.77).
* Chain profiles from the zoning shares: Dia favours the old town (1.31) and avoids planned estates (0.82); Caprabo avoids the old town (0.70);
  Consum is more frequent where much was built after 1990 (1.62, p = 0.05). Mercadona's detached-zone ratio (0.00) is complete separation (no store there), not an effect.
* Next step if needed: building-level data (Catastro INSPIRE buildings: year of construction and use per building) to test the age of the store's own building.

## 11. v5: the store's own building (Spanish cadastre INSPIRE; `docs/model_v5_buildings_*.csv`)

Data: 69,911 cadastral buildings of Barcelona (year of construction, use, footprint, floors; `raw.cad_inspire_buildings`, `prepare_inspire_buildings.py`).
675 of 701 city stores and 54,379 other active ground-floor premises of the 2024 census (controls) matched to their building (`ana.site_buildings`).
Design: **case-control within barri** - logit of "store vs other premise" with barri fixed effects (only comparisons inside the same barri),
errors clustered by census section. Odds ratio (OR) > 1 = a supermarket is more likely in such a building than another shop in the same barri.

| | median year | built after 1980 | median footprint | residential building |
|---|---|---|---|---|
| control premises | 1961 | 17% | 344 m2 | 85% |
| all stores | ~1969 | 16-42% by chain | 418 (Dia) - 1,672 (Mercadona) m2 | 56-96% |

Odds ratios, all 675 stores (reference: built before 1941): built 1961-1980 **1.87**, 1981-2000 **1.63**, after 2000 **2.25**;
footprint **1.60 per SD**; residential building **1.88**; floors 0.99 (no effect).
* **Footprint is the one driver shared by every chain** (Mercadona 2.58, Consum 2.66, Caprabo 2.37, Bon Preu 2.00; Condis 1.17 and Dia 1.19 weaker: small formats).
* Building age matters beyond footprint for Caprabo (after 2000: 5.4), Consum (1961-1980: 3.5) and the network as a whole; **not for Mercadona** once footprint is in
  (all period ORs n.s.): Mercadona needs a large ground floor, wherever its age comes from.
* Dia sits in older buildings (no premium for new ones, after 2000: 0.87) with small footprints: the neighbourhood shop of the old fabric.
* New sites 2016-2024 (192): after-2000 buildings 2.95, footprint 1.62. But only 19 of the 192 opened in a building completed in the 10 years before:
  new stores mostly reuse existing large ground floors rather than follow new construction.
* Why "newer" works: pre-1941 fabric (old town, Gracia, early Eixample) has narrow, small ground floors; the 1960s-80s blocks and later buildings were built with
  large commercial ground floors. So building age is mainly a proxy for the **size of the available ground floor**, which the section-level model could only see indirectly.
Caveats: footprint is the whole building, not the shop; controls include every kind of premise (bars, offices, empty-shop conversions); 26 stores unmatched.

### 11.1 Robustness of the period effects (checked 2026-10-13)

Cell counts are small (Caprabo: 9 stores in pre-1941 buildings = the reference, 9 in post-2000 ones), so period odds ratios are imprecise.
* Caprabo: robust in **direction** - continuous year 1.19 per decade (CI 1.08-1.31), also without footprint (1.28); the size "5.4 for after 2000" (CI 1.9-15.9) is not.
* Consum / Charter: **not robust** - continuous year 1.07 (CI 0.96-1.21) once footprint is in; against a 1941-1960 reference the 1961-1980 ratio is 2.75 (CI 0.89-8.45).
  43 of its 68 stores are in 1961-1980 blocks, but this is not clearly more than other shops of the same barris. The earlier statement is withdrawn.

## 12. Barri building stock and the chains (`docs/model_v5_barri_building_stock.csv`, `docs/model_v5_store_building_percentiles.csv`)

Building stock of a barri = buildings that hold its other ground-floor premises (2024). Smallest median footprints: la Barceloneta 188 m2, el Coll, Verdun,
la Trinitat Vella, Vila de Gracia 220, Sant Pere / Santa Caterina 230; largest: Ciutat Meridiana, el Besos, el Bon Pastor, la Guineueta 1,711,
la Marina del Prat Vermell, Vila Olimpica 2,767, Diagonal Mar 4,287 m2. Small-floor barris are both very old ones and 1960s hillside estates (el Coll, Verdun, Can Baro).

* Across barris the links are weak (Spearman |rho| <= 0.33): Dia's share of stores falls where ground floors are large (-0.33), Mercadona's rises (+0.26 with the share of buildings > 1,000 m2);
  stores per 10,000 residents are higher in old-fabric barris (+0.27 with the pre-1941 share).
* Thirds of barris by footprint: small-floor barris Dia 23% / Mercadona 5% of stores; large-floor barris Dia 17% / Mercadona 9%.
* **Inside its own barri a supermarket picks one of the biggest buildings**: median footprint percentile Lidl 89, Aldi 89, Mercadona 87, Caprabo 81, Consum 81,
  Bon Preu 75, Dia 64, Condis 62 (50 = typical shop building of the barri).
* The constraint binds in the old / small-floor fabric: there stores sit at the 77th percentile of their barri, in large-floor barris at the 56th
  (almost any building is big enough). Building age percentiles are lower (56-78): size is chosen, age comes along.

## 13. v6 data additions (2026-10-13)

* **Ring around the city** (`fetch_ring_stores.py`, `fetch_ring_osm.py` -> `raw.store_ring_stores_2km`): official locators (Condis 374, Consum / Charter 119, Bon Preu / Esclat 49,
  Alcampo 46) and OSM (409) in the city box widened by 2 km. Of 186 chain stores outside the city within 2 km, **179 (96%) were already in the store list**;
  5 were added. The earlier statement that the 263 outside stores were "only the corners of the box" was wrong: they already cover the 2 km ring (129 within 1 km, 211 within 2 km).
* **Premises asking prices** per barri 2008-2011 (`raw.hou_locve_preu_oferta_locals_2008_2011`, median 2,277 EUR/m2) - the only open premises price series.
* **Pacified streets** 2020-2022 (Eixample axes) and **pedestrian-priority streets** 2023-2026 (`raw.trf_streets_*`).
* Not available as open data: commercial rents or listings (portal listings are behind anti-bot protection and were not scraped), footfall / mobile-phone data,
  historical TMB timetables (needed for a Nova Xarxa bus natural experiment).

## 14. What changes around a new supermarket (`docs/model_v6_substitution.csv`)

Event study of 201 new sites vs 243 legacy sites, by premise type within 150 m (site and edition fixed effects):

| Type | pre-trend | 2+ censuses after |
|---|---|---|
| other daily food shops (bakeries, greengrocers, small grocers) | +3% (n.s.) | **+18%** (p = 0.02) |
| other retail | +1% (n.s.) | **+18%** (p = 0.01) |
| restaurants and bars (2016+) | -4% (p = 0.06) | +1% (n.s.) |
| services and others | -2% (n.s.) | +8% (p = 0.07) |

No evidence of substitution: small food shops **increase** after a supermarket opens - complementarity (shared footfall), not crowding out.

## 15. Supermarket closures (`docs/model_v6_closure_rates.csv`, `model_v6_closure_model.csv`)

Supermarket-class premises of the 2019 and 2022 censuses without a supermarket premise within 20 m in the next census (closure or relocation > 20 m):
independents 10.9%, Dia 12.1%, Carrefour 9.4%, Mercadona 9.0% (likely relocations), Caprabo 6.6%, Consum 3.4%, Condis 2.7%, Lidl / Aldi 0%.
Chain premises close half as often as independents (OR 0.51). Closures are more frequent in higher-income sections (OR 1.15 per SD); competition within 300 m,
new chain openings nearby, building size and age show no effect - closures look driven by rents and business decisions, not by measurable competition.

## 16. Site choice - conditional logit (`docs/model_v6_site_choice.csv`)

Each of 277 stores opened 2016-2024 (new sites and takeovers) chose its site among itself and 49 randomly sampled ground-floor premises of the city
(McFadden: sampling alternatives keeps the estimates consistent). Odds ratios per SD, all chains:
**footprint 1.47**, newer building 1.27 per SD of age, residential building 1.24, **farther from the chain's own 2014 stores 1.53**,
**fewer shops in the section in 2014 0.76**, other chains within 500 m 1.14 (p = 0.08); demographics of 2015 n.s.
Chains: Condis = spacing from its own stores (2.44) and younger areas; Consum and Mercadona = large footprint (2.41, 2.85);
Caprabo and Mercadona = next to other chains (2.73, 2.19). New stores go to big premises away from their own network and to sections that were less commercial in 2014
(fill gaps), consistent with the event study (commerce then grows around them).

## 17. Out-of-time prediction (`docs/model_v6_holdout_2024.csv`, `model_v6_predicted_gaps.csv`)

Trained on openings first seen 2016-2022 with pre-2016 predictors, tested on the 69 openings of the 2024 census: AUC 0.58-0.60 (Poisson), 0.54 (gradient boosting);
the top 10% predicted sections captured 23% of the 2024 openings (random: 12%) - a two-fold lift, but most openings remain unpredictable from area data.
The two new variables (premises price 2011, pedestrian-priority streets) are n.s. and lower the out-of-time AUC slightly (0.60 -> 0.58).

## 18. Methods comparison (`docs/model_v6_ml_spatial_cv.csv`, `model_v6_slx.csv`)

* Store present in a section: logit AUC 0.65, random forest 0.63-0.64, gradient boosting 0.60-0.61, with random or spatial (barri-grouped) cross-validation alike.
  Machine learning does not beat the logit: the missing information is in the data (premise availability, rents, company decisions), not in the functional form.
  Permutation importance: active premises, 65+ share, population, commercial floor share, transit, cadastral value.
* SLX (spatial lags of the predictors, neighbours within 750 m): jointly significant for all chains (p = 0.001) and Dia, but AIC worsens for every group -
  neighbourhood averages add little beyond the section itself.

## 19. Natural experiment 2: pacified streets (Eixample, from 2020 Q3; `docs/model_v6_pacified_streets.csv`)

31 sections along the pacified axes vs 142 other Eixample sections. Pre-trend 2016-2019 +1.2% (p = 0.76; parallel trends hold).
Active premises: DiD **+1.8%** (CI -3.4 to +7.3, p = 0.50). Supermarket openings 3 -> 5 vs 24 -> 14, randomisation p = 0.24. No detectable effect within 2024.

## 20. Walking access (food deserts; `build_food_access.py`, `ana.py_section_food_access`)

Network walking distance (OSM streets, motorways excluded) from every residential building (dwelling-weighted) to the nearest chain supermarket, stores outside the city included.
Median walk **171 m**; about **65,000 residents (3.8%) live more than 500 m** from one (13,100 aged 65+). (Updated 2026-10-15 with the corrected store list; before the corrections: 174 m, 72,000 / 4.2%.) Concentrated on the hillsides
(Vallcarca, el Carmel, la Font d'en Fargues, Sant Genis, Vall d'Hebron, Torre Baro, Vallvidrera) and in low-density Sarria / Pedralbes; Baro de Viver is cut off by motorways.
(First version: 7 sections combined >50% of dwellings beyond 500 m with an old or car-less population; replaced by slope-aware tests, section 29.)

## 21. Store-list corrections (2026-10-13) - all results above were re-run after these

1. **57 "Dia Market" entries of the Dia locator are Clarel drugstores**, not supermarkets: no Dia-named premise within 60 m in any census, a Clarel within 60 m in 2024 (56 of 57),
   the nearest 2024 premise a drugstore, bar or dry-cleaner. Excluded (`ana.store_points_excluded`). Dia in the city: 130 -> 73 listed. The earlier "57 Clarel -> Dia conversions"
   came from this error and is withdrawn: Dia opened only 16 stores 2014-2024 and its census premises fell from 107 (2014) to 85 (2024) - a shrinking network.
2. **Condis coordinates**: by address (street + door number) 50 Condis stores (and 1 Consum) are confirmed by a Condis premise of the 2024 census, but the locator coordinates
   are off by a median 80 m (up to ~150 m). Coordinates replaced (`check_store_addresses.py`, `raw.store_coordinate_corrections`).
3. **Missing stores**: chain supermarkets of the 2024 census without a listed store of the chain within 150 m were added (`point_source = census_2024_supplement`):
   Caprabo 28 (OSM covers ~70%), Condis 18, Dia 11, Carrefour 9, Consum 4, Alcampo 3, Mercadona 2, Aldi 2, Bon Preu 1, Lidl 1. City stores: 701 -> 723.
4. Validation of every city store (`ana.store_list_validation`, rebuilt automatically): chain name confirmed within 60 m in 2024 for 67-88% of each chain's stores;
   most others are coordinate offsets, stores opened after the 2024 fieldwork or franchisees under their own sign. Aldi has the most doubtful entries (7 of 21: 2 at Mercadona sites, 3 vacant in 2024).

## 22. Answers to specific questions (after corrections)

* **What was at the site before a new store** (previous census, within 15 m; 273 openings): supermarket 17, other food shop 19, vacant premise 31, no activity / no information 23,
  other businesses ~100 (home goods, restaurants, services, "other"), no premise recorded 82 (new buildings, non-commercial ground floors or coordinate offsets).
* **Aldi** (entered the city 2017-2019; census premises 0, 0, 4, 9, 20 in 2014-2024): its sites were car dealers, car rental, parkings / garages, a municipal depot, a bingo hall,
  a driving school - large non-shop ground floors (median building footprint ~1,100 m2) in central, well-connected, highly educated areas, next to rivals and ~900 m from its own stores.
* **Mi Alcampo** sits in the most expensive sections of any chain (cadastral value 1,103 vs 905 EUR/m2 city median; premises asking price 2011: 2,302 vs 2,051; tourism 2.7x),
  but its sites were already small supermarkets (Simply / Simply Basic of the same group, Coaliment, Coviran, independents, Condis Express): conversions and franchises inherit
  central premises; the format is small (median footprint 451 m2) with high sales per m2. It is not a free choice of the centre against rents.
* **Mercadona and cars** (rate ratio 0.46-0.71 depending on controls): alone, car ownership has no link with Mercadona (1.04); the negative ratio appears only when income is held
  constant (cars and income correlate 0.62). Read: among areas with the same income, Mercadona is more frequent where car ownership is lower than income predicts (denser, central),
  i.e. not a car-oriented location; fragile (43 stores).
* **Consum avoiding rivals in new openings** (0.69, p = 0.03): not robust - 0.79 (n.s.) on new sites only, 0.75 (p = 0.08) with time-ordered predictors, 1.08 (n.s.) in the site-choice model.
* **Vehicles** (`ana.motorization_section`): 471,498 cars, 278,508 motorcycles + mopeds, 54,360 vans / trucks. Cars per 1,000 residents: Sarria-Sant Gervasi 371, les Corts 341 ...
  Ciutat Vella 137; two-wheelers highest in Sarria-Sant Gervasi (271) and Ciutat Vella (201). Across sections cars correlate with income (0.62) and inversely with density (-0.41),
  barely with transit (0.08). 13 sections are distorted by company fleets (611-1,886 cars per 1,000; la Marina del Prat Vermell, les Corts, Barri Gotic) and are excluded from models.

## 23. Food deserts with slope, fresh food and why no supermarket opens (`build_food_access.py`, `food_desert_viability.py`)

Walking time now uses terrain (Copernicus GLO-30, street level approximated by a 90 m minimum filter) with Tobler's hiking function (round trip), at adult and older pace (70%).
Destinations: chain supermarkets, any supermarket-class premise, municipal markets, and fresh food (chain supermarkets + markets + greengrocers, butchers, fishmongers,
poultry shops; convenience stores and independent mini-markets do not count as fresh food).

**Low-income food deserts** (half the dwellings more than 10 min from fresh food at older pace, income in the bottom quarter): **4 sections (range 1-5), 5,000 residents**
(main = middle definition of fresh food, section 28)
(corrected 2026-10-16, see section 27; the first version had 11 sections / 17,100 residents because of false slopes in the surface model).
They include **Torre Baro 8109, Vallbona 8116, Baro de Viver 9006** - exactly the three barris that the Institut Metropoli classifies as Barcelona's food deserts
(betevé report; "70 of 73 barris" have a rich fresh-food supply) - plus la Marina de Port 3038 and Sant Genis 7090. Ciutat Meridiana, les Roquetes and el Carmel are
NOT food deserts after the correction (their long walking times were an artefact of the slope data).
Torre Baro 8109: 34 min to a chain supermarket (48 min at older pace) and an 80 m climb home; Baro de Viver: convenience stores 1.4 min away but fresh food 12 min (older pace),
in Santa Coloma or Bon Pastor - matches the report (3 convenience stores, no fresh meat, fish or vegetables; a 90-year-old walks 25 min to Santa Coloma).

**Why no supermarket opens there** (400 m catchment vs the existing stores): residents 1,070 (Torre Baro), 1,430 (Vallbona), 2,670 (Baro de Viver) vs 11,190 for the 10th
percentile of existing stores (median 19,490); spending power 14-37 M EUR vs 232 M (p10); only 0-1% of existing stores have such small catchments. Terrain relief 95 m in Torre Baro
(median store 15 m), few large buildings with shops (0-4 vs 12), incomes ~12,700-13,700 EUR. Les Roquetes and el Carmel have enough residents (12-14k) but low incomes, steep
streets (54-57 m relief) and few large ground floors (2-3): there the constraint is premises and slope, not population.

## 24. Large ground-floor premises: who uses them and how they change hands (`large_premises_turnover.py`)

Premise size proxy = building footprint / number of 2024 premises in the building; large = >= 600 m2 (3,950 of 68,024 premises).
Over-represented among large premises (location quotient): parking / garages 4.5, education 4.2, culture / leisure / bingo 3.5, gyms 2.6, car dealers / repair 1.7,
health 1.6, supermarkets 1.5, banks 1.4; under-represented: other food shops 0.15, clothing 0.29, other retail 0.41, restaurants 0.59 (furniture / DIY 0.69: big-box formats are outside the city).
30% of the large premises linked 2016 -> 2024 changed activity. Real flows into supermarkets: former furniture / household shops 8, banks 6, other retail 6, no activity 11,
car businesses 3 (the 156 "other food -> supermarket" cases are a classification change: 2016 had no supermarket class). Closing bank branches went to vacancy (11),
other services (6) and supermarkets (6); car dealers / workshops to vacancy (14), storage (8), gyms (5), supermarkets (3).
Baro de Viver: its 9 vacant premises (2024) were a precision-grinding / car-repair workshop, an electricity substation, a warehouse, a construction firm, a church,
a bakery later used by social services - mostly industrial or utility spaces at the edge, not shop units in the residential core; active premises fell from 89 (2016) to 71 (2024).

## 25. Tourism, foreign residents and municipal markets (v7; `analyze_tourism_markets.py`, `docs/model_v7_*.csv`)

New data (2026-10-15): Padro nationality 2015 + 2026 (`ana.pop_nationality_section`), Inside Airbnb 2026-09 listings + review dates, licensed tourist flats 2026 and
2017, hotels (`ana.section_tourism`, `ana.section_airbnb_reviews_year`), the 39 food markets (`ana.market_supermarkets`). Main specification as v4 (Poisson,
ln(population) offset, barri-clustered errors, rate ratio per +1 SD); every result was re-estimated while control blocks are added one at a time
(S0 none, S1 demand, S2 + transit and premises, S3 + distance to the centre = v7, S4 + cadastral value as a rent proxy + building stock, S5 + district fixed effects),
with alternative measures and alternative outcomes (`model_v7_robust_*.csv`).

**1. Tourism - who serves tourists is the INDEPENDENT supermarket, not the chains.**
- Chain stores as a whole: positive raw association with tourism (1.10-1.17 per SD), which disappears once density, transit, commercial premises and centrality
  are controlled (0.94-1.09, never significant, for HUT beds in the section, HUT beds within 300 m and Airbnb listings). Tourism is strongly tied to the centre
  (Spearman -0.72 / -0.81 with distance to Placa Catalunya), so the test is "tourism on top of centrality".
- Rent offset (high rents in tourist areas cancelling tourist demand): adding the cadastral value as a rent proxy does not reveal a hidden positive tourism effect
  for chains (HUT 0.94; Airbnb 1.12, p = 0.06). Weak test: there is no open commercial-rent data, and the cadastral value mostly tracks income (Spearman 0.83).
- Convenience formats of all chains pooled (91 stores: Carrefour Express / small Market, Condis convenience, Bon Preu ...): more of them where Airbnb listings are
  dense, robust to every control block (1.31-1.56 per SD, p <= 0.007), but NOT with licensed tourist-flat beds (1.07-1.19, n.s.); within the chains that run both
  formats, a store is not more often the convenience format where tourists stay once distance to the centre is controlled (odds ratio 0.9-2.0, n.s.).
  Reading: suggestive for small formats, not established; the two tourism measures disagree (Airbnb also counts seasonal and unlicensed rentals).
- Independent supermarket-class shops of the 2024 census (1,684 premises "Autoservei / Supermercat" with no chain store within 50 m): clearly more where tourists
  stay, in every specification (HUT beds 1.17-1.44, Airbnb 1.17-1.43, p < 0.001; with district fixed effects 1.17), so tourist grocery demand is met by
  independent mini-markets. Openings of chain stores 2016-2024 are not predicted by the 2017 tourist-flat beds (all chains 1.01), except Condis
  (1.28 per SD, p = 0.005, after the dating completion of section 26): Condis opened more where tourist flats were dense in 2017.

**2. Foreign residents - fewer chain stores where the share of non-EU residents is high, not explained by income, centrality, buildings, Ciutat Vella or household size.**
- All chain stores per resident 0.78 per SD (S3), 0.82 with cadastre + buildings, 0.82 with district fixed effects, 0.85-0.88 without Ciutat Vella,
  0.87 per DWELLING instead of per resident (p = 0.03); the non-EU share is almost unrelated to persons per dwelling (Spearman 0.07). VIF 3.2 (moderate collinearity).
- By chain: Lidl 0.38-0.42 (robust), Caprabo 0.70-0.78, Condis 0.70 -> 0.82 with district fixed effects (no longer significant), Carrefour 0.59 (p 0.04-0.07).
- Time-ordered (after the dating completion of section 26): openings 2016-2024 of Condis are rarer where the non-EU share was high in 2015 (0.62, p = 0.02);
  Carrefour no longer (0.90, p = 0.59; it was 0.60 with the incomplete dates) - so the time-ordered evidence rests on Condis alone.
- NOT a substitution by independent shops: independent supermarket-class premises are as frequent as elsewhere (0.95-1.0), and other daily-food shops are also
  rarer (0.77 per resident, 0.88 per dwelling). The chain share of supermarket-class shops is lower (odds ratio 0.83, p = 0.03) because chains are fewer, not
  independents more. What explains it is open (not tested): lower spending per person at the same mean income, more shopping outside the neighbourhood,
  chain choice of sites, measurement at section level (ecological: it says nothing about individual residents).

**3. Municipal markets - chains sit AT the markets by design, and the fresh-food shops around markets did better than around comparable places.**
- 22 of 39 food markets have a chain store within 50 m and 30 within 100 m. If markets were ordinary premises of their barri, 7.4 and 19.9 would be expected
  (p < 0.001 and p = 0.001). This matches the municipal policy of putting a large supermarket inside remodelled markets: 30 of 39 food markets have one or are
  getting one (Nacio Digital, 2026-08, from the Institut Municipal de Mercats). Across whole sections, chains are not more frequent within 300 m of a market (1.01).
- Fresh-food shops (meat, fruit and vegetables, poultry and eggs, fish: the activities coded identically 2016-2024) in a ring 100-400 m around each market, market stalls
  excluded: 2019-2024 -6.1% around markets vs -15.1% around matched control places (same baseline count, >= 800 m from a market); median difference +10 pp
  (Wilcoxon p = 0.06). 2016-2024: -14.5% vs -17.9% (p = 0.17). Markets with a chain store at them do not differ from the others (Mann-Whitney p = 0.6-0.8),
  and chain openings nearby are unrelated to the change (Spearman 0.02-0.06). So there is no sign that supermarkets at markets empty the surrounding fresh shops;
  small numbers (2-69 shops per ring), so this is "no evidence of harm", not "evidence of no harm".
- Data traps found: the 2016 census has no supermarket class (supermarkets and tobacconists sit in "Resta alimentacio", 3,266 premises), and market stalls are census
  premises (the Boqueria ~270), so earlier 300 m counts that included both were wrong and were replaced.

**Re-check on the audited store list (2026-10-21, 663 stores in the model sections; analyze_tourism_markets.py re-run).**
- Independent supermarket-class shops (1,740): still clearly more where tourists stay - HUT beds 1.22 per SD with the centre-distance control, 1.16 with
  district fixed effects; Airbnb 1.20 / 1.17 (all p <= 0.001). Unchanged conclusion.
- All chains, licensed tourist-flat beds: never significant once demand, transit and premises are controlled (0.96-1.06). Unchanged.
- All chains, Airbnb listings: n.s. with transit and premises (1.02), but 1.15 per SD (p = 0.01) once the rent proxy or district fixed effects are added
  (earlier list: 1.12, p = 0.06). The two tourism measures still disagree, Airbnb is tied to the centre (Spearman -0.81) and this is one of many tests:
  read as "weak", not as an established effect.
- Convenience formats pooled (76 stores): Airbnb 1.28-1.73 per SD in every controlled specification, HUT beds n.s. (1.13-1.21). Within chains that run
  both formats, the convenience format is not significantly more likely where tourists stay (odds ratio 1.08-2.57, p >= 0.07). Unchanged.
- Condis openings 2016-2024 follow 2017 tourist-flat beds: 1.28 per SD, p = 0.006 (identical). Other chains n.s.

## 26. Opening dates completed (2026-10-15) - what changed

Gap: 215 of 723 city stores had no first census year. 79 were the census-2024 supplement (added after the dating step) and 51 had coordinates corrected by
address, so they no longer matched the dating table (census_panel.py, joined on the original coordinates within 1 m). Fix (dbt model store_points): stores
not dated by census_panel.py get the earliest census edition with a premise of the same chain name within 60 m - the rule of store_list_validation; the two
rules agree for 500 of the 508 stores dated by both (98.4%). Result: 639 dated (88%; column first_seen_source), 84 still undated (no premise with the chain's
name within 60 m in any edition: franchisees under their own sign, coordinate errors, or openings after the 2024 fieldwork). Openings 2016-2024: 352 (was 276).
All models were re-run. What changed (old -> new):

- Event study, new sites: +10.4% active premises within 150 m two or more editions after the opening (was +11.8%); takeovers still about 0; no pre-trend.
- Substitution: daily-food shops +15% and other retail +17% after a new site (were +18% / +16%); restaurants unchanged.
- Site choice (conditional logit, 344 openings): further from the chain's own 2014 stores 2.21 per SD (was 1.53), larger footprint 1.49 (1.43),
  residential building 1.28 (1.19), now also denser sections 1.19 (p = 0.02); fewer existing premises in the section 0.80 (unchanged).
  (Sampled alternatives are now drawn from a fixed row order, so this model is exactly reproducible; values moved by 0.01-0.09.)
- Building of new sites (case-control): built after 2000 2.55 (2.82), residential building now significant 2.05 (p = 0.01).
- Out-of-time prediction of 2024 openings: AUC 0.57 (was 0.59); top 10% of sections hold 20% of the 2024 openings (24%).
- Time ordering (v4): 7 of 96 coefficients cross p = 0.05, all near the threshold (e.g. Condis income 2015 1.75, p = 0.015; Caprabo transit no longer significant).
- v3 openings: 12 of 265 coefficients cross p = 0.05 (e.g. all chains open fewer stores where many chain stores already are, 0.88, p = 0.002; Dia avoids its
  own stores 0.51, p = 0.008; Consum's income effect 0.52, p = 0.053, now borderline).
- Tourism / foreign residents: see section 25 (Condis openings follow 2017 tourist flats; the Carrefour non-EU result disappears).
- L10 metro: unchanged conclusion (randomisation p = 0.58 / 0.27, no effect).
Unchanged by construction: all models of the CURRENT store network (v1, v2, v4 blocks, v5 store buildings, v7 cross-section, food access).

## 27. Food access corrected (2026-10-16): slope artefacts, unreachable buildings, shops outside the city

Three problems were found while checking the edge effect raised by the user (`build_food_access.py`):
1. **False slopes.** The Copernicus surface model contains roofs, bridges and the hill above tunnels; 7,044 of 148,630 street edges (4.7%) showed slopes above 30%,
   up to 100%+, where Tobler's speed collapses (e.g. 128 m on the flat taking 10 min, 0.8 km/h). The slope of an edge is now capped at 30% (about the steepest walkable
   streets; steeper = stairs). Sensitivity: caps of 25%, 30% and 40% give the SAME five food-desert sections (65+ beyond 10 min: 7,500 / 7,730 / 8,050).
2. **Buildings beyond the search cutoff dropped out.** Buildings on the network not reached within 60 min (3,000 m) had no value and silently left the shares and
   medians (1,519 dwellings; in Sant Genis 7090, 146 of 643). They now get the cutoff value and count as "beyond 10 min / 500 m".
3. **Shops outside the city.** Chain supermarkets outside the city were already targets (273 ring stores; the street network reaches ~1 km beyond the city), so the
   3.8% beyond 500 m is unaffected. Markets, independent supermarkets and fresh shops came from the city census only: they are now added outside the city from
   OpenStreetMap (`fetch_ring_food_osm.py`). OSM completeness inside the city vs the census (gis.osm_completeness, market stalls excluded, 50 m): markets 95%, supermarkets / convenience 61%, fresh shops 23-33%
   (poultry 0%), so outside fresh food is a lower bound. Adding them changed market walking times in 19 edge sections but no fresh-food result. Sections on the city
   edge with OSM food shops across the boundary within 600 m are flagged `edge_outside_food_uncertain` (63 sections; 3 of the 5 food deserts: Marina de Port 3038,
   Torre Baro 8109, Baro de Viver 9006 - shops just across the boundary may be missing from the data, the access there may be better than shown).

Result: low-income food deserts **11 -> 5 sections** (Torre Baro 8109, Vallbona 8116, Baro de Viver 9006, la Marina de Port 3038, Sant Genis 7090); 65+ residents more than
10 min from fresh food at older pace 10,650 -> 7,730; vulnerable low-access sections redefined in section 29; residents beyond 500 m from a chain store unchanged (65,000, 3.8%).
The external check holds: the three Institut Metropoli food deserts are still all identified.

## 28. Food deserts: main result with a range of fresh-food definitions (2026-10-16)

The 1,711 supermarket-class premises outside the 10 chains are not all alike: regional chains that sell fresh food (Ametller Origen, BonArea, Coaliment, Veritas,
Coviran, Spar, Suma, Sorli ...), shops that are really greengrocers / butchers, and small 24 h mini-markets without fresh produce. Three definitions:

| Definition of fresh food | Fresh-food destinations | Low-income food deserts |
|---|---|---|
| strict: 10 chains + markets + greengrocers, butchers, fishmongers, poultry shops | 4,032 | 5: Torre Baro, Vallbona, Sant Genis, la Marina de Port, Baro de Viver |
| **middle (main): strict + fresh-selling regional chains and named fruit / meat / fish shops, petrol-station shops excluded** | **4,500** | **5: Torre Baro 8109, Vallbona 8116, Sant Genis 7090, la Marina de Port 3038, Baro de Viver 9006 (6,333 residents)** |
| broad: strict + every supermarket-class premise (24 h mini-markets included) | 8,200 | 1: Torre Baro |

Torre Baro is a food desert under every definition. **Correction 2026-10-19:** Baro de Viver had dropped out of the middle definition because of a
"Supercor" 250 m away (Pg Santa Coloma 73-79) that is the shop of a Repsol petrol station (census fuel premise 7 m away, OSM fuel = Repsol, Pg Santa Coloma 71);
every other Supercor in the city is a Supercor Exprés convenience store. Supercor was removed from the fresh-selling list and any supermarket-class premise
within 20 m of a 2024 fuel premise is excluded (only the two Repsol Supercors matched). Middle = strict now: 5 food deserts, 6,333 residents, 65+ far from
fresh food 7,000; all three Institut Metropoli barris are identified by the main definition. Range 1 (broad) - 5.
Sensitivity to the share threshold (main definition): 50% -> 5 sections / 6,333 residents; 40% -> 6 (+ Torre Baro 8108) / 8,604; 33% (USDA low-access share)
-> 7 (+ Baro de Viver 9007) / 9,950. The 50% cut was fixed before the results and is kept. The name-based classification of independent shops is approximate (no product data).
Columns: food_desert_low_income (middle), _strict, _broad in ana.py_section_food_access and gis.section_indicators.

## 29. Vulnerable low-access sections: same slope-aware test as the food deserts (2026-10-16)

The first indicator used only CHAIN supermarkets and network DISTANCE (> 500 m, no slope): 7 sections. It is replaced by two slope-aware tests (older pace, 10 min),
for the vulnerable population (65+ share in the top quarter or cars per 1,000 in the bottom quarter); the food-desert flag uses the same access test with low income.

| Question | Test | Sections |
|---|---|---|
| Fresh food out of reach (MAIN, `vulnerable_low_access`) | > 50% of dwellings > 10 min to fresh food (middle definition) | **2: Sarria 5004, Pedralbes 4054** |
| Full chain supermarket out of reach (`vulnerable_low_access_chain`) | > 50% of dwellings > 10 min to one of the 10 chains | **5: + la Vall d'Hebron 7101, Vallcarca 6010, Can Baro 7021** |
| (old, distance only) | > 50% of dwellings > 500 m from a chain store | 7 (+ 7100, 7102, which are within 10 min once slope is taken into account) |

Reading: on the upper hillsides of Sarria and Pedralbes old residents have neither a supermarket nor fresh shops within 10 min; in Vall d'Hebron, Vallcarca and
Can Baro small fresh shops and markets are near, but a full supermarket is a steep walk away (Can Baro: 80% of dwellings beyond 10 min to a chain, 5% to fresh food).

## 30. Store list audit against official locators (2026-10-16) - what changed

**Why.** Checking the Sant Marti story showed the store list still held the Mercadona of the Mercat del Poblenou (closed March 2024) and missed the
Aldi that replaced it (December 2024). A full audit followed, with the rule "one store = one point".

**Steps.**
1. Official locators for Mercadona and Aldi (`fetch_official_locators.py`, 2026-10-16) replace OSM: listed stores with no locator store within 150 m are
   dropped (closed), locator stores missing from the list are added (city + 2 km ring).
2. Re-scrape of Condis, Consum / Charter, Bon Preu / Esclat (`refresh_store_list.py`, compared by address): Consum and Bon Preu unchanged; Condis
   5 city stores closed, 2 new. Dia (403) and Alcampo (Selenium hangs) keep the 2026-06 list; Lidl / Carrefour (bot protection, not bypassed) and
   Caprabo (no locator) stay OSM, checked against the current OSM.
3. `check_store_addresses.py` bug: a partial street-name match moved a Barceloneta Condis 4.1 km onto another Condis; fixed (whole words >= 8 letters,
   corrections <= 1,000 m).
4. Hand-documented removals with evidence (`store_removals_manual.csv`): a Lidl site taken over by Aldi, a Carrefour Express that the census shows as
   Mi Alcampo, a corner Condis listed under two addresses, an Alcampo listed as Alcampo and Mi Alcampo, two Alcampo stores with wrong coordinates.
5. **Census supplement restricted** to the OSM-sourced chains without a locator (Caprabo, Lidl, Carrefour). For chains with an official current
   list the census-only premises were the same store again (locator coordinates 150-250 m off: Condis Carreras i Candi 101, Gran Via 940 / 1176 ...)
   or stores closed since the 2024 fieldwork (Condis Alt de Pedrell, Cantabria 73, Poesia 9 ...): 41 points removed (Condis 22, Dia 11, Consum 4,
   Alcampo 3, Bon Preu 1).
6. New quality check "one store = one point" (same chain < 40 m, two chains < 10 m): OK; two pairs outside the city reviewed and kept (Condis / Dia
   Badalona, Charter / Dia L'Hospitalet: both locators list a store; the Dia list is the older one).

| Chain | City before | City after |
|---|---|---|
| Condis | 259 | 237 |
| Caprabo | 103 | 103 |
| Dia | 84 | 73 |
| Consum / Charter | 73 | 69 |
| Mercadona | 45 | 40 |
| Carrefour | 38 | 37 |
| Bon Preu / Esclat | 37 | 36 |
| Lidl | 28 | 27 (Bac de Roda site taken over by Aldi) |
| Alcampo | 33 | 28 |
| Aldi | 23 | 27 |
| **All** | **723** | **677** (3.9 per 10k residents, was 4.2) |

**Results after the rebuild (same specifications):**
* Food access: residents beyond 500 m of a chain 72,379 = 4.2% (was 3.8%; 95.8% within 500 m, was 96.2%); food deserts unchanged (4: Marina de Port,
  Sant Genis, Torre Baro, Vallbona; range 1-5); vulnerable sections 3 (+ la Font d'en Fargues 7052) and 7 with a full chain supermarket
  (+ Font d'en Fargues, Montbau 7097); 65+ with fresh food > 10 min 6,834.
* Districts: Horta-Guinardo 2.95 stores per 10k, 85.7% within 500 m (lowest on both); Eixample 99.9%.
* Spacing (descriptive): median distance to a rival 89-171 m, to the own chain 267-871 m (unchanged pattern). Ring models: own-chain ratio < 1 for
  most chains; significant now for Mercadona (own 0.70 / others 1.61), Lidl (own 0.35), Aldi (own 0.47 / others 2.13), Condis 2014 network (own 0.67),
  Consum 2014 network (others 2.41). No longer significant: Dia (own 0.82, others 1.10; was 0.69 / 1.34) and Condis 2014 others (1.26; was 1.59).
* Mercadona density with the offset: back to significant in v2 (3.55, p = 0.01), 65+ 1.94, larger sections 5.17; Aldi transit 1.45 (p = 0.05).
* Sant Marti (14.6% of residents): Condis 44 vs 34.6 expected (p = 0.07), Caprabo + Dia + Consum 26 vs 35.8 (p = 0.055), the four small-format
  chains together 70 vs 70.4; 22 of the 44 Condis first seen in 2022 / 2024. Mercadona 8 vs 5.8 (n.s.). Name-matched census premises 2014-2024:
  Caprabo / Dia / Consum under-represented in Sant Marti in every edition -> long-standing, before Condis' growth and before the 2023 licence freeze.
* Municipal markets: both Mercadona closures were inside municipal markets that could not be remodelled to its format; Aldi took both (press).
* Reference date: Mercadona / Aldi / Condis / Consum / Bon Preu 2026-10-16, Dia / Alcampo 2026-06, Lidl / Carrefour / Caprabo OSM 2026-10-16 + census 2024.

**Opening type corrected (2026-10-19).** "Takeover" had matched any premise within 25 m whose activity or group contained "alimentari", which also took
the 2014 group "QUOTIDIÀ NO ALIMENTARI" (pharmacies, drugstores) and specialised food shops next door (bakeries, greengrocers). Now a takeover =
the store replaced a supermarket / grocery self-service (the supermarket class of each census edition, as in gis.chain_census_premises).
City openings 2016-2024: new site 238, replaced a grocery 88, Clarel conversion 1 (were 222 / 104 / 1). Dashboard page 03 label: "Replaced a grocery".
Results that used the old split (opening-type shares in sections 7 and 14) are superseded by these counts.

**Store dating: earliest evidence (2026-10-19).** A renamed store (Dia Market -> Dia, Simply -> Mi Alcampo, Charter -> Consum, Esclat -> Bon Preu)
had been dated by its new banner and counted as an opening; the dating now takes the earliest census in which the chain (including its old
banners) stands at the site. Dia pattern now also accepts "Día". City openings 2016-2024: new site 238, replaced a grocery 85, Clarel conversion 1.
Census series (gis.chain_census_premises): 2014 = 408 (Dia 109 with the accented "DÍA MARKET"), 2024 = 639, +231 (+57%); Condis +136 (59% of
the net growth), Dia -33. Previous occupant of the 86 replaced sites: independent grocery 50, regional / franchise banner 21, another of the 10
chains 14 (9 of them Dia), same company 1 (a Clarel drugstore of the Dia group).
**Neighbour vs takeover (2026-10-19).** A new store whose previous-census neighbour was one of the 10 chains is a takeover only if that chain no
longer has a store within 40 m today (a Condis opened beside the Mercadona of Diagonal Mar, which still trades; its census point moved 90 m in 2022).
The check also exposed a stale OSM Caprabo at Fabra i Puig 299 (Caprabo in the 2022 census, Aldi at the same point in 2024): removed. City stores 676.
Openings: new site 239, replaced a grocery 84, Clarel 1. Previous occupant: independent 50, regional / franchise 21, another chain 13 (9 Dia), Clarel 1.

**Systematic audit of the opening types (2026-10-19, data/store_openings_audit.csv).** Every takeover was checked for: (A) the previous grocery
still trading at the same spot when the chain store appears, (B) distance of the previous occupant, (C) several groceries within 25 m,
(D) the chain itself already at the site earlier. A found 18 of 84 "takeovers" that were neighbours: rule added - the previous grocery must be gone
(its sign not within 30 m) in the census where the chain store appears; D found none. Final: new site 258, replaced a grocery 65, Clarel 1.
Sensitivity to the distance tolerance: takeovers 15% (15 m) / 20% (25 m, main) / 29% (40 m) of the 323 dated openings - "about one in five".
Previous occupant of the 66 replaced sites: independent grocery 36, regional / franchise banner 16, another of the 10 chains 13 (9 of them Dia),
same company 1 (Clarel -> Dia).
