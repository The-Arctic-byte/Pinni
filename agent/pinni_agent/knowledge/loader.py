"""Seed loader: populates Store, VectorStore and KnowledgeGraph from contract/mock/."""
import json
from pathlib import Path
from typing import Optional

from ..config import Settings, default_settings
from ..store import Store
from .graph import KnowledgeGraph
from .vector_store import VectorStore


def load_mock_data(
    settings: Optional[Settings] = None,
    store: Optional[Store] = None,
    vector_store: Optional[VectorStore] = None,
    graph: Optional[KnowledgeGraph] = None,
) -> None:
    s = settings or default_settings
    st = store or Store(s)
    vs = vector_store or VectorStore(s)
    kg = graph or KnowledgeGraph(s)

    mock_dir = s.contract_dir / "mock"
    if not mock_dir.exists():
        return

    # 1. Stories
    stories_file = mock_dir / "stories.json"
    if stories_file.exists():
        stories = json.loads(stories_file.read_text(encoding="utf-8"))
        for item in stories:
            st.save_story(item)
            vs.add_story(item)
            kg.record_story(item)

    # 2. Profiles
    profiles_file = mock_dir / "profiles.json"
    if profiles_file.exists():
        profiles = json.loads(profiles_file.read_text(encoding="utf-8"))
        for prof in profiles:
            st.save_profile(prof)
            kg.record_profile(prof)

    # 3. Events
    events_file = mock_dir / "events.json"
    if events_file.exists():
        events = json.loads(events_file.read_text(encoding="utf-8"))
        for ev in events:
            st.save_event(ev)
            kg.record_event(ev)

    # 4. Channels
    channels_file = mock_dir / "channels.json"
    if channels_file.exists():
        channels = json.loads(channels_file.read_text(encoding="utf-8"))
        for ch in channels:
            kg.merge_node(f"channel:{ch['id']}", "Channel", ch)

    # 5. Places
    places_file = mock_dir / "places.json"
    if places_file.exists():
        places = json.loads(places_file.read_text(encoding="utf-8"))
        for pl in places:
            kg.merge_node(f"place:{pl['id']}", "Place", pl)
