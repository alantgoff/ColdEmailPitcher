"""The evidence store: write-once snippets with provenance, TTL caching, and a floor.

R1.3 has three separate requirements and they are easy to conflate:

1. a *coverage floor* — portfolio, thesis and recent activity all present;
2. a *staleness limit* — evidence older than the window does not count as homework;
3. a *cache TTL* — a URL fetched inside the TTL is never re-fetched.

They are implemented as three distinct functions so a failure says which one failed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence

from sqlmodel import Session, select

from pitchline import events, textutil as tu
from pitchline.models import Evidence, EvidenceArea, EvidenceKind, EventKind, Investor, SourceType
from pitchline.rules import (
    EVIDENCE_CACHE_TTL_DAYS,
    MAX_EVIDENCE_AGE_DAYS,
    MIN_EVIDENCE_SNIPPETS,
    MIN_SNIPPETS_PER_REQUIRED_AREA,
    RECENT_ACTIVITY_MAX_AGE_DAYS,
    REQUIRED_EVIDENCE_AREAS,
)
from pitchline.timeutil import age_days, ensure_utc


def store_evidence(
    session: Session,
    *,
    investor: Investor | None,
    raw_text: str,
    area: EvidenceArea = EvidenceArea.OTHER,
    kind: EvidenceKind = EvidenceKind.OTHER,
    title: str | None = None,
    url: str | None = None,
    firm_id: int | None = None,
    published_at: datetime | None = None,
    source: SourceType = SourceType.PUBLIC_WRITING,
    source_detail: str | None = None,
    entities: Sequence[str] | None = None,
    retrieval_query: str | None = None,
    ttl_days: int = EVIDENCE_CACHE_TTL_DAYS,
) -> Evidence | None:
    """Store a snippet. Returns ``None`` if an identical snippet is already on file."""
    text = (raw_text or "").strip()
    if not text:
        return None
    digest = tu.content_hash(text)
    investor_id = investor.id if investor else None
    existing = session.exec(
        select(Evidence).where(
            Evidence.investor_id == investor_id, Evidence.content_hash == digest
        )
    ).first()
    if existing:
        return None

    evidence = Evidence(
        investor_id=investor_id,
        firm_id=firm_id if firm_id is not None else (investor.firm_id if investor else None),
        area=area,
        kind=kind,
        title=title,
        url=url,
        raw_text=text,
        excerpt=text[:400],
        content_hash=digest,
        published_at=published_at,
        ttl_days=ttl_days,
        entities=list(entities or []),
        source=source,
        source_url=url,
        source_detail=source_detail,
        retrieval_query=retrieval_query,
    )
    session.add(evidence)
    session.flush()
    events.record(
        session,
        EventKind.EVIDENCE_STORED,
        entity_type="evidence",
        entity_id=evidence.id,
        summary=f"{area.value}/{kind.value} for investor {investor_id}",
        payload={"url": url, "chars": len(text)},
        flush=False,
    )
    return evidence


def evidence_for(
    session: Session,
    investor_id: int,
    *,
    areas: Sequence[EvidenceArea] | None = None,
    fresh_only: bool = False,
    limit: int | None = None,
    include_firm: bool = True,
) -> list[Evidence]:
    """Evidence about this investor, including their fund's.

    R1.3 asks for "an investor's portfolio, fund thesis, and recent activity" — two of
    those three are properties of the *firm*, not the person. Counting only
    person-attached evidence would mean a partner at a fund whose thesis and portfolio are
    fully documented still reads as unresearched, which is not what the rule says.
    """
    statement = select(Evidence).where(Evidence.investor_id == investor_id)
    rows = list(session.exec(statement))
    if include_firm:
        investor = session.get(Investor, investor_id)
        if investor is not None and investor.firm_id is not None:
            firm_rows = session.exec(
                select(Evidence).where(
                    Evidence.firm_id == investor.firm_id,
                    Evidence.investor_id == None,  # noqa: E711 — SQL IS NULL
                )
            ).all()
            seen = {r.content_hash for r in rows}
            rows.extend(r for r in firm_rows if r.content_hash not in seen)
    if areas:
        wanted = set(areas)
        rows = [r for r in rows if r.area in wanted]
    if fresh_only:
        rows = [row for row in rows if within_staleness_limit(row)]
    rows.sort(key=_sort_key, reverse=True)
    return rows[:limit] if limit else rows


def _sort_key(row: Evidence) -> datetime:
    return ensure_utc(row.published_at or row.fetched_at) or ensure_utc(row.fetched_at)  # type: ignore[return-value]


def is_fresh(evidence: Evidence, *, now: datetime | None = None) -> bool:
    """R1.3 cache TTL — inside the TTL a re-fetch is forbidden."""
    return age_days(evidence.fetched_at, now=now) < evidence.ttl_days


def within_staleness_limit(evidence: Evidence, *, now: datetime | None = None) -> bool:
    """R1.3 — evidence past the staleness window does not count toward the floor."""
    reference = evidence.published_at or evidence.fetched_at
    limit = (
        RECENT_ACTIVITY_MAX_AGE_DAYS
        if evidence.area is EvidenceArea.RECENT_ACTIVITY
        else MAX_EVIDENCE_AGE_DAYS
    )
    return age_days(reference, now=now) <= limit


def needs_refetch(session: Session, url: str, *, now: datetime | None = None) -> bool:
    """R1.3 — never re-fetch a URL inside its TTL."""
    if not url:
        return True
    cached = session.exec(select(Evidence).where(Evidence.url == url)).all()
    return not any(is_fresh(row, now=now) for row in cached)


@dataclass
class ResearchCoverage:
    """Whether an investor has had the thirty minutes of homework done (R1.3)."""

    investor_id: int
    total: int = 0
    by_area: dict[str, int] = field(default_factory=dict)
    missing_areas: list[str] = field(default_factory=list)
    meets_floor: bool = False

    def reason(self) -> str:
        if self.meets_floor:
            return "research floor met"
        problems = []
        if self.missing_areas:
            problems.append(f"missing evidence for: {', '.join(self.missing_areas)}")
        if self.total < MIN_EVIDENCE_SNIPPETS:
            problems.append(f"{self.total}/{MIN_EVIDENCE_SNIPPETS} fresh snippets")
        return "; ".join(problems) or "research floor not met"


def research_coverage(
    session: Session, investor_id: int, *, now: datetime | None = None
) -> ResearchCoverage:
    rows = [
        row
        for row in evidence_for(session, investor_id)
        if within_staleness_limit(row, now=now)
    ]
    by_area: dict[str, int] = {}
    for row in rows:
        by_area[row.area.value] = by_area.get(row.area.value, 0) + 1
    missing = [
        area
        for area in REQUIRED_EVIDENCE_AREAS
        if by_area.get(area, 0) < MIN_SNIPPETS_PER_REQUIRED_AREA
    ]
    return ResearchCoverage(
        investor_id=investor_id,
        total=len(rows),
        by_area=by_area,
        missing_areas=missing,
        meets_floor=not missing and len(rows) >= MIN_EVIDENCE_SNIPPETS,
    )


def evidence_payload(
    session: Session, investor_id: int, *, limit: int = 20, fresh_only: bool = True
) -> list[dict[str, Any]]:
    """Serialise evidence for an LLM call. Includes ids so the model can cite them."""
    return [
        {
            "id": row.id,
            "area": row.area.value,
            "kind": row.kind.value,
            "title": row.title,
            "url": row.url,
            "raw_text": row.raw_text[:1500],
            "entities": row.entities,
            "published_at": (ensure_utc(row.published_at).isoformat() if row.published_at else None),
            "fetched_at": (ensure_utc(row.fetched_at).isoformat() if row.fetched_at else None),
        }
        for row in evidence_for(session, investor_id, fresh_only=fresh_only, limit=limit)
    ]
