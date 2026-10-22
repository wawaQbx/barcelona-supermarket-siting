"""Large ground-floor premises: which activities occupy them and how they change hands 2016 -> 2024 (commercial census, premises linked by id_bcn_2016).
Premise size proxy: footprint of the cadastral building that contains the 2024 premise point (nearest within 15 m) divided by the number of 2024 premises in
that building ('approx_floor_m2'); large = 600 m2 or more. Output: docs/large_premises_activities.csv, docs/large_premises_transitions.csv.
"""
import sys; sys.path.insert(0, ".")
import analyze_siting as A, pandas as pd, numpy as np
pd.set_option("display.width", 250)
p = A.load("""
with c as (select id_bcn_2016, nom_activitat, nom_grup_activitat, nom_sector_activitat, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 25831) g
           from raw.cen_census_2024 where lon is not null),
m as (select c.*, b.referencia_cadastral, b.footprint_area_m2 from c
      left join lateral (select referencia_cadastral, footprint_area_m2 from raw.cad_inspire_buildings x where ST_DWithin(x.geom, c.g, 15) order by x.geom <-> c.g limit 1) b on true)
select m.*, count(*) over (partition by referencia_cadastral) as premises_in_building from m""")
p["approx_floor_m2"] = p.footprint_area_m2 / p.premises_in_building
p["large"] = p.approx_floor_m2 >= 600
def act(r):
    a, g, s = str(r.nom_activitat), str(r.nom_grup_activitat), str(r.nom_sector_activitat)
    if a == "Autoservei / Supermercat": return "supermarket"
    if s.startswith("Locals buits"): return "vacant"
    if s.startswith("Sense") or g == "Grup no definit": return "no activity / no information"
    if a in ("Vehicles", "Concessionaris", "Reparacions (Electrodomèstics i automòbils)") or g.startswith("Automoci") or "Reparacions" in g: return "cars: dealers, repair"
    if "Pàrquings" in a or "Pàrkings" in a or "garatge" in a.lower(): return "parking / garage"
    if "emmagatzematge" in a.lower() or "transport" in a.lower(): return "storage / transport"
    if g.startswith("Parament de la llar"): return "furniture / household / DIY"
    if "esport" in a.lower() or "gimn" in a.lower(): return "gym / sport"
    if g.startswith("Ensenyament"): return "education"
    if g.startswith("Equipaments culturals") or "Bingo" in a or "Cinema" in a: return "culture / leisure / bingo"
    if g.startswith("Sanitat"): return "health"
    if g.startswith("Finances"): return "banks / insurance"
    if g.startswith("Restaurants"): return "restaurants / bars / hotels"
    if g.startswith("Quotidià alimentari"): return "other food shops"
    if g.startswith("Equipament personal"): return "clothing / personal"
    if "industrial" in a.lower() or "construcció" in a.lower() or g.startswith("Manteniment"): return "industry / construction"
    if s.startswith("Comerç al detall"): return "other retail"
    return "other services"
p["activity"] = p.apply(act, axis=1)
tab = p.groupby("activity").agg(premises=("large", "size"), large=("large", "sum"))
tab["share_of_large_premises_pct"] = 100 * tab.large / tab.large.sum(); tab["pct_of_this_activity_that_is_large"] = 100 * tab.large / tab.premises
tab["location_quotient_large"] = (tab.large / tab.large.sum()) / (tab.premises / tab.premises.sum())
print("all premises", len(p), "| large (>= 600 m2 approx)", int(p.large.sum()))
print(tab.sort_values("location_quotient_large", ascending=False).round(2).to_string())
tab.round(3).to_csv(A.ROOT / "docs" / "large_premises_activities.csv")
# transitions 2016 -> 2024 of LARGE premises (same id_bcn_2016)
old = A.load("select id_bcn_2016, nom_activitat, nom_grup_activitat, nom_sector_activitat from raw.cen_census_2016")
old["activity_2016"] = old.apply(act, axis=1)
L = p[p.large & p.id_bcn_2016.notna()].merge(old[["id_bcn_2016", "activity_2016"]], on="id_bcn_2016", how="inner").rename(columns={"activity": "activity_2024"})
L["changed"] = L.activity_2016 != L.activity_2024
print("\nlarge premises linked 2016-2024:", len(L), "| changed activity:", f"{100 * L.changed.mean():.0f}%")
tr = pd.crosstab(L.activity_2016, L.activity_2024); tr.to_csv(A.ROOT / "docs" / "large_premises_transitions.csv")
for a in ("supermarket", "cars: dealers, repair", "parking / garage", "furniture / household / DIY", "banks / insurance"):
    into = L[(L.activity_2024 == a) & L.changed].activity_2016.value_counts().head(5); out = L[(L.activity_2016 == a) & L.changed].activity_2024.value_counts().head(5)
    print(f"\n{a}: became {a} from -> {dict(into)}\n   former {a} became -> {dict(out)}")
