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

    loc_value = data.get("loc", "")
    latitude = longitude = None
    if isinstance(loc_value, str) and "," in loc_value:
        latitude, longitude = loc_value.split(",", 1)

    def to_str(value: object) -> str:
        if value is None:
            return ""
        return str(value)

    return {
        "ip": ip_address,
        "city": to_str(data.get("city")),
        "region": to_str(data.get("region")),
        "country": to_str(data.get("country")),
        "postal": to_str(data.get("postal")),
        "timezone": to_str(data.get("timezone")),
        "latitude": to_str(latitude),
        "longitude": to_str(longitude),
    }
