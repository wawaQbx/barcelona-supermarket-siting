#!/usr/bin/env python3
"""
Barcelona Supermarket Location Scraper
Collects store data from 10 official supermarket brand websites.
Strategy: REST API discovery first (including XHR interception),
          then Selenium HTML-parse fallback. Nominatim geocoding
          used when coordinates are missing.
"""

import subprocess
import sys
import json
import os
import time
import logging
import re
from dataclasses import dataclass
from typing import Optional, Callable
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# 1.  AUTO-INSTALL REQUIRED PACKAGES
# ─────────────────────────────────────────────────────────────────────────────
_REQUIRED: dict[str, str] = {
    "requests":          "requests>=2.31",
    "bs4":               "beautifulsoup4>=4.12",
    "selenium":          "selenium>=4.20",
    "webdriver_manager": "webdriver-manager>=4.0",
    "geopandas":         "geopandas>=0.14",
    "pandas":            "pandas>=2.0",
    "lxml":              "lxml>=5.0",
    "shapely":           "shapely>=2.0",
}

def _install_missing(pkgs: dict[str, str]) -> None:
    import importlib.util
    missing = [pip for mod, pip in pkgs.items()
               if importlib.util.find_spec(mod) is None]
    if missing:
        print(f"[setup] Installing: {', '.join(missing)}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", *missing, "-q"]
        )

_install_missing(_REQUIRED)

# ─────────────────────────────────────────────────────────────────────────────
# 2.  IMPORTS
# ─────────────────────────────────────────────────────────────────────────────
import requests
from bs4 import BeautifulSoup
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# ─────────────────────────────────────────────────────────────────────────────
# 3.  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
BCN_BBOX = dict(lat_min=41.32, lat_max=41.47, lon_min=2.05, lon_max=2.23)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/html, */*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,ca;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
}

# Barcelona postal codes (08001–08080 covers the city and close municipalities)
BCN_POSTAL_CODES: list[str] = [f"0{8000 + i}" for i in range(1, 81)]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bcn_scraper")

# ─────────────────────────────────────────────────────────────────────────────
# 4.  DATA MODEL
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Store:
    brand:      str
    name:       str
    address:    str
    lat:        float
    lon:        float
    store_type: str             = "supermarket"
    source:     str             = ""
    group:      str             = ""


# ── Brand → corporate group mapping ──────────────────────────────────────────
BRAND_GROUP: dict[str, str] = {
    "Consum":            "Consum Group",
    "Charter":           "Consum Group",
    "Carrefour":         "Carrefour Group",
    "Carrefour Market":  "Carrefour Group",
    "Carrefour Express": "Carrefour Group",
    "Alcampo":           "Auchan Group",
    "Mi Alcampo":        "Auchan Group",
    "Dia":               "Dia Group",
    "Mercadona":         "Mercadona",
    "Lidl":              "Lidl Group",
    "Aldi":              "Aldi Group",
    "Bon Preu":          "Bon Preu Group",
    "Esclat":            "Bon Preu Group",
    "Caprabo":           "Eroski Group",
    "Condis":            "Condis Group",
}

# ── Strict name-validation whitelist per brand ────────────────────────────────
BRAND_NAME_PATTERNS: dict[str, re.Pattern] = {
    "Mercadona":         re.compile(r'^Mercadona$', re.I),
    "Caprabo":           re.compile(r'^Caprabo', re.I),
    "Condis":            re.compile(r'^Condis', re.I),
    "Consum":            re.compile(
        r'^(?:Consum|Supermercados?\s+Consum|Supermercats?\s+Consum|Consum\s+i\s+[Ss]erveis)$', re.I),
    "Charter":           re.compile(
        r'^(?:Charter|Supermercat\s+Charter|Supermercado\s+Charter|'
        r'Supermercados\s+Charter|Supermercats\s+Charter|Charter\s+Consum|Charter\s+-\s+Consum)$', re.I),
    "Lidl":              re.compile(r'^Lidl$', re.I),
    "Aldi":              re.compile(r'^Aldi(?:\s+Supermercados?)?$', re.I),
    "Dia":               re.compile(r'^(?:Dia|Supermercados?\s+Dia|Dia\s*%|Dia\s+Market)$', re.I),
    "Carrefour":         re.compile(r'^Carrefour$', re.I),
    "Carrefour Market":  re.compile(r'^Carrefour\s+Market$', re.I),
    "Carrefour Express": re.compile(r'^Carrefour\s+[Ee]xpress$', re.I),
    "Alcampo":           re.compile(r'^Alcampo$', re.I),
    "Mi Alcampo":        re.compile(r'^Mi\s+Alcampo$', re.I),
    "Bon Preu":          re.compile(r'^Bon\s*Preu', re.I),
    "Esclat":            re.compile(r'^(?:Esclat|HI\s+\d+)', re.I),
}

# All brands expected to appear in the output (determines OSM fallback scope)
ALL_EXPECTED_BRANDS: set[str] = set(BRAND_GROUP.keys())


# ─────────────────────────────────────────────────────────────────────────────
# 5.  CORE UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def in_bcn(lat: float, lon: float) -> bool:
    """Return True if coordinates fall inside the Barcelona bounding box."""
    return (BCN_BBOX["lat_min"] <= lat <= BCN_BBOX["lat_max"] and
            BCN_BBOX["lon_min"] <= lon <= BCN_BBOX["lon_max"])


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


# ── Selenium helpers ──────────────────────────────────────────────────────────

def _make_driver(intercept: bool = False, geo: tuple[float, float] = (41.385, 2.173)):
    """
    Build a headless Chrome WebDriver.
    intercept=True  – enable performance logging to capture XHR responses.
    geo             – (lat, lon) injected via CDP so map-based locators
                      auto-load stores for that location (default: BCN centre).
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--log-level=3")
    opts.add_argument(f"--user-agent={HEADERS['User-Agent']}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    # Skip images for speed
    opts.add_experimental_option("prefs", {
        "profile.managed_default_content_settings.images": 2,
    })
    if intercept:
        opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    service = Service(ChromeDriverManager().install())
    drv = webdriver.Chrome(service=service, options=opts)

    # Hide the webdriver flag that Cloudflare / other WAFs detect
    drv.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    # Override browser geolocation to Barcelona so map locators auto-center there
    drv.execute_cdp_cmd("Emulation.setGeolocationOverride", {
        "latitude":  geo[0],
        "longitude": geo[1],
        "accuracy":  10,
    })
    return drv


def selenium_page_source(url: str, wait: float = 8.0) -> str:
    """Load url in headless Chrome and return page source after `wait` seconds."""
    drv = _make_driver()
    try:
        drv.get(url)
        time.sleep(wait)
        return drv.page_source
    finally:
        drv.quit()


def selenium_capture_xhr(url: str, wait: float = 12.0) -> list[dict]:
    """
    Load url in headless Chrome, capture every JSON XHR response via CDP.
    Returns list of {"url": str, "data": any} objects.
    Useful for discovering hidden API endpoints.
    """
    drv = _make_driver(intercept=True)
    results: list[dict] = []
    try:
        drv.get(url)
        time.sleep(wait)
        perf_logs = drv.get_log("performance")
        for entry in perf_logs:
            try:
                msg = json.loads(entry["message"])["message"]
                if msg.get("method") != "Network.responseReceived":
                    continue
                resp = msg["params"]["response"]
                if "json" not in resp.get("mimeType", ""):
                    continue
                rid = msg["params"]["requestId"]
                resp_url = resp["url"]
                body_obj = drv.execute_cdp_cmd(
                    "Network.getResponseBody", {"requestId": rid}
                )
                raw = body_obj.get("body", "")
                if not raw:
                    continue
                data = json.loads(raw)
                results.append({"url": resp_url, "data": data})
            except Exception:
                pass
    finally:
        drv.quit()
    return results


# ── Cookie / consent helpers ──────────────────────────────────────────────────

def accept_cookies(drv) -> None:
    """
    Click the OneTrust / generic "Accept all cookies" button if present.
    Silently swallows all errors (consent dialogs are optional).
    """
    from selenium.webdriver.common.by import By
    selectors = [
        "#onetrust-accept-btn-handler",       # OneTrust standard
        ".ot-accept-button",
        "button[id*='accept']",
        "button[aria-label*='Aceptar']",
        "button[aria-label*='Accept']",
        "a[id*='accept']",
        ".cookie-btn--accept",
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    ]
    for sel in selectors:
        try:
            btn = drv.find_element(By.CSS_SELECTOR, sel)
            if btn.is_displayed():
                btn.click()
                time.sleep(1.5)
                return
        except Exception:
            pass


# ── Geocoding ─────────────────────────────────────────────────────────────────

_geo_cache: dict[str, Optional[tuple[float, float]]] = {}

def geocode(address: str) -> Optional[tuple[float, float]]:
    """Geocode via Nominatim (free, 1 req/s). Returns (lat, lon) or None."""
    if address in _geo_cache:
        return _geo_cache[address]
    try:
        q = address if "barcelona" in address.lower() else f"{address}, Barcelona, Spain"
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": q, "format": "json", "limit": 1, "countrycodes": "es"},
            headers={"User-Agent": "bcn-supermarket-scraper/1.0 (academic)"},
            timeout=10,
        )
        data = r.json()
        if data:
            lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
            _geo_cache[address] = (lat, lon)
            time.sleep(1.1)   # Nominatim rate-limit: max 1 req/s
            return lat, lon
    except Exception as exc:
        log.warning(f"Geocode error for '{address}': {exc}")
    _geo_cache[address] = None
    return None


# ── JSON / HTML parsing helpers ───────────────────────────────────────────────

def _coerce_float(val) -> Optional[float]:
    """Safe float conversion; returns None on failure."""
    try:
        v = float(val)
        return v if v != 0 else None
    except (TypeError, ValueError):
        return None


def extract_coords(obj: dict) -> tuple[Optional[float], Optional[float]]:
    """Pull (lat, lon) from a dict using common key aliases."""
    lat = (_coerce_float(obj.get("lat")) or _coerce_float(obj.get("latitude"))
           or _coerce_float(obj.get("latitud")) or _coerce_float(obj.get("y")))
    lon = (_coerce_float(obj.get("lon")) or _coerce_float(obj.get("lng"))
           or _coerce_float(obj.get("longitude")) or _coerce_float(obj.get("longitud"))
           or _coerce_float(obj.get("x")))
    return lat, lon


def extract_address(obj: dict) -> str:
    """Build an address string from common key aliases."""
    parts = []
    for key in ("address", "direccion", "calle", "street", "address1",
                "domicilio", "via", "streetAddress"):
        if obj.get(key):
            parts.append(str(obj[key]).strip())
            break
    for key in ("city", "ciudad", "municipio", "municipality", "poblacion"):
        if obj.get(key):
            parts.append(str(obj[key]).strip())
            break
    for key in ("postal_code", "cp", "zip", "postalCode", "zipCode"):
        if obj.get(key):
            parts.append(str(obj[key]).strip())
            break
    return ", ".join(parts) if parts else "N/A"


def walk_json_for_stores(obj, brand: str, source: str,
                          store_type: str = "supermarket",
                          depth: int = 0) -> list[Store]:
    """
    Recursively walk any JSON structure looking for objects with
    lat/lon coordinate pairs. Returns Store instances for Barcelona hits.
    """
    if depth > 12:
        return []
    stores: list[Store] = []
    if isinstance(obj, dict):
        lat, lon = extract_coords(obj)
        if lat is not None and lon is not None and in_bcn(lat, lon):
            name = (obj.get("name") or obj.get("nombre") or
                    obj.get("title") or brand)
            stores.append(Store(
                brand=brand,
                name=str(name).strip() or brand,
                address=extract_address(obj),
                lat=lat, lon=lon,
                store_type=store_type,
                source=source,
            ))
        else:
            for v in obj.values():
                stores.extend(walk_json_for_stores(v, brand, source, store_type, depth + 1))
    elif isinstance(obj, list):
        for item in obj:
            stores.extend(walk_json_for_stores(item, brand, source, store_type, depth + 1))
    return stores


def parse_json_ld(html: str, brand: str, source: str) -> list[Store]:
    """Extract Store instances from JSON-LD <script> blocks in HTML."""
    soup = BeautifulSoup(html, "lxml")
    stores: list[Store] = []
    for sc in soup.find_all("script", type="application/ld+json"):
        try:
            obj = json.loads(sc.string or "")
            items = obj if isinstance(obj, list) else [obj]
            for item in items:
                geo = item.get("geo", {})
                lat = _coerce_float(geo.get("latitude"))
                lon = _coerce_float(geo.get("longitude"))
                if lat and lon and in_bcn(lat, lon):
                    addr = item.get("address", {})
                    address_str = ", ".join(filter(None, [
                        addr.get("streetAddress", ""),
                        addr.get("postalCode", ""),
                        addr.get("addressLocality", ""),
                    ])) or "N/A"
                    stores.append(Store(
                        brand=brand,
                        name=item.get("name", brand),
                        address=address_str,
                        lat=lat, lon=lon,
                        store_type="supermarket",
                        source=source,
                    ))
        except Exception:
            pass
    return stores


def probe_json_api(candidates: list[str], brand: str, source: str,
                   session: requests.Session,
                   store_type: str = "supermarket",
                   extra_params: Optional[dict] = None) -> list[Store]:
    """
    Try a list of candidate API URLs. Return stores from the first
    URL that responds with valid JSON containing coordinate data.
    """
    for url in candidates:
        try:
            r = session.get(url, params=extra_params, timeout=15)
            ct = r.headers.get("Content-Type", "")
            if r.status_code == 200 and ("json" in ct or r.text.lstrip().startswith(("[", "{"))):
                data = r.json()
                stores = walk_json_for_stores(data, brand, source, store_type)
                if stores:
                    log.info(f"{brand}: API hit at {url} → {len(stores)} BCN stores")
                    return stores
                else:
                    log.debug(f"{brand}: {url} returned JSON but no BCN stores")
        except Exception as exc:
            log.debug(f"{brand}: probe {url} failed — {exc}")
    return []


# ─────────────────────────────────────────────────────────────────────────────
# 6.  BRAND SCRAPERS
# ─────────────────────────────────────────────────────────────────────────────

# ── 6.1  Mercadona ────────────────────────────────────────────────────────────
def scrape_mercadona() -> list[Store]:
    """
    Mercadona's Vue SPA queries an internal REST API.
    We try the postal-code endpoint for each BCN postal code,
    then a bounding-box query, then Selenium XHR interception.
    """
    SOURCE = "https://www.mercadona.es/nuestros-supermercados"
    s = make_session()
    s.headers["Referer"] = "https://www.mercadona.es/"
    seen: dict[str, Store] = {}

    # -- Try postal-code API --
    test_r = None
    for pc in ["08001", "08015"]:
        try:
            test_r = s.get(
                "https://www.mercadona.es/api/v3/supermarkets/",
                params={"postal_code": pc}, timeout=15
            )
            if test_r.status_code == 200 and "json" in test_r.headers.get("Content-Type", ""):
                break
            test_r = None
        except Exception:
            test_r = None

    if test_r:
        log.info("Mercadona: postal-code API available")
        for pc in BCN_POSTAL_CODES:
            try:
                r = s.get(
                    "https://www.mercadona.es/api/v3/supermarkets/",
                    params={"postal_code": pc}, timeout=15
                )
                if r.status_code != 200:
                    continue
                data = r.json()
                items = data if isinstance(data, list) else (
                    data.get("results") or data.get("supermarkets") or
                    data.get("stores") or []
                )
                for item in items:
                    sid = str(item.get("id") or item.get("code") or
                              f"{item.get('lat')}{item.get('lng')}")
                    if sid in seen:
                        continue
                    stores = walk_json_for_stores(item, "Mercadona", SOURCE)
                    for st in stores:
                        seen[sid] = st
                time.sleep(0.4)
            except Exception as exc:
                log.debug(f"Mercadona postal {pc}: {exc}")
        if seen:
            return list(seen.values())

    # -- Try lat/lon bounding-box API --
    bbox_stores = probe_json_api(
        [
            "https://www.mercadona.es/api/v3/supermarkets/",
            "https://www.mercadona.es/api/v3/supermarkets",
        ],
        "Mercadona", SOURCE, s,
        extra_params={"lat": 41.39, "lng": 2.17, "range": 25},
    )
    if bbox_stores:
        return bbox_stores

    # -- Selenium with postal-code UI interaction --
    log.info("Mercadona: falling back to Selenium with UI interaction")
    try:
        stores = _mercadona_selenium(SOURCE)
        if stores:
            return stores
    except Exception as exc:
        log.error(f"Mercadona Selenium failed: {exc}")

    log.warning("Mercadona: no stores found")
    return []


def _mercadona_selenium(source: str) -> list[Store]:
    """
    Load the Mercadona store locator in headless Chrome, try to find
    the postal-code search input, type sample BCN codes, and capture
    the XHR JSON responses. Deduplicates on (lat, lon).
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from webdriver_manager.chrome import ChromeDriverManager

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--log-level=3")
    opts.add_argument(f"--user-agent={HEADERS['User-Agent']}")
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    drv = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts,
    )
    drv.execute_cdp_cmd("Emulation.setGeolocationOverride",
                        {"latitude": 41.385, "longitude": 2.173, "accuracy": 10})

    seen: dict[str, Store] = {}
    processed_rids: set[str] = set()

    def _harvest_logs() -> None:
        for entry in drv.get_log("performance"):
            try:
                msg = json.loads(entry["message"])["message"]
                if msg.get("method") != "Network.responseReceived":
                    continue
                resp = msg["params"]["response"]
                if "json" not in resp.get("mimeType", ""):
                    continue
                rid = msg["params"]["requestId"]
                if rid in processed_rids:
                    continue
                processed_rids.add(rid)
                body_obj = drv.execute_cdp_cmd("Network.getResponseBody", {"requestId": rid})
                raw = body_obj.get("body", "")
                if not raw:
                    continue
                data = json.loads(raw)
                for st in walk_json_for_stores(data, "Mercadona", source):
                    key = f"{st.lat:.5f},{st.lon:.5f}"
                    seen[key] = st
            except Exception:
                pass

    try:
        drv.get(source)
        time.sleep(5)
        accept_cookies(drv)
        time.sleep(8)
        _harvest_logs()   # capture any auto-load stores

        # Use JS to find all visible text/search inputs and their properties
        inputs_info = drv.execute_script("""
            return Array.from(document.querySelectorAll('input')).map(function(i){
                return {
                    type: i.type, id: i.id, name: i.name,
                    placeholder: i.placeholder,
                    className: i.className.slice(0,60),
                    visible: i.offsetParent !== null
                };
            });
        """)
        log.debug(f"Mercadona inputs: {inputs_info}")

        # Pick first visible text/search input
        search_input = None
        for info in (inputs_info or []):
            if info.get("type") in ("text", "search", "") and info.get("visible"):
                sel = (f"#{info['id']}" if info.get("id")
                       else f"input[name='{info['name']}']" if info.get("name")
                       else "input[type='text'], input[type='search']")
                try:
                    from selenium.webdriver.common.by import By
                    search_input = drv.find_element(By.CSS_SELECTOR, sel)
                    log.info(f"Mercadona: using input sel={sel}")
                    break
                except Exception:
                    pass

        sample_pcs = ["08001", "08010", "08020", "08030", "08040", "08050"]
        for pc in sample_pcs:
            try:
                if search_input:
                    search_input.clear()
                    search_input.send_keys(pc)
                    time.sleep(0.5)
                    search_input.send_keys(Keys.RETURN)
                    time.sleep(5)
                    _harvest_logs()
            except Exception as exc:
                log.debug(f"Mercadona search {pc}: {exc}")
                # Re-find input in case DOM was rebuilt
                try:
                    search_input = drv.find_element(By.CSS_SELECTOR,
                        "input[type='text'], input[type='search']")
                except Exception:
                    search_input = None
    finally:
        drv.quit()

    return list(seen.values())


# ── 6.2  Caprabo ─────────────────────────────────────────────────────────────
def scrape_caprabo() -> list[Store]:
    """
    Caprabo (Eroski group in Catalonia).
    Diagnostic found their store locator at /es/home/localizador-de-supermercados/.
    We capture XHR with Selenium (geolocation set to BCN centre) and walk any
    JSON responses for store records.
    """
    SOURCE = "https://www.caprabo.com/es/home/localizador-de-supermercados/"
    s = make_session()
    s.headers["Referer"] = "https://www.caprabo.com/"

    # Try static HTML first (some Caprabo pages embed store JSON)
    try:
        r = s.get(SOURCE, timeout=20)
        if r.status_code == 200:
            stores = parse_json_ld(r.text, "Caprabo", SOURCE)
            if stores:
                return stores
            found = walk_json_for_stores(
                re.findall(r'\{[^{}]{0,1000}"lat[^{}]{0,500}\}', r.text),
                "Caprabo", SOURCE)
            if found:
                return found
    except Exception as exc:
        log.debug(f"Caprabo static: {exc}")

    log.info("Caprabo: using Selenium XHR interception on localizador page")
    try:
        xhr_results = selenium_capture_xhr(SOURCE, wait=15)
        for r in xhr_results:
            found = walk_json_for_stores(r["data"], "Caprabo", SOURCE)
            if found:
                log.info(f"Caprabo: {len(found)} stores from {r['url']}")
                return found
        html = selenium_page_source(SOURCE, wait=12)
        stores = parse_json_ld(html, "Caprabo", SOURCE)
        if not stores:
            matches = re.findall(
                r'"lat(?:itude)?"\s*:\s*([\d.]+)[^}]*"l(?:ng|on)(?:gitude)?"\s*:\s*([\d.]+)',
                html, re.DOTALL,
            )
            for lat_s, lon_s in matches:
                lat, lon = float(lat_s), float(lon_s)
                if in_bcn(lat, lon):
                    stores.append(Store("Caprabo", "Caprabo", "N/A", lat, lon, source=SOURCE))
    except Exception as exc:
        log.error(f"Caprabo Selenium failed: {exc}")
        stores = []

    return stores


# ── 6.3  Condis ──────────────────────────────────────────────────────────────
def scrape_condis() -> list[Store]:
    """
    Condis Supermercats S.A. (Catalan chain).
    Diagnostic confirmed a hidden PHP API: GET /data/get-tiendas.php returns
    stores as JSON [{id, calle, cp, ciudad, lat, lng, talla, tipo_tienda}, ...].
    The API respects a session location set by /data/getSetLocation.php.
    Strategy:
      1. Set BCN location via getSetLocation; call get-tiendas.php → all nearby stores.
      2. Cover any missed postal codes by iterating BCN_POSTAL_CODES.
    """
    SOURCE     = "https://www.condis.es/establecimientos"
    BASE       = "https://www.condis.es/data"
    TIPO_TYPE  = {"CONDIS": "supermarket", "CEX": "convenience"}

    s = make_session()
    s.headers["Referer"] = "https://www.condis.es/"

    def _parse_response(raw) -> list[Store]:
        if not isinstance(raw, list):
            return []
        out: list[Store] = []
        for item in raw:
            lat = _coerce_float(item.get("lat"))
            lon = _coerce_float(item.get("lng"))
            if not lat or not lon or not in_bcn(lat, lon):
                continue
            tipo = (item.get("tipo_tienda") or "CONDIS").upper()
            address = ", ".join(filter(None, [
                item.get("calle", ""),
                item.get("cp", ""),
                item.get("ciudad", ""),
            ]))
            out.append(Store(
                brand="Condis",
                name=f"Condis {item.get('cp', '')}".strip(),
                address=address,
                lat=lat, lon=lon,
                store_type=TIPO_TYPE.get(tipo, "supermarket"),
                source=SOURCE,
            ))
        return out

    # Step 1: set BCN location in the session, then pull all nearby stores
    try:
        s.get(f"{BASE}/getSetLocation.php",
              params={"tipo": "set", "lat": 41.385, "lng": 2.173}, timeout=10)
        r = s.get(f"{BASE}/get-tiendas.php", timeout=15)
        if r.status_code == 200 and r.text.lstrip().startswith("["):
            stores = _parse_response(r.json())
            if stores:
                log.info(f"Condis: {len(stores)} stores (geolocation API)")
                return stores
    except Exception as exc:
        log.debug(f"Condis geolocation API: {exc}")

    # Step 2: sweep postal codes to maximise coverage
    seen_ids: set[str] = set()
    all_stores: list[Store] = []
    import random
    for cp in BCN_POSTAL_CODES:
        try:
            cb = str(random.random())
            r = s.get(f"{BASE}/get-tiendas.php",
                      params={"i": cb, "cp": cp}, timeout=10)
            if r.status_code != 200 or not r.text.lstrip().startswith("["):
                continue
            for item in r.json():
                sid = str(item.get("id", ""))
                if sid in seen_ids:
                    continue
                seen_ids.add(sid)
                lat = _coerce_float(item.get("lat"))
                lon = _coerce_float(item.get("lng"))
                if not lat or not lon or not in_bcn(lat, lon):
                    continue
                tipo = (item.get("tipo_tienda") or "CONDIS").upper()
                address = ", ".join(filter(None, [
                    item.get("calle", ""),
                    item.get("cp", ""),
                    item.get("ciudad", ""),
                ]))
                all_stores.append(Store(
                    brand="Condis",
                    name=f"Condis {item.get('cp', '')}".strip(),
                    address=address,
                    lat=lat, lon=lon,
                    store_type=TIPO_TYPE.get(tipo, "supermarket"),
                    source=SOURCE,
                ))
            time.sleep(0.3)
        except Exception:
            pass

    if all_stores:
        log.info(f"Condis: {len(all_stores)} stores (postal sweep)")
    return all_stores


# ── 6.4  Consum / Charter ─────────────────────────────────────────────────────
def _parse_consum_page(html: str, source: str, seen_coords: set) -> list[Store]:
    """Parse one paginated /supermercados/barcelona/N/ page into Store objects."""
    soup = BeautifulSoup(html, "lxml")
    stores: list[Store] = []
    for article in soup.find_all("article", class_="page-list-supermarket"):
        lat = _coerce_float(article.get("data-lat"))
        lon = _coerce_float(article.get("data-lon"))
        if not lat or not lon or not in_bcn(lat, lon):
            continue
        coord_key = f"{lat:.4f},{lon:.4f}"
        if coord_key in seen_coords:
            continue
        seen_coords.add(coord_key)

        # Brand: detect from logo img alt attribute
        logo = article.find("img")
        brand = "Charter" if (logo and "charter" in (logo.get("alt") or "").lower()) else "Consum"

        # Name: first <a> linking to /supermercados/ subpage
        name = ""
        for a in article.find_all("a", href=True):
            if "/supermercados/" in a.get("href", "") and a.get_text(strip=True):
                name = a.get_text(strip=True).title()
                break
        name = name or brand

        # Address: paragraph in .supermarket-description containing a postal code
        address = ""
        desc = article.find(class_="supermarket-description")
        if desc:
            for p in desc.find_all("p"):
                txt = p.get_text(" ", strip=True)
                if re.search(r'08\d{3}', txt):
                    address = txt
                    break

        stores.append(Store(
            brand=brand, name=name, address=address,
            lat=lat, lon=lon, store_type="supermarket", source=source,
        ))
    return stores


def scrape_consum() -> list[Store]:
    """
    Consum Cooperativa + Charter discount banner.
    Diagnostic confirmed both brands appear on paginated
    /supermercados/barcelona/ pages (11 pages × ≤20 stores each).
    Brand detected from the store logo's alt-text (img alt='Consum'
    vs img alt='Charter'). Returns stores for BOTH brands in one list.
    """
    SOURCE = "https://www.consum.es/supermercados/barcelona/"
    sess = make_session()
    sess.headers["Referer"] = "https://www.consum.es/"

    all_stores: list[Store] = []
    seen_coords: set = set()

    for page in range(1, 30):
        url = f"{SOURCE}{page}/" if page > 1 else SOURCE
        try:
            r = sess.get(url, timeout=15)
            if r.status_code == 404:
                break
            page_stores = _parse_consum_page(r.text, SOURCE, seen_coords)
            if not page_stores and page > 1:
                break
            all_stores.extend(page_stores)
            time.sleep(0.4)
        except Exception as exc:
            log.debug(f"Consum page {page}: {exc}")
            break

    consum_n = sum(1 for st in all_stores if st.brand == "Consum")
    charter_n = sum(1 for st in all_stores if st.brand == "Charter")
    log.info(f"Consum: {consum_n} Consum + {charter_n} Charter stores (paginated HTML)")
    return all_stores


# ── 6.5  Lidl ────────────────────────────────────────────────────────────────
def scrape_lidl() -> list[Store]:
    """
    Lidl Spain. Their store locator calls an internal REST API.
    We also try Woosmap (common backend for Lidl) and Selenium.
    """
    SOURCE = "https://www.lidl.es/tiendas"
    s = make_session()
    s.headers["Referer"] = "https://www.lidl.es/"

    # Lidl typically uses an internal API with a bounding box or lat/lon
    bcn_params = {"lat": 41.39, "lng": 2.17, "radius": 25, "limit": 200,
                  "countryCode": "ES", "latitude": 41.39, "longitude": 2.17,
                  "radiusInKm": 25}

    stores = probe_json_api(
        [
            "https://www.lidl.es/api/v2/stores",
            "https://www.lidl.es/api/v1/stores",
            "https://www.lidl.es/api/stores",
            "https://www.lidl.es/s10022538",          # internal slug sometimes used
            "https://www.lidl.es/tiendas?format=json",
        ],
        "Lidl", SOURCE, s,
        extra_params=bcn_params,
    )
    if stores:
        return stores

    # Lidl sometimes uses Woosmap; try that CDN endpoint pattern
    stores = probe_json_api(
        [
            "https://api.woosmap.com/stores/",
            "https://api.woosmap.com/stores/search",
        ],
        "Lidl", SOURCE, s,
        extra_params={"key": "", "lat": 41.39, "lng": 2.17,
                      "max_distance": 25000, "limit": 200},
    )
    if stores:
        return stores

    log.info("Lidl: using Selenium with cookie acceptance + XHR interception")
    try:
        # Lidl uses OneTrust; store data loads only after consent
        drv = _make_driver(intercept=True)
        xhr_results_drv: list[dict] = []
        try:
            drv.get(SOURCE)
            time.sleep(6)
            accept_cookies(drv)   # dismiss OneTrust dialog
            time.sleep(10)        # let store map tiles + data load
            perf = drv.get_log("performance")
            for entry in perf:
                try:
                    msg = json.loads(entry["message"])["message"]
                    if msg.get("method") != "Network.responseReceived":
                        continue
                    resp = msg["params"]["response"]
                    if "json" not in resp.get("mimeType", ""):
                        continue
                    rid = msg["params"]["requestId"]
                    body_obj = drv.execute_cdp_cmd("Network.getResponseBody",
                                                   {"requestId": rid})
                    raw = body_obj.get("body", "")
                    if raw:
                        xhr_results_drv.append({"url": resp["url"],
                                                "data": json.loads(raw)})
                except Exception:
                    pass
            html_after = drv.page_source
        finally:
            drv.quit()

        for r in xhr_results_drv:
            found = walk_json_for_stores(r["data"], "Lidl", SOURCE)
            if found:
                log.info(f"Lidl: {len(found)} stores from {r['url']}")
                return found
        html = html_after
        return parse_json_ld(html, "Lidl", SOURCE)
    except Exception as exc:
        log.error(f"Lidl Selenium failed: {exc}")

    return []


# ── 6.6  Aldi ────────────────────────────────────────────────────────────────
def scrape_aldi() -> list[Store]:
    """
    Aldi Spain. Their store finder renders via JS.
    Try common API patterns then Selenium.
    """
    # Their store locator page (probe confirmed 200 on this URL)
    SOURCE = "https://www.aldi.es/supermercados.html"
    s = make_session()
    s.headers["Referer"] = "https://www.aldi.es/"

    bcn_params = {"lat": 41.39, "lng": 2.17, "radius": 25,
                  "latitude": 41.39, "longitude": 2.17}

    stores = probe_json_api(
        [
            "https://www.aldi.es/api/stores",
            "https://www.aldi.es/api/v1/stores",
            "https://www.aldi.es/api/tiendas",
        ],
        "Aldi", SOURCE, s,
        extra_params=bcn_params,
    )
    if stores:
        return stores

    # Static HTML probe first (page may embed JS marker data)
    try:
        r = s.get(SOURCE, timeout=20)
        if r.status_code == 200:
            found = parse_json_ld(r.text, "Aldi", SOURCE)
            if found:
                return found
    except Exception:
        pass

    log.info("Aldi: using Selenium XHR interception")
    try:
        xhr_results = selenium_capture_xhr(SOURCE, wait=14)
        for r in xhr_results:
            found = walk_json_for_stores(r["data"], "Aldi", SOURCE)
            if found:
                log.info(f"Aldi: {len(found)} stores from {r['url']}")
                return found
        html = selenium_page_source(SOURCE, wait=12)
        return parse_json_ld(html, "Aldi", SOURCE)
    except Exception as exc:
        log.error(f"Aldi Selenium failed: {exc}")

    return []


# ── 6.7  Dia ─────────────────────────────────────────────────────────────────
def scrape_dia() -> list[Store]:
    """
    Grupo Dia. Diagnostic confirmed the shopFinder.js fetches a gzipped JSON
    from the URL stored in a hidden <input id='gz'> element on the /tiendas page
    (which redirects to /folleto but still serves the #gz input in static HTML).
    Fields: posicionX=lat, posicionY=lon, tipoTienda (0=Dia, 1=Dia Market).
    220 BCN stores confirmed. No name or address in the JSON (only coords + type).
    """
    import gzip

    SOURCE = "https://www.dia.es/tiendas"
    TIPO_NAME = {0: "Dia", 1: "Dia Market"}

    # Use plain Accept header — make_session()'s application/json first causes
    # the Dia server to serve different content, hiding the #gz input element.
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "text/html, application/xhtml+xml, */*;q=0.8",
        "Accept-Language": HEADERS["Accept-Language"],
        "Referer": "https://www.dia.es/",
    })

    # Step 1: get the versioned gzip URL from the static page's hidden input
    gz_url: Optional[str] = None
    try:
        r = sess.get(SOURCE, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
        gz_inp = soup.find("input", id="gz")
        if gz_inp:
            gz_url = gz_inp.get("value") or None
        if not gz_url:
            m = re.search(r'https://[^"\']+tiendas\.v\d+\.json\.gz', r.text)
            if m:
                gz_url = m.group(0)
    except Exception as exc:
        log.debug(f"Dia: could not read /tiendas page — {exc}")

    if not gz_url:
        log.warning("Dia: #gz URL not found; skipping")
        return []

    # Step 2: download and decompress the gzipped JSON
    try:
        r2 = sess.get(gz_url, timeout=30)
        if r2.status_code != 200:
            log.warning(f"Dia: gz download HTTP {r2.status_code}")
            return []
        raw_bytes = r2.content
        if raw_bytes[:2] == b'\x1f\x8b':
            data = json.loads(gzip.decompress(raw_bytes))
        else:
            data = r2.json()
    except Exception as exc:
        log.error(f"Dia: gz download/parse failed — {exc}")
        return []

    if not isinstance(data, list):
        log.warning("Dia: unexpected JSON structure")
        return []

    stores: list[Store] = []
    for item in data:
        lat = _coerce_float(item.get("posicionX"))
        lon = _coerce_float(item.get("posicionY"))
        if not lat or not lon or not in_bcn(lat, lon):
            continue
        tipo = item.get("tipoTienda", 0)
        name = TIPO_NAME.get(tipo, "Dia")
        stores.append(Store(
            brand="Dia", name=name, address="",
            lat=lat, lon=lon, store_type="supermarket", source=SOURCE,
        ))

    log.info(f"Dia: {len(stores)} BCN stores (official gzipped JSON)")
    return stores


# ── 6.8  Carrefour ───────────────────────────────────────────────────────────
def scrape_carrefour() -> list[Store]:
    """
    Carrefour Spain. Their supermercados locator uses a JS-heavy SPA.
    Includes hypermarket (Carrefour) and express (Carrefour Express) types.
    """
    SOURCE = "https://www.carrefour.es/supermercados"
    s = make_session()
    s.headers["Referer"] = "https://www.carrefour.es/"

    bcn_params = {"lat": 41.39, "lon": 2.17, "lng": 2.17,
                  "latitude": 41.39, "longitude": 2.17, "radius": 25}

    stores = probe_json_api(
        [
            "https://www.carrefour.es/api/v1/tiendas",
            "https://www.carrefour.es/api/tiendas",
            "https://www.carrefour.es/api/stores",
            "https://www.carrefour.es/api/v2/stores",
            "https://www.carrefour.es/supermercados?format=json",
        ],
        "Carrefour", SOURCE, s,
        extra_params=bcn_params,
    )
    if stores:
        return stores

    log.info("Carrefour: using Selenium XHR interception")
    try:
        xhr_results = selenium_capture_xhr(SOURCE, wait=15)
        for r in xhr_results:
            found = walk_json_for_stores(r["data"], "Carrefour", SOURCE)
            if found:
                # Classify hypermarkets vs supermarkets by name
                for st in found:
                    if "express" in st.name.lower():
                        st.store_type = "convenience"
                    elif "market" in st.name.lower() or "hyper" in st.name.lower():
                        st.store_type = "hypermarket"
                log.info(f"Carrefour: {len(found)} stores from {r['url']}")
                return found
        html = selenium_page_source(SOURCE, wait=12)
        return parse_json_ld(html, "Carrefour", SOURCE)
    except Exception as exc:
        log.error(f"Carrefour Selenium failed: {exc}")

    return []


# ── 6.9  Bon Preu ────────────────────────────────────────────────────────────
def scrape_bonpreu() -> list[Store]:
    """
    Bon Preu / Bon Preu Ràpid / esclat (Catalan chain).
    Liferay CMS embeds all stores as var establimentsJson = [...] in the
    rendered HTML of the store finder page. Confirmed 51 BCN-bbox stores.
    Fields: latitud, longitud, direccio, codiPostal, poblacio, ensenya,
    descripcio (ensenya values: BONPREU / BONPREU_RAPID / ESCLAT).
    """
    SOURCE = "https://www.bonpreuesclat.cat/ca/cercador-d-establiments"

    ENSENYA_TYPE = {
        "BONPREU":               "supermarket",
        "BONPREU_RAPID":         "convenience",
        "MINIMERCAT":            "supermarket",
        "ESCLAT":                "hypermarket",
        "BONPREUESCLAT_ONLINE":  None,   # skip — online-only format
        "ESCLATOIL":             None,   # skip — fuel stations
    }
    ENSENYA_BRAND = {
        "BONPREU":       "Bon Preu",
        "BONPREU_RAPID": "Bon Preu",
        "MINIMERCAT":    "Bon Preu",
        "ESCLAT":        "Esclat",
    }

    def _parse(html: str) -> list[Store]:
        # Locate the opening '[' of establimentsJson; use raw_decode so that
        # the JSON parser itself finds the matching ']', avoiding regex pitfalls
        # with lazy quantifiers stopping at the wrong ']' inside the data.
        m = re.search(r'var\s+establimentsJson\s*=\s*\[', html)
        if not m:
            return []
        try:
            data, _ = json.JSONDecoder().raw_decode(html, m.end() - 1)
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        out: list[Store] = []
        for item in data:
            lat = _coerce_float(item.get("latitud"))
            lon = _coerce_float(item.get("longitud"))
            if not lat or not lon or not in_bcn(lat, lon):
                continue
            ensenya = (item.get("ensenya") or "BONPREU").upper()
            store_type = ENSENYA_TYPE.get(ensenya, "supermarket")
            if store_type is None:
                continue   # fuel station or online-only variant
            address = ", ".join(filter(None, [
                item.get("direccio", ""),
                item.get("codiPostal", ""),
                item.get("poblacio", ""),
            ]))
            brand = ENSENYA_BRAND.get(ensenya, "Bon Preu")
            out.append(Store(
                brand=brand,
                name=item.get("descripcio") or brand,
                address=address,
                lat=lat, lon=lon,
                store_type=store_type,
                source=SOURCE,
            ))
        return out

    # Liferay is SSR — try static HTML first (fastest path)
    s = make_session()
    s.headers["Referer"] = "https://www.bonpreuesclat.cat/"
    try:
        r = s.get(SOURCE, timeout=20)
        if r.status_code == 200:
            stores = _parse(r.text)
            if stores:
                log.info(f"Bon Preu: {len(stores)} stores (static HTML)")
                return stores
    except Exception as exc:
        log.debug(f"Bon Preu static: {exc}")

    # The Liferay portlet may load via AJAX — fall back to Selenium
    log.info("Bon Preu: using Selenium (15 s wait for Liferay portlet)")
    try:
        drv = _make_driver()
        try:
            drv.get(SOURCE)
            time.sleep(5)
            accept_cookies(drv)
            time.sleep(15)
            stores = _parse(drv.page_source)
            if stores:
                log.info(f"Bon Preu: {len(stores)} stores (Selenium)")
                return stores
        finally:
            drv.quit()
    except Exception as exc:
        log.error(f"Bon Preu Selenium failed: {exc}")

    return []


# ── 6.10  Alcampo ────────────────────────────────────────────────────────────
def scrape_alcampo() -> list[Store]:
    """
    Alcampo (Auchan Spain) uses Woosmap as their store locator backend.
    Diagnostic confirmed the API key and endpoint from browser network traffic.
    The Woosmap API enforces CORS (rejects direct Python requests), so we
    load the Alcampo store-locator SPA in Selenium, then call the API
    via in-page JavaScript fetch (same-origin → CORS allowed).
    Confirmed: returns 44 Barcelona stores.
    """
    SOURCE   = "https://store-locator.bckts.are.external.alcampo.es/"
    # public front-end key of the Alcampo locator (visible in the page's network traffic); not stored in the repository
    WOOS_KEY = os.environ.get("ALCAMPO_WOOSMAP_KEY", "")
    if not WOOS_KEY:
        raise SystemExit("set ALCAMPO_WOOSMAP_KEY (read it from the store-locator page's network requests)")

    drv = _make_driver()
    try:
        drv.get(SOURCE)
        time.sleep(6)

        result = drv.execute_async_script(
            "var cb=arguments[arguments.length-1];"
            f"fetch('https://api.woosmap.com/stores/search/?key={WOOS_KEY}"
            "&lat=41.385&lng=2.173&stores_by_page=200&radius=30000')"
            ".then(function(r){return r.json();})"
            ".then(function(d){cb(d);})"
            ".catch(function(e){cb({error:String(e)});});"
        )

        if not result or "error" in result:
            log.warning(f"Alcampo Woosmap call failed: {result}")
            return []

        stores = []
        for feat in result.get("features", []):
            coords = feat.get("geometry", {}).get("coordinates", [])
            if len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            if not in_bcn(lat, lon):
                continue
            props   = feat.get("properties", {})
            addr_obj = props.get("address", {})
            street  = (addr_obj.get("lines") or [""])[0]
            city    = addr_obj.get("city", "")
            zipcode = addr_obj.get("zipcode", "")
            address = ", ".join(filter(None, [street, zipcode, city]))
            name    = props.get("name") or "Alcampo"
            # "Mi Alcampo" = compact urban format; "Alcampo" = hypermarket
            if "mi alcampo" in name.lower():
                brand = "Mi Alcampo"
                stype = "supermarket"
            else:
                brand = "Alcampo"
                stype = "hypermarket"
            stores.append(Store(
                brand=brand, name=name, address=address,
                lat=lat, lon=lon, store_type=stype, source=SOURCE,
            ))
        alcampo_n  = sum(1 for st in stores if st.brand == "Alcampo")
        mi_n       = sum(1 for st in stores if st.brand == "Mi Alcampo")
        log.info(f"Alcampo: {alcampo_n} Alcampo + {mi_n} Mi Alcampo (Woosmap)")
        return stores
    finally:
        drv.quit()



# ─────────────────────────────────────────────────────────────────────────────
# 6.12  OpenStreetMap Overpass API (fallback for brands that resist scraping)
# ─────────────────────────────────────────────────────────────────────────────
def scrape_osm_bcn(target_brands: list[str]) -> list[Store]:
    """
    Query Overpass API for all shops in the BCN bbox whose OSM `name` tag
    matches any of the requested brand names.  Used as a fallback when the
    official website scraper returns 0 stores.  Results are tagged
    source='OpenStreetMap'.

    For multi-format brands (Carrefour, Alcampo, Consum) the actual OSM name
    is used to assign the correct sub-brand rather than collapsing everything
    to the parent brand.
    """
    if not target_brands:
        return []

    SOURCE   = "https://www.openstreetmap.org"
    OVERPASS = "https://overpass-api.de/api/interpreter"

    # Maps each expected brand to the OSM name variants that identify it.
    # For multi-format brands (Carrefour, Alcampo, Consum/Charter) the
    # variants cover ALL sub-brands so one query fetches everything; the
    # brand assignment logic below then picks the right sub-brand per element.
    OSM_VARIANTS: dict[str, list[str]] = {
        "Mercadona":         ["Mercadona"],
        "Caprabo":           ["Caprabo"],
        "Lidl":              ["Lidl"],
        "Aldi":              ["Aldi"],
        "Dia":               ["Dia", "Dia Market"],
        "Carrefour":         ["Carrefour", "Carrefour Express", "Carrefour Market"],
        "Carrefour Market":  ["Carrefour Market"],
        "Carrefour Express": ["Carrefour Express"],
        "Condis":            ["Condis"],
        "Consum":            ["Consum"],
        "Charter":           ["Charter", "Supermercat Charter", "Supermercado Charter",
                              "Supermercats Charter", "Charter Consum"],
        "Bon Preu":          ["Bon Preu", "BonPreu"],
        "Esclat":            ["Esclat"],
        "Alcampo":           ["Alcampo"],
        "Mi Alcampo":        ["Mi Alcampo"],
    }
    DEFAULT_TYPE: dict[str, str] = {
        "Mercadona":         "supermarket",
        "Caprabo":           "supermarket",
        "Lidl":              "supermarket",
        "Aldi":              "supermarket",
        "Dia":               "supermarket",
        "Carrefour":         "supermarket",
        "Carrefour Market":  "supermarket",
        "Carrefour Express": "convenience",
        "Condis":            "supermarket",
        "Consum":            "supermarket",
        "Charter":           "supermarket",
        "Bon Preu":          "supermarket",
        "Esclat":            "hypermarket",
        "Alcampo":           "hypermarket",
        "Mi Alcampo":        "supermarket",
    }

    # Expand requested brands to their OSM name variants (dedup)
    # For multi-format groups, requesting "Carrefour" auto-includes sub-brands
    BRAND_EXPANSION: dict[str, list[str]] = {
        "Carrefour": ["Carrefour", "Carrefour Market", "Carrefour Express"],
        "Alcampo":   ["Alcampo", "Mi Alcampo"],
        "Consum":    ["Consum", "Charter"],
        "Bon Preu":  ["Bon Preu", "Esclat"],
    }
    expanded_brands: list[str] = []
    for b in target_brands:
        expanded_brands.extend(BRAND_EXPANSION.get(b, [b]))
    expanded_brands = list(dict.fromkeys(expanded_brands))   # deduplicate, preserve order

    all_variants: list[str] = []
    for b in expanded_brands:
        all_variants.extend(OSM_VARIANTS.get(b, [b]))
    all_variants = list(dict.fromkeys(all_variants))
    name_re = "|".join(re.escape(v) for v in all_variants)

    bbox = (f"{BCN_BBOX['lat_min']},{BCN_BBOX['lon_min']},"
            f"{BCN_BBOX['lat_max']},{BCN_BBOX['lon_max']}")
    query = (
        f'[out:json][timeout:30];'
        f'(node["shop"]["name"~"{name_re}",i]({bbox});'
        f' way["shop"]["name"~"{name_re}",i]({bbox}););'
        f'out center tags;'
    )

    # Overpass requires plain Accept; fresh session to avoid 406 from make_session().
    osm_sess = requests.Session()
    osm_sess.headers.update({
        "User-Agent": "barcelona-supermarket-scraper/1.0 (research)",
        "Accept": "*/*",
    })
    try:
        r = osm_sess.post(OVERPASS, data={"data": query}, timeout=45)
        if r.status_code != 200:
            log.warning(f"OSM Overpass HTTP {r.status_code}: {r.text[:200]}")
            return []
        elements = r.json().get("elements", [])
        log.info(f"OSM: {len(elements)} raw elements for {target_brands}")
    except Exception as exc:
        log.error(f"OSM Overpass failed: {exc}")
        return []

    osm_stores: list[Store] = []
    for el in elements:
        if el.get("type") == "node":
            lat = _coerce_float(el.get("lat"))
            lon = _coerce_float(el.get("lon"))
        else:
            ctr = el.get("center", {})
            lat = _coerce_float(ctr.get("lat"))
            lon = _coerce_float(ctr.get("lon"))
        if not lat or not lon or not in_bcn(lat, lon):
            continue

        tags     = el.get("tags", {})
        name     = tags.get("name", "")
        shop_tag = tags.get("shop", "supermarket")

        # Find the most specific matching brand using strict name patterns
        matched_brand: Optional[str] = None
        for b in expanded_brands:
            if b not in target_brands and not any(
                b in BRAND_EXPANSION.get(tb, []) for tb in target_brands
            ):
                continue
            pat = BRAND_NAME_PATTERNS.get(b)
            if pat and pat.match(name):
                matched_brand = b
                break
        if not matched_brand:
            continue

        addr = ", ".join(filter(None, [
            " ".join(filter(None, [tags.get("addr:street", ""),
                                   tags.get("addr:housenumber", "")])),
            tags.get("addr:postcode", ""),
            tags.get("addr:city", ""),
        ]))

        store_type = DEFAULT_TYPE.get(matched_brand, "supermarket")
        if shop_tag == "convenience":
            store_type = "convenience"
        elif shop_tag == "hypermarket":
            store_type = "hypermarket"

        osm_stores.append(Store(
            brand=matched_brand,
            name=name or matched_brand,
            address=addr or "N/A",
            lat=lat, lon=lon,
            store_type=store_type,
            source=SOURCE,
        ))

    log.info(f"OSM: {len(osm_stores)} BCN stores added")
    return osm_stores


# ─────────────────────────────────────────────────────────────────────────────
# 6.13  Name validation + deduplication
# ─────────────────────────────────────────────────────────────────────────────

OSM_SOURCE = "https://www.openstreetmap.org"


def validate_stores(stores: list[Store]) -> list[Store]:
    """
    Remove OSM records whose `name` tag does not match the strict brand whitelist.
    (OSM uses the `name` field as the brand identifier; false positives are common
    because regex matching may capture unrelated stores like "MediaMarkt" for Dia.)

    Official-source records (not from OSM) are always kept: for those, `brand` is
    set from domain knowledge and `name` is the store's own display name which may
    be a location identifier ("Santa Coloma De Cervelló") rather than a brand name.
    Manually-added records (lat==lon==0) are also always kept.
    Logs the count of removed records per brand.
    """
    kept: list[Store] = []
    removed_counts: dict[str, int] = {}

    for st in stores:
        is_manual  = (st.lat == 0 and st.lon == 0)
        is_osm     = (OSM_SOURCE in st.source)

        if is_manual or not is_osm:
            kept.append(st)
            continue

        # OSM record — apply strict name whitelist
        pat = BRAND_NAME_PATTERNS.get(st.brand)
        if pat is None or pat.match(st.name):
            kept.append(st)
        else:
            removed_counts[st.brand] = removed_counts.get(st.brand, 0) + 1
            log.debug(f"Validation removed [{st.brand}] name={st.name!r}")

    for brand, n in sorted(removed_counts.items()):
        log.info(f"Validation: removed {n} OSM records for {brand} (name mismatch)")

    return kept


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two WGS-84 points."""
    import math
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = math.radians(lat2 - lat1)
    dlambda    = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _completeness(st: Store) -> int:
    """Score a store record by data completeness (higher = more complete)."""
    score = 0
    if st.name and st.name != st.brand:
        score += 2
    if st.address and st.address not in ("", "N/A"):
        score += 2
    return score


def deduplicate_stores(stores: list[Store]) -> list[Store]:
    """
    For brands with <100 stores: if two records of the same brand are within
    100 m of each other, keep the one with higher data completeness.
    Manually-added records (lat==lon==0) are never the removed duplicate;
    they can only be removed if a more complete non-manual record exists
    within 100 m (per spec: brand <100 stores AND 100m violation AND
    more complete duplicate exists).
    """
    from collections import defaultdict

    by_brand: dict[str, list[Store]] = defaultdict(list)
    for st in stores:
        by_brand[st.brand].append(st)

    result: list[Store] = []
    for brand, bstores in by_brand.items():
        if len(bstores) >= 100:
            result.extend(bstores)
            continue

        before = len(bstores)
        surviving = list(bstores)
        changed = True
        while changed:
            changed = False
            survivors_next: list[Store] = []
            removed_indices: set[int] = set()
            for i, a in enumerate(surviving):
                if i in removed_indices:
                    continue
                for j, b in enumerate(surviving):
                    if j <= i or j in removed_indices:
                        continue
                    if haversine_m(a.lat, a.lon, b.lat, b.lon) <= 100:
                        a_is_manual = (a.lat == 0 and a.lon == 0)
                        b_is_manual = (b.lat == 0 and b.lon == 0)
                        score_a = _completeness(a)
                        score_b = _completeness(b)
                        # Keep more complete; if equal keep a
                        if score_b > score_a and not (a_is_manual and score_a >= score_b):
                            removed_indices.add(i)
                        else:
                            removed_indices.add(j)
                        changed = True
            surviving = [s for idx, s in enumerate(surviving) if idx not in removed_indices]

        after = len(surviving)
        if after < before:
            log.info(f"Dedup [{brand}]: {before} → {after} stores (removed {before-after} within 100 m)")
        result.extend(surviving)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 7.  MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

SCRAPERS: list[tuple[str, Callable]] = [
    ("Mercadona",   scrape_mercadona),
    ("Caprabo",     scrape_caprabo),
    ("Condis",      scrape_condis),
    ("Consum",      scrape_consum),      # returns Consum + Charter stores
    ("Lidl",        scrape_lidl),
    ("Aldi",        scrape_aldi),
    ("Dia",         scrape_dia),
    ("Carrefour",   scrape_carrefour),
    ("Bon Preu",    scrape_bonpreu),     # returns Bon Preu + Esclat stores
    ("Alcampo",     scrape_alcampo),     # returns Alcampo + Mi Alcampo stores
]


def run_all() -> list[Store]:
    """Run all brand scrapers; OSM fallback for any expected brand with 0 stores."""
    all_stores: list[Store] = []
    brand_counts: dict[str, int] = {}

    for scraper_brand, fn in SCRAPERS:
        log.info(f"{'─'*60}")
        log.info(f"Scraping {scraper_brand} …")
        try:
            result = fn()
            all_stores.extend(result)
            # Count by actual store.brand (handles functions returning multiple brands)
            for st in result:
                brand_counts[st.brand] = brand_counts.get(st.brand, 0) + 1
            if not result:
                brand_counts.setdefault(scraper_brand, 0)
        except Exception as exc:
            log.error(f"{scraper_brand} scraper crashed: {exc}", exc_info=True)
            brand_counts.setdefault(scraper_brand, 0)

    # OSM fallback for any expected brand that ended up with 0 stores
    zero_brands = [b for b in ALL_EXPECTED_BRANDS if brand_counts.get(b, 0) == 0]
    if zero_brands:
        log.info(f"{'─'*60}")
        log.info(f"OSM fallback for: {', '.join(sorted(zero_brands))}")
        osm_result = scrape_osm_bcn(zero_brands)
        all_stores.extend(osm_result)
        for st in osm_result:
            brand_counts[st.brand] = brand_counts.get(st.brand, 0) + 1

    log.info(f"{'─'*60}")
    log.info(f"Pre-validation total: {len(all_stores)} stores")

    # Name validation — remove records whose name doesn't match brand whitelist
    all_stores = validate_stores(all_stores)
    log.info(f"Post-validation total: {len(all_stores)} stores")

    # Deduplication — 100 m radius for brands with <100 stores
    all_stores = deduplicate_stores(all_stores)
    log.info(f"Post-dedup total: {len(all_stores)} stores")

    # Assign corporate group to each store
    for st in all_stores:
        st.group = BRAND_GROUP.get(st.brand, "")

    log.info(f"{'─'*60}")
    log.info(f"Total Barcelona stores: {len(all_stores)}")
    return all_stores


def build_geodataframe(stores: list[Store]) -> gpd.GeoDataFrame:
    """Convert Store list to a GeoDataFrame (EPSG:4326)."""
    rows = []
    for st in stores:
        rows.append({
            "brand":      st.brand,
            "group":      st.group,
            "name":       st.name,
            "address":    st.address,
            "store_type": st.store_type,
            "source":     st.source,
            "lat":        st.lat,
            "lon":        st.lon,
            "geometry":   Point(st.lon, st.lat),
        })
    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    return gdf


def export_results(gdf: gpd.GeoDataFrame, out_dir: Path = Path(".")) -> None:
    """Write GeoJSON and CSV to out_dir."""
    geojson_path = out_dir / "barcelona_supermarkets_official.geojson"
    csv_path     = out_dir / "barcelona_supermarkets_official.csv"

    gdf.to_file(geojson_path, driver="GeoJSON")
    gdf.drop(columns=["geometry"]).to_csv(csv_path, index=False, encoding="utf-8")

    log.info(f"GeoJSON → {geojson_path}")
    log.info(f"CSV     → {csv_path}")


def print_summary(gdf: gpd.GeoDataFrame) -> None:
    """Print a per-brand store count table with corporate group."""
    summary = (
        gdf.groupby(["group", "brand"])
           .size()
           .reset_index(name="count")
           .sort_values(["group", "count"], ascending=[True, False])
    )
    print("\n" + "═" * 58)
    print(f"  BARCELONA SUPERMARKETS SUMMARY")
    print("═" * 58)
    print(f"  {'Brand':<20}  {'Group':<22}  {'Stores':>6}")
    print("─" * 58)
    for _, row in summary.iterrows():
        print(f"  {row['brand']:<20}  {row['group']:<22}  {row['count']:>6}")
    print("─" * 58)
    print(f"  {'TOTAL':<44}  {gdf.shape[0]:>6}")
    print("═" * 58 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# 8.  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    stores = run_all()

    if not stores:
        log.warning("No stores were collected. Check network access and website availability.")
    else:
        gdf = build_geodataframe(stores)
        export_results(gdf)
        print_summary(gdf)
        log.info("Done.")
