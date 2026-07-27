"""CSV import for Crunchbase / PitchBook / OpenVC-style exports.

Three things happen here that the rules require:

* **Partner-level resolution (R1.4).** A row that does not resolve to a named individual
  with an investing role is *quarantined*, not imported as a target. Generic inboxes are
  quarantined too. Quarantined rows are kept — the fix is usually a better export, and
  throwing the row away loses that signal.
* **Dedupe (R1.4).** On normalized name + normalized firm, so "Ann O'Brien, Foo Capital
  LLC" and "ann obrien, Foo Capital" are one person.
* **Provenance (R5.3).** Source type, source file, and ingestion timestamp on every row.

Any thesis/portfolio text in the export is also stored as evidence, because that text *is*
retrieved homework (R1.3) and re-typing it later would lose its provenance.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from sqlmodel import Session, select

from pitchline import events, textutil as tu
from pitchline.models import (
    EmailConfidence,
    Evidence,
    EvidenceArea,
    EvidenceKind,
    EventKind,
    Firm,
    Investor,
    InvestorRole,
    SourceType,
)
from pitchline.rules import EVIDENCE_CACHE_TTL_DAYS, is_generic_mailbox, is_partner_level

# Header aliases seen across Crunchbase, PitchBook and OpenVC exports.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "full_name": ("full name", "name", "investor name", "person", "person name", "contact", "partner name"),
    "first_name": ("first name", "firstname", "given name"),
    "last_name": ("last name", "lastname", "surname", "family name"),
    "firm": ("firm", "firm name", "fund", "fund name", "organization", "organisation", "company", "investor firm", "vc firm"),
    "role": ("role", "title", "position", "job title", "seniority"),
    "email": ("email", "email address", "e-mail", "contact email", "work email"),
    "email_confidence": ("email confidence", "email status", "verification status"),
    "segment": ("segment", "category", "tier"),
    "website": ("website", "firm website", "url", "fund website", "domain"),
    "personal_site": ("personal site", "blog", "personal website", "substack"),
    "x_handle": ("twitter", "x", "twitter handle", "x handle"),
    "country": ("country", "hq country", "investor country"),
    "city": ("city", "hq city", "location", "hq location", "headquarters"),
    "timezone": ("timezone", "time zone", "tz"),
    "stages": ("stages", "stage", "investment stages", "investment stage", "stage focus", "rounds"),
    "sectors": ("sectors", "sector", "industries", "industry", "focus", "verticals", "categories", "sector focus"),
    "check_min": ("check size min", "min check", "check min", "minimum check", "min investment"),
    "check_max": ("check size max", "max check", "check max", "maximum check", "max investment"),
    "check_size": ("check size", "typical check", "check", "typical check size", "investment size"),
    "thesis": ("thesis", "investment thesis", "bio", "description", "about", "summary", "focus areas"),
    "portfolio": ("portfolio", "portfolio companies", "investments", "notable investments"),
    "recent_investments": ("recent investments", "recent activity", "recent deals", "latest investments"),
    "recent_writing": ("recent writing", "recent post", "blog post", "latest post", "podcast", "recent commentary"),
    "activity_date": ("recent activity date", "last activity", "activity date"),
    "aum": ("aum", "assets under management", "fund size"),
    "linkedin": ("linkedin", "linkedin url", "linkedin profile"),
}

_MULTI_SEPARATORS = (";", "|", ",", "/")


@dataclass
class ImportReport:
    """What the importer did, in numbers the operator can act on."""

    source_path: str = ""
    rows_read: int = 0
    firms_created: int = 0
    investors_created: int = 0
    investors_updated: int = 0
    duplicates: int = 0
    quarantined: int = 0
    evidence_created: int = 0
    errors: list[str] = field(default_factory=list)
    quarantine_reasons: dict[str, int] = field(default_factory=dict)

    def note_quarantine(self, reason: str) -> None:
        self.quarantined += 1
        self.quarantine_reasons[reason] = self.quarantine_reasons.get(reason, 0) + 1

    def summary(self) -> str:
        return (
            f"{self.rows_read} rows -> {self.investors_created} new investors, "
            f"{self.investors_updated} updated, {self.duplicates} duplicates, "
            f"{self.quarantined} quarantined, {self.firms_created} firms, "
            f"{self.evidence_created} evidence snippets"
        )


def parse_role(raw: str | None) -> InvestorRole:
    """Map an export's free-text title to a role. Order matters: 'venture partner'
    must not be swallowed by the bare 'partner' branch."""
    if not raw:
        return InvestorRole.UNKNOWN
    title = raw.strip().lower()
    checks: tuple[tuple[tuple[str, ...], InvestorRole], ...] = (
        (("managing partner", "managing director", "manager partner", "md,"), InvestorRole.MANAGING_PARTNER),
        (("general partner", "gp", "g.p."), InvestorRole.GENERAL_PARTNER),
        # "Founder" of a *fund* is the most senior investing role there is — Don Thompson at
        # Cleveland Avenue, Kirsten Green at Forerunner. Treating it as unresolvable
        # quarantined eight of the best contacts on a real list. The opposite risk — an
        # operating-company founder leaking in from a messy export — is caught downstream by
        # the fit score (no fund thesis) and by per-email human approval (R6.1).
        (("founding partner", "founder & partner", "founder and partner", "co-founder",
          "cofounder", "founding gp", "founder", "chief executive", "ceo"),
         InvestorRole.FOUNDING_PARTNER),
        (("venture partner",), InvestorRole.VENTURE_PARTNER),
        (("principal",), InvestorRole.PRINCIPAL),
        (("partner",), InvestorRole.PARTNER),
        (("associate",), InvestorRole.ASSOCIATE),
        (("analyst",), InvestorRole.ANALYST),
        (("platform", "talent", "community", "chief of staff", "operations", "marketing"), InvestorRole.PLATFORM),
        (("scout",), InvestorRole.SCOUT),
        (("angel", "individual investor"), InvestorRole.ANGEL),
    )
    for needles, role in checks:
        if any(needle in title for needle in needles):
            return role
    return InvestorRole.UNKNOWN


def _normalize_header(header: str) -> str:
    return header.strip().lower().replace("_", " ").replace("-", " ")


def build_column_map(fieldnames: Iterable[str]) -> dict[str, str]:
    """Map canonical field -> actual header, tolerating export naming differences."""
    normalized = {_normalize_header(name): name for name in fieldnames if name}
    mapping: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[canonical] = normalized[alias]
                break
    return mapping


def _get(row: Mapping[str, Any], colmap: Mapping[str, str], key: str) -> str:
    value = row.get(colmap.get(key, ""), "")
    return str(value).strip() if value is not None else ""


def _split_multi(value: str) -> list[str]:
    if not value:
        return []
    for sep in _MULTI_SEPARATORS:
        if sep in value:
            return [part.strip() for part in value.split(sep) if part.strip()]
    return [value.strip()]


def _parse_money(value: str) -> float | None:
    """Parse '$250k', '1.5M', '250,000' and ranges like '$100k-$500k' (first number)."""
    if not value:
        return None
    cleaned = value.replace(",", "").replace("$", "").strip().lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*([km]?)", cleaned)
    if not match:
        return None
    amount = float(match.group(1))
    suffix = match.group(2)
    if suffix == "k":
        amount *= 1_000
    elif suffix == "m":
        amount *= 1_000_000
    elif amount < 1000:  # bare "250" in a check-size column means $250k
        amount *= 1_000
    return amount


def _parse_money_range(value: str) -> tuple[float | None, float | None]:
    if not value:
        return None, None
    parts = [p for p in value.replace("to", "-").split("-") if p.strip()]
    if len(parts) >= 2:
        return _parse_money(parts[0]), _parse_money(parts[1])
    single = _parse_money(value)
    return single, single


def _parse_date(value: str) -> "datetime | None":
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _parse_confidence(value: str) -> EmailConfidence:
    """Absent or unrecognised means unknown. Never optimistic by default."""
    try:
        return EmailConfidence((value or "").strip().lower())
    except ValueError:
        return EmailConfidence.UNKNOWN


def _normalize_stage(value: str) -> str:
    token = value.strip().lower().replace("-", " ").replace("_", " ")
    table = {
        "pre seed": "pre_seed", "preseed": "pre_seed", "pre-seed": "pre_seed",
        "seed": "seed", "series a": "series_a", "a": "series_a",
        "series b": "series_b", "b": "series_b",
        "growth": "growth", "late stage": "growth", "series c": "growth",
        "early stage": "seed", "early": "seed",
    }
    return table.get(token, token.replace(" ", "_"))


def iter_rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def import_investors_csv(
    session: Session,
    path: Path | str,
    *,
    source: SourceType = SourceType.CSV_IMPORT,
    create_evidence: bool = True,
    limit: int | None = None,
) -> ImportReport:
    """Import an investor export. Idempotent: re-importing updates rather than duplicates."""
    path = Path(path)
    report = ImportReport(source_path=str(path))

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        colmap = build_column_map(reader.fieldnames or [])
        if "full_name" not in colmap and "first_name" not in colmap:
            raise ValueError(
                f"{path}: no name column found. Expected one of "
                f"{COLUMN_ALIASES['full_name'] + COLUMN_ALIASES['first_name']}"
            )

        for line_no, row in enumerate(reader, start=2):
            if limit is not None and report.rows_read >= limit:
                break
            report.rows_read += 1
            try:
                _import_row(session, row, colmap, source, path, report, create_evidence)
            except Exception as exc:  # keep going; one bad row must not kill an import
                report.errors.append(f"line {line_no}: {exc}")

    session.flush()
    events.record(
        session,
        EventKind.INGESTED,
        entity_type="import",
        summary=report.summary(),
        payload={
            "path": str(path),
            "rows": report.rows_read,
            "created": report.investors_created,
            "quarantined": report.quarantined,
            "quarantine_reasons": report.quarantine_reasons,
        },
    )
    return report


def _import_row(
    session: Session,
    row: Mapping[str, Any],
    colmap: Mapping[str, str],
    source: SourceType,
    path: Path,
    report: ImportReport,
    create_evidence: bool,
) -> None:
    full_name = _get(row, colmap, "full_name")
    if not full_name:
        first, last = _get(row, colmap, "first_name"), _get(row, colmap, "last_name")
        full_name = " ".join(p for p in (first, last) if p).strip()
    if not full_name:
        # A firm with no named individual is real data, but it is not a target. R1.4 wants
        # a person; record the firm, bank its evidence, and flag the missing partner as the
        # work to be done.
        firm_only = _upsert_firm(session, _get(row, colmap, "firm"), row, colmap, source, path, report)
        if firm_only is not None and create_evidence:
            report.evidence_created += _seed_evidence(
                session, None, firm_only, row, colmap, path, source
            )
        report.note_quarantine("needs_partner_resolution")
        return

    firm_name = _get(row, colmap, "firm")
    firm = _upsert_firm(session, firm_name, row, colmap, source, path, report)

    name_normalized = tu.normalize_person_name(full_name)
    existing = session.exec(
        select(Investor).where(
            Investor.name_normalized == name_normalized,
            Investor.firm_id == (firm.id if firm else None),
        )
    ).first()

    role_raw = _get(row, colmap, "role")
    role = parse_role(role_raw)
    email = tu.normalize_email(_get(row, colmap, "email"))

    # R1.4 — decide up front whether this row belongs in the campaign universe.
    # Quarantine is about whether this is the right *kind* of record (R1.4), not about
    # whether we can reach them yet. A named partner with no address is still a legitimate
    # target to research and draft for; send.preflight refuses the dispatch until the
    # address is verified, which is the correct place for that decision.
    quarantine_reason: str | None = None
    if not is_partner_level(role.value):
        quarantine_reason = f"role_not_partner_level:{role.value}"
    elif email and is_generic_mailbox(email):
        quarantine_reason = "generic_mailbox"

    stages = [_normalize_stage(s) for s in _split_multi(_get(row, colmap, "stages"))]
    sectors = _split_multi(_get(row, colmap, "sectors"))
    check_min = _parse_money(_get(row, colmap, "check_min"))
    check_max = _parse_money(_get(row, colmap, "check_max"))
    if check_min is None and check_max is None:
        check_min, check_max = _parse_money_range(_get(row, colmap, "check_size"))

    values: dict[str, Any] = {
        "full_name": full_name,
        "name_normalized": name_normalized,
        "firm_id": firm.id if firm else None,
        "role": role,
        "role_raw": role_raw or None,
        "is_partner_level": is_partner_level(role.value),
        "email": email or None,
        "email_domain": tu.email_domain(email) or None,
        "email_confidence": _parse_confidence(_get(row, colmap, "email_confidence")),
        "personal_site": _get(row, colmap, "personal_site") or None,
        "x_handle": _get(row, colmap, "x_handle") or None,
        "country": _get(row, colmap, "country") or None,
        "city": _get(row, colmap, "city") or None,
        "timezone": _get(row, colmap, "timezone") or None,
        "stages": stages,
        "sectors": sectors,
        "check_size_min_usd": check_min,
        "check_size_max_usd": check_max,
        "thesis_summary": _get(row, colmap, "thesis") or None,
        "quarantined": quarantine_reason is not None,
        "quarantine_reason": quarantine_reason,
        "source": source,
        "source_url": _get(row, colmap, "website") or None,
        "source_detail": path.name,
    }

    if existing:
        report.duplicates += 1
        changed = False
        for key, value in values.items():
            if value in (None, [], "") or key in {"source", "ingested_at"}:
                continue
            if getattr(existing, key) != value:
                setattr(existing, key, value)
                changed = True
        if changed:
            report.investors_updated += 1
        investor = existing
    else:
        investor = Investor(**values)
        session.add(investor)
        session.flush()
        report.investors_created += 1
        if quarantine_reason:
            report.note_quarantine(quarantine_reason)
            events.record(
                session,
                EventKind.QUARANTINED,
                entity_type="investor",
                entity_id=investor.id,
                summary=f"{full_name}: {quarantine_reason}",
                flush=False,
            )

    if create_evidence:
        report.evidence_created += _seed_evidence(session, investor, firm, row, colmap, path, source)


def _upsert_firm(
    session: Session,
    firm_name: str,
    row: Mapping[str, Any],
    colmap: Mapping[str, str],
    source: SourceType,
    path: Path,
    report: ImportReport,
) -> Firm | None:
    if not firm_name:
        return None
    normalized = tu.normalize_firm_name(firm_name)
    firm = session.exec(select(Firm).where(Firm.name_normalized == normalized)).first()
    website = _get(row, colmap, "website")
    if firm is None:
        firm = Firm(
            name=firm_name,
            name_normalized=normalized,
            website=website or None,
            domain=(website or "").replace("https://", "").replace("http://", "").split("/")[0] or None,
            hq_city=_get(row, colmap, "city") or None,
            hq_country=_get(row, colmap, "country") or None,
            aum_usd=_parse_money(_get(row, colmap, "aum")),
            stages=[_normalize_stage(s) for s in _split_multi(_get(row, colmap, "stages"))],
            sectors=_split_multi(_get(row, colmap, "sectors")),
            thesis_summary=_get(row, colmap, "thesis") or None,
            portfolio_companies=_split_multi(_get(row, colmap, "portfolio")),
            source=source,
            source_url=website or None,
            source_detail=path.name,
        )
        session.add(firm)
        session.flush()
        report.firms_created += 1
    else:
        portfolio = _split_multi(_get(row, colmap, "portfolio"))
        if portfolio and set(portfolio) - set(firm.portfolio_companies):
            firm.portfolio_companies = sorted(set(firm.portfolio_companies) | set(portfolio))
    return firm


def _seed_evidence(
    session: Session,
    investor: Investor | None,
    firm: Firm | None,
    row: Mapping[str, Any],
    colmap: Mapping[str, str],
    path: Path,
    source: SourceType,
) -> int:
    """Store thesis and portfolio text from the export as first-class evidence (R1.3).

    An export column is retrieved, dated, attributable text — exactly what the evidence
    table is for. Storing it here means a draft can cite it, and the citation resolves.
    """
    created = 0
    thesis = _get(row, colmap, "thesis")
    portfolio = _split_multi(_get(row, colmap, "portfolio"))
    recent_investments = _split_multi(_get(row, colmap, "recent_investments"))
    recent_writing = _get(row, colmap, "recent_writing")
    published_at = _parse_date(_get(row, colmap, "activity_date"))
    website = _get(row, colmap, "website") or (firm.website if firm else None)

    candidates: list[tuple[EvidenceArea, EvidenceKind, str, str, list[str]]] = []
    if thesis:
        candidates.append(
            (EvidenceArea.THESIS, EvidenceKind.THESIS_STATEMENT, f"{(investor.full_name if investor else firm.name if firm else 'investor')} stated thesis", thesis, [])
        )
    if portfolio:
        candidates.append(
            (
                EvidenceArea.PORTFOLIO,
                EvidenceKind.PORTFOLIO_COMPANY,
                f"{(firm.name if firm else investor.full_name if investor else 'fund')} portfolio",
                "Portfolio companies on record: " + ", ".join(portfolio) + ".",
                portfolio,
            )
        )
    if recent_investments:
        candidates.append(
            (
                EvidenceArea.RECENT_ACTIVITY,
                EvidenceKind.INVESTMENT,
                f"{(investor.full_name if investor else firm.name if firm else 'investor')} recent investments",
                "Recent investments on record: " + ", ".join(recent_investments) + ".",
                recent_investments,
            )
        )
    if recent_writing:
        candidates.append(
            (
                EvidenceArea.RECENT_ACTIVITY,
                EvidenceKind.BLOG_POST,
                f"{(investor.full_name if investor else firm.name if firm else 'investor')} recent writing",
                recent_writing,
                [],
            )
        )

    investor_id = investor.id if investor else None
    for area, kind, title, text, entities in candidates:
        digest = tu.content_hash(text)
        exists = session.exec(
            select(Evidence).where(
                Evidence.investor_id == investor_id,
                Evidence.firm_id == (firm.id if firm else None),
                Evidence.content_hash == digest,
            )
        ).first()
        if exists:
            continue
        session.add(
            Evidence(
                investor_id=investor_id,
                firm_id=firm.id if firm else None,
                area=area,
                kind=kind,
                title=title,
                url=website or None,
                raw_text=text,
                excerpt=text[:400],
                content_hash=digest,
                published_at=published_at,
                ttl_days=EVIDENCE_CACHE_TTL_DAYS,
                entities=entities,
                source=source,
                source_url=website or None,
                source_detail=path.name,
                retrieval_query="csv_column",
            )
        )
        created += 1
    if created:
        session.flush()
    return created
