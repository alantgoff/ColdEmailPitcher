"""Module 2 — enrichment and the evidence store.

The evidence table is the compressed "thirty minutes of homework" (R1.3) and the thing
that makes personalization verifiable (R2.6). Everything a draft asserts about an investor
resolves to a row here.
"""

from pitchline.research.store import (
    ResearchCoverage,
    evidence_for,
    evidence_payload,
    is_fresh,
    needs_refetch,
    research_coverage,
    store_evidence,
)
from pitchline.research.enrich import enrich_investor, enrich_campaign

__all__ = [
    "ResearchCoverage",
    "evidence_for",
    "evidence_payload",
    "is_fresh",
    "needs_refetch",
    "research_coverage",
    "store_evidence",
    "enrich_investor",
    "enrich_campaign",
]
