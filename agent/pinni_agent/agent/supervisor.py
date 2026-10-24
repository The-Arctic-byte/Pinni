"""LangChain Supervisor (orchestrator) implementing Track B B3 tasks.

Orchestrates work across:
  1. Find: news by preferences, by location, by recommendation, by place (city, country).
  2. Gather by profile: add sources from a person's profile (e.g. PSOAS tenant -> PSOAS site, university student -> campus news).
  3. Select: deduplicate, merge, classify topic / need / scale / risk, drop irrelevant items with a logged reason.
  4. Explain: write the explanation sections and context cards per language.
  5. Translate + check: translate, back-translate, compare with sources, set tier.
  6. Route to human: anything red-risk (residence, health, money, work, safety) and all community reports go to editor queue.
  7. Distribute: pick target readers, trigger notifications.
  8. Moderate community: triage reports, apply hard filters from rejects.
  9. Suggest channels: from similar people in the knowledge graph.
  10. Audit: every step writes to an append-only log that the admin page can show.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..config import Settings, default_settings
from ..knowledge.graph import KnowledgeGraph
from ..knowledge.vector_store import VectorStore
from ..llm import OllamaLLM
from ..store import Store
from .skills import SupervisorSkills
from .trace import SupervisorTrace


class Supervisor:
    """The central orchestrator agent for Pinni Track B."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        store: Optional[Store] = None,
        vector_store: Optional[VectorStore] = None,
        graph: Optional[KnowledgeGraph] = None,
        llm: Optional[OllamaLLM] = None,
    ):
        self.s = settings or default_settings
        self.store = store or Store(self.s)
        self.vector_store = vector_store or VectorStore(self.s)
        self.graph = graph or KnowledgeGraph(self.s)
        self.llm = llm or OllamaLLM(self.s)
        self.skills = SupervisorSkills(
            settings=self.s,
            store=self.store,
            vector_store=self.vector_store,
            graph=self.graph,
            llm=self.llm,
        )

    # 1. FIND
    def find(
        self,
        preferences: Optional[List[str]] = None,
        location: Optional[str] = None,
        place: Optional[str] = None,
        category: Optional[str] = None,
        scale: Optional[str] = None,
        limit: int = 10,
        trace: Optional[SupervisorTrace] = None,
    ) -> List[Dict[str, Any]]:
        tr = trace or SupervisorTrace(self.store)
        tr.step("find", f"Finding news for location={location or place}, category={category}, preferences={preferences}")
        res = self.skills.find_news(
            preferences=preferences,
            location=location,
            place=place,
            category=category,
            scale=scale,
            limit=limit,
        )
        return res.data.get("hits", [])

    # 2. GATHER BY PROFILE
    def gather_by_profile(
        self,
        user_id: str,
        trace: Optional[SupervisorTrace] = None,
    ) -> List[Dict[str, Any]]:
        tr = trace or SupervisorTrace(self.store)
        tr.step("gather", f"Gathering personalized news sources for user '{user_id}' based on profile")
        res = self.skills.gather_by_profile(user_id)
        items = res.data.get("items", [])
        tr.step("gather", f"Gathered {len(items)} source articles for user '{user_id}'")
        return items

    # 3. SELECT
    def select(
        self,
        raw_items: List[Dict[str, Any]],
        trace: Optional[SupervisorTrace] = None,
    ) -> List[Dict[str, Any]]:
        tr = trace or SupervisorTrace(self.store)
        selected_items = []
        seen_titles = set()

        for item in raw_items:
            title_key = item.get("title", "").strip().lower()
            if title_key in seen_titles:
                tr.step("skip", f"Deduplicated duplicate story: '{item.get('title')}'")
                continue
            seen_titles.add(title_key)

            res = self.skills.select_and_classify(item)
            if res.dropped:
                tr.step("skip", f"Dropped irrelevant story: {res.drop_reason}")
            else:
                data = res.data
                tr.step(
                    "select",
                    f"Selected story '{data.get('title')}' classified as {data.get('category')} (risk: {data.get('risk')})",
                )
                selected_items.append(data)

        return selected_items

    # 4. EXPLAIN
    def explain(
        self,
        selected_item: Dict[str, Any],
        trace: Optional[SupervisorTrace] = None,
    ) -> Dict[str, Any]:
        tr = trace or SupervisorTrace(self.store)
        title = selected_item.get("title", "")
        tr.step("explain", f"Writing structured explanation sections and context card for '{title}'")
        res = self.skills.explain_story(selected_item)
        return res.data.get("explanation", {})

    # 5. TRANSLATE + CHECK
    def translate_and_check(
        self,
        title: str,
        for_you: str,
        target_languages: Optional[List[str]] = None,
        trace: Optional[SupervisorTrace] = None,
    ) -> Dict[str, Any]:
        tr = trace or SupervisorTrace(self.store)
        langs = target_languages or ["fi", "fa", "sv"]
        tr.step("translate", f"Translating story into {langs} and performing back-translation check")
        res = self.skills.translate_and_check(title=title, for_you=for_you, target_languages=langs)
        tr.step("check", "Checked translations against source; validated accuracy and assigned tiers")
        return res.data

    # 6. ROUTE TO HUMAN
    def route_to_human(
        self,
        story_or_report_id: str,
        kind: str,
        risk: str,
        trail: Optional[List[Dict[str, Any]]] = None,
        extra: Optional[Dict[str, Any]] = None,
        trace: Optional[SupervisorTrace] = None,
    ) -> Dict[str, Any]:
        tr = trace or SupervisorTrace(self.store)
        tr.step(
            "route",
            f"Routing {kind} '{story_or_report_id}' with {risk} risk to editor review queue",
            story_id=story_or_report_id if "story" in kind.lower() or kind == "agentDraft" else None,
            report_id=story_or_report_id if "report" in kind.lower() else None,
        )
        res = self.skills.route_to_human(
            story_or_report_id=story_or_report_id,
            kind=kind,
            risk=risk,
            trail=trail or tr.get_trail(),
            extra=extra,
        )
        return res.data

    # 7. DISTRIBUTE
    def distribute(
        self,
        story: Dict[str, Any],
        trace: Optional[SupervisorTrace] = None,
    ) -> List[Dict[str, Any]]:
        tr = trace or SupervisorTrace(self.store)
        sid = story.get("id", "")
        tr.step("distribute", f"Picking target readers and triggering notifications for story '{sid}'", story_id=sid)
        res = self.skills.distribute_story(story)
        readers = res.data.get("targetReaders", [])
        tr.step("distribute", f"Dispatched notifications to {len(readers)} matching readers", story_id=sid)
        return readers

    # 8. MODERATE COMMUNITY
    def moderate_community(
        self,
        report: Dict[str, Any],
        trace: Optional[SupervisorTrace] = None,
    ) -> Dict[str, Any]:
        tr = trace or SupervisorTrace(self.store)
        rid = report.get("id", "rep-unknown")
        tr.step("moderate", f"Triaging community report '{rid}'", report_id=rid)
        res = self.skills.moderate_community(report)
        return res.data

    # 9. SUGGEST CHANNELS
    def suggest_channels(
        self,
        user_id: str,
        limit: int = 5,
        trace: Optional[SupervisorTrace] = None,
    ) -> List[Dict[str, Any]]:
        tr = trace or SupervisorTrace(self.store)
        tr.step("rank", f"Querying Knowledge Graph for similar people to suggest channels for '{user_id}'")
        res = self.skills.suggest_channels(user_id=user_id, limit=limit)
        return res.data.get("suggestions", [])

    # 10. AUDIT
    def audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.store.list_audit_log(limit=limit)

    # ---- FULL PIPELINE EXECUTION ----
    def process_incoming_news(
        self,
        raw_items: List[Dict[str, Any]],
        auto_publish_non_red: bool = False,
    ) -> List[Dict[str, Any]]:
        """End-to-end orchestration pipeline:

        Find/Gather -> Select -> Explain -> Translate + Check -> Route (if red) -> Distribute
        """
        trace = SupervisorTrace(self.store)
        trace.step("gather", f"Ingesting batch of {len(raw_items)} incoming items")

        # Select & Classify
        selected = self.select(raw_items, trace=trace)
        results = []

        for item in selected:
            title_en = item.get("title", "")
            sid = item.get("id") or hashlib.md5(title_en.encode()).hexdigest()[:12]

            # Explain
            explanation = self.explain(item, trace=trace)
            for_you_en = explanation.get("forYou", {}).get("en", "")

            # Translate & Check
            trans_res = self.translate_and_check(title=title_en, for_you=for_you_en, trace=trace)
            titles = {lang: t_info["title"] for lang, t_info in trans_res.get("translations", {}).items()}
            labels = {lang: titles[lang][:15] for lang in titles}
            tiers = trans_res.get("tiers", [])

            # Build Full Story model
            now_iso = datetime.now(timezone.utc).isoformat()
            risk = item.get("risk", "none")
            story = {
                "id": sid,
                "status": "draft",
                "origin": "agent",
                "scale": item.get("scale", "city"),
                "placeId": item.get("placeId", "oulu"),
                "location": item.get("location"),
                "category": item.get("category", "cityLife"),
                "tags": item.get("tags", []),
                "needs": item.get("needs", ["information"]),
                "risk": risk,
                "isOpinion": False,
                "importance": item.get("importance", 0.6),
                "affects": item.get("affects", []),
                "label": labels,
                "title": titles,
                "explanation": explanation,
                "sources": [{"name": item.get("source", "Web"), "url": item.get("url"), "publishedAt": now_iso}],
                "translations": tiers,
                "createdAt": now_iso,
                "updatedAt": now_iso,
            }

            # Save in vector store & graph & SQLite
            self.store.save_story(story)
            self.vector_store.add_story(story)
            self.graph.record_story(story)

            # Route to human review if red-risk
            if risk == "red":
                self.route_to_human(
                    story_or_report_id=sid,
                    kind="agentDraft",
                    risk="red",
                    trail=trace.get_trail(),
                    extra={"title": titles},
                    trace=trace,
                )
            elif auto_publish_non_red:
                story["status"] = "published"
                story["publishedAt"] = now_iso
                story["verification"] = {"verifiedBy": "agent:supervisor", "verifiedAt": now_iso}
                self.store.save_story(story)
                trace.step("publish", f"Published non-red-risk story '{sid}'", story_id=sid)
                self.distribute(story, trace=trace)

            results.append(story)

        return results
