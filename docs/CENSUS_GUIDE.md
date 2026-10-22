# How to read the commercial census tables (raw.cen_census_*)

Source: Open Data BCN dataset "Census of premises on the ground floor intended for economic activity" (Ajuntament de Barcelona).
One row = **one ground-floor premise** (a shop, a bar, an office, an empty unit ...). Five editions are loaded:

| Table | Rows | Edition | Coordinates | Notes |
|---|---|---|---|---|
| `raw.cen_census_2014` | 67,433 | 2014 | **ED50 only** (`x_ed50`, `y_ed50`, EPSG:23031) | Old structure; fewer columns |
| `raw.cen_census_2016` | 78,033 | 2016 | `lat`, `lon`, `x_utm_etrs89`, `y_utm_etrs89` | `data_entrada` = date the premise entered the inventory |
| `raw.cen_census_2019` | 80,554 | 2019 | `geom` (spatial table) | `sn_*` flags were stored inverted in the source and are corrected |
| `raw.cen_census_2022` | 66,088 | 2022 | `lat`, `lon` | |
| `raw.cen_census_2024` | 68,024 | 2024 (latest) | `lat`, `lon` | |

2016, 2019, 2022 and 2024 share one schema (column names were harmonised); 2014 only has the first part of it.

## 1. The three-level activity classification

```
sector  (nom_sector_activitat)     7 values in 2024:  Serveis | Comerc al detall | Altres | Comerc al detall /Engros | 3 kinds of vacant premises
  └─ group (nom_grup_activitat)    e.g. Quotidia alimentari, Equipament personal, Restaurants bars i hotels, Ensenyament ...
       └─ activity (nom_activitat) 80+ values, e.g. Autoservei / Supermercat, Vestir, Bars / CIBERCAFE, Farmacies ...
```

Retail ("Comerc al detall", 20,784 premises in 2024) splits into groups: Quotidia alimentari (daily food, 8,144), Equipament personal (4,168),
Quotidia no alimentari (2,486), Parament de la llar (2,370), Oci i cultura (1,698), Altres (1,534), Automocio (384).
**Supermarkets** are `nom_activitat = 'Autoservei / Supermercat'` inside the group `Quotidia alimentari`.

`nom_principal_activitat` (values `Actiu`, `Sense activitat Economica`, ...) says whether the premise is active, vacant, or without information.
Vacant premises are their own sector ("Locals buits en lloguer / en venda / en venda i lloguer").

## 2. Columns (official definitions from the Open Data BCN field dictionary)

| Column | Meaning |
|---|---|
| `id_global` (2022, 2024) | Unique global id of the premise record |
| `id_bcn_2016` | Unique id of the premise in the 2016 census. **Use it to follow the same premise across editions** (2016, 2019, 2022, 2024) |
| `id_bcn_2019` (2019) | Premise id in the 2019 census |
| `codi_principal_activitat` / `nom_principal_activitat` | Active / empty / no information |
| `codi_sector_activitat` / `nom_sector_activitat` | Sector |
| `codi_grup_activitat` / `nom_grup_activitat` | Activity group |
| `codi_activitat_2022` (or `_2019`) / `codi_activitat_2016` / `nom_activitat` | Activity code (two classification versions) and name |
| `nom_local` | **Name of the premise as recorded by the surveyor (the shop sign)**. Chain brands are found here (`MERCADONA`, `LIDL` ...); franchised shops often carry an independent name |
| `sn_oci_nocturn` | Night-life activity |
| `sn_coworking` | Co-working activity |
| `sn_servei_degustacio` | Tasting service |
| `sn_obert24h` | Open 24 hours |
| `sn_mixtura` | Mixed activity |
| `sn_carrer` | Street-level shop (opens onto the street) |
| `sn_mercat`, `nom_mercat` | Shop inside a (municipal) market, and its name |
| `sn_galeria`, `nom_galeria` | Shop inside a commercial gallery |
| `sn_ccomercial`, `nom_ccomercial` | Shop inside a shopping centre |
| `sn_eix`, `nom_eix` | Shop on a commercial axis, and the axis name |
| `lat`, `lon`, `x_utm_etrs89`, `y_utm_etrs89` | Position (WGS84 degrees / ETRS89 metres) |
| `direccio_unica` | Unambiguous address of the premise |
| `nom_via`, `num_policia_inicial` / `_final`, `planta`, `porta` | Street, street number range, floor (`LOC` = premise), premise door number |
| `solar`, `codi_parcela`, `codi_illa` | Plot, parcel and city-block codes |
| `seccio_censal`, `codi_barri`, `nom_barri`, `codi_districte`, `nom_districte` | Administrative units (`seccio_censal` is district x 1000 + section) |
| `referencia_cadastral` | Cadastral reference (links to the Catastro) |
| `data_revisio` | Date the premise record was last updated (2016: `data_entrada` = entry date) |

All `sn_*` columns are **boolean in this database (true = yes)**. In the 2019 source the coding was inverted (0 = yes); this was corrected and verified by comparing
the share of "yes" per flag with the other editions.

## 3. 2014 and 2016 differences

* 2014 (`cen_census_2014`): `nom_sector_activitat` / `nom_grup_activitat` / `nom_activitat` come from the old fields BCN1 / BCN2 / BCN3; `data_inici` = start of the inventory
  (first registration, from 2012), `data_revisio` = date of the last visit; **no lat/lon** (use `x_ed50`, `y_ed50`, EPSG:23031).
* 2016: no activity code lists identical to 2019+, but sector 100% and group 94% of the values coincide with 2019.

## 4. Starter queries

```sql
-- how many premises per sector in 2024
SELECT nom_sector_activitat, count(*) FROM raw.cen_census_2024 GROUP BY 1 ORDER BY 2 DESC;

-- supermarkets of a chain in 2024 (brand is in the shop sign)
SELECT nom_local, nom_via, num_policia_inicial, codi_barri, lat, lon
FROM raw.cen_census_2024
WHERE nom_activitat = 'Autoservei / Supermercat' AND nom_local ILIKE '%MERCADONA%';

-- follow one premise over time (2016 -> 2024)
SELECT a.id_bcn_2016, a.nom_local AS name_2016, b.nom_local AS name_2024, b.nom_activitat
FROM raw.cen_census_2016 a JOIN raw.cen_census_2024 b USING (id_bcn_2016) LIMIT 20;

-- share of vacant premises per barri in 2024
SELECT codi_barri,
       round(100.0 * count(*) FILTER (WHERE nom_sector_activitat LIKE 'Locals buits%') / count(*), 1) AS pct_vacant
FROM raw.cen_census_2024 GROUP BY 1 ORDER BY 2 DESC;
```

## 5. Cautions

* A premise name is what the surveyor saw. Independent shops, franchisees and renamed shops cannot be matched to a brand by name.
* About 1,800 premise or street names have characters lost in the source files (kept as they are; listed in `meta.type_audit`).
* The classification changes slightly between editions (activity codes are versioned); compare sectors and groups across years, activities with care.
* The census records ground-floor premises only (no upper floors, no home-based activity).
