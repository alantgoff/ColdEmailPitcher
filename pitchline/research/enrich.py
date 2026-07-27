"""Enrichment: run scrapers for an investor and file the results as evidence.

Cache-first by construction. A URL fetched inside its TTL is not re-fetched (R1.3) — the
cache hit is recorded as an event so the operator can see how much research was reused
rather than re-bought.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from pitchline import events
from pitchline.ingest.scrapers import ScrapeResult, available_scrapers
from pitchline.models import EventKind, Firm, Investor
from pitchline.research.store import needs_refetch, research_coverage, store_evidence
from pitchline.rules import EVIDENCE_CACHE_TTL_DAYS


@dataclass
class EnrichReport:
    investors_processed: int = 0
    snippets_stored: int = 0
    cache_hits: int = 0
    fetch_errors: list[str] = field(default_factory=list)
    now_meeting_floor: int = 0

    def summary(self) -> str:
        return (
            f"{self.investors_processed} investors enriched, {self.snippets_stored} snippets "
            f"stored, {self.cache_hits} cache hits, {self.now_meeting_floor} now meet the "
            f"R1.3 research floor"
        )


def enrich_investor(
    session: Session,
    investor: Investor,
    *,
    scrapers: dict | None = None,
    include_form_d: bool = True,
    report: EnrichReport | None = None,
) -> EnrichReport:
    """Fetch public sources for one investor and store what comes back as evidence."""
    report = report or EnrichReport()
    report.investors_processed += 1
    registry = scrapers if scrapers is not None else available_scrapers()

    firm = session.get(Firm, investor.firm_id) if investor.firm_id else None
    website = investor.personal_site or (firm.website if firm else None)

    results: list[ScrapeResult] = []
    if website and "fund_site" in registry:
        if needs_refetch(session, website):
            try:
                results.extend(registry["fund_site"].scrape(website=website))
            except Exception as exc:
                report.fetch_errors.append(f"{investor.full_name}: fund_site: {exc}")
        else:
            report.cache_hits += 1
            events.record(
                session,
                EventKind.EVIDENCE_CACHE_HIT,
                entity_type="investor",
                entity_id=investor.id,
                summary=f"{website} is inside its {EVIDENCE_CACHE_TTL_DAYS}-day TTL",
                flush=False,
            )

    if include_form_d and firm and "sec_form_d" in registry:
        try:
            results.extend(registry["sec_form_d"].scrape(firm_name=firm.name))
        except Exception as exc:
            report.fetch_errors.append(f"{investor.full_name}: sec_form_d: {exc}")

    for result in results:
        stored = store_evidence(
            session,
            investor=investor,
            raw_text=result.text,
            area=result.area,
            kind=result.kind,
            title=result.title,
            url=result.url,
            published_at=result.published_at,
            source=result.source_type,
            entities=result.entities,
            retrieval_query="enrich",
        )
        if stored:
            report.snippets_stored += 1

    if research_coverage(session, investor.id).meets_floor:  # type: ignore[arg-type]
        report.now_meeting_floor += 1
    return report


def enrich_campaign(
    session: Session,
    *,
    investor_ids: list[int] | None = None,
    limit: int | None = None,
    include_form_d: bool = True,
) -> EnrichReport:
    """Enrich a shortlist. Only shortlisted investors are researched — research is the
    expensive step, so it runs after targeting has narrowed the universe."""
    statement = select(Investor).where(Investor.quarantined == False)  # noqa: E712
    if investor_ids:
        statement = statement.where(Investor.id.in_(investor_ids))  # type: ignore[attr-defined]
    investors = list(session.exec(statement))[: limit or None]

    report = EnrichReport()
    for investor in investors:
        enrich_investor(session, investor, include_form_d=include_form_d, report=report)
    session.flush()
    events.record(
        session,
        EventKind.EVIDENCE_STORED,
        entity_type="enrichment",
        summary=report.summary(),
        payload={"errors": report.fetch_errors[:20]},
    )
    return report
