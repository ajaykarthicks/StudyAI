from __future__ import annotations

import os
from typing import Dict, Optional

import requests


def lookup_location(ip_address: Optional[str]) -> Optional[Dict[str, str]]:
    if not ip_address:
        return None

    token = (os.getenv("IPINFO_TOKEN") or "").strip()
    if not token:
        return None

    url = f"https://ipinfo.io/{ip_address}?token={token}"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None

    loc = data.get("loc", "")
    latitude = longitude = None
    if loc and "," in loc:
        latitude, longitude = loc.split(",", 1)

    return {
        "ip": ip_address,
        "city": data.get("city"),
        "region": data.get("region"),
        "country": data.get("country"),
        "postal": data.get("postal"),
        "timezone": data.get("timezone"),
        "latitude": latitude,
        "longitude": longitude,
    }
