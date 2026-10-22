"""v7: tourism, foreign residents and municipal markets (docs/MODEL_RESULTS.md section 25, outputs docs/model_v7_*.csv).
Same specification as v4 (analyze_siting.py): Poisson, ln(population) as offset, barri-clustered errors, rate ratio per +1 SD.
(1) tourism and store FORMAT: do small formats (Carrefour Express / Market small, Mi Alcampo, Condis ...) sit where tourists stay?
    tourism = tourist-flat beds (HUT 2026) and hotels per section, Airbnb listings as an alternative measure
(2) time ordering: openings 2016-2024 explained by HUT 2017 beds + the 2014/2015 baseline (like v4 time_order)
(3) foreign residents: share of non-EU and EU foreigners (Padro 2026) added to the v4 model of every chain
(4) municipal markets: chain stores at / near the 43 markets; do chains cluster near markets; daily-food shops around markets 2014-2024
"""
import numpy as np, pandas as pd
import analyze_siting as A

ROOT = A.ROOT
FORMATS = ["ALL", "Carrefour_convenience", "Carrefour_supermarket", "Alcampo_MiAlcampo", "Condis", "Caprabo", "Dia", "Mercadona", "Lidl", "Consum_Charter", "BonPreu_Esclat"]

def frame():
    m, c, key, cl = A.load_unit("section")
    t = A.load("select * from ana.section_tourism").set_index("seccio_censal")
    n = A.load("select * from ana.pop_nationality_section").set_index("seccio_censal")
    mk = A.load("""select s.seccio_censal, min(ST_Distance(s.geom, m.geom)) as dist_market_m
                   from raw.adm_units_polygons s, ana.market_supermarkets m where s.tipus_ua = 'SEC_CENS' and m.food_market group by 1""").set_index("seccio_censal")
    for col in ("hut_beds_per_100_residents", "hut_beds_2017_per_100_residents", "hotels_n", "airbnb_listings_per_100_residents"):
        m[col] = m[key].map(t[col]).astype(float).fillna(0)
    for col in ("share_foreign_non_eu_2026_pct", "share_foreign_2026_pct", "share_foreign_non_eu_2015_pct"):
        m[col] = m[key].map(n[col]).astype(float)
    m["market_within_300m"] = (m[key].map(mk.dist_market_m) <= 300).astype(float)
    return m, c, key, cl

def rr(r, v):
    ci = r.conf_int()
    return dict(rate_ratio_per_sd=float(np.exp(r.params[v])), ci95_low=float(np.exp(ci.loc[v, 0])), ci95_high=float(np.exp(ci.loc[v, 1])), p_value=float(r.pvalues[v]))

def counts(c, key, m, grp, col="n_inside"):
    return m[key].map(c[c.brand_group == grp].set_index(key)[col]).fillna(0).astype(float)

def run_tourism(m, c, key, cl):
    g = m[cl].astype(int).to_numpy(); off = np.log(m.population_n.astype(float)); X0 = A.design(m, "section")[A.BASE4]
    rows = []
    for spec, cols in (("hut_beds_and_hotels", ["ln_hut_beds_per_100", "ln_hotels"]), ("airbnb_listings", ["ln_airbnb_per_100"])):
        X = X0.copy()
        if "ln_hut_beds_per_100" in cols: X["ln_hut_beds_per_100"] = np.log1p(m.hut_beds_per_100_residents); X["ln_hotels"] = np.log1p(m.hotels_n)
        else: X["ln_airbnb_per_100"] = np.log1p(m.airbnb_listings_per_100_residents)
        for grp in FORMATS:
            y = counts(c, key, m, grp)
            if y.sum() < 15: continue
            r, _ = A.glm_offset(y, X, off, g)
            rows += [dict(spec=spec, group=grp, stores=int(y.sum()), variable=v, **rr(r, v)) for v in cols]
    return pd.DataFrame(rows)

def run_tourism_time_order(m, c, key, cl):
    """openings 2016-2024 (Clarel conversions excluded) ~ 2014/2015 baseline + HUT beds 2017"""
    g = m[cl].astype(int).to_numpy()
    b15 = A.load("select * from ana.section_baseline_2015").set_index("seccio_censal")
    o = A.load("select * from ana.store_openings_section").set_index(["seccio_censal", "brand_group"])
    get = lambda grp, col: m[key].map(lambda s: o[col].get((s, grp), 0)).astype(float)
    now = A.design(m, "section")[A.BASE4]
    X = pd.DataFrame(index=m.index)
    X["ln_population_per_ha"] = np.log(m[key].map(b15.population_per_ha_2015).astype(float).clip(lower=1))
    X["share_age_65plus_pct"] = m[key].map(b15.share_age_65plus_2015_pct).astype(float)
    X["share_tertiary_education_pct"] = m[key].map(b15.share_tertiary_education_2015_pct).astype(float)
    X["ln_income_eur"] = np.log(m[key].map(b15.disposable_income_2015_eur_per_person).astype(float))
    X["cars_per_1000_residents"] = now.cars_per_1000_residents
    X["ln_transit_departures_300m"] = now.ln_transit_departures_300m
    X["ln_active_premises"] = np.log1p(m[key].map(b15.premises_active_2014_n).astype(float))
    X["dist_centre_km"] = now.dist_centre_km
    X["ln_hut_beds_2017_per_100"] = np.log1p(m.hut_beds_2017_per_100_residents)
    X["share_foreign_non_eu_2015_pct"] = m.share_foreign_non_eu_2015_pct
    off = np.log(m[key].map(b15.population_2015_n).astype(float))
    ok = X.notna().all(axis=1) & np.isfinite(off)
    rows = []
    for grp in ["ALL", "Carrefour", "Alcampo", "Condis", "Caprabo", "Mercadona", "Consum_Charter", "Lidl"]:
        y = (get(grp, "n_openings_2016_2024") - get(grp, "n_openings_clarel"))[ok]
        if y.sum() < 10: continue
        r, _ = A.glm_offset(y, X[ok], off[ok], g[ok.to_numpy()])
        rows += [dict(group=grp, openings=int(y.sum()), variable=v, **rr(r, v)) for v in ("ln_hut_beds_2017_per_100", "share_foreign_non_eu_2015_pct")]
    return pd.DataFrame(rows)

def run_foreign(m, c, key, cl):
    g = m[cl].astype(int).to_numpy(); off = np.log(m.population_n.astype(float))
    X = A.design(m, "section")[A.BASE4].copy()
    X["share_foreign_non_eu_pct"] = m.share_foreign_non_eu_2026_pct
    X["share_foreign_eu_pct"] = m.share_foreign_2026_pct - m.share_foreign_non_eu_2026_pct
    ok = X.notna().all(axis=1)
    rows = []
    for grp in A.BRANDS:
        y = counts(c, key, m, grp)[ok]
        if y.sum() < 15: continue
        r, _ = A.glm_offset(y, X[ok], off[ok], g[ok.to_numpy()])
        rows += [dict(group=grp, stores=int(y.sum()), variable=v, **rr(r, v)) for v in r.params.index if v != "const"]
    return pd.DataFrame(rows)

def run_markets(m, c, key, cl):
    """chain stores at / near the 39 FOOD markets; fresh-food shops in a 100-400 m ring (market stalls excluded) 2016-2024"""
    mk = A.load("select * from ana.market_supermarkets where food_market")
    g = m[cl].astype(int).to_numpy(); off = np.log(m.population_n.astype(float))
    X = A.design(m, "section")[A.BASE4].copy(); X["market_within_300m"] = m.market_within_300m
    rows = []
    for grp in A.BRANDS:
        y = counts(c, key, m, grp)
        if y.sum() < 15: continue
        r, _ = A.glm_offset(y, X, off, g); rows.append(dict(group=grp, stores=int(y.sum()), variable="market_within_300m", **rr(r, "market_within_300m")))
    near = pd.DataFrame(rows)
    for y in (2016, 2019, 2022, 2024): mk[f"fresh_{y}"] = mk[f"fresh_shops_ring_100_400m_{y}_n"].astype(float)
    mk["fresh_change_2016_2024_pct"] = 100 * (mk.fresh_2024 / mk.fresh_2016.replace(0, np.nan) - 1)
    mk["fresh_change_2019_2024_pct"] = 100 * (mk.fresh_2024 / mk.fresh_2019.replace(0, np.nan) - 1)
    per = mk[["nom_mercat", "nom_districte", "chain_stores_50m_n", "chain_stores_50m", "chain_stores_100m_n", "chain_stores_300m_n", "nearest_chain_store_m",
              "chain_openings_2016_2024_300m_n", "fresh_2016", "fresh_2019", "fresh_2024", "fresh_change_2016_2024_pct", "fresh_change_2019_2024_pct"]]
    return near, per

# ======================================================================= robustness / cross-validation
from scipy import stats
import statsmodels.api as sm, statsmodels.formula.api as smf

def extra_outcomes(m, key):
    """per section: chain stores of CONVENIENCE format (all chains pooled); INDEPENDENT supermarket-class premises 2024
    (Autoservei / Supermercat, active, no chain store within 50 m) = shops outside our chain list; tourist-flat beds within 300 m of the section"""
    conv = A.load("""select u.seccio_censal, count(*) n from ana.store_points p join raw.adm_units_polygons u on u.tipus_ua = 'SEC_CENS' and ST_Intersects(u.geom, p.geom)
                     where p.in_city and p.store_type = 'convenience' group by 1""").set_index("seccio_censal").n
    ind = A.load("""select u.seccio_censal, count(*) n from dbt_int.int_census_premises c join raw.adm_units_polygons u on u.tipus_ua = 'SEC_CENS' and ST_Intersects(u.geom, c.geom)
                    where c.census_year = 2024 and c.nom_activitat = 'Autoservei / Supermercat' and c.nom_principal_activitat = 'Actiu'
                      and not exists (select 1 from ana.store_points p where p.in_city and ST_DWithin(p.geom, c.geom, 50)) group by 1""").set_index("seccio_censal").n
    buf = A.load("""with h as (select numero_places, ST_Transform(ST_SetSRID(ST_MakePoint(longitud_x, latitud_y), 4326), 25831) g from raw.tou_hut_comunicacio_2026_1t)
                    select u.seccio_censal, coalesce(sum(h.numero_places), 0) beds from raw.adm_units_polygons u
                    left join h on ST_DWithin(u.geom, h.g, 300) where u.tipus_ua = 'SEC_CENS' group by 1""").set_index("seccio_censal").beds
    return (m[key].map(conv).fillna(0).astype(float), m[key].map(ind).fillna(0).astype(float), m[key].map(buf).fillna(0).astype(float))

def stepwise(m, key, cl, y, var, values):
    """coefficient of `var` as control blocks are added one at a time (S0 nothing ... S5 district fixed effects)"""
    g = m[cl].astype(int).to_numpy(); off = np.log(m.population_n.astype(float)); D = A.design(m, "section")
    _, cad, _ = A.blocks(m)
    cad = cad.assign(bldg_share_pre1941_pct=m.bldg_share_pre1941_pct.astype(float).fillna(0))
    specs = {"S0_no_controls": [], "S1_demand": ["ln_population_per_ha", "share_age_65plus_pct", "share_tertiary_education_pct", "ln_income_eur", "cars_per_1000_residents"],
             "S2_plus_transit_premises": ["ln_transit_departures_300m", "ln_active_premises"], "S3_plus_centre_distance_v7": ["dist_centre_km"],
             "S4_plus_cadastre_rent_proxy_buildings": list(cad.columns), "S5_plus_district_fixed_effects": ["district_fe"]}
    rows, cols = [], []
    for s, add in specs.items():
        cols = cols + add
        X = pd.DataFrame({var: values}, index=m.index)
        for v in cols:
            if v == "district_fe": X = X.join(pd.get_dummies(m.codi_districte.astype(int), prefix="d", drop_first=True).astype(float))
            elif v in cad.columns: X[v] = cad[v]
            else: X[v] = D[v]
        ok = X.notna().all(axis=1)
        r, _ = A.glm_offset(y[ok], X[ok], off[ok], g[ok.to_numpy()])
        rows.append(dict(spec=s, variable=var, **rr(r, var)))
    return rows

def rob_tourism(m, c, key, cl):
    conv, ind, buf = extra_outcomes(m, key)
    m = m.assign(ln_hut_beds_per_100=np.log1p(m.hut_beds_per_100_residents), ln_airbnb_per_100=np.log1p(m.airbnb_listings_per_100_residents),
                 ln_hut_beds_300m_per_100=np.log1p(100 * buf / m.population_n.astype(float)))
    outcomes = {"ALL chain stores": counts(c, key, m, "ALL"), "convenience format, all chains": conv, "Carrefour_convenience": counts(c, key, m, "Carrefour_convenience"),
                "Condis": counts(c, key, m, "Condis"), "Alcampo_MiAlcampo": counts(c, key, m, "Alcampo_MiAlcampo"), "independent supermarkets (census 2024)": ind}
    rows = []
    for name, y in outcomes.items():
        for var in ("ln_hut_beds_per_100", "ln_hut_beds_300m_per_100", "ln_airbnb_per_100"):
            rows += [dict(outcome=name, n=int(y.sum()), **r) for r in stepwise(m, key, cl, y, var, m[var])]
    corr = m[["ln_hut_beds_per_100", "ln_airbnb_per_100", "dist_placa_catalunya_m", "premises_active_n", "cadastral_value_eur_per_m2", "disposable_income_eur_per_person",
              "share_foreign_non_eu_2026_pct"]].astype(float).corr(method="spearman").round(2)
    # store level: among the chains that run both formats (Carrefour, Condis, Bon Preu), is a store more often a CONVENIENCE store where tourists stay?
    s = A.load("""with h as (select numero_places, ST_Transform(ST_SetSRID(ST_MakePoint(longitud_x, latitud_y), 4326), 25831) g from raw.tou_hut_comunicacio_2026_1t)
                  select p.store_id, p.brand_group, (p.store_type = 'convenience')::int conv, u.codi_barri,
                    ST_Distance(p.geom, ST_Transform(ST_SetSRID(ST_MakePoint(2.17, 41.387), 4326), 25831)) / 1000 dist_km,
                    (select coalesce(sum(h.numero_places), 0) from h where ST_DWithin(p.geom, h.g, 300)) hut_beds_300m,
                    (select count(*) from raw.tou_airbnb_listings_2026_09 a where ST_DWithin(p.geom, ST_Transform(ST_SetSRID(ST_MakePoint(a.lon, a.lat), 4326), 25831), 300)) airbnb_300m,
                    (select count(*) from dbt_int.int_census_premises c where c.census_year = 2024 and c.nom_principal_activitat = 'Actiu' and ST_DWithin(c.geom, p.geom, 300)) premises_300m,
                    m.disposable_income_eur_per_person income, m.population_per_ha
                  from ana.store_points p join raw.adm_units_polygons u on u.tipus_ua = 'SEC_CENS' and ST_Intersects(u.geom, p.geom)
                  join ana.section_model_table m on m.seccio_censal = u.seccio_censal
                  where p.in_city and p.brand_group in ('Carrefour', 'Condis', 'BonPreu_Esclat')""")
    s = s.assign(ln_hut_beds_300m=np.log1p(s.hut_beds_300m.astype(float)), ln_airbnb_300m=np.log1p(s.airbnb_300m.astype(float)), ln_premises_300m=np.log1p(s.premises_300m.astype(float)),
                 ln_income=np.log(s.income.astype(float)), ln_density=np.log(s.population_per_ha.astype(float).clip(lower=1))).dropna()
    for v in ("ln_hut_beds_300m", "ln_airbnb_300m", "dist_km", "ln_premises_300m", "ln_income", "ln_density"): s["z_" + v] = (s[v] - s[v].mean()) / s[v].std()
    fmt = []
    for tv in ("z_ln_hut_beds_300m", "z_ln_airbnb_300m"):
        for f in (f"conv ~ {tv} + C(brand_group)", f"conv ~ {tv} + z_dist_km + C(brand_group)",
                  f"conv ~ {tv} + z_dist_km + z_ln_premises_300m + z_ln_income + z_ln_density + C(brand_group)"):
            r = smf.logit(f, data=s).fit(disp=0, cov_type="cluster", cov_kwds={"groups": s.codi_barri.astype(int)})
            ci = r.conf_int().loc[tv]
            fmt.append(dict(model=f, stores=len(s), convenience_stores=int(s.conv.sum()), odds_ratio_per_sd=float(np.exp(r.params[tv])),
                            ci95_low=float(np.exp(ci[0])), ci95_high=float(np.exp(ci[1])), p_value=float(r.pvalues[tv])))
    return pd.DataFrame(rows), corr, pd.DataFrame(fmt)

def rob_foreign(m, c, key, cl):
    conv, ind, _ = extra_outcomes(m, key)
    var = "share_foreign_non_eu_2026_pct"; rows = []
    outcomes = {"ALL chain stores": counts(c, key, m, "ALL"), "Lidl": counts(c, key, m, "Lidl"), "Caprabo": counts(c, key, m, "Caprabo"),
                "Condis": counts(c, key, m, "Condis"), "Carrefour": counts(c, key, m, "Carrefour"), "independent supermarkets (census 2024)": ind,
                "other daily-food shops (census 2024)": m.premises_daily_food_other_n.astype(float)}
    for name, y in outcomes.items():
        rows += [dict(outcome=name, sample="all sections", n=int(y.sum()), **r) for r in stepwise(m, key, cl, y, var, m[var])]
        keep = (m.codi_districte.astype(int) != 1).to_numpy()
        mm = m[keep].reset_index(drop=True); yy = y[keep].reset_index(drop=True)
        rows += [dict(outcome=name, sample="without Ciutat Vella", n=int(yy.sum()), **r) for r in stepwise(mm, key, cl, yy, var, mm[var])
                 if r["spec"] in ("S3_plus_centre_distance_v7", "S5_plus_district_fixed_effects")]
    # per DWELLING instead of per resident (are areas with many non-EU residents just more crowded households?)
    md = m[m.dwellings_n.astype(float) > 0].reset_index(drop=True); Xd = A.design(md, "section")[A.BASE4].copy(); Xd[var] = md[var]
    for name, grp in (("ALL chain stores", "ALL"), ("Lidl", "Lidl"), ("Caprabo", "Caprabo"), ("Condis", "Condis"), ("other daily-food shops (census 2024)", None)):
        y = md.premises_daily_food_other_n.astype(float) if grp is None else counts(c, key, md, grp)
        r, _ = A.glm_offset(y, Xd, np.log(md.dwellings_n.astype(float)), md[cl].astype(int).to_numpy())
        rows.append(dict(outcome=name, sample="all sections", n=int(y.sum()), spec="S3_offset_ln_dwellings_instead_of_population", variable=var, **rr(r, var)))
    # share of chain stores among all supermarket-class shops (chain + independent): binomial model with the v4 controls
    chain = counts(c, key, m, "ALL"); X = A.design(m, "section")[A.BASE4].copy(); X[var] = m[var]
    ok = ((chain + ind) > 0) & X.notna().all(axis=1)
    Xc = sm.add_constant(A.zs(X[ok]))
    r = sm.GLM(np.column_stack([chain[ok], ind[ok]]), Xc, family=sm.families.Binomial()).fit(cov_type="cluster", cov_kwds={"groups": m.loc[ok, cl].astype(int).to_numpy()})
    ci = r.conf_int().loc[var]
    Z = A.zs(X[ok]); r2 = sm.OLS(Z[var], sm.add_constant(Z.drop(columns=var))).fit().rsquared
    share = dict(model="chain share of supermarket-class shops (binomial, v4 controls)", sections=int(ok.sum()), chain=int(chain[ok].sum()), independent=int(ind[ok].sum()),
                 odds_ratio_per_sd=float(np.exp(r.params[var])), ci95_low=float(np.exp(ci[0])), ci95_high=float(np.exp(ci[1])), p_value=float(r.pvalues[var]),
                 r2_non_eu_share_on_controls=r2, vif_non_eu_share=1 / (1 - r2))
    return pd.DataFrame(rows), pd.DataFrame([share])

def rob_markets():
    mk = A.load("select * from ana.market_supermarkets where food_market")
    # (1) null benchmark: how often does an ordinary ACTIVE ground-floor premise of the SAME BARRI have a chain store within 50 / 100 m?
    nb = A.load("""select u.codi_barri, avg((exists (select 1 from ana.store_points p where p.in_city and ST_DWithin(p.geom, c.geom, 50)))::int) p50,
                          avg((exists (select 1 from ana.store_points p where p.in_city and ST_DWithin(p.geom, c.geom, 100)))::int) p100
                   from dbt_int.int_census_premises c join raw.adm_units_polygons u on u.tipus_ua = 'SEC_CENS' and ST_Intersects(u.geom, c.geom)
                   where c.census_year = 2024 and c.nom_principal_activitat = 'Actiu' and c.nom_activitat <> 'Autoservei / Supermercat' group by 1""").set_index("codi_barri")
    e50 = mk.codi_barri.map(nb.p50).astype(float); e100 = mk.codi_barri.map(nb.p100).astype(float)
    o50 = int((mk.chain_stores_50m_n > 0).sum()); o100 = int((mk.chain_stores_100m_n > 0).sum())
    def tail(p, k):            # Poisson-binomial: P(at least k markets) if each market were an ordinary premise of its barri
        dist = np.array([1.0])
        for q in p: dist = np.convolve(dist, [1 - q, q])
        return float(dist[k:].sum())
    bench = pd.DataFrame([dict(radius_m=50, markets=len(mk), observed=o50, expected_if_like_other_premises=float(e50.sum()), p_value=tail(e50, o50)),
                          dict(radius_m=100, markets=len(mk), observed=o100, expected_if_like_other_premises=float(e100.sum()), p_value=tail(e100, o100))])
    # (2) fresh-food shops in the 100-400 m ring: markets vs CONTROL rings around comparable points
    #     (active 2019 premises at least 800 m from any food market, matched on the baseline ring count), same activities, same ring
    ctl = A.load("""with fresh as (select census_year, geom g from dbt_int.int_census_premises where census_year >= 2016 and nom_principal_activitat = 'Actiu'
                           and nom_activitat in ('Carn i Porc', 'Fruites i verdures', 'Ous i aus', 'Peix i marisc')),
                    pts as (select c.geom from dbt_int.int_census_premises c where c.census_year = 2019 and c.nom_principal_activitat = 'Actiu'
                            and not exists (select 1 from ana.market_supermarkets m where m.food_market and ST_DWithin(m.geom, c.geom, 800))
                            order by md5(ST_AsText(c.geom)) limit 1500)
                    select count(*) filter (where f.census_year = 2016) f2016, count(*) filter (where f.census_year = 2019) f2019, count(*) filter (where f.census_year = 2024) f2024
                    from pts p left join fresh f on ST_DWithin(f.g, p.geom, 400) and not ST_DWithin(f.g, p.geom, 100)
                    group by p.geom""")
    ctl = ctl[ctl.f2019 > 0].reset_index(drop=True)
    rows = []
    for base in (2016, 2019):
        mc = []
        for r in mk.itertuples():
            b = getattr(r, f"fresh_shops_ring_100_400m_{base}_n")
            nn = ctl.iloc[(ctl[f"f{base}"] - b).abs().argsort()[:5]]          # the 5 control rings with the closest baseline count
            mc.append(dict(chain_at_market=r.chain_stores_50m_n > 0, base=b, now=r.fresh_shops_ring_100_400m_2024_n, ctl_base=nn[f"f{base}"].mean(), ctl_now=nn.f2024.mean(),
                           openings=r.chain_openings_2016_2024_300m_n))
        d = pd.DataFrame(mc)
        d = d[d.base > 0].reset_index(drop=True)                               # no percentage change from a zero baseline
        d["chg"] = 100 * (d.now / d.base - 1); d["ctl_chg"] = 100 * (d.ctl_now / d.ctl_base - 1); d["diff_pp"] = d.chg - d.ctl_chg
        rows.append(dict(period=f"{base}-2024", markets_change_pct=100 * (d.now.sum() / d.base.sum() - 1), matched_controls_change_pct=100 * (d.ctl_now.sum() / d.ctl_base.sum() - 1),
                         median_market_minus_control_pp=float(d.diff_pp.median()), wilcoxon_p=float(stats.wilcoxon(d.diff_pp).pvalue),
                         median_change_chain_at_market_pct=float(d[d.chain_at_market].chg.median()), median_change_no_chain_pct=float(d[~d.chain_at_market].chg.median()),
                         mannwhitney_p=float(stats.mannwhitneyu(d[d.chain_at_market].chg, d[~d.chain_at_market].chg).pvalue),
                         spearman_openings_vs_change=float(stats.spearmanr(d.openings, d.chg).statistic), markets_used=len(d), control_points=len(ctl)))
    return bench, pd.DataFrame(rows)

def main():
    m, c, key, cl = frame()
    tr = run_tourism(m, c, key, cl); to = run_tourism_time_order(m, c, key, cl); fo = run_foreign(m, c, key, cl); near, per = run_markets(m, c, key, cl)
    rt, corr, fmt = rob_tourism(m, c, key, cl); rf, share = rob_foreign(m, c, key, cl); bench, fresh = rob_markets()
    for name, df in (("tourism_formats", tr), ("tourism_time_order", to), ("foreign_residents", fo), ("markets_nearby", near), ("markets_per_market", per),
                     ("robust_tourism_stepwise", rt), ("robust_tourism_correlations", corr.reset_index()), ("robust_tourism_store_format", fmt),
                     ("robust_foreign_stepwise", rf), ("robust_foreign_chain_share", share), ("robust_markets_benchmark", bench), ("robust_markets_fresh_shops", fresh)):
        df.round(5).to_csv(ROOT / "docs" / f"model_v7_{name}.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print("== tourism stepwise\n", rt.round(3).to_string(index=False)); print(corr.to_string()); print(fmt.round(3).to_string(index=False))
    print("== foreign stepwise\n", rf.round(3).to_string(index=False)); print(share.round(3).to_string(index=False))
    print("== markets\n", near.round(3).to_string(index=False)); print(bench.round(3).to_string(index=False)); print(fresh.round(3).to_string(index=False))
    print(per.to_string(index=False))

if __name__ == "__main__": main()
