"""Keep the derived stores (knowledge graph, vector store) in step with SQLite.

SQLite is written first and is the source of truth. If a derived store is down, the request still
succeeds and the failure is logged; restarting with an empty graph or index rebuilds it."""

import logging
import sqlite3

from fastapi import Request

from . import graph as kg

log = logging.getLogger("pinni.stores")


def _safely(what: str, fn, *args) -> None:
    try:
        fn(*args)
    except Exception:  # noqa: BLE001
        log.exception("Could not update %s", what)


def graph(request: Request) -> kg.Graph:
    return request.app.state.graph


def vectors(request: Request):
    return request.app.state.vectors


def story_changed(request: Request, story: dict) -> None:
    _safely("graph", graph(request).upsert_story, story)
    _safely("vector store", vectors(request).index, [story])


def events_added(request: Request, events: list[dict]) -> None:
    g = graph(request)
    for e in events:
        _safely("graph", kg.record_event, g, e)


def profile_changed(request: Request, profile: dict) -> None:
    _safely("graph", graph(request).upsert_profile, profile)


def membership_changed(request: Request, user_id: str, channel_id: str, member: bool) -> None:
    _safely("graph", graph(request).set_member, user_id, channel_id, member)


def replay_user(request: Request, conn: sqlite3.Connection, user_id: str) -> None:
    _safely("graph", kg.replay_user, conn, graph(request), user_id)
