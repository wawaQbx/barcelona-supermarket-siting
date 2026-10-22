import requests, time
B="https://opendata-ajuntament.barcelona.cat/data/api/3/action/package_show"
def retry(f,n=8):
    for i in range(n):
        try: return f()
        except Exception as e: print("  retry",i,str(e)[:60],flush=True); time.sleep(5)
r=retry(lambda: requests.get(B,params={"id":"cens-locals-planta-baixa-act-economica"},timeout=120).json()["result"])
for x in r["resources"]: print(x["name"],x["format"],x["url"][-60:],flush=True)
want={"2014_CENS_ACTIVITATS_COMERCIALS.csv":"census_2014.csv","2016_CENS_LOCALS_PlantaBaixa.csv":"census_2016.csv","2022_CensComercialBCN.csv":"census_2022.csv"}
for x in r["resources"]:
    if x["name"] in want:
        d=retry(lambda: requests.get(x["url"],timeout=300).content)
        if d: open("data/raw/"+want[x["name"]],"wb").write(d); print("OK",x["name"],len(d),flush=True)
