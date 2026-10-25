"""Live news for the agent: real RSS feeds, read at each newsroom round (pinni/newsroom.py).

The agent's own sources (agent/pinni_agent/mcp/tools/sources.py) are fixed samples whose links do
not exist. With PINNI_AGENT_LIVE on, the newsroom reads these feeds instead and the agent writes up
real items, each linking to the article it came from. A feed that cannot be read is left out of
that round; if none can be read, the round falls back to the samples.

Only feeds in English are read: the agent writes English and offline it cannot translate, so a
Finnish article would end up in the English slot."""

import html
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

log = logging.getLogger("pinni.feeds")


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    # Where an item that names no place we know belongs.
    place_id: str
    # Older items are not news any more (feeds keep some for years).
    max_age: timedelta = timedelta(days=7)
    # Service pages some feeds list next to their news.
    skip_links: tuple[str, ...] = ()


FEEDS = [
    Feed("Yle News", "https://feeds.yle.fi/uutiset/v1/recent.rss?publisherIds=YLE_NEWS", "finland"),
    # Student housing in Oulu; posts a few times a month.
    Feed("PSOAS", "https://psoas.fi/en/feed/", "oulu", max_age=timedelta(days=45), skip_links=("/fault-reports/",)),
]
TIMEOUT = 10
MAX_ITEMS_PER_FEED = 25

# First match wins: the more specific topics come first. English words, matched at word starts.
CATEGORY_WORDS = [
    ("safety", ["police", "crime", "fire", "accident", "shooting", "stabbing", "rescue", "missing person", "storm warning"]),
    ("health", ["health", "hospital", "doctor", "vaccin", "disease", "flu", "covid", "patient", "medicine"]),
    ("housing", ["rent", "housing", "apartment", "tenant", "landlord", "psoas"]),
    ("transport", ["train", "bus", "tram", "traffic", "road", "airport", "flight", "finnair", "vr ", "taxi", "railway", "cycling"]),
    ("education", ["universit", "school", "student", "teacher", "education", "pupil"]),
    ("work", ["job", "unemploy", "strike", "union", "layoff", "worker", "employ", "wage", "salar"]),
    ("economy", ["econom", "price", "inflation", "bank", "budget", "tax", "market", "compan", "business", "euro"]),
    ("politics", ["government", "minister", "parliament", "election", "party", "president", "orpo", "eduskunta"]),
    ("environment", ["climate", "weather", "snow", "nature", "forest", "emission", "environment", "northern lights"]),
    ("technology", ["tech", "data cent", "ai ", "software", "internet", "digital"]),
    ("culture", ["music", "film", "art", "festival", "museum", "book", "theatre", "concert", "culture"]),
    ("sport", ["sport", "football", "hockey", "olympic", "match", "championship", "athlet"]),
    ("world", ["ukraine", "russia", "nato", "eu ", "european union", "sweden", "estonia", "war", "united states", "china"]),
    ("shopping", ["shop", "store", "grocer", "retail", "lidl", "k-market", "s-market"]),
    ("society", ["immigra", "migri", "residence permit", "refugee", "integration", "church", "social"]),
]
TAG = re.compile(r"<[^>]+>")


def _text(item: ET.Element, tag: str) -> str:
    return html.unescape(TAG.sub(" ", item.findtext(tag) or "")).strip()


def category_of(text: str) -> str:
    t = f" {text.lower()} "
    for category, words in CATEGORY_WORDS:
        if any(re.search(r"\b" + re.escape(w), t) for w in words):
            return category
    return "society"


def place_of(text: str, places: list[dict], default: str) -> str:
    """The most local place the item names (an area before its city before the country)."""
    order = {"area": 0, "city": 1, "region": 2, "country": 3, "world": 4}
    found = []
    for p in places:
        names = {n for n in p.get("name", {}).values() if n and len(n) > 3}
        if any(re.search(r"\b" + re.escape(n) + r"\b", text, re.IGNORECASE) for n in names):
            found.append(p)
    if not found:
        return default
    return min(found, key=lambda p: order.get(p["kind"], 9))["id"]


def parse(feed: Feed, body: bytes, places: list[dict], now: datetime | None = None) -> list[dict]:
    """RSS 2.0 items as the agent's source items (see agent/pinni_agent/mcp/tools/sources.py)."""
    now = now or datetime.now(timezone.utc)
    out = []
    for item in ET.fromstring(body).iter("item"):
        title, link = _text(item, "title"), (item.findtext("link") or "").strip()
        if not title or not link or any(part in link for part in feed.skip_links):
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if now - published > feed.max_age:
            continue
        description = _text(item, "description")
        text = f"{title}. {description}"
        out.append({
            "title": title,
            "description": description,
            "url": link,
            "source": feed.name,
            "category": category_of(text),
            "place": place_of(text, places, feed.place_id),
            "publishedAt": published.isoformat(timespec="seconds"),
        })
        if len(out) == MAX_ITEMS_PER_FEED:
            break
    return out


def read_all(places: list[dict], feeds: list[Feed] = FEEDS) -> list[dict]:
    items: list[dict] = []
    for feed in feeds:
        try:
            response = httpx.get(feed.url, timeout=TIMEOUT, follow_redirects=True,
                                 headers={"User-Agent": "Pinni newsroom (local news for Oulu)"})
            response.raise_for_status()
            got = parse(feed, response.content, places)
        except Exception as err:  # noqa: BLE001  (a dead feed must not stop the round)
            log.warning("Could not read %s: %s", feed.name, err)
            continue
        log.info("Read %d items from %s", len(got), feed.name)
        items += got
    return items
