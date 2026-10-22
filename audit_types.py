"""Data-type / value audit of every table in supermarket_bcn. Read-only. Writes data/type_audit.csv and prints a summary.
Severity: HIGH = wrong or misleading type / impossible values; MED = suspicious; INFO = harmless note."""
import re, sys
from collections import defaultdict
import pandas as pd, psycopg
import bcn_naming as N
OSM_TABLES = {'trf_osm_roads', 'hist_osm_shops', 'com_plazaparc_clean'}

CONN = "host=localhost port=5432 dbname=supermarket_bcn user=postgres"
conn = psycopg.connect(CONN)
Q = lambda s, *a: conn.execute(s, a).fetchall()
issues = []
def add(sev, table, col, kind, detail): issues.append((sev, table, col, kind, str(detail)[:230]))

tabs = Q("select table_schema, table_name, kind, n_rows from meta.tables order by 1,2")
cols = Q("select table_schema, table_name, column_name, data_type from information_schema.columns where table_schema in ('raw','ana') order by 1,2,ordinal_position")
bytab = defaultdict(list)
for s, t, c, d in cols: bytab[(s, t)].append((c, d))
rows_of = {(s, t): n for s, t, k, n in tabs}

NUM = r"^-?[0-9]+([.][0-9]+)?([eE][-+]?[0-9]+)?$"
ISO_D = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
ISO_TS = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}"
DMY = r"^[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}$"
CODE_NAME = N.CODE_RX

for (s, t), cl in bytab.items():
    fq = f'{s}."{t}"'; n = rows_of.get((s, t), 0)
    for c, d in cl:
        if c == "geom": continue
        qc = f'"{c}"'
        osm = t in OSM_TABLES
        if d == "text":
            nn, num, iso_d, iso_ts, dmy, ws, moj, lit = conn.execute(f"""select count({qc}),
                count(*) filter (where {qc} ~ '{NUM}'), count(*) filter (where {qc} ~ '{ISO_D}'), count(*) filter (where {qc} ~ '{ISO_TS}'),
                count(*) filter (where {qc} ~ '{DMY}'), count(*) filter (where {qc} <> btrim({qc})),
                count(*) filter (where {qc} ~ '(Ã|�|ï¿½)'), count(*) filter (where lower({qc}) in ('nan','none','null','n/a','na'))
                from {fq}""").fetchone()
            if nn == 0: continue
            if num / nn >= 0.98 and not CODE_NAME.match(c) and not osm and c not in N.INT_KEYS | N.FLOAT_KEYS:
                bad = Q(f"select {qc} from {fq} where {qc} !~ '{NUM}' and {qc} is not null group by 1 order by count(*) desc limit 3")
                add("HIGH", f"{s}.{t}", c, "numeric values stored as text", f"{num}/{nn} numeric; stray values {[b[0] for b in bad]}")
            if (iso_d + iso_ts) / nn >= 0.95 and not osm: add("HIGH", f"{s}.{t}", c, "date/timestamp stored as text", f"{iso_d} dates, {iso_ts} timestamps of {nn}")
            if dmy / nn >= 0.95: add("HIGH", f"{s}.{t}", c, "dd/mm/yyyy date stored as text", f"{dmy} of {nn}")
            if ws: add("MED", f"{s}.{t}", c, "leading/trailing whitespace", f"{ws} values")
            if moj: add("MED", f"{s}.{t}", c, "source-damaged text (bytes lost in the original file; not recoverable)", f"{moj} values")
            if lit: add("MED", f"{s}.{t}", c, "literal NaN/None/null/NA strings", f"{lit} values")
        elif d in ("integer", "bigint", "double precision", "numeric", "smallint", "real"):
            if CODE_NAME.match(c) and c not in N.INT_KEYS and not osm:
                add("MED", f"{s}.{t}", c, "identifier/code column stored as number (policy: codes are text)", f"type {d}")
            # value ranges
            rng = {"codi_districte": (1, 10), "codi_barri": (1, 73), "seccio_censal": (1001, 10999), "any_": (1900, 2035), "lat": (39, 43), "lon": (0, 4)}
            if c in rng:
                lo, hi = rng[c]; mn, mx, bad = conn.execute(f"select min({qc}), max({qc}), count(*) filter (where {qc} < {lo} or {qc} > {hi}) from {fq}").fetchone()
                if bad: add("HIGH", f"{s}.{t}", c, "value outside valid range", f"{bad} rows outside [{lo},{hi}] (min {mn}, max {mx})")
            if (c.startswith("pct_") or c.endswith("_pct") or "_pct_" in c) and not re.search(r"growth|change", c):   # growth rates may be < 0 or > 100
                mn, mx = conn.execute(f"select min({qc}), max({qc}) from {fq}").fetchone()
                if mn is not None and (mn < 0 or mx > 100.0001): add("MED", f"{s}.{t}", c, "percentage outside 0-100", f"min {mn}, max {mx}")
            if d in ("integer", "bigint") and (c.startswith(("n_", "total_", "num_")) or c in ("nombre", "valor")):
                neg = conn.execute(f"select count(*) from {fq} where {qc} < 0").fetchone()[0]
                if neg: add("MED", f"{s}.{t}", c, "negative count", f"{neg} rows")

# ---- same column name, different type across tables
types = defaultdict(lambda: defaultdict(list))
for (s, t), cl in bytab.items():
    if t in OSM_TABLES: continue                      # OSM tag dumps are text by policy; their tags are not the same concepts
    for c, d in cl:
        if c != "geom": types[c][d].append(f"{s}.{t}")
compat = set()    # strict since 2026-10-14: integer vs bigint and numeric vs double are type inconsistencies too
# documented exceptions: OSM free-text tags (values such as "yes", "2019-05", "~1990") and a mixed-unit long table (EUR / count / m2 in one column)
TYPE_EXCEPTIONS = {"area": {"raw.com_plazaparc_clean"}, "date": {"raw.com_plazaparc_clean"}, "start_date": {"raw.com_plazaparc_clean", "raw.hist_osm_shops"},
                   "nombre": {"raw.hou_2026_locals_us_desti"}}
for c, dd in types.items():
    if c in TYPE_EXCEPTIONS:
        dd = {k: [t_ for t_ in v if t_ not in TYPE_EXCEPTIONS[c]] for k, v in dd.items()}; dd = {k: v for k, v in dd.items() if v}
    if len(dd) > 1:
        ks = frozenset(dd.keys())
        sev = "INFO" if ks in compat else ("HIGH" if c in ("codi_districte", "nom_districte", "codi_barri", "nom_barri", "seccio_censal", "any_", "lat", "lon", "total_poblacio") else "MED")
        add(sev, "(several)", c, "same column name has different types", {k: [t_ for t_ in v][:4] for k, v in dd.items()})

# ---- geometry audit
for s, t, k, n in tabs:
    if k != "spatial": continue
    fq = f'{s}."{t}"'
    srid, = conn.execute(f"select coalesce(max(st_srid(geom)),0) from {fq}").fetchone()
    inv, emp, nul, mix = conn.execute(f"select count(*) filter (where not st_isvalid(geom)), count(*) filter (where st_isempty(geom)), count(*) filter (where geom is null), count(distinct geometrytype(geom)) from {fq}").fetchone()
    xmin, ymin, xmax, ymax = conn.execute(f"select min(st_xmin(geom)), min(st_ymin(geom)), max(st_xmax(geom)), max(st_ymax(geom)) from {fq} where geom is not null").fetchone()
    if srid != 25831: add("HIGH", f"{s}.{t}", "geom", "wrong SRID", srid)
    if inv: add("HIGH", f"{s}.{t}", "geom", "invalid geometries", f"{inv} of {n}")
    if emp: add("MED", f"{s}.{t}", "geom", "empty geometries", f"{emp} of {n}")
    if nul: add("MED", f"{s}.{t}", "geom", "NULL geometries", f"{nul} of {n}")
    if mix > 1: add("INFO", f"{s}.{t}", "geom", "mixed geometry types", mix)
    if xmin is not None and (xmin < 380000 or xmax > 470000 or ymin < 4560000 or ymax > 4610000):
        add("MED", f"{s}.{t}", "geom", "extent outside Barcelona area (EPSG:25831)", f"x {xmin:.0f}-{xmax:.0f}, y {ymin:.0f}-{ymax:.0f}")

# ---- key uniqueness for per-barri / per-section tables
for (s, t), cl in bytab.items():
    names = [c for c, _ in cl]; n = rows_of.get((s, t), 0)
    for key, expect in (("codi_barri", 73), ("seccio_censal", 1068)):
        if key in names and n == expect:
            dist = conn.execute(f'select count(distinct "{key}") from {s}."{t}"').fetchone()[0]
            if dist != expect: add("HIGH", f"{s}.{t}", key, "key not unique in a one-row-per-unit table", f"{n} rows, {dist} distinct")

df = pd.DataFrame(issues, columns=["severity", "table", "column", "problem", "detail"]).sort_values(["severity", "table", "column"])
df.to_csv("data/type_audit.csv", index=False, encoding="utf-8")
df.to_csv("data/type_audit.csv", index=False, encoding="utf-8")
with conn.transaction():
    conn.execute("DROP TABLE IF EXISTS meta.type_audit"); conn.execute("CREATE TABLE meta.type_audit (severity text, table_name text, column_name text, problem text, detail text)")
    conn.cursor().executemany("INSERT INTO meta.type_audit VALUES (%s,%s,%s,%s,%s)", df.values.tolist())
conn.commit()
print("tables:", len(bytab), "| columns:", sum(len(v) for v in bytab.values()), "| issues:", len(df)); print(df.groupby(["severity", "problem"]).size().to_string())
