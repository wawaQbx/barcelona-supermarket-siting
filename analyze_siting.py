"""Siting models: store count per census section and per barri, one model per chain.
v1 (exploratory): Poisson, robust HC1 errors, outcome definitions inside / within 500 m (city only, with outside stores) / 1000 m.
v2 (current):     Poisson with errors clustered by barri (sections) or district (barris); negative-binomial alpha reported as over-dispersion check,
                  + competition (other chains' stores within 500 m) + vacant ground-floor share; residual spatial autocorrelation (Moran's I).
Results -> docs/model_summary.csv, docs/model_coefficients_{section,barri}.csv (v1), docs/model_v2_*.csv (v2); write-up in docs/MODEL_RESULTS.md.
Run after import_all.py:  .venv\\Scripts\\python.exe analyze_siting.py
"""
import warnings
from pathlib import Path
import numpy as np, pandas as pd, psycopg, statsmodels.api as sm
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")
ROOT = Path(__file__).parent
CONN = "host=localhost port=5432 dbname=supermarket_bcn user=postgres"   # password from pgpass.conf
BRANDS = ["ALL", "Condis", "Dia", "Caprabo", "Mercadona", "Consum_Charter", "BonPreu_Esclat", "Lidl", "Aldi", "Carrefour", "Alcampo"]

def load(sql):
    with psycopg.connect(CONN) as c: return pd.read_sql(sql, c)

def zs(X): return (X - X.mean()) / X.std()      # standardised: a coefficient = effect of +1 standard deviation

def design(df, unit):
    X = pd.DataFrame(index=df.index)
    X["ln_population_per_ha"] = np.log(df.population_per_ha.clip(lower=1))
    X["share_age_65plus_pct"] = df.share_age_65plus_pct
    X["share_tertiary_education_pct"] = df.share_tertiary_education_pct
    X["ln_income_eur"] = np.log(df.disposable_income_eur_per_person)
    X["cars_per_1000_residents"] = df.cars_per_1000_residents
    X["ln_transit_departures_300m"] = np.log1p(df.transit_departures_weekday_300m_n if unit == "section" else df.transit_departures_weekday_300m_mean_n)
    X["ln_active_premises"] = np.log1p(df.premises_active_n)
    X["ln_area_ha"] = np.log(df.area_ha)
    if unit == "section": X["dist_centre_km"] = df.dist_placa_catalunya_m / 1000.0
    return X

def cv_auc(y, X):
    pres = (y > 0).astype(int)
    if min(pres.sum(), len(pres) - pres.sum()) < 10: return None     # too few units in one class for 5-fold CV
    p = cross_val_predict(LogisticRegression(max_iter=2000), X, pres, cv=StratifiedKFold(5, shuffle=True, random_state=1), method="predict_proba")[:, 1]
    return roc_auc_score(pres, p)

def morans_i(r, xy, band=500.0):
    """Moran's I of residuals r with binary weights for unit centres closer than `band` metres (row-standardised)."""
    d = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(-1)); W = ((d > 0) & (d <= band)).astype(float)
    rs = W.sum(1); W = W[rs > 0] / rs[rs > 0, None]; z = r - r.mean()
    return float((z[rs > 0] * (W @ z)).sum() / (z ** 2).sum() * len(z) / (rs > 0).sum())

def load_unit(unit):
    if unit == "section":
        m = load("select * from ana.section_model_table where not coalesce(cars_fleet_distorted, false)")
        c = load("select * from ana.store_counts_section"); key, cl = "seccio_censal", "codi_barri"
    else:
        m = load("select b.*, n.codi_districte from ana.barri_model_table b join ana.dim_neighborhood n using (codi_barri)")
        c = load("select * from ana.store_counts_barri"); key, cl = "codi_barri", "codi_districte"
    m = m.dropna(subset=["disposable_income_eur_per_person", "share_age_65plus_pct", "cars_per_1000_residents"])
    # fixed row order: cross-validation folds and sampled alternatives must not depend on the order PostgreSQL returns rows in
    m = m.sort_values(key).reset_index(drop=True); c = c.sort_values([key, "brand_group"]).reset_index(drop=True)
    return m, c, key, cl

# ------------------------------------------------------------------ v1
def run_v1(unit):
    m, c, key, _ = load_unit(unit)
    defs = ({"inside": "n_inside", "city_500m": "n_city_within_500m", "all_500m": "n_all_within_500m", "all_1000m": "n_all_within_1000m"} if unit == "section"
            else {"inside": "n_inside", "city_1000m": "n_city_within_1000m", "all_1000m": "n_all_within_1000m"})
    X = zs(design(m, unit)); rows, summary = [], []
    for b in BRANDS:
        cb = c[c.brand_group == b].set_index(key)
        for dname, col in defs.items():
            y = m[key].map(cb[col]).fillna(0).astype(float)
            r = sm.GLM(y, sm.add_constant(X), family=sm.families.Poisson()).fit(cov_type="HC1")
            summary.append(dict(unit=unit, brand=b, definition=dname, units_n=len(y), stores_counted=int(y.sum()), units_with_store=int((y > 0).sum()),
                                deviance_explained=1 - r.deviance / r.null_deviance, cv_auc_presence=cv_auc(y, X)))
            for v in X.columns:
                rows.append(dict(unit=unit, brand=b, definition=dname, variable=v, coef_per_sd=r.params[v], rate_ratio_per_sd=float(np.exp(r.params[v])), p_value=r.pvalues[v]))
    return pd.DataFrame(rows), pd.DataFrame(summary)

# ------------------------------------------------------------------ v2
def run_v2(unit):
    m, c, key, cl = load_unit(unit)
    base = design(m, unit)
    vac = m.premises_vacant_n / (m.premises_active_n + m.premises_vacant_n).replace(0, np.nan)
    base["vacant_share_pct"] = (100 * vac).fillna(0)
    allc = c[c.brand_group == "ALL"].set_index(key)
    comp_col = "n_all_within_500m" if unit == "section" else "n_all_within_1000m"
    xy = m[["x_utm25831_m", "y_utm25831_m"]].to_numpy() if unit == "section" else None
    rows, summary = [], []
    for b in BRANDS:
        cb = c[c.brand_group == b].set_index(key)
        y = m[key].map(cb["n_inside"]).fillna(0).astype(float)
        X = base.copy()
        if b != "ALL":   # competition: stores of the OTHER chains near the unit (own chain removed)
            X["ln_other_chains_near"] = np.log1p(m[key].map(allc[comp_col]).fillna(0) - m[key].map(cb[comp_col]).fillna(0))
        X = zs(X); Xc = sm.add_constant(X); groups = m[cl].astype(int).to_numpy()
        # Poisson with clustered errors; a negative-binomial fit is kept only as an over-dispersion diagnostic
        # (alpha ~ 0 for every chain except Alcampo: inside-unit counts are mostly 0 / 1, Poisson is adequate)
        r = sm.GLM(y, Xc, family=sm.families.Poisson()).fit(cov_type="cluster", cov_kwds={"groups": groups})
        try: alpha = float(sm.NegativeBinomial(y, Xc).fit(disp=0, maxiter=300).params["alpha"])
        except Exception: alpha = None
        llf = r.llf; ll0 = sm.GLM(y, np.ones((len(y), 1)), family=sm.families.Poisson()).fit().llf
        mu = r.predict(Xc); resid = (y - mu) / np.sqrt(mu); conv = bool(r.converged)
        summary.append(dict(unit=unit, brand=b, units_n=len(y), stores_inside=int(y.sum()), units_with_store=int((y > 0).sum()), nb_alpha=alpha,
                            mcfadden_pseudo_r2=1 - llf / ll0, cv_auc_presence=cv_auc(y, X), converged=conv,
                            residual_morans_i_500m=morans_i(resid.to_numpy(), xy) if xy is not None else None))
        for v in X.columns:
            rows.append(dict(unit=unit, brand=b, variable=v, coef_per_sd=r.params[v], rate_ratio_per_sd=float(np.exp(r.params[v])),
                             ci95_low=float(np.exp(r.conf_int().loc[v, 0])), ci95_high=float(np.exp(r.conf_int().loc[v, 1])), p_value=r.pvalues[v]))
    return pd.DataFrame(rows), pd.DataFrame(summary)

# ------------------------------------------------------------------ v3
# (1) format split: Alcampo hypermarkets / Mi Alcampo, Carrefour convenience / supermarket
# (2) competition split: OWN chain vs OTHER chains, counted in a RING (within 500 m, 2000 m for hypermarkets, but outside the section),
#     so the store being explained never appears in its own predictor
# (3) openings 2016-2024 (first seen after the 2014 census; Clarel -> Dia conversions excluded), with the 2014 network as competition,
#     compared with a model of the stores already open in 2014 (same predictors)
CORE = ["ln_population_per_ha", "share_age_65plus_pct", "share_tertiary_education_pct", "ln_income_eur", "ln_transit_departures_300m", "ln_active_premises", "ln_area_ha"]
CHAIN_OF = {"Alcampo_hypermarket": "Alcampo", "Alcampo_MiAlcampo": "Alcampo", "Carrefour_convenience": "Carrefour", "Carrefour_supermarket": "Carrefour"}
GROUPS_V3 = ["ALL", "Condis", "Dia", "Caprabo", "Mercadona", "Consum_Charter", "BonPreu_Esclat", "Lidl", "Aldi",
             "Alcampo_MiAlcampo", "Alcampo_hypermarket", "Carrefour_convenience", "Carrefour_supermarket"]
MIN_EVENTS = 15     # fewer stores than this: no model, description only

def fit_poisson(y, X, groups, xy):
    X = X.loc[:, X.std() > 0]          # a constant column (e.g. a chain with no store in any ring in 2014) cannot be estimated
    Xc = sm.add_constant(zs(X)); r = sm.GLM(y, Xc, family=sm.families.Poisson()).fit(cov_type="cluster", cov_kwds={"groups": groups})
    ll0 = sm.GLM(y, np.ones((len(y), 1)), family=sm.families.Poisson()).fit().llf
    mu = r.predict(Xc); ci = r.conf_int()
    stats = dict(mcfadden_pseudo_r2=1 - r.llf / ll0, cv_auc_presence=cv_auc(y, zs(X)), residual_morans_i_500m=morans_i(((y - mu) / np.sqrt(mu)).to_numpy(), xy),
                 events_per_variable=y.sum() / X.shape[1])
    coefs = [dict(variable=v, rate_ratio_per_sd=float(np.exp(r.params[v])), ci95_low=float(np.exp(ci.loc[v, 0])), ci95_high=float(np.exp(ci.loc[v, 1])), p_value=r.pvalues[v]) for v in X.columns]
    return stats, coefs

def run_v3():
    m, c, key, cl = load_unit("section")
    base = design(m, "section")[CORE]; groups = m[cl].astype(int).to_numpy(); xy = m[["x_utm25831_m", "y_utm25831_m"]].to_numpy()
    o = load("select * from ana.store_openings_section").set_index(["seccio_censal", "brand_group"])
    C = c.set_index(["seccio_censal", "brand_group"])
    get = lambda df, grp, col: m[key].map(lambda s: df[col].get((s, grp), 0)).astype(float)
    rows, summ = [], []
    for g in GROUPS_V3:
        chain = CHAIN_OF.get(g, g); hyper = g == "Alcampo_hypermarket"; ring = "2000m" if hyper else "500m"
        specs = {"all_current_stores": (get(C, g, "n_inside"), "n_ring_" + ring),
                 "legacy_open_in_2014": (get(C, g, "n_inside_legacy_2014"), "n_ring_" + ring),
                 "openings_2016_2024": (get(o, g, "n_openings_2016_2024") - get(o, g, "n_openings_clarel"), f"n_ring_{ring}_legacy_2014"),
                 "openings_new_site_only": (get(o, g, "n_openings_new_site"), f"n_ring_{ring}_legacy_2014")}
        for spec, (y, ringcol) in specs.items():
            if y.sum() < MIN_EVENTS:
                summ.append(dict(group=g, outcome=spec, stores=int(y.sum()), note=f"fewer than {MIN_EVENTS} stores: not modelled")); continue
            X = base.copy()
            if g != "ALL":   # own chain vs other chains in the ring (for openings: the network that existed in 2014)
                own = get(C, chain, ringcol); allr = get(C, "ALL", ringcol)
                X["ln_own_chain_ring"] = np.log1p(own); X["ln_other_chains_ring"] = np.log1p(allr - own)
            else:
                X["ln_all_stores_ring"] = np.log1p(get(C, "ALL", ringcol))
            st, cf = fit_poisson(y, X, groups, xy)
            summ.append(dict(group=g, outcome=spec, stores=int(y.sum()), sections_with_store=int((y > 0).sum()), competition_ring=ringcol, **st))
            rows += [dict(group=g, outcome=spec, **d) for d in cf]
    return pd.DataFrame(rows), pd.DataFrame(summ)

# ------------------------------------------------------------------ v4
# Specification: ln(population) as OFFSET (outcome = stores per resident) - area and density are collinear (corr -0.95), so area is dropped.
# (1) do cadastral and traffic variables add information?  joint Wald test of each block with barri-clustered errors
# (2) time ordering: openings 2016-2024 explained by predictors measured BEFORE them (Padro 2015, income 2015, 2014 census, 2014 network)
# (3) before / after: event study of active premises around new store sites (site and edition fixed effects)
# (4) natural experiment: L10 Sud metro (Foc / Foneria, Sep 2018) -> difference in differences on supermarket openings
import statsmodels.formula.api as smf
BASE4 = ["ln_population_per_ha", "share_age_65plus_pct", "share_tertiary_education_pct", "ln_income_eur", "cars_per_1000_residents",
         "ln_transit_departures_300m", "ln_active_premises", "dist_centre_km"]
GROUPS_V4 = ["ALL", "Condis", "Dia", "Caprabo", "Consum_Charter", "Mercadona", "BonPreu_Esclat"]

def blocks(m):
    X = design(m, "section")[BASE4].copy()
    cad = pd.DataFrame(index=m.index)
    cad["bldg_mean_age_years"] = m.bldg_mean_age_years.astype(float).fillna(m.bldg_mean_age_years.astype(float).median())
    cad["ln_cadastral_value_eur_m2"] = np.log(m.cadastral_value_eur_per_m2.astype(float))
    cad["floor_area_ratio"] = m.floor_area_ratio.astype(float)
    cad["commercial_floor_share_pct"] = m.commercial_floor_share_pct.astype(float).fillna(0)
    trf = pd.DataFrame(index=m.index)
    trf["ln_main_road_len_m"] = np.log1p(m.main_road_len_50m_m.astype(float))
    trf["ln_pedestrian_street_len_m"] = np.log1p(m.pedestrian_street_len_50m_m.astype(float))
    # motorway length dropped: only 17 sections have one and several chains have no store there (complete separation, rate ratios ~0.02)
    trf["ln_imd_max_300m"] = np.log1p(m.imd_max_300m_vehicles_per_day.astype(float).fillna(0))
    return X, cad, trf

def glm_offset(y, X, off, groups):
    Xc = sm.add_constant(zs(X.loc[:, X.std() > 0]))
    return sm.GLM(y, Xc, family=sm.families.Poisson(), offset=off).fit(cov_type="cluster", cov_kwds={"groups": groups}), Xc

def joint_wald(r, names):
    names = [n for n in names if n in r.params.index]
    R = np.zeros((len(names), len(r.params))); idx = list(r.params.index)
    for i, n in enumerate(names): R[i, idx.index(n)] = 1
    w = r.wald_test(R, scalar=True); return float(np.squeeze(w.statistic)), float(w.pvalue)

def run_v4_blocks():
    m, c, key, cl = load_unit("section"); g = m[cl].astype(int).to_numpy(); off = np.log(m.population_n.astype(float))
    X, cad, trf = blocks(m); rows, coefs = [], []
    for b in GROUPS_V4:
        y = m[key].map(c[c.brand_group == b].set_index(key)["n_inside"]).fillna(0).astype(float)
        r0, _ = glm_offset(y, X, off, g); full = pd.concat([X, cad, trf], axis=1); r1, _ = glm_offset(y, full, off, g)
        w_cad = joint_wald(r1, list(cad.columns)); w_trf = joint_wald(r1, list(trf.columns))
        rows.append(dict(group=b, stores=int(y.sum()), aic_base=r0.aic, aic_with_cadastre_traffic=r1.aic,
                         wald_cadastre_chi2=w_cad[0], wald_cadastre_p=w_cad[1], wald_traffic_chi2=w_trf[0], wald_traffic_p=w_trf[1],
                         cv_auc_base=cv_auc(y, zs(X)), cv_auc_full=cv_auc(y, zs(full))))
        ci = r1.conf_int()
        coefs += [dict(group=b, variable=v, rate_ratio_per_sd=float(np.exp(r1.params[v])), ci95_low=float(np.exp(ci.loc[v, 0])), ci95_high=float(np.exp(ci.loc[v, 1])), p_value=r1.pvalues[v])
                  for v in r1.params.index if v != "const"]
    return pd.DataFrame(rows), pd.DataFrame(coefs)

def run_v4_time_order():
    m, c, key, cl = load_unit("section"); g = m[cl].astype(int).to_numpy()
    b15 = load("select * from ana.section_baseline_2015").set_index("seccio_censal")
    o = load("select * from ana.store_openings_section").set_index(["seccio_censal", "brand_group"]); C = c.set_index(["seccio_censal", "brand_group"])
    get = lambda df, grp, col: m[key].map(lambda s: df[col].get((s, grp), 0)).astype(float)
    now = design(m, "section")[BASE4].copy()
    bl = pd.DataFrame(index=m.index)
    bl["ln_population_per_ha"] = np.log(m[key].map(b15.population_per_ha_2015).astype(float).clip(lower=1))
    bl["share_age_65plus_pct"] = m[key].map(b15.share_age_65plus_2015_pct).astype(float)
    bl["share_tertiary_education_pct"] = m[key].map(b15.share_tertiary_education_2015_pct).astype(float)
    bl["ln_income_eur"] = np.log(m[key].map(b15.disposable_income_2015_eur_per_person).astype(float))
    bl["cars_per_1000_residents"] = now.cars_per_1000_residents          # no vehicle history: 2025 value (slow-moving)
    bl["ln_transit_departures_300m"] = now.ln_transit_departures_300m    # no GTFS history: current timetable
    bl["ln_active_premises"] = np.log1p(m[key].map(b15.premises_active_2014_n).astype(float))
    bl["dist_centre_km"] = now.dist_centre_km
    off_now = np.log(m.population_n.astype(float)); off_15 = np.log(m[key].map(b15.population_2015_n).astype(float))
    rows = []
    for b in ["ALL", "Condis", "Consum_Charter", "Caprabo", "Mercadona"]:
        y = get(o, b, "n_openings_2016_2024") - get(o, b, "n_openings_clarel")
        for spec, X, off in (("contemporaneous_2022_2026", now, off_now), ("time_ordered_2014_2015", bl, off_15)):
            X = X.copy()
            if b != "ALL":
                own = get(C, b, "n_ring_500m_legacy_2014"); allr = get(C, "ALL", "n_ring_500m_legacy_2014")
                X["ln_own_chain_ring_2014"] = np.log1p(own); X["ln_other_chains_ring_2014"] = np.log1p(allr - own)
            r, _ = glm_offset(y, X, off, g); ci = r.conf_int()
            rows += [dict(group=b, spec=spec, openings=int(y.sum()), variable=v, rate_ratio_per_sd=float(np.exp(r.params[v])),
                          ci95_low=float(np.exp(ci.loc[v, 0])), ci95_high=float(np.exp(ci.loc[v, 1])), p_value=r.pvalues[v], aic=r.aic)
                     for v in r.params.index if v != "const"]
    return pd.DataFrame(rows)

def run_v4_event_study():
    p = load("select * from ana.store_site_premises_panel")
    ED = [2014, 2016, 2019, 2022, 2024]; idx = {y: i for i, y in enumerate(ED)}
    out = []
    for sample in ("new_site", "takeover_of_food_premise"):
        d = p[p.opening_type.isin([sample, "legacy_2014"])].copy()
        d["ln_premises"] = np.log1p(d.active_premises_150m_n)
        d["k"] = np.where(d.opening_type == sample, d.census_year.map(idx) - d.first_seen_census_year.map(idx), np.nan)
        # event-time bins relative to the last census BEFORE the store appears (k = -1 is the reference)
        for name, cond in (("pre_k_le_m2", d.k <= -2), ("open_k0", d.k == 0), ("post_k1", d.k == 1), ("post_k_ge2", d.k >= 2)):
            d[name] = cond.astype(int)
        r = smf.ols("ln_premises ~ pre_k_le_m2 + open_k0 + post_k1 + post_k_ge2 + C(store_id) + C(census_year)", data=d).fit(
            cov_type="cluster", cov_kwds={"groups": pd.factorize(d.store_id)[0]})
        ci = r.conf_int()
        for v in ("pre_k_le_m2", "open_k0", "post_k1", "post_k_ge2"):
            out.append(dict(sample=sample, sites_treated=int(d[d.opening_type == sample].store_id.nunique()), sites_control=int(d[d.opening_type == "legacy_2014"].store_id.nunique()),
                            event_time=v, pct_change_premises=100 * (np.exp(r.params[v]) - 1),
                            ci95_low_pct=100 * (np.exp(ci.loc[v, 0]) - 1), ci95_high_pct=100 * (np.exp(ci.loc[v, 1]) - 1), p_value=r.pvalues[v]))
    return pd.DataFrame(out)

def run_v4_metro():
    s = load("select * from ana.section_metro_l10")
    rows = []
    for ctrl in ("no_metro_before", "all_sections"):
        d = (s[~s.had_metro_500m_before] if ctrl == "no_metro_before" else s[~(s.near_new_l10_station & s.had_metro_500m_before)]).reset_index(drop=True)
        long = pd.concat([pd.DataFrame(dict(treated=d.treated.astype(int), post=0, y=d.openings_pre_2014_2016_n, years=2.0, barri=d.codi_barri)),
                          pd.DataFrame(dict(treated=d.treated.astype(int), post=1, y=d.openings_post_2017_2024_n, years=8.0, barri=d.codi_barri))], ignore_index=True)
        r = smf.glm("y ~ treated * post", data=long, family=sm.families.Poisson(), offset=np.log(long.years)).fit(cov_type="cluster", cov_kwds={"groups": long.barri.astype(int)})
        pre, post = d.openings_pre_2014_2016_n.to_numpy(), d.openings_post_2017_2024_n.to_numpy()
        def did(tr):   # change in openings per section-year, treated minus control
            return (post[tr].sum() / (tr.sum() * 8) - pre[tr].sum() / (tr.sum() * 2)) - (post[~tr].sum() / ((~tr).sum() * 8) - pre[~tr].sum() / ((~tr).sum() * 2))
        tr0 = d.treated.to_numpy().astype(bool); obs = did(tr0); rng = np.random.default_rng(1); n_t = int(tr0.sum())
        sims = np.array([did(np.isin(np.arange(len(d)), rng.choice(len(d), n_t, replace=False))) for _ in range(5000)])
        rows.append(dict(control=ctrl, treated_sections=n_t, control_sections=int((~tr0).sum()),
                         openings_treated_pre=int(pre[tr0].sum()), openings_treated_post=int(post[tr0].sum()),
                         openings_control_pre=int(pre[~tr0].sum()), openings_control_post=int(post[~tr0].sum()),
                         did_rate_ratio=float(np.exp(r.params.get("treated:post", np.nan))), did_p_cluster=float(r.pvalues.get("treated:post", np.nan)),
                         did_openings_per_section_year=obs, randomisation_p=float(np.mean(np.abs(sims) >= abs(obs)))))
    return pd.DataFrame(rows)

def run_v4_building_origin():
    """Why are buildings newer? Decompose 'mean building age' into construction period, PGM zoning type and population growth 2007-2026
    (new development), and check whether the 'newer buildings' effect survives."""
    m, c, key, cl = load_unit("section"); g = m[cl].astype(int).to_numpy(); off = np.log(m.population_n.astype(float))
    ph = load("select seccio_censal, extract(year from data_referencia)::int y, habitants_n from raw.pop_padro_population_history").pivot(index="seccio_censal", columns="y", values="habitants_n")
    X, cad, _ = blocks(m)
    cad = cad.drop(columns=["bldg_mean_age_years"])
    origin = pd.DataFrame(index=m.index)
    for v in ("bldg_share_pre1941_pct", "bldg_share_1951_1980_pct", "bldg_share_post1990_pct", "pgm_share_12_old_town_pct",
              "pgm_share_18_specific_volume_pct", "pgm_share_20_detached_pct", "pgm_share_22_industrial_pct"):
        origin[v] = m[v].astype(float).fillna(0)
    origin["population_growth_2007_2026_pct"] = m[key].map(100 * (ph[2026] - ph[2007]) / ph[2007]).astype(float)
    age = m.bldg_mean_age_years.astype(float).fillna(m.bldg_mean_age_years.astype(float).median()).rename("bldg_mean_age_years")
    rows = []
    for b in ["ALL", "Condis", "Dia", "Caprabo", "Consum_Charter", "Mercadona"]:
        y = m[key].map(c[c.brand_group == b].set_index(key)["n_inside"]).fillna(0).astype(float)
        for spec, Z in (("A_mean_age_only", pd.concat([X, cad, age], axis=1)), ("B_origin_only", pd.concat([X, cad, origin], axis=1)),
                        ("C_origin_plus_mean_age", pd.concat([X, cad, origin, age], axis=1))):
            r, _ = glm_offset(y, Z, off, g); ci = r.conf_int()
            rows += [dict(group=b, spec=spec, variable=v, rate_ratio_per_sd=float(np.exp(r.params[v])), ci95_low=float(np.exp(ci.loc[v, 0])),
                          ci95_high=float(np.exp(ci.loc[v, 1])), p_value=r.pvalues[v], aic=r.aic)
                     for v in list(origin.columns) + ["bldg_mean_age_years", "commercial_floor_share_pct", "ln_cadastral_value_eur_m2"] if v in r.params.index]
    return pd.DataFrame(rows)

# ------------------------------------------------------------------ v5: the store's own building (cadastre INSPIRE)
# Case-control within barri: store buildings vs buildings of other active ground-floor premises (2024 census) IN THE SAME BARRI
# (logit with barri fixed effects, errors clustered by census section). Odds ratio > 1 = supermarkets are more likely in such buildings.
ERA_BINS = [0, 1940, 1960, 1980, 2000, 2100]; ERA_LAB = ["before_1941", "1941_1960", "1961_1980", "1981_2000", "after_2000"]

def run_v5_buildings():
    s = load("select site_type, store_id, brand_group, format_group, first_seen_census_year, opening_type, seccio_censal, codi_barri, year_of_construction, "
             "current_use, building_units_n, dwellings_n, gross_floor_area_m2, footprint_area_m2, floors_above_ground_max from ana.site_buildings "
             "where referencia_cadastral is not null and codi_barri is not null")
    s = s[s.year_of_construction.between(1700, 2026)].copy()
    s["era"] = pd.cut(s.year_of_construction, ERA_BINS, labels=ERA_LAB, right=True).astype(str)
    s["ln_footprint_m2"] = np.log(s.footprint_area_m2.clip(lower=10)); s["floors"] = s.floors_above_ground_max.clip(upper=30)
    s["residential_building"] = (s.current_use == "1_residential").astype(int)
    for v in ("ln_footprint_m2", "floors"): s["z_" + v] = (s[v] - s[v].mean()) / s[v].std()
    desc = s.assign(group=np.where(s.site_type == "store", s.brand_group, "control_premises")).groupby("group").agg(
        sites=("era", "size"), median_year=("year_of_construction", "median"), share_after_1980_pct=("year_of_construction", lambda x: 100 * (x > 1980).mean()),
        median_footprint_m2=("footprint_area_m2", "median"), median_floors=("floors", "median"), residential_pct=("residential_building", lambda x: 100 * x.mean())).round(1)
    rows = []
    groups = {"ALL_stores": s.site_type == "store", "new_sites_2016_2024": (s.site_type == "store") & (s.opening_type == "new_site"),
              "legacy_2014": (s.site_type == "store") & (s.first_seen_census_year == 2014)}
    for b in ("Condis", "Dia", "Caprabo", "Consum_Charter", "Mercadona", "BonPreu_Esclat"): groups[b] = (s.site_type == "store") & (s.brand_group == b)
    for name, case in groups.items():
        d = s[case | (s.site_type == "control_premise")].copy(); d["y"] = case[d.index].astype(int)
        d = d[d.codi_barri.isin(d.loc[d.y == 1, "codi_barri"].unique())]          # only barris with at least one case (others carry no information)
        f = "y ~ C(era, Treatment('before_1941')) + z_ln_footprint_m2 + z_floors + residential_building + C(codi_barri)"
        try:
            r = smf.logit(f, data=d).fit(disp=0, maxiter=200, cov_type="cluster", cov_kwds={"groups": d.seccio_censal.astype(int)})
        except Exception as e:
            print("  v5 failed", name, e); continue
        ci = r.conf_int()
        for v in [p for p in r.params.index if not p.startswith("C(codi_barri)") and p != "Intercept"]:
            rows.append(dict(group=name, cases=int(d.y.sum()), controls=int((d.y == 0).sum()),
                             variable=v.replace("C(era, Treatment('before_1941'))[T.", "built_").replace("]", ""),
                             odds_ratio=float(np.exp(r.params[v])), ci95_low=float(np.exp(ci.loc[v, 0])), ci95_high=float(np.exp(ci.loc[v, 1])), p_value=r.pvalues[v]))
    # new sites: was the store opened in a building completed just before (new development)?
    n = s[(s.site_type == "store") & (s.opening_type == "new_site")]
    lag = n.first_seen_census_year - n.year_of_construction
    newdev = pd.DataFrame([dict(new_site_stores=len(n), built_within_10y_before_first_seen=int(lag.between(0, 10).sum()),
                                built_after_2000=int((n.year_of_construction > 2000).sum()), median_building_year=float(n.year_of_construction.median()))])
    return desc.reset_index(), pd.DataFrame(rows), newdev

def run_v5_barri_patterns():
    """Barri building stock (buildings holding ground-floor premises) vs. chain mix, and where each store's building ranks inside its own barri."""
    s = load("select site_type, brand_group, codi_barri, year_of_construction, footprint_area_m2 from ana.site_buildings "
             "where referencia_cadastral is not null and codi_barri is not null and year_of_construction between 1700 and 2026 order by site_id")
    nb = load("select n.codi_barri, n.nom_barri, b.population_n from ana.dim_neighborhood n join ana.barri_model_table b using (codi_barri)")
    c = s[s.site_type == "control_premise"]; st = s[s.site_type == "store"].copy()
    stock = c.groupby("codi_barri").agg(commercial_buildings=("year_of_construction", "size"), median_year=("year_of_construction", "median"),
            share_pre1941_pct=("year_of_construction", lambda x: 100 * (x <= 1940).mean()), median_footprint_m2=("footprint_area_m2", "median"),
            share_footprint_over_1000_pct=("footprint_area_m2", lambda x: 100 * (x > 1000).mean()))
    stores = st.pivot_table(index="codi_barri", columns="brand_group", values="year_of_construction", aggfunc="size", fill_value=0); stores["ALL"] = stores.sum(1)
    B = nb.set_index("codi_barri").join(stock).join(stores).fillna(0)
    B["stores_per_10k_residents"] = 1e4 * B.ALL / B.population_n
    B["stock_type"] = pd.qcut(B.median_footprint_m2, 3, labels=["small_ground_floors", "middle", "large_ground_floors"]).astype(str)
    ref = {b: g for b, g in c.groupby("codi_barri")}
    st["footprint_pctile_in_barri"] = [100 * (ref[b].footprint_area_m2 < f).mean() if b in ref else np.nan for b, f in zip(st.codi_barri, st.footprint_area_m2)]
    st["year_pctile_in_barri"] = [100 * (ref[b].year_of_construction < y).mean() if b in ref else np.nan for b, y in zip(st.codi_barri, st.year_of_construction)]
    st = st.merge(B[["stock_type"]], left_on="codi_barri", right_index=True)
    return B.reset_index(), st

# ------------------------------------------------------------------ v6
# substitution around new stores, closures, discrete choice of the site, out-of-time prediction, machine learning with spatial CV,
# spatial lags of the predictors (SLX), pacified-streets natural experiment
from scipy.spatial import cKDTree
from statsmodels.discrete.conditional_models import ConditionalLogit
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold
from sklearn.inspection import permutation_importance

def run_v6_substitution():
    p = load("select * from ana.store_site_premises_by_type where opening_type in ('new_site', 'legacy_2014')")
    ED = [2014, 2016, 2019, 2022, 2024]; idx = {y: i for i, y in enumerate(ED)}; out = []
    sites = p[["store_id", "opening_type", "first_seen_census_year"]].drop_duplicates()
    for t in ("daily_food_other", "other_retail", "restaurants_bars", "services_other"):
        yrs = ED[1:] if t == "restaurants_bars" else ED
        full = sites.merge(pd.DataFrame({"census_year": yrs}), how="cross").merge(p[p.ptype == t][["store_id", "census_year", "premises_150m_n"]], how="left").fillna({"premises_150m_n": 0})
        d = full.copy(); d["y"] = np.log1p(d.premises_150m_n)
        d["k"] = np.where(d.opening_type == "new_site", d.census_year.map(idx) - d.first_seen_census_year.map(idx), np.nan)
        for name, cond in (("pre_k_le_m2", d.k <= -2), ("open_k0", d.k == 0), ("post_k1", d.k == 1), ("post_k_ge2", d.k >= 2)): d[name] = cond.astype(int)
        r = smf.ols("y ~ pre_k_le_m2 + open_k0 + post_k1 + post_k_ge2 + C(store_id) + C(census_year)", data=d).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d.store_id)[0]})
        ci = r.conf_int()
        for v in ("pre_k_le_m2", "open_k0", "post_k1", "post_k_ge2"):
            out.append(dict(premise_type=t, event_time=v, pct_change=100 * (np.exp(r.params[v]) - 1), ci95_low_pct=100 * (np.exp(ci.loc[v, 0]) - 1),
                            ci95_high_pct=100 * (np.exp(ci.loc[v, 1]) - 1), p_value=r.pvalues[v], mean_premises=d.premises_150m_n.mean()))
    return pd.DataFrame(out)

def run_v6_closures():
    c = load("select * from ana.supermarket_premises_closures where seccio_censal is not null")
    b = load("select seccio_censal, population_per_ha_2015, disposable_income_2015_eur_per_person, share_age_65plus_2015_pct from ana.section_baseline_2015")
    c = c.merge(b, on="seccio_censal", how="left")
    rates = c.groupby("brand_group").agg(premises=("closed_by_next_census", "size"), closed_pct=("closed_by_next_census", lambda x: 100 * x.mean())).round(1)
    c["closed"] = c.closed_by_next_census.astype(int)
    c["ln_supermarkets_300m"] = np.log1p(c.supermarkets_300m_n); c["ln_chain_openings_300m_next"] = np.log1p(c.chain_openings_300m_next_n)
    c["ln_footprint_m2"] = np.log(c.footprint_area_m2.fillna(c.footprint_area_m2.median()).clip(lower=10))
    c["building_decades_since_1900"] = (c.year_of_construction.fillna(c.year_of_construction.median()) - 1900) / 10
    c["ln_density_2015"] = np.log(c.population_per_ha_2015.clip(lower=1)); c["ln_income_2015"] = np.log(c.disposable_income_2015_eur_per_person)
    c["chain"] = (c.brand_group != "independent_or_other").astype(int)
    num = ["ln_supermarkets_300m", "ln_chain_openings_300m_next", "ln_footprint_m2", "building_decades_since_1900", "ln_density_2015", "ln_income_2015", "share_age_65plus_2015_pct"]
    for v in num: c["z_" + v] = (c[v] - c[v].mean()) / c[v].std()
    rows = []
    for sample, d in (("all_supermarket_premises", c), ("independent_only", c[c.chain == 0]), ("chain_only", c[c.chain == 1])):
        f = "closed ~ " + " + ".join("z_" + v for v in num) + (" + chain" if sample == "all_supermarket_premises" else "") + " + C(census_year)"
        r = smf.logit(f, data=d.dropna(subset=["z_" + v for v in num])).fit(disp=0, cov_type="cluster", cov_kwds={"groups": d.dropna(subset=["z_" + v for v in num]).codi_barri.astype(int)})
        ci = r.conf_int()
        rows += [dict(sample=sample, n=int(r.nobs), closed=int(d.closed.sum()), variable=v.replace("z_", ""), odds_ratio=float(np.exp(r.params[v])),
                      ci95_low=float(np.exp(ci.loc[v, 0])), ci95_high=float(np.exp(ci.loc[v, 1])), p_value=r.pvalues[v])
                 for v in r.params.index if v not in ("Intercept",) and not v.startswith("C(")]
    return rates.reset_index(), pd.DataFrame(rows)

def _site_frame():
    """All candidate sites (control premises 2024 + store sites) with building, section baseline and coordinates."""
    s = load("select site_id, site_type, store_id, brand_group, opening_type, first_seen_census_year, seccio_censal, codi_barri, year_of_construction, current_use, "
             "footprint_area_m2, st_x(geom) x, st_y(geom) y from ana.site_buildings where referencia_cadastral is not null and seccio_censal is not null order by site_id")
    b = load("select * from ana.section_baseline_2015")
    s = s.merge(b[["seccio_censal", "population_per_ha_2015", "share_age_65plus_2015_pct", "share_tertiary_education_2015_pct", "disposable_income_2015_eur_per_person", "premises_active_2014_n"]], on="seccio_censal", how="left")
    s["ln_footprint_m2"] = np.log(s.footprint_area_m2.clip(lower=10)); s["building_decades_since_1900"] = (s.year_of_construction.clip(1800, 2026) - 1900) / 10
    s["residential_building"] = (s.current_use == "1_residential").astype(int)
    s["ln_density_2015"] = np.log(s.population_per_ha_2015.clip(lower=1)); s["ln_income_2015"] = np.log(s.disposable_income_2015_eur_per_person)
    s["ln_premises_2014_section"] = np.log1p(s.premises_active_2014_n)
    return s.dropna(subset=["ln_footprint_m2", "building_decades_since_1900", "ln_density_2015", "ln_income_2015", "share_tertiary_education_2015_pct"])

def run_v6_choice(n_alt=49, seed=7):
    """Conditional logit (McFadden): every store opened 2016-2024 (Clarel conversions excluded) 'chose' its site among itself + 49 randomly sampled
    ground-floor premises of the city (random sampling of alternatives keeps the estimates consistent). Competition = the 2014 network."""
    s = _site_frame(); rng = np.random.default_rng(seed)
    net = load("select brand_group, st_x(geom) x, st_y(geom) y from ana.store_points where first_seen_census_year = 2014 or (not in_city)")   # network in 2014 (+ outside stores)
    trees = {b: cKDTree(g[["x", "y"]].to_numpy()) for b, g in net.groupby("brand_group")}; tall = cKDTree(net[["x", "y"]].to_numpy())
    alts = s[s.site_type == "control_premise"].reset_index(drop=True)
    ch = s[(s.site_type == "store") & s.opening_type.isin(["new_site", "takeover_of_food_premise"])].reset_index(drop=True)
    blocks_ = []
    for i, r in ch.iterrows():
        a = alts.iloc[rng.choice(len(alts), n_alt, replace=False)].copy(); a["chosen"] = 0
        me = ch.iloc[[i]].copy(); me["chosen"] = 1
        g = pd.concat([me, a], ignore_index=True); g["choice_id"] = i; g["chooser_chain"] = r.brand_group
        xy = g[["x", "y"]].to_numpy()
        own = trees.get(r.brand_group)
        g["own_chain_2014_500m_n"] = [len(own.query_ball_point(p, 500)) if own is not None else 0 for p in xy]
        g["all_chains_2014_500m_n"] = [len(tall.query_ball_point(p, 500)) for p in xy]
        g["other_chains_2014_500m_n"] = g.all_chains_2014_500m_n - g.own_chain_2014_500m_n
        g["ln_dist_own_chain_2014_m"] = np.log(own.query(xy)[0].clip(min=20)) if own is not None else np.log(5000.0)
        blocks_.append(g)
    D = pd.concat(blocks_, ignore_index=True)
    D["ln_own_chain_500m"] = np.log1p(D.own_chain_2014_500m_n); D["ln_other_chains_500m"] = np.log1p(D.other_chains_2014_500m_n)
    X = ["ln_footprint_m2", "building_decades_since_1900", "residential_building", "ln_density_2015", "share_age_65plus_2015_pct", "share_tertiary_education_2015_pct",
         "ln_income_2015", "ln_premises_2014_section", "ln_own_chain_500m", "ln_other_chains_500m", "ln_dist_own_chain_2014_m"]
    sd = D[X].std(); rows = []
    for name, d in [("ALL_openings", D)] + [(b, D[D.chooser_chain == b]) for b in ("Condis", "Consum_Charter", "Caprabo", "Mercadona")]:
        Z = (d[X] - D[X].mean()) / sd
        Z = Z.loc[:, Z.groupby(d.choice_id).transform("std").fillna(0).sum() > 0]
        try: r = ConditionalLogit(d.chosen.to_numpy(), Z.to_numpy(), groups=d.choice_id.to_numpy()).fit(disp=0, method="bfgs", maxiter=500)
        except Exception as e: print("  choice failed", name, e); continue
        ci = r.conf_int()
        rows += [dict(group=name, choices=int(d.choice_id.nunique()), variable=v, odds_ratio_per_sd=float(np.exp(r.params[j])),
                      ci95_low=float(np.exp(ci[j, 0])), ci95_high=float(np.exp(ci[j, 1])), p_value=float(r.pvalues[j])) for j, v in enumerate(Z.columns)]
    return pd.DataFrame(rows)

def run_v6_holdout():
    """Out-of-time test: model openings first seen 2016-2022 with pre-2016 predictors, then rank sections for the 2024 openings."""
    m, c, key, cl = load_unit("section")
    b = load("select * from ana.section_baseline_2015").set_index("seccio_censal")
    pts = load("select s.store_id, s.first_seen_census_year, u.seccio_censal from ana.store_openings s join raw.adm_units_polygons u on u.tipus_ua = 'SEC_CENS' and st_intersects(u.geom, s.geom) where s.opening_type <> 'clarel_conversion' order by s.store_id")
    y_tr = m[key].map(pts[pts.first_seen_census_year <= 2022].groupby("seccio_censal").size()).fillna(0)
    y_te = m[key].map(pts[pts.first_seen_census_year == 2024].groupby("seccio_censal").size()).fillna(0)
    X = pd.DataFrame(index=m.index)
    X["ln_density_2015"] = np.log(m[key].map(b.population_per_ha_2015).astype(float).clip(lower=1))
    X["share_65plus_2015"] = m[key].map(b.share_age_65plus_2015_pct).astype(float); X["tertiary_2015"] = m[key].map(b.share_tertiary_education_2015_pct).astype(float)
    X["ln_income_2015"] = np.log(m[key].map(b.disposable_income_2015_eur_per_person).astype(float)); X["ln_premises_2014"] = np.log1p(m[key].map(b.premises_active_2014_n).astype(float))
    X["commercial_floor_share_pct"] = m.commercial_floor_share_pct.astype(float).fillna(0); X["ln_cadastral_value"] = np.log(m.cadastral_value_eur_per_m2.astype(float))
    X["dist_centre_km"] = m.dist_placa_catalunya_m / 1000; X["ln_transit"] = np.log1p(m.transit_departures_weekday_300m_n)
    C = c.set_index([key, "brand_group"]); X["ln_chain_stores_ring_2014"] = np.log1p(m[key].map(lambda s: C["n_ring_500m_legacy_2014"].get((s, "ALL"), 0)).astype(float))
    off = np.log(m[key].map(b.population_2015_n).astype(float))
    # new data of v6: premises asking price per barri (2011, latest pre-period year; barri mean of 2008-2011 where 2011 is missing) and pedestrian-priority streets
    pr = load("select codi_barri, avg(preu_oferta_local_eur_m2) filter (where any_ = 2011) p11, avg(preu_oferta_local_eur_m2) pall from raw.hou_locve_preu_oferta_locals_2008_2011 group by 1").set_index("codi_barri")
    price = m.codi_barri.map(pr.p11.fillna(pr.pall)).astype(float)
    X["ln_premises_price_2011_barri"] = np.log(price.fillna(price.median()))
    wk = load("select * from ana.section_walkability").set_index("seccio_censal")
    X["ln_pedestrian_priority_len_m"] = np.log1p(m[key].map(wk.pedestrian_priority_len_m).astype(float).fillna(0))
    Z = zs(X); r = sm.GLM(y_tr, sm.add_constant(Z), family=sm.families.Poisson(), offset=off).fit(cov_type="cluster", cov_kwds={"groups": m[cl].astype(int).to_numpy()})
    coefs = pd.DataFrame({"variable": X.columns, "rate_ratio_per_sd": np.exp(r.params[X.columns]).values, "p_value": r.pvalues[X.columns].values})
    pred = r.predict(sm.add_constant(Z), offset=off)
    gb = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, random_state=1).fit(X, (y_tr > 0).astype(int))
    pg = gb.predict_proba(X)[:, 1]
    te = (y_te > 0).astype(int); out = []
    for name, sc in (("poisson_2015_predictors", pred), ("gradient_boosting_2015_predictors", pg), ("random_ranking", np.random.default_rng(0).random(len(m)))):
        top = sc >= np.quantile(sc, 0.9)
        out.append(dict(model=name, train_openings_2016_2022=int(y_tr.sum()), test_openings_2024=int(y_te.sum()), auc_2024=roc_auc_score(te, sc),
                        share_of_2024_openings_in_top10pct_sections=float(y_te[top].sum() / y_te.sum())))
    gaps = m[[key, "codi_barri"]].assign(predicted_openings_per_decade=pred * 10 / 8, stores_now=m[key].map(c[c.brand_group == "ALL"].set_index(key).n_inside).fillna(0))
    gaps = gaps[gaps.stores_now == 0].sort_values("predicted_openings_per_decade", ascending=False).head(25)
    return pd.DataFrame(out), gaps, coefs

def run_v6_ml():
    """Store present in the section (any chain): logit vs random forest vs gradient boosting, random 5-fold vs spatial (barri-grouped) 5-fold CV."""
    m, c, key, cl = load_unit("section")
    X, cad, trf = blocks(m); X = pd.concat([X, cad, trf], axis=1); X["ln_population"] = np.log(m.population_n.astype(float))
    y = (m[key].map(c[c.brand_group == "ALL"].set_index(key).n_inside).fillna(0) > 0).astype(int).to_numpy()
    groups = m[cl].astype(int).to_numpy(); Xz = zs(X).to_numpy(); out = []
    models = {"logit": LogisticRegression(max_iter=3000), "random_forest": RandomForestClassifier(500, min_samples_leaf=5, random_state=1, n_jobs=-1),
              "gradient_boosting": HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, random_state=1)}
    for cvname, cv in (("random_5fold", StratifiedKFold(5, shuffle=True, random_state=1)), ("spatial_barri_5fold", GroupKFold(5))):
        for mn, mod in models.items():
            p = cross_val_predict(mod, Xz, y, cv=cv, groups=groups if cvname.startswith("spatial") else None, method="predict_proba")[:, 1]
            out.append(dict(cv=cvname, model=mn, auc=roc_auc_score(y, p)))
    gb = models["gradient_boosting"].fit(Xz, y)
    pi = permutation_importance(gb, Xz, y, n_repeats=20, random_state=1, scoring="roc_auc")
    imp = pd.DataFrame({"variable": X.columns, "auc_drop_when_shuffled": pi.importances_mean}).sort_values("auc_drop_when_shuffled", ascending=False)
    return pd.DataFrame(out), imp

def run_v6_slx():
    """SLX: add the mean of each predictor over neighbouring sections (centres within 750 m) - do neighbourhood conditions beyond the section matter?"""
    m, c, key, cl = load_unit("section"); g = m[cl].astype(int).to_numpy(); off = np.log(m.population_n.astype(float))
    X, cad, _ = blocks(m); X = pd.concat([X, cad], axis=1)
    xy = m[["x_utm25831_m", "y_utm25831_m"]].to_numpy(); tree = cKDTree(xy); nb = tree.query_ball_point(xy, 750)
    W = [[j for j in l if j != i] for i, l in enumerate(nb)]
    lag = pd.DataFrame({f"lag_{v}": [X[v].iloc[l].mean() if l else X[v].iloc[i] for i, l in enumerate(W)] for v in X.columns}, index=m.index)
    rows = []
    for b in ("ALL", "Condis", "Dia", "Mercadona"):
        y = m[key].map(c[c.brand_group == b].set_index(key)["n_inside"]).fillna(0).astype(float)
        r0, _ = glm_offset(y, X, off, g); r1, _ = glm_offset(y, pd.concat([X, lag], axis=1), off, g)
        w = joint_wald(r1, list(lag.columns)); ci = r1.conf_int()
        rows.append(dict(group=b, aic_without_lags=r0.aic, aic_with_lags=r1.aic, wald_lags_chi2=w[0], wald_lags_p=w[1],
                         significant_lags="; ".join(f"{v} {np.exp(r1.params[v]):.2f}" for v in lag.columns if v in r1.params.index and r1.pvalues[v] < 0.05)))
    return pd.DataFrame(rows)

def run_v6_pacified():
    """Difference in differences, Eixample only: sections along the 2020 pacified streets vs other Eixample sections, 2016-2024 active premises (section and
    edition fixed effects) and supermarket openings before / after (randomisation inference)."""
    s = load("select * from ana.section_pacified_streets where codi_districte = 2")
    long = s.melt(id_vars=["seccio_censal", "treated_pacified_street", "codi_barri"], value_vars=[f"active_premises_{y}_n" for y in (2016, 2019, 2022, 2024)], var_name="v", value_name="premises")
    long["year"] = long.v.str.extract(r"(\d{4})").astype(int); long["post"] = (long.year >= 2022).astype(int); long["treated"] = long.treated_pacified_street.astype(int)
    long["y"] = np.log1p(long.premises)
    r = smf.ols("y ~ treated:post + C(seccio_censal) + C(year)", data=long).fit(cov_type="cluster", cov_kwds={"groups": long.codi_barri.astype(int)})
    # pre-trend check: 2016 -> 2019 change, treated vs control
    long["treated_x_2019"] = long.treated * (long.year == 2019).astype(int)      # explicit interaction (a boolean term in the formula splits into two columns)
    lp = long[long.year <= 2019]
    pre = smf.ols("y ~ treated_x_2019 + C(seccio_censal) + C(year)", data=lp).fit(cov_type="cluster", cov_kwds={"groups": lp.codi_barri.astype(int)})
    tr = s.treated_pacified_street.to_numpy(); a, b_ = s.openings_2014_2019_n.to_numpy(), s.openings_2020_2024_n.to_numpy()
    did = lambda t: (b_[t].mean() - a[t].mean()) - (b_[~t].mean() - a[~t].mean())
    obs = did(tr); rng = np.random.default_rng(1); sims = np.array([did(np.isin(np.arange(len(s)), rng.choice(len(s), tr.sum(), replace=False))) for _ in range(5000)])
    k = "treated:post"; kp = "treated_x_2019"
    return pd.DataFrame([dict(treated_sections=int(tr.sum()), control_sections=int((~tr).sum()),
        premises_did_pct=100 * (np.exp(r.params[k]) - 1), premises_did_ci_low_pct=100 * (np.exp(r.conf_int().loc[k, 0]) - 1), premises_did_ci_high_pct=100 * (np.exp(r.conf_int().loc[k, 1]) - 1),
        premises_did_p=r.pvalues[k], pretrend_2016_2019_pct=100 * (np.exp(pre.params[kp]) - 1), pretrend_p=pre.pvalues[kp],
        openings_treated_before=int(a[tr].sum()), openings_treated_after=int(b_[tr].sum()), openings_control_before=int(a[~tr].sum()), openings_control_after=int(b_[~tr].sum()),
        openings_did_per_section=obs, openings_randomisation_p=float(np.mean(np.abs(sims) >= abs(obs))))])

def main():
    s1, c2, s2 = [], [], []
    for unit in ("section", "barri"):
        coefs, summ = run_v1(unit); s1.append(summ); coefs.round(5).to_csv(ROOT / "docs" / f"model_coefficients_{unit}.csv", index=False)
        coefs, summ = run_v2(unit); c2.append(coefs); s2.append(summ)
    pd.concat(s1).round(4).to_csv(ROOT / "docs" / "model_summary.csv", index=False)
    c2, s2 = pd.concat(c2), pd.concat(s2)
    c2.round(5).to_csv(ROOT / "docs" / "model_v2_coefficients.csv", index=False); s2.round(4).to_csv(ROOT / "docs" / "model_v2_summary.csv", index=False)
    print(s2.round(3).to_string(index=False))
    for unit in ("section", "barri"):
        print(f"== v2 {unit}: significant rate ratios per SD (p<0.05, errors clustered)")
        s = c2[(c2.unit == unit) & (c2.p_value < 0.05)]
        for b, g in s.groupby("brand", sort=False): print(f"{b:15s}", "; ".join(f"{r.variable} {r.rate_ratio_per_sd:.2f}" for r in g.itertuples()))
    c3, s3 = run_v3()
    c3.round(5).to_csv(ROOT / "docs" / "model_v3_coefficients.csv", index=False); s3.round(4).to_csv(ROOT / "docs" / "model_v3_summary.csv", index=False)
    print(s3.round(3).to_string(index=False))
    bl, bc = run_v4_blocks(); to = run_v4_time_order(); es = run_v4_event_study(); mt = run_v4_metro(); bo = run_v4_building_origin()
    for name, df in (("blocks", bl), ("blocks_coefficients", bc), ("time_order", to), ("event_study", es), ("metro_l10", mt), ("building_origin", bo)):
        df.round(5).to_csv(ROOT / "docs" / f"model_v4_{name}.csv", index=False)
    vd, vc, vn = run_v5_buildings()
    for name, df in (("description", vd), ("case_control", vc), ("new_development", vn)): df.round(5).to_csv(ROOT / "docs" / f"model_v5_buildings_{name}.csv", index=False)
    bb, sp = run_v5_barri_patterns()
    bb.round(2).to_csv(ROOT / "docs" / "model_v5_barri_building_stock.csv", index=False); sp.round(2).to_csv(ROOT / "docs" / "model_v5_store_building_percentiles.csv", index=False)
    sub = run_v6_substitution(); cr, cm = run_v6_closures(); ch = run_v6_choice(); ho, gaps, hc = run_v6_holdout(); ml, imp = run_v6_ml(); slx = run_v6_slx(); pac = run_v6_pacified()
    for name, df in (("substitution", sub), ("closure_rates", cr), ("closure_model", cm), ("site_choice", ch), ("holdout_2024", ho), ("holdout_coefficients", hc),
                     ("predicted_gaps", gaps), ("ml_spatial_cv", ml), ("ml_importance", imp), ("slx", slx), ("pacified_streets", pac)):
        df.round(5).to_csv(ROOT / "docs" / f"model_v6_{name}.csv", index=False)
    print(bl.round(3).to_string(index=False)); print(bc[bc.p_value < 0.05].round(3).to_string(index=False))
    print(to[to.p_value < 0.1].round(3).to_string(index=False)); print(es.round(3).to_string(index=False)); print(mt.round(4).to_string(index=False))
    for spec in ("all_current_stores", "legacy_open_in_2014", "openings_2016_2024", "openings_new_site_only"):
        print(f"== v3 {spec}: significant rate ratios per SD (p<0.05)")
        s = c3[(c3.outcome == spec) & (c3.p_value < 0.05)]
        for b, g in s.groupby("group", sort=False): print(f"{b:22s}", "; ".join(f"{r.variable} {r.rate_ratio_per_sd:.2f}" for r in g.itertuples()))

if __name__ == "__main__": main()
