"""OSM highway ways in Barcelona bbox (name, highway, lanes, maxspeed, oneway) -> data/raw/osm_roads.json"""
import requests, json, time
M=["https://overpass.openstreetmap.fr/api/interpreter","https://overpass-api.de/api/interpreter","https://overpass.osm.ch/api/interpreter"]
ql='[out:json][timeout:240];way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|residential|living_street|pedestrian|unclassified)$"](41.315,2.05,41.470,2.235);out tags geom;'
for u in M*2:
    try:
        r=requests.post(u,data={"data":ql},headers={"User-Agent":"Supermarket_BCN-research/1.0"},timeout=280)
        print(u,r.status_code,len(r.content),flush=True)
        if r.status_code==200 and r.content[:1]==b"{":
            open("data/raw/osm_roads.json","wb").write(r.content); break
    except Exception as e: print(u,"ERR",str(e)[:80],flush=True); time.sleep(5)
