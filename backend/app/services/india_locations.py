"""India state/district reference data and optional coordinate lookup."""

from __future__ import annotations

import json
from functools import lru_cache
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# Kept outside application code dependencies: plain HTTPS JSON, no vendor SDK.
REFERENCE_URL = "https://codingmation.github.io/indian-states-districts/data/india_states_districts.min.json"
REVERSE_GEOCODE_URL = "https://nominatim.openstreetmap.org/reverse"
INDIA_STATES = (
    "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam",
    "Bihar", "Chandigarh", "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir",
    "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha",
    "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
    "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
)


def _read_json(url: str) -> object:
    request = Request(url, headers={"User-Agent": "SIH-Land-Risk-Dashboard/1.0"})
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


@lru_cache(maxsize=1)
def india_state_districts() -> dict[str, list[str]]:
    """Return all reference states and districts; retain state fallback offline."""
    try:
        payload = _read_json(REFERENCE_URL)
        locations = {
            item["name"]: sorted({district["name"] for district in item.get("districts", [])})
            for item in payload
            if item.get("name")
        }
        if locations:
            return locations
    except (KeyError, TypeError, URLError, TimeoutError, json.JSONDecodeError):
        pass
    return {state: [] for state in INDIA_STATES}


def reverse_geocode(latitude: float, longitude: float) -> dict[str, str | None]:
    """Resolve state/district from coordinates after an explicit user action."""
    query = urlencode({"format": "jsonv2", "lat": latitude, "lon": longitude, "zoom": 10, "addressdetails": 1})
    try:
        payload = _read_json(f"{REVERSE_GEOCODE_URL}?{query}")
        address = payload.get("address", {})
    except (AttributeError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ValueError("Coordinate lookup is unavailable. Enter location manually.") from error

    state = address.get("state") or address.get("state_district")
    district = address.get("state_district") or address.get("county") or address.get("district")
    country = address.get("country")
    if country and country.casefold() in {"india", "bharat"}:
        country = "India"
    return {"country": country, "state": state, "district": district}
