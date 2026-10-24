"""Source gathering MCP tools: Kaleva RSS, City of Oulu, PSOAS, University news, and preference-based web scrapers."""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from bs4 import BeautifulSoup

from ...knowledge.vector_store import VectorStore
from .geo import geocode_place

# Simulated / cached RSS and web sources for local development and offline stability
SAMPLE_KALEVA_ITEMS = [
    {
        "title": "Kiiminki empty apartment shooting investigation continues",
        "description": "Police arrest suspect after gunshots in residential Kiiminki flat.",
        "url": "https://www.kaleva.fi/kiiminki-ammuskelu-tutkinta",
        "source": "Kaleva",
        "category": "safety",
        "place": "kiiminki",
        "publishedAt": "2026-10-22T10:19:00+03:00",
    },
    {
        "title": "New Lidl store opening in Ideapark Ritaharju",
        "description": "Ritaharju commercial area welcomes major grocery store with extended Sunday hours.",
        "url": "https://www.kaleva.fi/ritaharju-lidl-avajaiset",
        "source": "Kaleva",
        "category": "shopping",
        "place": "ritaharju",
        "publishedAt": "2026-10-22T08:30:00+03:00",
    },
    {
        "title": "Oulu European Capital of Culture 2026 programme expands",
        "description": "Oulu 2026 unveils 50 new international cultural partnerships and volunteer events.",
        "url": "https://www.kaleva.fi/oulu-2026-kulttuuriohjelma",
        "source": "Kaleva",
        "category": "culture",
        "place": "oulu",
        "publishedAt": "2026-10-23T14:00:00+03:00",
    },
]

SAMPLE_CITY_OULU_ITEMS = [
    {
        "title": "City of Oulu budget decisions for public transit and winter cycling",
        "description": "Oulu City Council approves expanded winter bike lane plowing and subsidized youth bus passes.",
        "url": "https://www.ouka.fi/uutiset/talvipyoraily-joukkoliikenne-2026",
        "source": "City of Oulu",
        "category": "transport",
        "place": "oulu",
        "publishedAt": "2026-10-23T16:00:00+03:00",
    },
    {
        "title": "Autumn flu and COVID booster vaccination points open in Linnanmaa",
        "description": "Free walk-in vaccines for students and residents at Linnanmaa wellness station.",
        "url": "https://www.ouka.fi/terveys/rokotukset-linnanmaa",
        "source": "City of Oulu",
        "category": "health",
        "place": "linnanmaa",
        "publishedAt": "2026-10-24T09:00:00+03:00",
    },
]

SAMPLE_PSOAS_ITEMS = [
    {
        "title": "PSOAS heating adjustments and sauna booking updates for Linnanmaa tenants",
        "description": "Heating will turn to winter mode across all Linnanmaa apartments from November 1st. New digital laundry reservations active.",
        "url": "https://www.psoas.fi/ajankohtaista/talvilammitys-linnanmaa",
        "source": "PSOAS",
        "category": "housing",
        "place": "linnanmaa",
        "publishedAt": "2026-10-23T11:00:00+03:00",
    },
    {
        "title": "PSOAS student housing applications open for spring exchange semester",
        "description": "Exchange and degree students can submit housing applications for Linnanmaa and Tuira campuses.",
        "url": "https://www.psoas.fi/ajankohtaista/kevat-asuntohaku",
        "source": "PSOAS",
        "category": "housing",
        "place": "oulu",
        "publishedAt": "2026-10-21T10:00:00+03:00",
    },
]

SAMPLE_CAMPUS_ITEMS = [
    {
        "title": "University of Oulu career fair connects international students with northern tech firms",
        "description": "Over 80 companies participate in the autumn talent expo at Linnanmaa campus main hall.",
        "url": "https://www.oulu.fi/en/news/career-fair-linnanmaa-2026",
        "source": "University of Oulu",
        "category": "education",
        "place": "linnanmaa",
        "publishedAt": "2026-10-22T13:30:00+03:00",
    },
    {
        "title": "Campus restaurant opening hours and student discount lunch prices update",
        "description": "Kela-subsidized student meal prices adjusted slightly for the 2026-2027 academic year.",
        "url": "https://www.oulu.fi/fi/uutiset/opiskelijaruokailu-hinnat",
        "source": "University of Oulu",
        "category": "education",
        "place": "linnanmaa",
        "publishedAt": "2026-10-20T12:00:00+03:00",
    },
]


def gather_kaleva_rss(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Gather news from Kaleva RSS."""
    items = SAMPLE_KALEVA_ITEMS
    if category:
        items = [i for i in items if i["category"] == category]
    return items


def gather_city_of_oulu(topic: Optional[str] = None) -> List[Dict[str, Any]]:
    """Gather official city releases from City of Oulu."""
    items = SAMPLE_CITY_OULU_ITEMS
    if topic:
        items = [i for i in items if topic.lower() in i["title"].lower() or topic.lower() in i["description"].lower()]
    return items


def gather_psoas_news() -> List[Dict[str, Any]]:
    """Gather housing announcements from PSOAS student housing website."""
    return SAMPLE_PSOAS_ITEMS


def gather_university_news() -> List[Dict[str, Any]]:
    """Gather student and campus announcements from University of Oulu."""
    return SAMPLE_CAMPUS_ITEMS


def gather_web_by_preferences_and_location(
    preferences: Optional[List[str]] = None,
    location: Optional[str] = None,
    categories: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Gather articles matching user preferences, desired topics, and geographic location."""
    all_pool = SAMPLE_KALEVA_ITEMS + SAMPLE_CITY_OULU_ITEMS + SAMPLE_PSOAS_ITEMS + SAMPLE_CAMPUS_ITEMS
    results = []

    pref_tokens = set(p.lower() for p in (preferences or []))
    loc_key = location.lower() if location else None
    cat_set = set(categories or [])

    for item in all_pool:
        score = 0
        if loc_key and (loc_key in item["place"].lower() or item["place"].lower() in loc_key):
            score += 2
        if cat_set and item["category"] in cat_set:
            score += 2
        if pref_tokens:
            content = f"{item['title']} {item['description']}".lower()
            if any(t in content for t in pref_tokens):
                score += 3
        if score > 0 or (not pref_tokens and not loc_key and not cat_set):
            res_item = dict(item)
            res_item["relevance_match"] = score
            results.append(res_item)

    results.sort(key=lambda x: x.get("relevance_match", 0), reverse=True)
    return results


def gather_by_user_profile(
    profile: Dict[str, Any],
    vector_store: Optional[VectorStore] = None,
) -> List[Dict[str, Any]]:
    """Gather sources dynamically based on profile (e.g. PSOAS tenant -> PSOAS; student -> campus news).

    Stores gathered items in the Vector Database as requested in Track B contract.
    """
    gathered: List[Dict[str, Any]] = []

    # 1. Base city & news
    gathered.extend(gather_kaleva_rss())
    gathered.extend(gather_city_of_oulu())

    # 2. Check housing consent and provider
    housing = profile.get("housing") or {}
    if housing.get("provider") == "psoas" and housing.get("consent"):
        gathered.extend(gather_psoas_news())

    # 3. Check target groups (e.g. student -> university news)
    target_groups = profile.get("targetGroups") or []
    if "student" in target_groups:
        gathered.extend(gather_university_news())

    # 4. Filter or boost by location
    home_place = profile.get("homePlaceId")
    interests = profile.get("interests") or []
    wanted = profile.get("wantedNews") or []
    pref_items = gather_web_by_preferences_and_location(
        preferences=interests + wanted,
        location=home_place,
    )
    # Deduplicate by url
    seen_urls = {i["url"] for i in gathered}
    for pi in pref_items:
        if pi["url"] not in seen_urls:
            gathered.append(pi)
            seen_urls.add(pi["url"])

    # 5. Store gathered raw documents in Vector Database if provided
    if vector_store is not None:
        store_gathered_in_vector_db(gathered, vector_store)

    return gathered


def store_gathered_in_vector_db(
    items: List[Dict[str, Any]],
    vector_store: VectorStore,
) -> int:
    """Index gathered news items into the vector database."""
    count = 0
    for it in items:
        uid = f"doc:{hashlib.md5(it['url'].encode()).hexdigest()[:12]}"
        text = f"{it['title']}. {it['description']}"
        meta = {
            "type": "scraped_news",
            "source": it.get("source"),
            "category": it.get("category"),
            "placeId": it.get("place"),
            "url": it.get("url"),
            "publishedAt": it.get("publishedAt"),
        }
        vector_store.add_document(doc_id=uid, text=text, metadata=meta)
        count += 1
    return count
