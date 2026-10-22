"""Shared naming rules. Rule: language is unified INSIDE each table; different tables may use Catalan / Spanish / English.
Every table gets a language tag ('ca' | 'es' | 'en'); variant spellings of the same concept are merged using that language's canonical name."""
import re, unicodedata
from pathlib import Path

RESERVED = set((Path(__file__).parent / "data/pg_reserved.txt").read_text().split())

def clean_name(c):
    s = unicodedata.normalize("NFKD", str(c)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    s = re.sub(r"^(19|20)\d{2}_", "", s) or "col"          # leading year prefixes come from QGIS joins
    return "c_" + s if s[0].isdigit() else s

# ---- canonical names per language (only the concepts shared across tables) ----
CANON = {
    "ca": {  # Open Data BCN statistical / commercial tables: Catalan terms
        "codi_districte": "codi_districte", "cdistri": "codi_districte", "addresses_district_id": "codi_districte",
        "nom_districte": "nom_districte", "n_distri": "nom_districte", "ndistric": "nom_districte", "addresses_district_name": "nom_districte",
        "codi_barri": "codi_barri", "cbarri": "codi_barri", "addresses_neighborhood_id": "codi_barri",
        "nom_barri": "nom_barri", "nbarri": "nom_barri", "addresses_neighborhood_name": "nom_barri",
        "latitud": "lat", "latitude": "lat", "longitud": "lon", "longitude": "lon",          # lat / lon are language-neutral abbreviations
        "x_utm_etrs89": "x_utm_etrs89", "x_etrs89": "x_utm_etrs89", "x_utm": "x_utm_etrs89", "geo_epgs_25831_x": "x_utm_etrs89", "x_etrs": "x_utm_etrs89",
        "y_utm_etrs89": "y_utm_etrs89", "y_etrs89": "y_utm_etrs89", "y_utm": "y_utm_etrs89", "geo_epgs_25831_y": "y_utm_etrs89", "y_etrs": "y_utm_etrs89",
        "geo_epgs_4326_lat": "lat", "geo_epgs_4326_lon": "lon", "any": "any_", "data_revisio": "data_revisio",
        "districte": "codi_districte", "barri": "codi_barri"},   # official admin-unit layers: DISTRICTE / BARRI hold the codes
    "en": {  # our own tables, OSM, English-schema lists: shared concepts use the SAME Catalan names as every other table
        "codi_districte": "codi_districte", "cdistri": "codi_districte", "addresses_district_id": "codi_districte", "district_code": "codi_districte",
        "nom_districte": "nom_districte", "n_distri": "nom_districte", "ndistric": "nom_districte", "addresses_district_name": "nom_districte", "district_name": "nom_districte",
        "codi_barri": "codi_barri", "cbarri": "codi_barri", "addresses_neighborhood_id": "codi_barri", "neighborhood_code": "codi_barri",
        "nom_barri": "nom_barri", "nbarri": "nom_barri", "addresses_neighborhood_name": "nom_barri", "neighborhood_name": "nom_barri", "barri": "nom_barri",
        "municipi": "municipi", "municipality": "municipi", "total_poblacio": "total_poblacio", "population": "total_poblacio",
        "group": "corporate_group", "brand_group": "brand_std", "natural": "osm_natural",
        "latitud": "lat", "latitude": "lat", "longitud": "lon", "longitude": "lon", "geo_epgs_4326_lat": "lat", "geo_epgs_4326_lon": "lon",
        "x_utm_etrs89": "x_utm_etrs89", "x_etrs89": "x_utm_etrs89", "x_utm": "x_utm_etrs89", "geo_epgs_25831_x": "x_utm_etrs89",
        "y_utm_etrs89": "y_utm_etrs89", "y_etrs89": "y_utm_etrs89", "y_utm": "y_utm_etrs89", "geo_epgs_25831_y": "y_utm_etrs89",
        "any": "any_", "year": "any_", "data_revisio": "data_revisio", "review_date": "data_revisio",
        "census_section_id": "seccio_censal", "section_code_orig": "seccio_censal_orig"},
    "es": {"latitud": "lat", "longitud": "lon", "lng": "lon"},   # e.g. Condis store list (calle, ciudad, talla ...): left in Spanish
}

# ---- more shared concepts (verified by VALUES, 2026-10-12): same Catalan name in every table ----
SHARED = {
    "addresses_zip_code": "codi_postal", "cp": "codi_postal",                                   # postal code
    "addresses_town": "municipi", "poblacio": "municipi", "nom_poblacio": "municipi", "ciudad": "municipi", "id_poblacio": "codi_municipi",
    "addresses_road_name": "nom_via", "carrer": "nom_via",                                      # street name
    "addresses_start_street_number": "num_policia_inicial", "addresses_end_street_number": "num_policia_final", "numero": "num_policia_inicial",
    "address": "adreca", "calle": "adreca",                                                     # full address (street + number)
    "name": "nom", "brand": "ensenya",                                                          # entity name, store banner
}
# census editions 2014 / 2016 use their own field names for the concepts of 2019-2024 (overlap of values: sector 100%, group 94%, activity 89%;
# 2016 id_bcn == 2019 id_bcn_2016 for 70,529 records)
EDITION_MAP = {
    "census_2016": {"id_bcn": "id_bcn_2016", "id_princip": "codi_principal_activitat", "n_princip": "nom_principal_activitat",
                    "id_sector": "codi_sector_activitat", "n_sector": "nom_sector_activitat", "id_grupact": "codi_grup_activitat",
                    "n_grupact": "nom_grup_activitat", "id_act": "codi_activitat_2016", "n_act": "nom_activitat", "n_local": "nom_local",
                    "n_mercat": "nom_mercat", "n_galeria": "nom_galeria", "sn_ccomerc": "sn_ccomercial", "id_ccomerc": "id_ccomercial",
                    "n_ccomerc": "nom_ccomercial", "n_carrer": "nom_via", "num_polici": "num_policia_inicial", "ref_cad": "referencia_cadastral",
                    "data": "data_entrada", "n_eix": "nom_eix", "x_utm_etrs": "x_utm_etrs89", "y_utm_etrs": "y_utm_etrs89"},
    "census_2014": {"bcn1": "nom_sector_activitat", "bcn2": "nom_grup_activitat", "bcn3": "nom_activitat", "nom": "nom_local",
                    "carrcadast": "nom_via", "doornum": "num_policia_inicial", "rcnumber": "referencia_cadastral",
                    "datainici": "data_inici", "ultima_visita": "data_revisio"},
}
for _l in CANON: CANON[_l].update(SHARED)

# translations so that OUR derived tables are English from end to end
EN_TRANSLATE = {
    "veh_altres_vehicles": "veh_other", "veh_camions": "veh_trucks", "veh_ciclomotors": "veh_mopeds", "veh_furgonetes": "veh_vans",
    "veh_motos": "veh_motorcycles", "veh_turismes": "veh_cars",
    "plot_superficie_construida": "plot_built_m2", "plot_superficie_edificada_sobre_rasant": "plot_above_ground_m2",
    "plot_superficie_edificada_sota_rasant": "plot_below_ground_m2", "plot_superficie_sol": "plot_land_m2",
    "bldg_superficie_locals": "bldg_premises_m2", "bldg_superficie_serveis": "bldg_services_m2",
}
CA_RENAMES = {"first_seen": "primer_mes", "last_seen": "ultim_mes", "n_snaps": "n_captures", "snap": "mes_captura"}   # our own columns inside Catalan-source tables
FORCE_LANG = {  # file stem (lower) -> language; everything else is decided by a vote over its original column names
    "barcelona_supermarkets_official": "en", "barri_features": "en", "stores_model_table_city": "en", "stores_features_city": "en",
    "stores_opening_era_city": "en", "bonpreu_first_seen": "ca", "bonpreu_snapshots_long": "ca", "consum_now": "en", "condis_raw": "es",
    "age_groups_by_barri": "ca", "age_groups_by_seccio": "ca", "educa_superior_by_barri": "ca", "educa_superior_by_seccio": "ca"}   # user-built QGIS summaries: Catalan keys decide
TRANSLATE_FILES = {"barcelona_supermarkets_official", "barri_features", "stores_model_table_city", "stores_features_city", "stores_opening_era_city"}
CA_RENAME_FILES = {"bonpreu_first_seen", "bonpreu_snapshots_long"}

CA_TOK = set("codi nom seccio barri districte data superficie poblacio activitat carrer direccio tipus habitatge comerc local parada linia estacio renda edat sexe valor nombre desc resta alimentacio restauracio magatzems mercat mercats serveis equipaments lloguer buits eix turisme allotjament acces turismes motos camions furgonetes ciclomotors altres llars persona viari descripcio ensenya via illa parcela solar planta porta mercat galeria".split())
EN_TOK = set("code name section neighborhood neighbourhood district date year area population street address type value housing shop count age ratio pct mean dist flag road brand store first last seen era source total large units premises services cars vans trucks addresses register values institution secondary category attribute outstanding timetable".split())

def detect_lang(stem, orig_cols):
    st = stem.lower()
    if st in FORCE_LANG: return FORCE_LANG[st]
    ca = en = 0
    for c in orig_cols:
        toks = set(clean_name(c).split("_"))
        ca += bool(toks & CA_TOK); en += bool(toks & EN_TOK)
    return "ca" if ca > en else "en"

def std_cols(cols, lang, stem=""):
    cm = CANON.get(lang, {}); out, seen = [], {}
    translate = lang == "en" and stem.lower() in TRANSLATE_FILES
    em = EDITION_MAP.get(stem.lower(), {})
    for c in cols:
        k = clean_name(c); k = em.get(k, k); k = cm.get(k, k)
        if translate: k = EN_TRANSLATE.get(k, k)
        if stem.lower() in CA_RENAME_FILES: k = CA_RENAMES.get(k, k)
        k = apply_units(k, stem)
        if k in RESERVED: k += "_"
        if k in seen: seen[k] += 1; k = f"{k}_{seen[k]}"
        else: seen[k] = 1
        out.append(k[:63])
    return out

# names used for the district / neighbourhood / census-section keys per language
KEYS = {l: dict(dcode="codi_districte", dname="nom_districte", bcode="codi_barri", bname="nom_barri", sec="seccio_censal", year="any_") for l in ("ca", "en", "es")}

SECTION_SRC = {"seccio_censal", "codi_seccio_censal", "sec_cens"}
def compose_section(df, notes=None):
    """census-section key = district*1000 + section-in-district (sources differ: some already composite, some only the within-district number)."""
    import pandas as pd
    cols = [c for c in df.columns if c in SECTION_SRC]
    if not cols: return df
    c = cols[0]; v = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    if v.notna().any() and v.max() >= 1000:                      # already composite: just type it, no redundant copy
        df = df.drop(columns=[c]); df["seccio_censal"] = v
        for c2 in cols[1:]: df = df.rename(columns={c2: c2 + "_orig"})
        return df
    elif "codi_districte" in df.columns: comp = pd.to_numeric(df["codi_districte"], errors="coerce").astype("Int64") * 1000 + v
    else: comp = v; (notes or []).append(f"{c}: within-district but no district code - NOT composite")
    df = df.rename(columns={c: "seccio_censal_orig"}); df["seccio_censal"] = comp
    for c2 in cols[1:]: df = df.rename(columns={c2: c2 + "_orig"})
    return df

import re as _re
CODE_RX = _re.compile(r"^(codi|values_value|stop_code|parent_station|.*_color|telefon.*|phone.*|codi_(?!districte$|barri$).*|id|id_.*|.*_id|cp|.*zip.*|telefon|tel|referencia_cadastral|ref_cad.*|rcnumber|num_policia.*|numero|porta|literal|seccio_censal_orig|pgm_family|pgm_key|pgm_clau.*|official_store_code|feed_version|aeb|solar|planta|terme)$")
INT_KEYS = {"codi_districte", "codi_barri", "seccio_censal", "any_"}
FLOAT_KEYS = {"lat", "lon", "x_utm_etrs89", "y_utm_etrs89", "x_ed50", "y_ed50"}
NA_TOKENS = ["NA", "N/A", "#N/A", "NaN", "nan", "", "..", "null", "NULL", "None", "0000-00-00", "1899-12-30", "Mesura no disponible"]
BAD_AFTER_FIX = _re.compile("[ÿ�-]")

def fix_mojibake(s):
    """Undo UTF-8-read-as-latin1/cp1252 ONLY when the result is provably clean (no 'ÿ', no replacement or control characters)."""
    if not isinstance(s, str) or ("Ã" not in s and "Â" not in s): return s
    for enc in ("latin-1", "cp1252"):
        try:
            r = s.encode(enc).decode("utf-8")
            if not BAD_AFTER_FIX.search(r): return r
        except Exception: pass
    return s

def repair_fffd(series, good_names):
    """Replace U+FFFD in a name with the unique matching clean name from another source edition (same length, same other characters)."""
    import pandas as pd
    good = [g for g in set(good_names) if isinstance(g, str) and "�" not in g]
    bad = [b for b in series.dropna().unique() if "�" in b]
    fixes = {}
    for b in bad:
        rx = _re.compile("^" + "".join("." if ch == "�" else _re.escape(ch) for ch in b) + "$")
        m = [g for g in good if rx.match(g)]
        if len(set(m)) == 1: fixes[b] = m[0]
    return series.replace(fixes), len(fixes), len(bad)

def merge_dup_keys(df, notes=None):
    """A source can carry the same key twice (e.g. BARRI and Codi_Barri). If the duplicate never disagrees, fold it into the key and drop it."""
    import pandas as pd
    for k in ("codi_barri", "codi_districte"):
        d = f"{k}_2"
        if k in df.columns and d in df.columns:
            a = pd.to_numeric(df[k], errors="coerce"); b = pd.to_numeric(df[d], errors="coerce")
            if ((a != b) & a.notna() & b.notna()).sum() == 0:
                df[k] = a.fillna(b).astype("Int64"); df = df.drop(columns=[d])
                if notes is not None: notes.append(f"{d} identical to {k} where both present -> merged and dropped")
    return df

DMY_RX = _re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
def dmy_to_iso(series, tolerance=0.001):
    """dd/mm/yyyy -> yyyy-mm-dd when (almost) every value is such a date; impossible placeholders like 00/01/1900 (<= 0.1%) become NULL."""
    import pandas as pd
    s = series.dropna().astype(str)
    if s.empty or not s.str.match(DMY_RX).all(): return series, False, 0
    d = pd.to_datetime(series, format="%d/%m/%Y", errors="coerce")
    n_bad = int((series.notna() & d.isna()).sum())
    if n_bad > tolerance * len(s): return series, False, n_bad
    return d.dt.strftime("%Y-%m-%d").where(d.notna(), None), True, n_bad

# ---- Sí/No flags (sn_*): 2016 uses 1=yes, 2022/2024 use 'Sí'/'Si'/'No', and the 2019 edition is INVERTED (0=yes, 1=no):
#      verified on every flag: 2019 share of '1' ~= 100 - share of 'Sí' in 2016/2022/2024 (e.g. sn_mercat 4.2% / 3.3% vs 97.3% in 2019).
SN_INVERTED_STEMS = {"2019_censcomercialbcn_detall"}
def sn_to_bool(series, inverted=False):
    import pandas as pd
    words = {"si": True, "sí": True, "s": True, "yes": True, "no": False, "n": False}
    def f(v):
        if v is None or (not isinstance(v, str) and pd.isna(v)): return None
        s = str(v).strip().lower()
        if s in ("1", "1.0"): return not inverted
        if s in ("0", "0.0"): return inverted
        return words.get(s)
    return series.map(f).astype("boolean")

YMD_INT = _re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$")
def yyyymmdd_to_iso(series):
    """20191002 -> 2019-10-02 when every non-null value is a compact date (only applied to date-named columns)."""
    import pandas as pd
    s = series.dropna().astype(str).str.replace(r"\.0$", "", regex=True)
    if s.empty or not s.str.match(YMD_INT).all(): return series, False
    d = pd.to_datetime(series.astype("string").str.replace(r"\.0$", "", regex=True), format="%Y%m%d", errors="coerce")
    return d.dt.strftime("%Y-%m-%d").where(d.notna(), None), True

def stray_markers_to_na(series, name):
    """A measure column that is >=95% numeric but contains a few digit-free words ('Mesura no disponible', 'NC', '-') -> those words are NULL."""
    import pandas as pd
    if CODE_RX.match(name): return series, []
    s = series.dropna().astype(str).str.strip()
    if len(s) < 20: return series, []
    isnum = s.str.match(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$")
    bad = s[~isnum].unique().tolist()
    if isnum.mean() >= 0.95 and 0 < len(bad) <= 3 and all(not _re.search(r"\d", b) for b in bad):
        return series.where(~series.astype("string").str.strip().isin(bad), None), bad
    return series, []

# ---- column names that carry their UNIT / DENOMINATOR (only columns whose meaning was verified against the data) ----
_US = {"hab_n": "habitatges_n", "hab_m2": "habitatges_m2", "com_n": "locals_comercials_n", "com_m2": "locals_comercials_m2", "com_v": "locals_comercials_valor_eur",
       "park_n": "aparcaments_n", "ofic_m2": "oficines_m2", "mag_m2": "magatzems_m2", "tur_n": "turisme_hostaleria_n",
       "saturacio_comerc": "locals_comercials_per_100_habitatges", "interferencia_tur": "turisme_hostaleria_per_100_habitatges",
       "preu_comerc_m2": "valor_comercial_eur_per_m2", "ratio_oficines": "oficines_m2_per_100_m2_habitatge",
       "espai_reciclable": "magatzems_m2_per_100_m2_habitatge", "hab_per_comerc": "habitatges_per_local_comercial"}
_INC = {"import_euros": "renda_disponible_eur_per_persona"}
UNIT_RENAMES = {
    "2026_us_desti_by_seccio": _US, "2026_us_desti_by_barri": _US,
    "2022_renda_disponible_llars_per_persona": _INC, "renda_gini_by_barri": _INC, "renda_gini_by_seccio": _INC,
    "2026_valor_cadastral_by_barri": {"valor_cadastral_unitari": "valor_cadastral_eur_per_m2"},
    "2026_valor_cadastral_by_seccio": {"valor_cadastral_unitari": "valor_cadastral_eur_per_m2"},
    "aforament_detall_2025": {"valor_imd": "imd_vehicles_per_day"},
    "motor_2025": {"index_motoritzacio": "index_motoritzacio_per_1000_hab"},
    "edat_mitjana": {},   # placeholder for symmetry
}
UNIT_RENAMES["cad_edif_edat"] = {"edat_mitjana": "edat_mitjana_anys"}
# Padro `valor` = count of people / households (verified: base sums to the official population; the three dom tables each sum to 684,077 households)
for _s, _n in {"2026_pad_base": "habitants_n", "2026_pad_base_by_barri": "habitants_n", "2026_pads_edat-1": "habitants_n", "2026_pad_16niv-educa_sexe": "habitants_n",
               "2026_pad_dom18": "llars_n", "2026_pad_dom_mdbas_edat-1864": "llars_n", "2026_pad_dom_mdbas_edat-6599": "llars_n",
               "2025_pad_def_mdbas": "defuncions_n", "2025_pad_nai_mdbas": "naixements_n"}.items():
    UNIT_RENAMES[_s] = {"valor": _n}
# historical downloads (fetch_history.py): same measures as the 2026 tables
for _s in ("padro_population_history", "padro_age5_2015", "padro_education_2015", "padro_nationality_2015_2026"): UNIT_RENAMES[_s] = {"valor": "habitants_n"}
UNIT_RENAMES["income_history"] = _INC
# our store / barri feature files (verified in census_panel.py, build_store_features.py, build_barri_features.py):
#   d<year> = distance (m) from the store to the nearest supermarket premise of that census edition (seen_<year> = within 60 m);
#   pgm_street_width = PGM label "Cota d'ample oficial de vial o carrer" (official street width, m); road rank 1 (pedestrian) .. 7 (motorway);
#   imd = mean daily traffic (vehicles / day); bldg_total = number of buildings (cadastre Nombre); bldg_mean_age = mean of section building ages (years)
_STORE = {**{f"d{y}": f"dist_census_supermarket_{y}_m" for y in (2014, 2016, 2019, 2022, 2024)},
          "first_seen_census": "first_seen_census_year", "last_seen_census": "last_seen_census_year", "supermarket_premises_since": "supermarket_premises_since_year",
          "imd_nearest": "imd_nearest_vehicles_per_day", "imd_mean_500m": "imd_mean_500m_vehicles_per_day", "road_rank_max_50m": "road_rank_max_50m_1to7",
          "pgm_street_width": "pgm_street_width_m"}
_BARRI = {"veh_other": "veh_other_n", "veh_trucks": "veh_trucks_n", "veh_mopeds": "veh_mopeds_n", "veh_vans": "veh_vans_n", "veh_motorcycles": "veh_motorcycles_n",
          "veh_cars": "veh_cars_n", "cars_per_1000": "cars_per_1000_hab", "motos_per_1000": "motos_per_1000_hab", "vans_trucks_per_1000": "vans_trucks_per_1000_hab",
          "bldg_total": "bldg_n", "bldg_mean_age": "bldg_mean_age_years"}
for _s in ("stores_features_city", "stores_opening_era_city"): UNIT_RENAMES[_s] = _STORE
UNIT_RENAMES["stores_model_table_city"] = {**_STORE, **_BARRI}
UNIT_RENAMES["barri_features"] = _BARRI
DROP_COLS = {s: ["d19", "d24"] for s in ("stores_features_city", "stores_model_table_city", "stores_opening_era_city")}   # exact duplicates of d2019 / d2024
INT_COLS = {"first_seen_census_year", "last_seen_census_year", "supermarket_premises_since_year", "official_store_code", "year_of_construction"}  # floats only because of NULLs
YYYYMM_COLS = {"primer_mes", "ultim_mes", "mes_captura"}   # 202111 -> date 2021-11-01 (first day of the month)
UNIT_SUFFIX = {  # (suffix regex -> replacement) per file stem
    "age_groups_by_seccio": [(r"_pct_local$", "_pct_of_unit_pop"), (r"_city_share$", "_pct_of_city_group"), (r"_lq$", "_location_quotient")],
    "age_groups_by_barri":  [(r"_pct_local$", "_pct_of_unit_pop"), (r"_city_share$", "_pct_of_city_group"), (r"_lq$", "_location_quotient")]}
def apply_units(k, stem):
    s = stem.lower()
    k = UNIT_RENAMES.get(s, {}).get(k, k)
    for rx, rep in UNIT_SUFFIX.get(s, []): k = _re.sub(rx, rep, k)
    return k

# ---- counts: stored as integer even when the source writes them as 1234.0 (type policy, 2026-10-14)
COUNT_EXTRA = {"habitants", "num_vivend", "hut_casos", "hut_places"}
def is_count_name(c):
    """count-like column: ends with _n (but not estimated / mean values, which may be fractional) or a known count field"""
    return (c.endswith("_n") and not c.endswith(("_estimated_n", "_mean_n"))) or c in COUNT_EXTRA
