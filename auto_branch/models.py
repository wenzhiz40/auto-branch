from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Relationship(StrEnum):
    SAME = "same"
    RELATED = "related"
    UNRELATED = "unrelated"
    UNCERTAIN = "uncertain"


class Action(StrEnum):
    CONTINUE = "continue"
    SUGGEST_BRANCH = "suggest_branch"
    ASK = "ask"


class BranchStatus(StrEnum):
    ACTIVE = "active"
    DELIVERY_UNKNOWN = "delivery_unknown"
    DELIVERY_FAILED = "delivery_failed"
    ARCHIVED = "archived"
    ADOPTED = "adopted"
    REJOINED = "rejoined"


@dataclass(frozen=True)
class Classification:
    current_topic: str
    new_topic: str
    relationship: Relationship
    confidence: float
    reason: str
    inherit_context: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "current_topic": self.current_topic,
            "new_topic": self.new_topic,
            "relationship": self.relationship.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "inherit_context": self.inherit_context,
        }


@dataclass(frozen=True)
class Decision:
    action: Action
    classification: Classification
    needs_confirmation: bool
    mode: str
    operation_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "needs_confirmation": self.needs_confirmation,
            "mode": self.mode,
            "operation_id": self.operation_id,
            "classification": self.classification.as_dict(),
        }
