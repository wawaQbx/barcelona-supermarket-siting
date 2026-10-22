"""Reconstruct Bon Preu/Esclat first-seen month per store (codi) from Wayback snapshots of the official store finder."""
import requests, re, json, time, pandas as pd
URL = "bonpreuesclat.cat/ca/cercador-d-establiments"
def retry(f, n=5):
    for i in range(n):
        try: return f()
        except Exception as e: time.sleep(6)
rows = retry(lambda: requests.get("https://web.archive.org/cdx/search/cdx", params={"url": URL, "output": "json", "fl": "timestamp", "filter": "statuscode:200"}, timeout=120).json())[1:]
ts = sorted({r[0] for r in rows}); print("raw snapshots:", len(ts))
by_month = {}
for t in ts: by_month.setdefault(t[:6], t)       # one snapshot per month
recs = []
for ym, t in sorted(by_month.items()):
    h = retry(lambda: requests.get(f"https://web.archive.org/web/{t}id_/https://www.bonpreuesclat.cat/ca/cercador-d-establiments", timeout=120).text)
    m = re.search(r'var\s+establimentsJson\s*=\s*\[', h) if h else None
    if not m: print(ym, "no JSON", flush=True); continue
    try: d, _ = json.JSONDecoder().raw_decode(h, m.end() - 1)
    except Exception: print(ym, "parse fail", flush=True); continue
    for x in d: recs.append({"snap": ym, "codi": x.get("codi"), "descripcio": x.get("descripcio"), "ensenya": x.get("ensenya"), "poblacio": x.get("poblacio"), "lat": x.get("latitud"), "lon": x.get("longitud"), "tipus": x.get("tipus")})
    print(ym, len(d), flush=True)
df = pd.DataFrame(recs); df.to_csv("data/bonpreu_snapshots_long.csv", index=False)
first = df.groupby("codi").agg(first_seen=("snap", "min"), last_seen=("snap", "max"), n_snaps=("snap", "nunique"), descripcio=("descripcio", "last"), ensenya=("ensenya", "last"), poblacio=("poblacio", "last"), lat=("lat", "last"), lon=("lon", "last")).reset_index()
first.to_csv("data/bonpreu_first_seen.csv", index=False); print(first.shape, first.first_seen.value_counts().sort_index().to_dict())
