from __future__ import annotations

from enum import StrEnum

from .models import Action, Classification, Relationship, Decision


class DecisionMode(StrEnum):
    SUGGEST = "suggest"
    MANUAL = "manual"
    AUTO = "auto"
    DISABLED = "disabled"


class DecisionEngine:
    def __init__(self, *, unrelated_threshold: float = 0.90):
        self.unrelated_threshold = unrelated_threshold

    def decide(self, classification: Classification, mode: DecisionMode) -> Decision:
        if mode in {DecisionMode.DISABLED, DecisionMode.MANUAL}:
            return Decision(Action.CONTINUE, classification, False, mode.value)
        if classification.relationship in {Relationship.SAME, Relationship.RELATED}:
            return Decision(Action.CONTINUE, classification, False, mode.value)
        if classification.relationship == Relationship.UNRELATED and classification.confidence >= self.unrelated_threshold:
            return Decision(Action.SUGGEST_BRANCH, classification, mode != DecisionMode.AUTO, mode.value)
        return Decision(Action.ASK, classification, True, mode.value)
