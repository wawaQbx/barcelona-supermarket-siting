"""Model results for the dashboard: the siting model (v4: Poisson, ln(population) offset, barri-clustered errors; analyze_siting.py) is written
to docs/model_v4_blocks*.csv. This script loads those files into ana.py_model_v4_coefficients / ana.py_model_v4_fit and rebuilds the dashboard
layer gis.model_drivers (dbt, tag after_models). Run after analyze_siting.py.
"""
import subprocess
from pathlib import Path
import pandas as pd, psycopg
from sqlalchemy import create_engine

ROOT = Path(__file__).parent
eng = create_engine("postgresql+psycopg://postgres@localhost:5432/supermarket_bcn")   # password from pgpass.conf
coef = pd.read_csv(ROOT / "docs" / "model_v4_blocks_coefficients.csv").rename(columns={"group": "brand_group", "variable": "factor_code"})
# multiple testing: 7 groups x 15 predictors = 105 tests. Benjamini-Hochberg q value = expected share of false positives among the results
# declared significant at that level (q < 0.05: at most ~5% of them are chance findings)
from statsmodels.stats.multitest import multipletests
coef["q_value_bh"] = multipletests(coef.p_value, method="fdr_bh")[1]
fit = pd.read_csv(ROOT / "docs" / "model_v4_blocks.csv").rename(columns={"group": "brand_group", "stores": "stores_n"})
coef.to_sql("py_model_v4_coefficients", eng, schema="ana", if_exists="replace", index=False)
fit.to_sql("py_model_v4_fit", eng, schema="ana", if_exists="replace", index=False)
with psycopg.connect("host=localhost port=5432 dbname=supermarket_bcn user=postgres", autocommit=True) as c:
    c.execute("COMMENT ON TABLE ana.py_model_v4_coefficients IS 'Siting model v4 (Poisson, ln(population) offset, errors clustered by barri, all predictors): rate ratio per SD with 95% interval per chain group and predictor. Built by load_model_outputs.py from docs/model_v4_blocks_coefficients.csv (analyze_siting.py)'")
    c.execute("COMMENT ON TABLE ana.py_model_v4_fit IS 'Siting model v4 fit per chain group: stores, AIC, Wald tests of the cadastre and traffic blocks, cross-validated AUC. Built by load_model_outputs.py from docs/model_v4_blocks.csv (analyze_siting.py)'")
print(len(coef), "coefficients,", len(fit), "groups loaded")
DBT = ROOT / "dbt_bcn"   # --full-refresh: the seed table is recreated even when its columns change
r = subprocess.run(["cmd", "/c", str(DBT / "dbt.cmd"), "build", "--select", "factor_labels", "tag:after_models", "--full-refresh"], cwd=DBT, capture_output=True, text=True, encoding="utf-8", errors="replace")
print(chr(10).join(l for l in r.stdout.splitlines() if any(k in l for k in ("OK created", "OK loaded", "ERROR", "FAIL", "Done."))))
print("gis.model_drivers", "OK" if r.returncode == 0 else f"FAILED (exit {r.returncode})")
