from __future__ import annotations

import re
from typing import Protocol

from .models import Classification, Relationship


class Classifier(Protocol):
    def classify(self, *, current_topic: str, current_summary: str, prompt: str) -> Classification: ...


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", text.lower()) if len(token) > 1}


def _topic_label(prompt: str, limit: int = 80) -> str:
    first_sentence = re.split(r"[\r\n.!?。！？]+", prompt.strip(), maxsplit=1)[0].strip()
    concise = re.sub(
        r"^(?:(?:please\s+)?(?:open|start|create)\s+(?:a\s+)?(?:new\s+)?(?:unrelated\s+)?topic\s*(?:about|on)?\s*|新开(?:一个)?(?:无关的?)?(?:话题|主题)[：:]?\s*)",
        "",
        first_sentence,
        flags=re.I,
    ).strip(" :-：")
    label = concise or first_sentence or prompt.strip()
    return label[:limit].rstrip()


class HeuristicClassifier:
    """Conservative offline fallback; use an LLM provider for semantic classification."""

    def classify(self, *, current_topic: str, current_summary: str, prompt: str) -> Classification:
        prompt_tokens = _tokens(prompt)
        context_tokens = _tokens(f"{current_topic} {current_summary}")
        overlap = len(prompt_tokens & context_tokens) / max(len(prompt_tokens), 1)
        explicit_continue = bool(re.search(r"继续|刚才|上面|same topic|continue", prompt, re.I))
        explicit_new = bool(re.search(r"新开|另开|独立|new topic|new branch|unrelated", prompt, re.I))

        if explicit_continue:
            return Classification(
                current_topic,
                _topic_label(prompt),
                Relationship.SAME,
                0.92,
                "检测到用户明确要求继续当前话题",
                True,
            )
        if overlap >= 0.45:
            confidence = 0.92 if explicit_continue else min(0.88, 0.55 + overlap)
            return Classification(
                current_topic,
                _topic_label(prompt),
                Relationship.SAME,
                confidence,
                "新输入与当前话题摘要有较强词汇重叠",
                True,
            )
        if explicit_new:
            return Classification(
                current_topic,
                _topic_label(prompt),
                Relationship.UNRELATED,
                0.96,
                "检测到用户明确要求开启独立话题",
                False,
            )
        return Classification(
            current_topic,
            _topic_label(prompt),
            Relationship.UNCERTAIN,
            0.45,
            "离线 fallback 无法可靠判断语义关系，建议由用户确认",
            True,
        )
