"""Text primitives shared by compose, guardrails and ingest.

These are the canonical implementations of the counting and detection methods the rules
file names (R2.1 ``word_count_method``, R3.1, R3.4, R3.5). Guardrails call these rather
than reimplementing them, so "what counts as a word" has exactly one definition.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WS_RE = re.compile(r"\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])[\s\n]+(?=[A-Z0-9\"'(])")
_URL_RE = re.compile(
    r"""(?ix)
    \b(
        https?://[^\s<>()\[\]"']+          # scheme
        | www\.[^\s<>()\[\]"']+            # www, no scheme
        | mailto:[^\s<>()\[\]"']+
        | [a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.(?:com|io|co|ai|dev|app|org|net|xyz|vc|fund|so|sh|me|gg)
          (?:/[^\s<>()\[\]"']*)?           # bare domain with a known TLD
    )
    """
)
_IMAGE_RE = re.compile(
    r"""(?ix)
    ( !\[[^\]]*\]\([^)]*\)          # markdown image
    | <\s*img\b[^>]*>               # html img tag
    | cid:[a-z0-9._-]+              # inline attachment reference
    | data:image/[a-z0-9.+-]+;base64
    | \[image:[^\]]*\]              # client-rendered inline image
    | \.(?:png|jpe?g|gif|bmp|webp|svg)\b
    )
    """
)
_TRACKING_RE = re.compile(
    r"(?i)(open\.track|utm_source=|/track/open|pixel\.gif|1x1\.(?:png|gif)|__track)"
)
_SHORTENER_DOMAINS = {
    "bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly", "buff.ly", "rebrand.ly",
    "lnkd.in", "cutt.ly", "is.gd", "shorturl.at",
}
_ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]*\b")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def count_words(text: str) -> int:
    """R2.1 — whitespace-delimited tokens. Empty string is zero, not one."""
    stripped = text.strip()
    return len(_WS_RE.split(stripped)) if stripped else 0


def split_sentences(text: str) -> list[str]:
    """Sentence split good enough to answer "is the marker in sentence one?" (R2.3)."""
    collapsed = _WS_RE.sub(" ", text.strip())
    if not collapsed:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(collapsed) if s.strip()]


def first_sentence(text: str) -> str:
    sentences = split_sentences(text)
    return sentences[0] if sentences else ""


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def find_urls(text: str) -> list[str]:
    """R3.5 — every URL form, including bare domains and mailto."""
    return [m.group(0) for m in _URL_RE.finditer(text)]


def has_url_shortener(text: str) -> bool:
    lowered = text.lower()
    return any(domain in lowered for domain in _SHORTENER_DOMAINS)


def find_images(text: str) -> list[str]:
    """R3.1 — embedded images are disproportionately spam-filtered."""
    return [m.group(0) for m in _IMAGE_RE.finditer(text)]


def find_tracking(text: str) -> list[str]:
    """R3.1 — no open/click tracking anywhere in the programme."""
    return [m.group(0) for m in _TRACKING_RE.finditer(text)]


def find_spam_terms(text: str, terms: tuple[str, ...], *, case_insensitive: bool = True) -> list[str]:
    """R3.4 — word-boundary matches against the deny list."""
    haystack = text.lower() if case_insensitive else text
    hits: list[str] = []
    for term in terms:
        needle = term.lower() if case_insensitive else term
        # \b does not work against a leading '$', so fall back to substring for those.
        pattern = (
            re.escape(needle)
            if not needle[:1].isalnum()
            else rf"\b{re.escape(needle)}\b"
        )
        if re.search(pattern, haystack):
            hits.append(term)
    return hits


def count_exclamations(text: str) -> int:
    return text.count("!")


def find_shouted_words(text: str, *, max_acronym_length: int = 5) -> list[str]:
    """R3.4 — ALL-CAPS words, excluding short acronyms like SaaS-era 'API' or 'SEC'."""
    return [
        word
        for word in _ACRONYM_RE.findall(text)
        if len(word) > max_acronym_length
    ]


def tokens(text: str) -> set[str]:
    """Lowercase alphanumeric tokens, for overlap scoring."""
    return set(_TOKEN_RE.findall(text.lower()))


def normalize_person_name(name: str) -> str:
    """Dedupe key component (R1.4): fold accents, drop punctuation and suffixes."""
    folded = _strip_accents(name).lower()
    folded = re.sub(r"[^a-z\s]", " ", folded)
    parts = [p for p in folded.split() if p not in {"jr", "sr", "ii", "iii", "iv", "dr", "mr", "ms", "mrs"}]
    return " ".join(parts)


#: Legal-entity suffixes only. "Capital", "Ventures" and "Partners" are deliberately NOT
#: stripped: "Northaven Capital" and "Northaven Ventures" are frequently different funds,
#: and merging them would pool their portfolios — which would then produce phantom
#: portfolio conflicts (R1.5) against a fund that holds nothing of the sort.
_FIRM_LEGAL_SUFFIXES = {
    "llc", "lp", "llp", "inc", "incorporated", "ltd", "limited", "gmbh",
    "ag", "sa", "bv", "pte", "plc", "co", "corp", "corporation", "the",
}


def normalize_firm_name(name: str) -> str:
    """Dedupe key component (R1.4): fold case/accents, drop punctuation and legal suffixes."""
    folded = _strip_accents(name).lower()
    # Collapse dotted abbreviations first: "L.P." -> "lp", not "l p" (which would survive
    # the suffix filter and split one firm into two).
    folded = folded.replace(".", "")
    folded = re.sub(r"[^a-z0-9\s]", " ", folded)
    parts = [p for p in folded.split() if p not in _FIRM_LEGAL_SUFFIXES]
    return " ".join(parts) or " ".join(folded.split())


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def email_domain(email: str | None) -> str:
    normalized = normalize_email(email)
    return normalized.rsplit("@", 1)[1] if "@" in normalized else ""


def content_hash(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(_WS_RE.sub(" ", (part or "").strip().lower()).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _strip_accents(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch)
    )


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def overlap_ratio(a: set[str], b: set[str]) -> float:
    """Fraction of ``a`` covered by ``b`` — asymmetric, better for thesis matching."""
    if not a:
        return 0.0
    return len(a & b) / len(a)
