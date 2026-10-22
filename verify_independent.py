"""Independent re-verification (does not reuse audit_types.py logic).
A) declared type vs actual content, per column; leading zeros lost vs source CSV.
B) naming unification judged by VALUES: columns whose content is a barri/district/section code or name, postal code, etc.
Writes data/verify_types.csv and data/verify_naming.csv."""
import re, unicodedata
from collections import defaultdict
import pandas as pd, psycopg

conn = psycopg.connect("host=localhost port=5432 dbname=supermarket_bcn user=postgres", autocommit=True)
Q = lambda s, a=None: conn.execute(s, a).fetchall()
cols = Q("""select c.table_schema, c.table_name, c.column_name, c.data_type from information_schema.columns c
            where c.table_schema in ('raw','ana') and c.column_name <> 'geom' order by 1,2,c.ordinal_position""")
SRC = dict(((s, t), f) for s, t, f in Q("select table_schema, table_name, source_file from meta.tables"))
FR = pd.read_csv("data_clean/FILE_REPORT.csv"); CLEAN_OF = dict(zip(FR.source_file.str.lower(), FR.clean_file))

def strip_acc(x): return unicodedata.normalize("NFKD", str(x)).encode("ascii", "ignore").decode().lower().replace("'", " ").replace(",", " ").strip()
BARRI_NAMES = {strip_acc(n) for (n,) in Q("select nom_barri from ana.dim_neighborhood")}
DIST_NAMES = {strip_acc(n) for (n,) in Q("select nom_districte from ana.dim_district")}
BARRI_NAMES = {re.sub(r"\s+", " ", n) for n in BARRI_NAMES}; DIST_NAMES = {re.sub(r"\s+", " ", n) for n in DIST_NAMES}

INT = re.compile(r"^-?\d+$"); FLT = re.compile(r"^-?\d+\.\d+$|^-?\d+(\.\d+)?[eE][-+]?\d+$"); ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TS = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}"); BOOL = {"true", "false", "t", "f"}
MEASURE = re.compile(r"(^|_)(num|total|nombre|valor|count|pct|ratio|share|lq|m2|superficie|import|euros|preu|index|gini|renda|edat_mitjana|mean|dist|imd|elevation|slope|length|len|km|area|capacity|population|poblacio)(_|$)")
CODEY = re.compile(r"(^|_)(codi|id|cp|zip|postal|referencia|rcnumber|num_policia|porta|literal|aeb|solar|planta|terme|osm_id|register)(_|$)|^numero$|^values_value$")
KEYS = {"codi_districte", "codi_barri", "seccio_censal", "any_"}

type_issues, naming = [], []
for s, t, c, d in cols:
    fq = f'{s}."{t}"'; qc = f'"{c}"'
    vals = [r[0] for r in Q(f"select distinct {qc}::text from {fq} where {qc} is not null limit 3000")]
    if not vals: continue
    v = [str(x).strip() for x in vals]; n = len(v)
    is_int = all(INT.match(x) for x in v); lead0 = any(re.match(r"^-?0\d", x) for x in v)
    is_num = all(INT.match(x) or FLT.match(x) for x in v); is_iso = all(ISO.match(x) for x in v); is_ts = all(TS.match(x) for x in v)
    # ---------- A) type vs content ----------
    if d == "text":
        if is_num and not lead0 and not CODEY.search(c) and t not in ("trf_osm_roads", "hist_osm_shops", "com_plazaparc_clean"):
            type_issues.append((s, t, c, d, "content is purely numeric but column is text", v[:3]))
        if (is_iso or is_ts) and t not in ("hist_osm_shops", "com_plazaparc_clean"):
            type_issues.append((s, t, c, d, "content is dates but column is text", v[:3]))
        if MEASURE.search(c) and not CODEY.search(c) and not is_num and t not in ("trf_osm_roads", "hist_osm_shops", "com_plazaparc_clean"):
            nonnum = [x for x in v if not (INT.match(x) or FLT.match(x))][:3]
            type_issues.append((s, t, c, d, "measure-like name but text content (check)", nonnum))
    elif d in ("integer", "bigint", "double precision", "smallint", "real", "numeric"):
        if CODEY.search(c) and c not in KEYS:
            type_issues.append((s, t, c, d, "code/identifier stored as a number", v[:3]))
        if d in ("integer", "bigint") and c.startswith(("lat", "lon", "x_", "y_")):
            type_issues.append((s, t, c, d, "coordinate stored as integer (precision lost)", v[:3]))
        # leading zeros lost? compare with the cleaned CSV source text
        src = SRC.get((s, t), ""); cf = CLEAN_OF.get(src.lower())
        if cf and d in ("integer", "bigint"):
            try:
                raw = pd.read_csv(f"data_clean/{cf}", usecols=[c], dtype=str)[c].dropna()
                if raw.str.match(r"^-?0\d").any() and c not in KEYS:
                    type_issues.append((s, t, c, d, "leading zeros in source were dropped by integer type", raw[raw.str.match(r'^-?0\d')].head(3).tolist()))
            except Exception: pass
    elif d == "date":
        mn, mx = conn.execute(f"select min({qc}), max({qc}) from {fq}").fetchone()
        if mn and (mn.year < 1900 or mx.year > 2035): type_issues.append((s, t, c, d, "implausible date range", (str(mn), str(mx))))
    elif d.startswith("timestamp"):
        mn, mx = conn.execute(f"select min({qc}), max({qc}) from {fq}").fetchone()
        if mn and (mn.year < 1900 or mx.year > 2035): type_issues.append((s, t, c, d, "implausible timestamp range", (str(mn), str(mx))))
    # ---------- B) naming judged by values ----------
    nums = None
    if is_int:
        nums = [int(x) for x in v]; lo, hi, k = min(nums), max(nums), len(set(nums))
        if 1 <= lo and hi <= 73 and k >= 20 and c != "codi_barri" and ("barri" in c or "neigh" in c or "bar" in c):
            naming.append((s, t, c, "barri code", "codi_barri"))
        if 1 <= lo and hi <= 10 and k >= 5 and c != "codi_districte" and ("distr" in c or "dto" in c):
            naming.append((s, t, c, "district code", "codi_districte"))
        if 1001 <= lo and hi <= 10999 and k >= 50 and c not in ("seccio_censal",) and ("secc" in c or "sec" in c):
            naming.append((s, t, c, "census section (composite)", "seccio_censal"))
    if d == "text" and n >= 5:
        nv = [re.sub(r"\s+", " ", strip_acc(x)) for x in v]
        if sum(x in BARRI_NAMES for x in nv) / len(nv) >= 0.8 and c != "nom_barri": naming.append((s, t, c, "barri name", "nom_barri"))
        if sum(x in DIST_NAMES for x in nv) / len(nv) >= 0.8 and c != "nom_districte": naming.append((s, t, c, "district name", "nom_districte"))
        if all(re.match(r"^0?8\d{3}$", x) for x in v) and n >= 5: naming.append((s, t, c, "postal code", "codi_postal"))

ti = pd.DataFrame(type_issues, columns=["schema", "table", "column", "type", "finding", "examples"]); ti.to_csv("data/verify_types.csv", index=False)
nm = pd.DataFrame(naming, columns=["schema", "table", "column", "content_is", "canonical_name"]); nm.to_csv("data/verify_naming.csv", index=False)
pd.set_option("display.width", 250, "display.max_colwidth", 90, "display.max_rows", 200)
print(f"columns checked: {len(cols)}\n\n=== A) type findings: {len(ti)}"); print(ti.to_string(index=False) if len(ti) else "none")
print(f"\n=== B) columns whose VALUES are a shared concept but whose NAME is not the canonical one: {len(nm)}"); print(nm.to_string(index=False) if len(nm) else "none")
