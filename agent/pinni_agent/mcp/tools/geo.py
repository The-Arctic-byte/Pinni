"""Geocoding and place resolver MCP tool."""
from typing import Any, Dict, Optional

# Oulu area place registry based on contract/mock/places.json
KNOWN_PLACES: Dict[str, Dict[str, Any]] = {
    "kiiminki": {
        "id": "kiiminki",
        "scale": "area",
        "coordinate": {"lat": 65.131, "lon": 25.735},
        "radiusMeters": 1500,
        "name": {"en": "Kiiminki", "fi": "Kiiminki", "fa": "کیمینکی"},
    },
    "linnanmaa": {
        "id": "linnanmaa",
        "scale": "area",
        "coordinate": {"lat": 65.059, "lon": 25.466},
        "radiusMeters": 1200,
        "name": {"en": "Linnanmaa", "fi": "Linnanmaa", "fa": "لینانما"},
    },
    "ritaharju": {
        "id": "ritaharju",
        "scale": "area",
        "coordinate": {"lat": 65.075, "lon": 25.441},
        "radiusMeters": 1000,
        "name": {"en": "Ritaharju", "fi": "Ritaharju", "fa": "ریتاهاریو"},
    },
    "tuira": {
        "id": "tuira",
        "scale": "area",
        "coordinate": {"lat": 65.021, "lon": 25.474},
        "radiusMeters": 800,
        "name": {"en": "Tuira", "fi": "Tuira", "fa": "تویرا"},
    },
    "oulu": {
        "id": "oulu",
        "scale": "city",
        "coordinate": {"lat": 65.012, "lon": 25.468},
        "radiusMeters": 12000,
        "name": {"en": "Oulu", "fi": "Oulu", "fa": "اولو"},
    },
    "finland": {
        "id": "finland",
        "scale": "finland",
        "coordinate": {"lat": 64.914, "lon": 26.067},
        "radiusMeters": 400000,
        "name": {"en": "Finland", "fi": "Suomi", "fa": "فنلاند"},
    },
    "iran": {
        "id": "iran",
        "scale": "world",
        "coordinate": {"lat": 32.427, "lon": 53.688},
        "radiusMeters": 1000000,
        "name": {"en": "Iran", "fi": "Iran", "fa": "ایران"},
    },
    "world": {
        "id": "world",
        "scale": "world",
        "coordinate": {"lat": 20.0, "lon": 0.0},
        "radiusMeters": 10000000,
        "name": {"en": "World", "fi": "Maailma", "fa": "جهان"},
    },
}


def geocode_place(place_name: str) -> Dict[str, Any]:
    """Map place name to canonical placeId, scale, coordinates, and radius."""
    key = place_name.lower().strip()
    if key in KNOWN_PLACES:
        return KNOWN_PLACES[key]

    # Substring search
    for k, v in KNOWN_PLACES.items():
        if k in key or key in k:
            return v

    # Fallback to general city scale
    return {
        "id": key.replace(" ", "-"),
        "scale": "city",
        "coordinate": {"lat": 65.012, "lon": 25.468},
        "radiusMeters": 5000,
        "name": {"en": place_name, "fi": place_name},
    }
