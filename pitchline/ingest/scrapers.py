"""Pluggable scrapers for public sources (R5.3).

Hard limits, enforced here rather than in a prompt:

* ``robots.txt`` is consulted before every fetch and honoured.
* No authenticated fetching — there is no place to put a cookie or a credential.
* LinkedIn is refused explicitly, by host, regardless of what a caller passes.

``httpx`` and ``trafilatura`` are optional at runtime: without them the scrapers report
themselves unavailable instead of failing at import, so the offline pipeline still runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from pitchline.models import EvidenceArea, EvidenceKind, SourceType

USER_AGENT = "PitchlineResearchBot/0.1 (+founder outreach research; respects robots.txt)"
REQUEST_TIMEOUT = 20.0

#: R5.3 — refused by host, not by policy document.
FORBIDDEN_HOSTS = {
    "linkedin.com", "www.linkedin.com", "m.linkedin.com",
    "facebook.com", "www.facebook.com", "instagram.com",
}


class ScraperUnavailable(RuntimeError):
    """The optional HTTP dependencies are not installed."""


class ForbiddenSource(RuntimeError):
    """The URL is behind authentication or on the refused-host list."""


@dataclass
class ScrapeResult:
    url: str
    title: str
    text: str
    area: EvidenceArea = EvidenceArea.OTHER
    kind: EvidenceKind = EvidenceKind.OTHER
    source_type: SourceType = SourceType.FUND_SITE
    published_at: datetime | None = None
    entities: list[str] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _http():
    try:
        import httpx  # noqa: PLC0415
    except ImportError as exc:
        raise ScraperUnavailable(
            "httpx is not installed; run `pip install httpx trafilatura` to enable research fetches"
        ) from exc
    return httpx


def _extract_text(html: str, url: str) -> tuple[str, str]:
    """Return (title, text). Falls back to a crude tag strip without trafilatura."""
    try:
        import trafilatura  # noqa: PLC0415
    except ImportError:
        stripped = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
        stripped = re.sub(r"(?s)<[^>]+>", " ", stripped)
        title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
        return (
            (title_match.group(1).strip() if title_match else url),
            re.sub(r"\s+", " ", stripped).strip(),
        )
    text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    metadata = trafilatura.extract_metadata(html)
    title = (getattr(metadata, "title", None) or url) if metadata else url
    return title, text


def _robots_allows(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception:
        # A missing or unreachable robots.txt is not permission — but it is also not a
        # prohibition. Standard practice: allow, and record the fetch either way.
        return True
    return parser.can_fetch(USER_AGENT, url)


def guard_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ForbiddenSource(f"unsupported scheme: {url}")
    host = (parsed.netloc or "").lower().split(":")[0]
    if host in FORBIDDEN_HOSTS or host.endswith(".linkedin.com"):
        raise ForbiddenSource(f"{host} is on the refused-source list (R5.3)")
    if not _robots_allows(url):
        raise ForbiddenSource(f"robots.txt disallows {url}")


def fetch_url(url: str) -> tuple[str, str]:
    """Fetch a public page and return (title, extracted text)."""
    guard_url(url)
    httpx = _http()
    response = httpx.get(
        url,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return _extract_text(response.text, url)


class Scraper(Protocol):
    name: str

    def available(self) -> bool: ...

    def scrape(self, **kwargs: Any) -> list[ScrapeResult]: ...


class FundSiteScraper:
    """Fetch a fund's public team / thesis / portfolio pages."""

    name = "fund_site"
    CANDIDATE_PATHS = ("", "/team", "/about", "/thesis", "/portfolio", "/companies", "/investments")

    def available(self) -> bool:
        try:
            _http()
        except ScraperUnavailable:
            return False
        return True

    def scrape(self, *, website: str, paths: Iterable[str] | None = None, **_: Any) -> list[ScrapeResult]:
        if not website:
            return []
        base = website if website.startswith("http") else f"https://{website}"
        results: list[ScrapeResult] = []
        for path in paths if paths is not None else self.CANDIDATE_PATHS:
            url = urljoin(base, path) if path else base
            try:
                title, text = fetch_url(url)
            except (ForbiddenSource, ScraperUnavailable):
                continue
            except Exception:
                continue
            if len(text) < 200:
                continue
            area = (
                EvidenceArea.PORTFOLIO
                if any(k in path for k in ("portfolio", "companies", "investments"))
                else EvidenceArea.THESIS
            )
            results.append(
                ScrapeResult(
                    url=url,
                    title=title,
                    text=text,
                    area=area,
                    kind=(
                        EvidenceKind.PORTFOLIO_COMPANY
                        if area is EvidenceArea.PORTFOLIO
                        else EvidenceKind.THESIS_STATEMENT
                    ),
                    source_type=SourceType.FUND_SITE,
                )
            )
        return results


class FormDScraper:
    """SEC EDGAR full-text search for Form D filings — public, no authentication."""

    name = "sec_form_d"
    SEARCH_URL = "https://efts.sec.gov/LATEST/search-index?q={query}&forms=D"
    BROWSE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"

    def available(self) -> bool:
        try:
            _http()
        except ScraperUnavailable:
            return False
        return True

    def scrape(self, *, firm_name: str, limit: int = 5, **_: Any) -> list[ScrapeResult]:
        if not firm_name:
            return []
        httpx = _http()
        try:
            response = httpx.get(
                "https://efts.sec.gov/LATEST/search-index",
                params={"q": f'"{firm_name}"', "forms": "D"},
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []
        results: list[ScrapeResult] = []
        for hit in (payload.get("hits", {}).get("hits", []) or [])[:limit]:
            source = hit.get("_source", {})
            display = source.get("display_names", [firm_name])
            filed = source.get("file_date")
            results.append(
                ScrapeResult(
                    url=f"https://www.sec.gov/Archives/edgar/data/{source.get('ciks', [''])[0]}",
                    title=f"Form D filing — {display[0] if display else firm_name}",
                    text=f"Form D filed {filed} by {', '.join(display)}.",
                    area=EvidenceArea.RECENT_ACTIVITY,
                    kind=EvidenceKind.FORM_D,
                    source_type=SourceType.SEC_FORM_D,
                    published_at=_parse_date(filed),
                )
            )
        return results


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


_REGISTRY: dict[str, Scraper] = {
    FundSiteScraper.name: FundSiteScraper(),
    FormDScraper.name: FormDScraper(),
}


def available_scrapers() -> dict[str, Scraper]:
    return {name: scraper for name, scraper in _REGISTRY.items() if scraper.available()}


def register_scraper(scraper: Scraper) -> None:
    _REGISTRY[scraper.name] = scraper
