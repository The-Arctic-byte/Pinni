"""Audit logging and trace tracking for supervisor orchestrator steps."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..store import Store
from ..types import AuditEntry, AuditStep


class SupervisorTrace:
    """Tracks each step in an agent run and writes to the store audit log."""

    def __init__(self, store: Optional[Store] = None, actor: str = "agent:supervisor"):
        self.store = store
        self.actor = actor
        self.entries: List[AuditEntry] = []

    def step(
        self,
        step_name: AuditStep,
        message: str,
        story_id: Optional[str] = None,
        report_id: Optional[str] = None,
    ) -> AuditEntry:
        now = datetime.now(timezone.utc).isoformat()
        entry = AuditEntry(
            at=now,
            actor=self.actor,
            step=step_name,
            message=message,
            storyId=story_id,
            reportId=report_id,
        )
        self.entries.append(entry)

        if self.store:
            self.store.log_audit(entry.model_dump())

        return entry

    def get_trail(self) -> List[Dict[str, Any]]:
        return [e.model_dump() for e in self.entries]
