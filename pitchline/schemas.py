"""Pydantic v2 contracts for every LLM call.

No LLM call in Pitchline returns free text. Each call names a schema here; the client
forces the model to emit exactly that shape and validates before the value is allowed
anywhere near the database. Bounds come from ``rules.py``, so tightening a rule tightens
model validation too.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pitchline.rules import (
    FIT_DIMENSION_WEIGHTS,
    NOVELTY_SCALE_MAX,
    NOVELTY_SCALE_MIN,
    SCORE_SCALE_MAX,
    SCORE_SCALE_MIN,
)

__all__ = [
    "DimensionScore",
    "FitScoreResult",
    "NoveltyVerdict",
    "HookProposal",
    "VariantSelection",
    "ReplyClassification",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DimensionScore(_Strict):
    """One of the six R1.2 dimensions: a score, a one-line rationale, and citations."""

    score: int = Field(ge=SCORE_SCALE_MIN, le=SCORE_SCALE_MAX)
    rationale: str = Field(min_length=3, max_length=300)
    evidence_ids: list[int] = Field(default_factory=list)


class FitScoreResult(_Strict):
    """R1.2 — the structured verdict of the targeting judge."""

    stage: DimensionScore
    sector: DimensionScore
    check_size: DimensionScore
    geography: DimensionScore
    thesis_recency: DimensionScore
    portfolio_conflict: DimensionScore
    #: R1.5 — portfolio companies that directly compete with the startup.
    conflict_companies: list[str] = Field(default_factory=list)
    summary: str = Field(default="", max_length=400)

    @property
    def dimensions(self) -> dict[str, DimensionScore]:
        return {
            "stage": self.stage,
            "sector": self.sector,
            "check_size": self.check_size,
            "geography": self.geography,
            "thesis_recency": self.thesis_recency,
            "portfolio_conflict": self.portfolio_conflict,
        }

    @property
    def composite(self) -> float:
        """R1.2 — weighted mean. Weights come from the rules file, not from here."""
        dims = self.dimensions
        total = sum(FIT_DIMENSION_WEIGHTS.get(name, 0.0) for name in dims)
        if not total:  # pragma: no cover - rules file would have to be empty
            return round(sum(d.score for d in dims.values()) / len(dims), 3)
        weighted = sum(d.score * FIT_DIMENSION_WEIGHTS.get(name, 0.0) for name, d in dims.items())
        return round(weighted / total, 3)

    @property
    def evidence_ids(self) -> list[int]:
        seen: list[int] = []
        for dim in self.dimensions.values():
            for eid in dim.evidence_ids:
                if eid not in seen:
                    seen.append(eid)
        return seen

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflict_companies)


class NoveltyVerdict(_Strict):
    """R2.4 — the source's own test, scored: "I've seen ten of these this week"."""

    score: float = Field(ge=NOVELTY_SCALE_MIN, le=NOVELTY_SCALE_MAX)
    reason: str = Field(min_length=3, max_length=400)
    cliches: list[str] = Field(default_factory=list)
    resembles: str = Field(default="", max_length=200)


class HookProposal(_Strict):
    """R2.6 — the single personalization hook, bound to one stored evidence snippet."""

    hook_text: str = Field(min_length=10, max_length=300)
    evidence_id: int
    rationale: str = Field(default="", max_length=300)

    @field_validator("hook_text")
    @classmethod
    def _single_sentence(cls, value: str) -> str:
        if value.count(".") > 2:
            raise ValueError("the personalization hook is one sentence, not a paragraph")
        return value


class VariantSelection(_Strict):
    """R2.2 — the model selects founder-authored slot text; it never writes it."""

    credibility_key: str
    problem_key: str
    approach_key: str
    ask_key: str
    rationale: str = Field(default="", max_length=400)


class ReplyClassification(_Strict):
    """Module 7 — the CRM state transition depends on getting this right."""

    label: Literal[
        "interested",
        "deck_request",
        "not_now",
        "pass",
        "auto_reply",
        "ooo",
        "bounce",
        "unsubscribe",
        "unknown",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=300)
