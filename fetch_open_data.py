import requests, time, os
B="https://opendata-ajuntament.barcelona.cat/data/api/3/action/package_show"
WANT={ # dataset -> list of (resource name substring, local file)
 "qualificacions-elements-urbanistics":[("Plan_Qualif_Elements_Urbanistics.shp","pgm_qualif.zip")],
 "mapa-parcelari":[("Parcel-lari.shp","parcelari.zip")],
 "mapa-graf-viari-carrers-wms":[("graf_viari.shp","graf_viari.zip")],
 "est-cadastre-edificacions-superficie":[("","cad_edif_sup.csv")],
 "est-cadastre-edificacions-any-const":[("","cad_edif_any.csv")],
 "est-cadastre-edificacions-nombre-locals":[("","cad_edif_locals.csv")],
 "est-cadastre-finques-superficie":[("","cad_finques_sup.csv")],
}
def show(n):
    for i in range(4):
        try: return requests.get(B,params={"id":n},timeout=60).json()["result"]
        except Exception: time.sleep(3)
for n,items in WANT.items():
    r=show(n)
    if not r: print(n,"no meta",flush=True); continue
    res=r["resources"]
    for sub,out in items:
        c=[x for x in res if sub in x["name"]] if sub else [x for x in res if x["format"]=="CSV"]
        # prefer most recent year in name
        c=sorted(c,key=lambda x:x["name"],reverse=True)
        if not c: print(n,"no resource",[x["name"] for x in res][:5],flush=True); continue
        x=c[0]
        try:
            d=requests.get(x["url"],timeout=300).content
            open("data/raw/"+out,"wb").write(d); print("OK",n,x["name"],len(d),flush=True)
        except Exception as e: print("ERR",n,x["name"],str(e)[:80],flush=True)
