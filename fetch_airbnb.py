"""Download the Inside Airbnb snapshot of Barcelona (insideairbnb.com, licence CC BY 4.0) for the tourism analysis.
Writes to data_catalog/08_tourism_other/tourism/:
  airbnb_listings_2026_09.csv     one row per listing of the 2026-09-17 snapshot: position, room type, price, reviews, availability, licence.
                                  Host names / host ids / listing titles are NOT kept (personal data, not needed).
  airbnb_reviews_per_year.csv     reviews per listing and year (from the review dates of the same snapshot) = a proxy of tourist activity over time.
                                  Only listings still online in 2026 are covered (listings removed earlier are missing: survivorship bias).
Only the latest quarterly snapshots are public; older snapshots need a data request, so there is no full listing history.
"""
import io, re
from pathlib import Path
import pandas as pd, requests

BASE = "https://data.insideairbnb.com/spain/catalonia/barcelona/2026-09-17/visualisations/"
OUT = Path(__file__).parent / "data_catalog" / "08_tourism_other" / "tourism"
OUT.mkdir(parents=True, exist_ok=True)

def get(name):
    r = requests.get(BASE + name, timeout=600, headers={"User-Agent": "Mozilla/5.0"}); r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content), dtype=str)

lst = get("listings.csv")
keep = ["id", "neighbourhood_group", "neighbourhood", "latitude", "longitude", "room_type", "price", "minimum_nights", "number_of_reviews",
        "last_review", "reviews_per_month", "calculated_host_listings_count", "availability_365", "number_of_reviews_ltm", "license"]
lst = lst[keep].rename(columns={"id": "listing_id", "neighbourhood_group": "nom_districte", "neighbourhood": "nom_barri"})   # shared concepts in Catalan
# the licence field is HTML text with a national and/or a regional number -> licence type + the regional tourist-flat number (HUTB-...)
raw = lst["license"].fillna("")
def ltype(s):
    if "HUTB" in s: return "tourist_flat_hutb"
    if re.search(r"Regional registration number<br />(HB|AJ)", s) or re.search(r"Exempt - (hostel|hotel)", s): return "hotel_or_hostel"
    if "seasonal" in s or re.search(r"ES\w{2}NT", s): return "seasonal_non_tourist"
    if "Exempt" in s: return "exempt_other"
    return "none_declared" if s == "" else "other"
lst["license_type"] = raw.map(ltype)
lst["license"] = raw.str.extract(r"(HUTB-?\d+)", expand=False)
lst.to_csv(OUT / "airbnb_listings_2026_09.csv", index=False, encoding="utf-8")
print("listings", lst.shape)

rev = get("reviews.csv")                      # listing_id, date
rev["year"] = rev["date"].str[:4]
per = rev.groupby(["listing_id", "year"]).size().rename("reviews_n").reset_index()
per.to_csv(OUT / "airbnb_reviews_per_year.csv", index=False, encoding="utf-8")
print("reviews", len(rev), "-> listing-years", per.shape, "years", per.year.min(), "-", per.year.max())
