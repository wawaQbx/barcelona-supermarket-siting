"""
Barcelona transit station scraper — FGC · Rodalies · TRAM
Bounding box: lat 41.32-41.47, lon 2.05-2.23

OSM tag reality (verified from live data):
  FGC stations  → operator="Ferrocarrils de la Generalitat de Catalunya"
  FGC L6/L7     → route relations with network="Metro de Barcelona"
  FGC S1/S2     → route relations with network="Rodalia de Barcelona"
  TRAM stops    → railway=tram_stop  (some miss operator/network tags)
  TRAM T1-T3    → route relations with network="Trambaix"
  TRAM T4-T6    → route relations with network="Trambesòs"
  Rodalies      → RENFE official API (resource e3969f12-…)
"""

from pathlib import Path
import csv
import json
import time
import requests

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "BCN-Transit/1.0", "Accept": "*/*"})

BBOX = (41.32, 2.05, 41.47, 2.23)   # south, west, north, east
S, W, N, E = BBOX

OVERPASS_MIRRORS = [
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]

SOURCES_USED: dict[str, str] = {}


# ── Overpass helper ───────────────────────────────────────────────────────────

def oq(ql: str, pause: int = 3) -> list[dict]:
    """Query Overpass (POST first, then GET on 406), trying all mirrors."""
    compact = " ".join(ql.split())
    last_err: object = None
    for url in OVERPASS_MIRRORS:
        for method, kw in [("POST", {"data": {"data": ql}}),
                           ("GET",  {"params": {"data": compact}})]:
            try:
                r = SESSION.request(method, url, timeout=90, **kw)
                if r.status_code == 200:
                    return r.json().get("elements", [])
                last_err = f"HTTP {r.status_code} ({method} {url})"
            except Exception as exc:
                last_err = exc
        time.sleep(pause)
    raise RuntimeError(f"Overpass failed: {last_err}")


def batch_nodes(ids: set[int]) -> list[dict]:
    """Fetch a set of node IDs from Overpass."""
    if not ids:
        return []
    id_str = ",".join(str(i) for i in ids)
    return oq(f"[out:json];node(id:{id_str});out;")


def in_bbox(lat: float, lon: float) -> bool:
    return S <= lat <= N and W <= lon <= E


# ── FGC ──────────────────────────────────────────────────────────────────────

FGC_OPEN_DATA_URL = "https://opendata.fgc.cat/api/v1/stations"
# Line → OSM route relation filter
FGC_LINE_QUERIES = {
    "L6": 'relation["ref"="L6"]["network"="Metro de Barcelona"]',
    "L7": 'relation["ref"="L7"]["network"="Metro de Barcelona"]',
    "S1": 'relation["ref"="S1"]["operator"~"FGC|Ferrocarrils",i]',
    "S2": 'relation["ref"="S2"]["operator"~"FGC|Ferrocarrils",i]',
}


def fetch_fgc_official() -> list[dict]:
    try:
        r = SESSION.get(FGC_OPEN_DATA_URL, timeout=15)
        if r.status_code != 200:
            raise ValueError(f"HTTP {r.status_code}")
        data = r.json()
        items = data if isinstance(data, list) else (
            data.get("data") or data.get("stations") or [])
        if not items:
            raise ValueError("empty")
        records = []
        for item in items:
            lat = float(item.get("lat") or item.get("latitude") or item.get("latitud") or 0)
            lon = float(item.get("lon") or item.get("longitude") or item.get("longitud") or 0)
            if not in_bbox(lat, lon):
                continue
            records.append({
                "name":    item.get("name") or item.get("nom") or item.get("nombre") or "",
                "network": "FGC",
                "lines":   str(item.get("line") or item.get("linia") or ""),
                "lat": round(lat, 6), "lon": round(lon, 6),
                "source":  FGC_OPEN_DATA_URL,
            })
        if not records:
            raise ValueError("no records in bbox")
        print(f"  FGC official API: {len(records)} stations")
        return records
    except Exception as exc:
        print(f"  FGC official API unavailable ({exc})")
        return []


def fetch_fgc_osm() -> list[dict]:
    src = OVERPASS_MIRRORS[0] + " (FGC operator)"

    # Step 1: get station nodes with operator=FGC in bbox
    station_nodes = oq(
        f'[out:json];'
        f'node["operator"~"FGC|Ferrocarrils de la Generalitat",i]'
        f'["railway"~"station|halt"]({S},{W},{N},{E});out;'
    )
    print(f"    FGC operator nodes in bbox: {len(station_nodes)}")

    # Index by node ID
    node_info: dict[int, dict] = {}
    for nd in station_nodes:
        tags = nd.get("tags", {})
        lat, lon = nd.get("lat"), nd.get("lon")
        if not lat or not lon:
            continue
        name = tags.get("name") or tags.get("name:ca") or ""
        nw = tags.get("network") or ""
        node_info[nd["id"]] = {
            "name": name, "lat": round(float(lat), 6), "lon": round(float(lon), 6),
            "network_tag": nw, "lines": [],
        }

    # Step 2: get line assignments from route relations.
    # OSM route relations reference stop_position nodes (on track), which differ
    # from the station nodes returned by the operator query.  Strategy:
    #   a) Collect all member node IDs from route relations
    #   b) Batch-fetch those nodes to get their lat/lon
    #   c) For each FGC station, assign lines whose stop nodes lie within 400 m

    def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        import math
        R = 6_371_000
        φ1, φ2 = math.radians(lat1), math.radians(lat2)
        dφ = math.radians(lat2 - lat1)
        dλ = math.radians(lon2 - lon1)
        a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    line_stop_coords: dict[str, list[tuple]] = {}   # line → [(lat, lon), …]
    for line, rel_filter in FGC_LINE_QUERIES.items():
        try:
            rels = oq(f"[out:json];{rel_filter};out body;", pause=4)
            print(f"    FGC {line}: {len(rels)} route relations")
            stop_ids: set[int] = set()
            for rel in rels:
                for m in rel.get("members", []):
                    if m.get("type") == "node":
                        stop_ids.add(m["ref"])
            if stop_ids:
                stop_nodes = batch_nodes(stop_ids)
                coords = []
                for nd in stop_nodes:
                    lat, lon = nd.get("lat"), nd.get("lon")
                    if lat and lon and in_bbox(float(lat), float(lon)):
                        coords.append((float(lat), float(lon)))
                line_stop_coords[line] = coords
                print(f"      → {len(coords)} stops in bbox")
            time.sleep(2)
        except Exception as exc:
            print(f"    FGC {line} relation query failed: {exc}")

    # Proximity matching: assign a line if any of its stop nodes is within 400 m
    for nid, info in node_info.items():
        for line, coords in line_stop_coords.items():
            for slat, slon in coords:
                if haversine_m(info["lat"], info["lon"], slat, slon) < 400:
                    if line not in info["lines"]:
                        info["lines"].append(line)
                    break

    # Step 3: build records — exclude Funicular-only nodes with no line match
    records = []
    for nid, info in node_info.items():
        if "Funicular" in info["network_tag"] and not info["lines"]:
            continue
        lines = ",".join(sorted(info["lines"]))
        records.append({
            "name": info["name"], "network": "FGC", "lines": lines,
            "lat": info["lat"], "lon": info["lon"], "source": src,
        })

    print(f"  FGC OSM: {len(records)} stations")
    return records


def get_fgc() -> list[dict]:
    print("[FGC]")
    records = fetch_fgc_official()
    if records:
        SOURCES_USED["FGC"] = "Official API (opendata.fgc.cat)"
        return records
    records = fetch_fgc_osm()
    SOURCES_USED["FGC"] = "OSM Overpass (operator=FGC)"
    return records


# ── Rodalies de Catalunya ─────────────────────────────────────────────────────

RENFE_RESOURCE_ID = "e3969f12-aff2-468e-9b82-a65a6dd1a0d3"
RENFE_API_URL = "https://data.renfe.com/api/action/datastore_search"
RENFE_SOURCE = f"https://data.renfe.com (resource {RENFE_RESOURCE_ID})"

RODALIES_LINE_QUERIES = {
    line: f'relation["ref"="{line}"]["route"~"train|rail",i]'
    for line in ["R1", "R2", "R2N", "R3", "R4", "R7", "R8"]
}


def fetch_rodalies_official() -> list[dict]:
    offset, limit = 0, 100
    rows: list[dict] = []
    while True:
        r = SESSION.get(RENFE_API_URL,
                        params={"resource_id": RENFE_RESOURCE_ID,
                                "limit": limit, "offset": offset},
                        timeout=20)
        r.raise_for_status()
        batch = r.json().get("result", {}).get("records", [])
        rows.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    records = []
    for item in rows:
        try:
            lat = float(item.get("LATITUD") or 0)
            lon = float(item.get("LONGITUD") or 0)
        except (ValueError, TypeError):
            continue
        if not lat or not lon or not in_bbox(lat, lon):
            continue
        raw = str(item.get("DESCRIPCION") or "").strip().title()
        # lower-case common Catalan particles
        for p in ("De ", "Del ", "d'", "Les ", "Els ", "La ", "El ", "L'", "En ", "I "):
            raw = raw.replace(p, p.lower())
        fichas = item.get("Fichas") or ""
        records.append({
            "name": raw.strip(), "network": "Rodalies", "lines": "",
            "lat": round(lat, 6), "lon": round(lon, 6),
            "source": fichas or RENFE_SOURCE,
        })
    if not records:
        raise ValueError("no stations in bbox")
    print(f"  Rodalies official API: {len(records)} stations "
          f"({len(rows)} total RENFE records)")
    return records


def fetch_rodalies_osm() -> list[dict]:
    els = oq(
        f'[out:json];'
        f'node["railway"="station"]["network"~"Rodalies|Cercanias",i]({S},{W},{N},{E});'
        f'out;'
    )
    src = OVERPASS_MIRRORS[0] + " (network=Rodalies)"
    records = []
    for el in els:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:ca") or ""
        lat, lon = el.get("lat"), el.get("lon")
        if name and lat and lon:
            records.append({
                "name": name, "network": "Rodalies",
                "lines": tags.get("ref") or "",
                "lat": round(float(lat), 6), "lon": round(float(lon), 6),
                "source": src,
            })
    print(f"  Rodalies OSM fallback: {len(records)} stations")
    return records


def get_rodalies() -> list[dict]:
    print("[Rodalies de Catalunya]")
    try:
        records = fetch_rodalies_official()
        SOURCES_USED["Rodalies"] = "Official API (data.renfe.com)"
        return records
    except Exception as exc:
        print(f"  Rodalies official API failed ({exc}), falling back to OSM")
    records = fetch_rodalies_osm()
    SOURCES_USED["Rodalies"] = "OSM Overpass (network=Rodalies)"
    return records


def enrich_rodalies_lines(records: list[dict]) -> list[dict]:
    """
    For each Rodalies line, fetch its route relation's stop members within
    the bbox, then match against Rodalies station records by lat/lon proximity.
    """
    print("[Enriching Rodalies line assignments …]")

    # Collect (lat, lon) → lines mapping from OSM
    coord_to_lines: dict[tuple, list[str]] = {}
    name_to_lines: dict[str, list[str]] = {}

    for line, rel_filter in RODALIES_LINE_QUERIES.items():
        try:
            rels = oq(f"[out:json];{rel_filter};out body;", pause=4)
            stop_ids: set[int] = set()
            for rel in rels:
                for m in rel.get("members", []):
                    if m.get("type") == "node" and m.get("role") in (
                        "stop", "stop_entry_only", "stop_exit_only", ""
                    ):
                        stop_ids.add(m["ref"])
            if not stop_ids:
                time.sleep(2)
                continue
            nodes = batch_nodes(stop_ids)
            for nd in nodes:
                lat, lon = nd.get("lat"), nd.get("lon")
                if not lat or not lon:
                    continue
                flat, flon = float(lat), float(lon)
                if not in_bbox(flat, flon):
                    continue
                tags = nd.get("tags", {})
                nm = (tags.get("name") or tags.get("name:ca") or "").lower().strip()
                for prec in (3, 2):
                    key = (round(flat, prec), round(flon, prec))
                    coord_to_lines.setdefault(key, [])
                    if line not in coord_to_lines[key]:
                        coord_to_lines[key].append(line)
                if nm:
                    name_to_lines.setdefault(nm, [])
                    if line not in name_to_lines[nm]:
                        name_to_lines[nm].append(line)
            print(f"    Rodalies {line}: {len(rels)} rels, {len(stop_ids)} stops")
            time.sleep(3)
        except Exception as exc:
            print(f"    Rodalies {line} failed: {exc}")
            time.sleep(4)

    def norm(s: str) -> str:
        """Normalise station name for fuzzy matching."""
        import unicodedata, re
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")  # strip accents
        s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
        s = re.sub(r"\b(barcelona|estaci[oò]|passejg|de|la|el|els|les|l|d)\b", "", s)
        return re.sub(r"\s+", " ", s).strip()

    matched = 0
    for r in records:
        if r["network"] != "Rodalies" or r.get("lines"):
            continue
        # 1. Coord match (3 dp ≈ 100 m)
        key = (round(float(r["lat"]), 3), round(float(r["lon"]), 3))
        if key in coord_to_lines:
            r["lines"] = ",".join(sorted(coord_to_lines[key]))
            matched += 1
            continue
        # 2. Relaxed coord (2 dp ≈ 1 km)
        key2 = (round(float(r["lat"]), 2), round(float(r["lon"]), 2))
        if key2 in coord_to_lines:
            r["lines"] = ",".join(sorted(coord_to_lines[key2]))
            matched += 1
            continue
        # 3. Exact name match
        rkey = r["name"].lower().strip()
        if rkey in name_to_lines:
            r["lines"] = ",".join(sorted(name_to_lines[rkey]))
            matched += 1
            continue
        # 4. Normalised substring match
        rn = norm(r["name"])
        for nm, lines in name_to_lines.items():
            nn = norm(nm)
            if rn and nn and (nn in rn or rn in nn or
                              any(w in rn for w in nn.split() if len(w) > 4)):
                r["lines"] = ",".join(sorted(lines))
                matched += 1
                break

    total = sum(1 for r in records if r["network"] == "Rodalies")
    print(f"  Rodalies line enrichment: {matched}/{total} stations assigned")
    return records


# ── TRAM ─────────────────────────────────────────────────────────────────────

TRAM_LINES = {
    "T1": 'relation["ref"="T1"]["network"="Trambaix"]',
    "T2": 'relation["ref"="T2"]["network"="Trambaix"]',
    "T3": 'relation["ref"="T3"]["network"="Trambaix"]',
    "T4": 'relation["ref"="T4"]["network"="Trambesòs"]',
    "T5": 'relation["ref"="T5"]["network"="Trambesòs"]',
    "T6": 'relation["ref"="T6"]["network"="Trambesòs"]',
}


def fetch_tram_osm() -> list[dict]:
    src = OVERPASS_MIRRORS[0] + " (TRAM stops + route relations)"

    # Step 1: fetch all tram_stop nodes in bbox
    stop_nodes = oq(
        f'[out:json];node["railway"="tram_stop"]({S},{W},{N},{E});out;'
    )
    print(f"    TRAM raw tram_stop nodes in bbox: {len(stop_nodes)}")

    node_map: dict[int, dict] = {}
    for nd in stop_nodes:
        tags = nd.get("tags", {})
        lat, lon = nd.get("lat"), nd.get("lon")
        if not lat or not lon:
            continue
        name = tags.get("name") or tags.get("name:ca") or ""
        if not name:
            continue
        node_map[nd["id"]] = {
            "name": name, "lat": round(float(lat), 6), "lon": round(float(lon), 6),
            "lines": [],
        }

    # Step 2: get line assignments from route relations
    for line, rel_filter in TRAM_LINES.items():
        try:
            rels = oq(f"[out:json];{rel_filter};out body;", pause=4)
            print(f"    TRAM {line}: {len(rels)} relations")
            for rel in rels:
                for m in rel.get("members", []):
                    if m.get("type") == "node":
                        nid = m["ref"]
                        if nid in node_map and line not in node_map[nid]["lines"]:
                            node_map[nid]["lines"].append(line)
        except Exception as exc:
            print(f"    TRAM {line} relation query failed: {exc}")

    # Step 3: collapse duplicate platform nodes by name
    raw = [
        {
            "name": info["name"], "network": "TRAM",
            "lines": ",".join(sorted(info["lines"])),
            "lat": info["lat"], "lon": info["lon"], "source": src,
        }
        for info in node_map.values() if info["name"]
    ]
    collapsed = _collapse_by_name(raw)
    print(f"  TRAM OSM: {len(raw)} nodes → {len(collapsed)} unique stops")
    return collapsed


def _collapse_by_name(raw: list[dict]) -> list[dict]:
    """Merge records with same name: average lat/lon, union lines."""
    by_name: dict[str, dict] = {}
    for r in raw:
        key = r["name"].strip()
        if key not in by_name:
            by_name[key] = {**r,
                            "_lats": [r["lat"]], "_lons": [r["lon"]],
                            "_lines": set(r["lines"].split(",")) if r["lines"] else set()}
        else:
            by_name[key]["_lats"].append(r["lat"])
            by_name[key]["_lons"].append(r["lon"])
            if r["lines"]:
                by_name[key]["_lines"].update(r["lines"].split(","))

    result = []
    for key, v in sorted(by_name.items()):
        lines = ",".join(sorted(l for l in v["_lines"] if l))
        result.append({
            "name": key, "network": "TRAM", "lines": lines,
            "lat": round(sum(v["_lats"]) / len(v["_lats"]), 6),
            "lon": round(sum(v["_lons"]) / len(v["_lons"]), 6),
            "source": v["source"],
        })
    return result


def get_tram() -> list[dict]:
    print("[TRAM]")
    records = fetch_tram_osm()
    SOURCES_USED["TRAM"] = "OSM Overpass (railway=tram_stop + route relations)"
    return records


# ── Dedup + I/O ───────────────────────────────────────────────────────────────

FIELDNAMES = ["name", "network", "lines", "lat", "lon", "source"]


def dedup(records: list[dict]) -> list[dict]:
    seen: set = set()
    out = []
    for r in records:
        key = (r["name"].lower().strip(), r["network"], r["lat"], r["lon"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def write_csv(records: list[dict], path: str):
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()
        csv.DictWriter(f, fieldnames=FIELDNAMES).writerows(records)
    print(f"  Wrote {path}")


def write_geojson(records: list[dict], path: str):
    features = [
        {"type": "Feature",
         "geometry": {"type": "Point",
                      "coordinates": [float(r["lon"]), float(r["lat"])]},
         "properties": {k: r[k] for k in FIELDNAMES if k not in ("lat", "lon")}}
        for r in records if r.get("lat") and r.get("lon")
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features},
                  f, ensure_ascii=False, indent=2)
    print(f"  Wrote {path}")


def print_summary(records: list[dict]):
    nets: dict[str, int] = {}
    for r in records:
        nets.setdefault(r["network"], 0)
        nets[r["network"]] += 1
    w = 70
    print("\n" + "=" * w)
    print(f"{'Network':<14} {'Count':>6}  {'Source'}")
    print("-" * w)
    for net, cnt in sorted(nets.items()):
        src = SOURCES_USED.get(net, "?")
        print(f"{net:<14} {cnt:>6}  {src}")
    print("-" * w)
    print(f"{'TOTAL':<14} {sum(nets.values()):>6}")
    print("=" * w)


# ── Main ──────────────────────────────────────────────────────────────────────

def apply_manual_fallbacks(records: list[dict]) -> None:
    """
    Fill in well-known line assignments that OSM route relations miss.
    Only applied when the record has no line yet.
    """
    # name (lowercase) → lines
    fallbacks: dict[str, str] = {
        # FGC terminal / suburban stops not in L6/L7/S1/S2 route relations
        "reina elisenda":          "L6",
        "barcelona-plaça espanya": "L8,S4,S8",
        "europa | fira":           "L8,S4,S8",
        "magòria-la campana":      "L8,S4,S8",
        # Rodalies
        "barcelona-estacio de frança": "R2N",
        # TRAM (unlinked in OSM — likely Trambaix T7 extension corridor)
        "plaça kennedy":    "T1,T2,T3",
        "román macaya":     "T1,T2,T3",
        "josep mª florensa":"T1,T2,T3",
    }
    for r in records:
        if r.get("lines"):
            continue
        key = r["name"].lower().strip()
        if key in fallbacks:
            r["lines"] = fallbacks[key]
            print(f"  [fallback] {r['name']} → {r['lines']}")


def main():
    out_dir = str(Path(__file__).parent)
    records: list[dict] = []

    records += get_fgc()
    time.sleep(5)

    records += get_rodalies()
    time.sleep(5)

    records += get_tram()
    time.sleep(5)

    records = dedup(records)
    print(f"\n{len(records)} unique records before line enrichment")

    records = enrich_rodalies_lines(records)
    apply_manual_fallbacks(records)
    records.sort(key=lambda r: (r["network"], r["name"]))

    print("\n[Writing output files]")
    write_csv(records, f"{out_dir}/barcelona_transit_stations.csv")
    write_geojson(records, f"{out_dir}/barcelona_transit_stations.geojson")
    print_summary(records)


if __name__ == "__main__":
    main()
