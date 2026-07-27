"""The linters.

Every check below maps to a rule ID and reads its threshold from ``rules.py``. None of
them are advisory: a failure blocks the draft from the approval queue. The novelty check
is the only one that consults a model, and even that returns a validated structure.

Two deliberate design choices:

* **Unverifiable is failing.** If the credibility marker cannot be resolved back to a
  registered variant, the draft fails. A marker nobody can check is not a marker.
* **The claim map must match the body.** A claim map that cites evidence for a sentence
  the body no longer contains is stale, and stale provenance is worse than none — it
  would pass the linter while the email says something else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

from sqlmodel import Session

from pitchline import textutil as tu
from pitchline.llm import LLMClient, get_client
from pitchline.models import (
    Draft,
    Evidence,
    GuardrailCode,
    GuardrailResult,
    PitchVariant,
    StartupProfile,
)
from pitchline.rules import (
    ALLOWED_ASK_TYPES,
    FORBID_FUNDING_ASK,
    FORBID_SPECIFIC_TIME_REQUEST,
    FORBID_TRACKING_PIXEL,
    FORBID_URL_SHORTENERS,
    MAX_ALL_CAPS_WORDS,
    MAX_ASK_SENTENCES,
    MAX_CAPS_ACRONYM_LENGTH,
    MAX_EMBEDDED_IMAGES,
    MAX_EXCLAMATION_MARKS,
    MAX_PARAGRAPHS,
    MAX_PERSONALIZATION_HOOKS,
    MAX_PITCH_WORDS,
    MAX_SPAM_TERM_HITS,
    MAX_SUBJECT_CHARS,
    MAX_UNSOURCED_CLAIMS,
    MIN_NOVELTY_SCORE,
    MIN_PERSONALIZATION_HOOKS,
    PROBLEM_PRECEDES_APPROACH,
    REQUIRE_CLAIM_MAP,
    REQUIRE_OPTOUT_MECHANISM,
    REQUIRE_PHYSICAL_POSTAL_ADDRESS,
    RULES_FINGERPRINT,
    SPAM_DENY_TERMS,
    SPAM_MATCH_CASE_INSENSITIVE,
    max_links_for_touch,
)
from pitchline.schemas import NoveltyVerdict

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# R2.5 forbids *asking for* a specific slot ("their office next Tuesday at 3 PM"). It does
# not forbid mentioning a time: a late-night delivery brand's whole pitch is "12AM to
# 4:30AM", and "arrives intact at 2AM" is a product claim, not a calendar request. So a
# sentence only fails when it pairs a time expression with a scheduling verb.
_TIME_EXPR_RE = re.compile(
    r"(?i)("
    r"\b\d{1,2}\s*(:\d{2})?\s*(am|pm)\b"
    r"|\b(mon|tues?|wed(nes)?|thurs?|fri|satur|sun)day\b"
    r"|\b\d{1,2}\s*o'?clock\b"
    r")"
)
_SCHEDULING_VERB_RE = re.compile(
    r"(?i)\b("
    r"meet(s|ing)?|schedul(e|es|ed|ing)|book(s|ed|ing)?|calendar|invit(e|ed|ing)|"
    r"pencil(l?ed)?|slot(ted)?|"
    r"come\s+by|drop\s+by|stop\s+by|swing\s+by|your\s+office|coffee|catch\s+up|"
    r"are\s+you\s+(free|available)|does\s+\w+\s+work\s+for\s+you"
    r")\b"
)
_FUNDING_ASK_RE = re.compile(
    r"(?i)\b(term sheet|wire (the )?funds|commit(ment)? of \$|invest \$|"
    r"lead (our|the) round|write (us )?a check for \$|sign (the|a) safe)\b"
)
_OPTOUT_RE = re.compile(r"(?i)(unsubscribe|opt out|opt-out|won'?t (contact|email) you again|reply .*stop)")
_PLACEHOLDER_RE = re.compile(
    r"(?i)(\[[^\]]*\]|\{\{[^}]*\}\}|<[^>]+>|\bTODO\b|\bFIXME\b|\bXXXX?\b|\byour address\b)"
)


class GuardrailError(RuntimeError):
    """Raised by :func:`assert_passes` when a draft does not clear the gate."""

    def __init__(self, report: "LintReport") -> None:
        super().__init__(report.describe())
        self.report = report


@dataclass(frozen=True)
class GuardrailFailure:
    code: GuardrailCode
    rule_id: str
    detail: str
    observed: str = ""
    allowed: str = ""

    def describe(self) -> str:
        suffix = f" (observed {self.observed}, allowed {self.allowed})" if self.observed else ""
        return f"[{self.rule_id} {self.code.value}] {self.detail}{suffix}"


@dataclass
class LintReport:
    draft_id: int | None = None
    failures: list[GuardrailFailure] = field(default_factory=list)
    checks_run: list[GuardrailCode] = field(default_factory=list)
    novelty: NoveltyVerdict | None = None
    rules_fingerprint: str = RULES_FINGERPRINT

    @property
    def passed(self) -> bool:
        return not self.failures

    @property
    def codes(self) -> set[GuardrailCode]:
        return {f.code for f in self.failures}

    def has(self, code: GuardrailCode) -> bool:
        return code in self.codes

    def describe(self) -> str:
        if self.passed:
            return f"draft {self.draft_id}: passed {len(self.checks_run)} guardrails"
        return f"draft {self.draft_id} failed:\n  - " + "\n  - ".join(
            f.describe() for f in self.failures
        )

    def as_dicts(self) -> list[dict[str, str]]:
        return [
            {
                "code": f.code.value,
                "rule_id": f.rule_id,
                "detail": f.detail,
                "observed": f.observed,
                "allowed": f.allowed,
            }
            for f in self.failures
        ]


def lint_draft(
    session: Session,
    draft: Draft,
    *,
    profile: StartupProfile | None = None,
    client: LLMClient | None = None,
    include_novelty: bool = True,
    persist: bool = False,
) -> LintReport:
    """Run every gate. Returns a report; never raises for a mere rule violation."""
    report = LintReport(draft_id=draft.id)
    body = draft.body or ""
    greeting = draft.greeting or ""
    pitch_text = f"{greeting}\n\n{body}".strip()

    checks: Iterable[Callable[[], list[GuardrailFailure]]] = (
        lambda: _check_length(pitch_text, report),
        lambda: _check_subject(draft, report),
        lambda: _check_paragraphs(body, report),
        lambda: _check_structure(session, draft, body, report),
        lambda: _check_credibility(session, draft, body, report),
        lambda: _check_ask(session, draft, body, report),
        lambda: _check_provenance(session, draft, body, report),
        lambda: _check_hooks(draft, body, report),
        lambda: _check_media(draft, report),
        lambda: _check_links(draft, pitch_text, report),
        lambda: _check_spam(draft, pitch_text, report),
        lambda: _check_shouting(pitch_text, report),
        lambda: _check_footer(draft, profile, report),
    )
    for check in checks:
        report.failures.extend(check())

    if include_novelty:
        report.failures.extend(_check_novelty(draft, report, client))

    if persist and draft.id is not None:
        _persist(session, draft, report)
    return report


def assert_passes(session: Session, draft: Draft, **kwargs) -> LintReport:
    report = lint_draft(session, draft, **kwargs)
    if not report.passed:
        raise GuardrailError(report)
    return report


# --------------------------------------------------------------------------------------
# Individual gates
# --------------------------------------------------------------------------------------


def _check_length(pitch_text: str, report: LintReport) -> list[GuardrailFailure]:
    """R2.1 — 150 words. The footer is compliance text and does not compete for room."""
    report.checks_run.append(GuardrailCode.LENGTH)
    words = tu.count_words(pitch_text)
    if words > MAX_PITCH_WORDS:
        return [
            GuardrailFailure(
                code=GuardrailCode.LENGTH,
                rule_id="R2.1",
                detail="draft is longer than a single short email",
                observed=f"{words} words",
                allowed=f"{MAX_PITCH_WORDS} words",
            )
        ]
    if words == 0:
        return [
            GuardrailFailure(
                code=GuardrailCode.LENGTH, rule_id="R2.1", detail="draft body is empty"
            )
        ]
    return []


def _check_subject(draft: Draft, report: LintReport) -> list[GuardrailFailure]:
    report.checks_run.append(GuardrailCode.SUBJECT_LENGTH)
    subject = (draft.subject or "").strip()
    if not subject:
        return [
            GuardrailFailure(
                code=GuardrailCode.SUBJECT_LENGTH, rule_id="R5.1", detail="subject line is empty"
            )
        ]
    if len(subject) > MAX_SUBJECT_CHARS:
        return [
            GuardrailFailure(
                code=GuardrailCode.SUBJECT_LENGTH,
                rule_id="R2.1",
                detail="subject line will be truncated in the inbox",
                observed=f"{len(subject)} chars",
                allowed=f"{MAX_SUBJECT_CHARS} chars",
            )
        ]
    return []


def _check_paragraphs(body: str, report: LintReport) -> list[GuardrailFailure]:
    report.checks_run.append(GuardrailCode.PARAGRAPHS)
    count = len(tu.paragraphs(body))
    if count > MAX_PARAGRAPHS:
        return [
            GuardrailFailure(
                code=GuardrailCode.PARAGRAPHS,
                rule_id="R2.1",
                detail="too many paragraphs; the email requires scrolling",
                observed=str(count),
                allowed=str(MAX_PARAGRAPHS),
            )
        ]
    return []


def _check_structure(
    session: Session, draft: Draft, body: str, report: LintReport
) -> list[GuardrailFailure]:
    """R2.2 — the problem must land before the solution."""
    report.checks_run.append(GuardrailCode.STRUCTURE)
    if not PROBLEM_PRECEDES_APPROACH:  # pragma: no cover
        return []
    if (draft.touch_number or 1) > 1 and not (draft.problem_variant_id or draft.approach_variant_id):
        # R2.2 describes the shape of the pitch. A follow-up carries new information
        # (R4.3), not a re-pitch, so it has no problem/approach slots to order.
        return []
    problem = _variant_text(session, draft.problem_variant_id)
    approach = _variant_text(session, draft.approach_variant_id)
    if problem is None or approach is None:
        return [
            GuardrailFailure(
                code=GuardrailCode.STRUCTURE,
                rule_id="R2.2",
                detail="draft is missing its problem or approach slot variant",
                observed=f"problem={draft.problem_variant_id}, approach={draft.approach_variant_id}",
                allowed="both slots filled from the founder variant library",
            )
        ]
    normalized = _norm(body)
    p_index, a_index = normalized.find(_norm(problem)), normalized.find(_norm(approach))
    if p_index < 0 or a_index < 0:
        return [
            GuardrailFailure(
                code=GuardrailCode.STRUCTURE,
                rule_id="R2.2",
                detail="body does not contain its registered problem/approach text verbatim",
                observed=f"problem_found={p_index >= 0}, approach_found={a_index >= 0}",
                allowed="slot text used verbatim (the model selects, it does not rewrite)",
            )
        ]
    if p_index > a_index:
        return [
            GuardrailFailure(
                code=GuardrailCode.STRUCTURE,
                rule_id="R2.2",
                detail="the solution is stated before the problem",
                observed=f"problem at char {p_index}, approach at char {a_index}",
                allowed="problem first",
            )
        ]
    return []


def _check_credibility(
    session: Session, draft: Draft, body: str, report: LintReport
) -> list[GuardrailFailure]:
    """R2.3 — a registered credibility marker, in sentence one, or the draft fails."""
    report.checks_run.append(GuardrailCode.CREDIBILITY_MARKER)
    variant = session.get(PitchVariant, draft.credibility_variant_id) if draft.credibility_variant_id else None
    if variant is None:
        return [
            GuardrailFailure(
                code=GuardrailCode.CREDIBILITY_MARKER,
                rule_id="R2.3",
                detail="no registered credibility marker on the draft; an unverifiable marker "
                "is not a marker",
                observed=str(draft.credibility_variant_id),
                allowed="a credibility variant id from the founder's registered set",
            )
        ]
    sentence = tu.first_sentence(body)
    if not sentence:
        return [
            GuardrailFailure(
                code=GuardrailCode.CREDIBILITY_MARKER, rule_id="R2.3", detail="body has no sentences"
            )
        ]
    if _norm(variant.body_text) not in _norm(sentence):
        return [
            GuardrailFailure(
                code=GuardrailCode.CREDIBILITY_MARKER,
                rule_id="R2.3",
                detail="the credibility marker is not in the first sentence",
                observed=f"first sentence: {sentence[:110]!r}",
                allowed=f"must contain the registered marker {variant.key!r}",
            )
        ]
    return []


def _check_ask(
    session: Session, draft: Draft, body: str, report: LintReport
) -> list[GuardrailFailure]:
    """R2.5 — low commitment only. No hard-scheduled meetings, no funding ask."""
    report.checks_run.append(GuardrailCode.ASK_TYPE)
    failures: list[GuardrailFailure] = []
    ask_type = draft.ask_type or ""
    if ask_type not in ALLOWED_ASK_TYPES:
        failures.append(
            GuardrailFailure(
                code=GuardrailCode.ASK_TYPE,
                rule_id="R2.5",
                detail="the ask is not one of the registered low-commitment forms",
                observed=ask_type or "(none)",
                allowed=", ".join(ALLOWED_ASK_TYPES),
            )
        )
    ask_text = _variant_text(session, draft.ask_variant_id)
    if ask_text and len(tu.split_sentences(ask_text)) > MAX_ASK_SENTENCES:
        failures.append(
            GuardrailFailure(
                code=GuardrailCode.ASK_TYPE,
                rule_id="R2.5",
                detail="the ask runs long enough to feel like a commitment",
                observed=f"{len(tu.split_sentences(ask_text))} sentences",
                allowed=str(MAX_ASK_SENTENCES),
            )
        )
    if FORBID_SPECIFIC_TIME_REQUEST:
        for sentence in tu.split_sentences(body):
            if _TIME_EXPR_RE.search(sentence) and _SCHEDULING_VERB_RE.search(sentence):
                failures.append(
                    GuardrailFailure(
                        code=GuardrailCode.ASK_TYPE,
                        rule_id="R2.5",
                        detail="asks for a specific time slot ('their office next Tuesday at 3 PM')",
                        observed=sentence[:110],
                        allowed="an easy, low-cost way to express interest",
                    )
                )
                break
    if FORBID_FUNDING_ASK and (match := _FUNDING_ASK_RE.search(body)):
        failures.append(
            GuardrailFailure(
                code=GuardrailCode.ASK_TYPE,
                rule_id="R2.5",
                detail="asks for money on a cold first touch",
                observed=match.group(0),
                allowed="get them hooked enough to want to learn more",
            )
        )
    return failures


def _check_provenance(
    session: Session, draft: Draft, body: str, report: LintReport
) -> list[GuardrailFailure]:
    """R2.6 — every investor-specific sentence maps to a stored evidence id."""
    report.checks_run.append(GuardrailCode.PROVENANCE)
    failures: list[GuardrailFailure] = []
    claims = draft.claim_map or []

    if REQUIRE_CLAIM_MAP and not claims:
        # A draft with no investor-specific text at all is generic, which R2.6 and R1.2
        # both exist to prevent.
        return [
            GuardrailFailure(
                code=GuardrailCode.PROVENANCE,
                rule_id="R2.6",
                detail="draft has no claim map, so no investor-specific claim can be verified",
                observed="0 claims",
                allowed=f"at least {MIN_PERSONALIZATION_HOOKS} sourced claim",
            )
        ]

    normalized_body = _norm(body)
    unsourced: list[str] = []
    for claim in claims:
        text = str(claim.get("text", "")).strip()
        evidence_id = claim.get("evidence_id")
        investor_specific = bool(claim.get("investor_specific", True))
        if not investor_specific:
            continue
        if evidence_id is None:
            unsourced.append(text[:80])
            continue
        if session.get(Evidence, int(evidence_id)) is None:
            failures.append(
                GuardrailFailure(
                    code=GuardrailCode.PROVENANCE,
                    rule_id="R2.6",
                    detail="claim cites an evidence id that does not resolve to a stored snippet",
                    observed=f"evidence_id={evidence_id}",
                    allowed="an id in the evidence table",
                )
            )
        if text and _norm(text) not in normalized_body:
            failures.append(
                GuardrailFailure(
                    code=GuardrailCode.PROVENANCE,
                    rule_id="R2.6",
                    detail="claim map is stale: the cited sentence is not in the body",
                    observed=text[:80],
                    allowed="claim text present verbatim in the body",
                )
            )

    if len(unsourced) > MAX_UNSOURCED_CLAIMS:
        failures.append(
            GuardrailFailure(
                code=GuardrailCode.PROVENANCE,
                rule_id="R2.6",
                detail="investor-specific claim with no evidence id: " + "; ".join(unsourced[:3]),
                observed=f"{len(unsourced)} unsourced",
                allowed=f"{MAX_UNSOURCED_CLAIMS} unsourced",
            )
        )
    return failures


def _check_hooks(draft: Draft, body: str, report: LintReport) -> list[GuardrailFailure]:
    """R2.6 — exactly one personalization hook, bound to evidence, present in the body."""
    report.checks_run.append(GuardrailCode.PERSONALIZATION_HOOKS)
    hook = (draft.personalization_hook or "").strip()
    count = 1 if hook else 0
    if count < MIN_PERSONALIZATION_HOOKS or count > MAX_PERSONALIZATION_HOOKS:
        return [
            GuardrailFailure(
                code=GuardrailCode.PERSONALIZATION_HOOKS,
                rule_id="R2.6",
                detail="wrong number of personalization hooks",
                observed=str(count),
                allowed=f"{MIN_PERSONALIZATION_HOOKS}-{MAX_PERSONALIZATION_HOOKS}",
            )
        ]
    failures = []
    if draft.hook_evidence_id is None:
        failures.append(
            GuardrailFailure(
                code=GuardrailCode.PERSONALIZATION_HOOKS,
                rule_id="R2.6",
                detail="the personalization hook has no evidence id",
                observed="hook_evidence_id=None",
                allowed="an evidence id",
            )
        )
    if hook and _norm(hook) not in _norm(body):
        failures.append(
            GuardrailFailure(
                code=GuardrailCode.PERSONALIZATION_HOOKS,
                rule_id="R2.6",
                detail="the recorded hook does not appear in the body",
                observed=hook[:80],
                allowed="hook text present in the body",
            )
        )
    return failures


def _check_media(draft: Draft, report: LintReport) -> list[GuardrailFailure]:
    """R3.1 — images are disproportionately spam-filtered; tracking is never allowed."""
    report.checks_run.extend([GuardrailCode.IMAGES, GuardrailCode.TRACKING])
    failures = []
    rendered = draft.rendered
    images = tu.find_images(rendered)
    if len(images) > MAX_EMBEDDED_IMAGES:
        failures.append(
            GuardrailFailure(
                code=GuardrailCode.IMAGES,
                rule_id="R3.1",
                detail="embedded image or attachment reference in a plain-text pitch",
                observed=", ".join(images[:3]),
                allowed=f"{MAX_EMBEDDED_IMAGES} images",
            )
        )
    if FORBID_TRACKING_PIXEL and (tracking := tu.find_tracking(rendered)):
        failures.append(
            GuardrailFailure(
                code=GuardrailCode.TRACKING,
                rule_id="R3.1",
                detail="tracking artefact found; the programme runs no open or click tracking",
                observed=", ".join(tracking[:3]),
                allowed="none",
            )
        )
    return failures


def _check_links(draft: Draft, pitch_text: str, report: LintReport) -> list[GuardrailFailure]:
    """R3.5 — zero links on the first touch. Email addresses are not links."""
    report.checks_run.append(GuardrailCode.LINKS)
    allowed = max_links_for_touch(draft.touch_number or 1)
    scrubbed = _EMAIL_RE.sub(" ", pitch_text)
    urls = tu.find_urls(scrubbed)
    failures = []
    if len(urls) > allowed:
        failures.append(
            GuardrailFailure(
                code=GuardrailCode.LINKS,
                rule_id="R3.5",
                detail=f"touch {draft.touch_number} carries more links than allowed",
                observed=", ".join(urls[:3]),
                allowed=f"{allowed} links",
            )
        )
    if FORBID_URL_SHORTENERS and tu.has_url_shortener(pitch_text):
        failures.append(
            GuardrailFailure(
                code=GuardrailCode.LINKS,
                rule_id="R3.5",
                detail="URL shortener present; filters treat them as a redirect signal",
                allowed="none",
            )
        )
    return failures


def _check_spam(draft: Draft, pitch_text: str, report: LintReport) -> list[GuardrailFailure]:
    """R3.4 — deny-list terms, subject included."""
    report.checks_run.append(GuardrailCode.SPAM_TERMS)
    haystack = f"{draft.subject or ''}\n{pitch_text}"
    hits = tu.find_spam_terms(
        haystack, SPAM_DENY_TERMS, case_insensitive=SPAM_MATCH_CASE_INSENSITIVE
    )
    if len(hits) > MAX_SPAM_TERM_HITS:
        return [
            GuardrailFailure(
                code=GuardrailCode.SPAM_TERMS,
                rule_id="R3.4",
                detail="spam trigger words present",
                observed=", ".join(hits[:5]),
                allowed=f"{MAX_SPAM_TERM_HITS} hits",
            )
        ]
    return []


def _check_shouting(pitch_text: str, report: LintReport) -> list[GuardrailFailure]:
    """R3.4 — formatting tells filters weight alongside vocabulary."""
    report.checks_run.append(GuardrailCode.SHOUTING)
    failures = []
    exclamations = tu.count_exclamations(pitch_text)
    if exclamations > MAX_EXCLAMATION_MARKS:
        failures.append(
            GuardrailFailure(
                code=GuardrailCode.SHOUTING,
                rule_id="R3.4",
                detail="exclamation marks read as promotional",
                observed=str(exclamations),
                allowed=str(MAX_EXCLAMATION_MARKS),
            )
        )
    shouted = tu.find_shouted_words(pitch_text, max_acronym_length=MAX_CAPS_ACRONYM_LENGTH)
    if len(shouted) > MAX_ALL_CAPS_WORDS:
        failures.append(
            GuardrailFailure(
                code=GuardrailCode.SHOUTING,
                rule_id="R3.4",
                detail="ALL-CAPS words beyond short acronyms",
                observed=", ".join(shouted[:4]),
                allowed=str(MAX_ALL_CAPS_WORDS),
            )
        )
    return failures


def _check_footer(
    draft: Draft, profile: StartupProfile | None, report: LintReport
) -> list[GuardrailFailure]:
    """R5.1 — postal address and a working opt-out in every commercial message."""
    report.checks_run.append(GuardrailCode.FOOTER)
    footer = draft.footer or ""
    failures = []
    if REQUIRE_PHYSICAL_POSTAL_ADDRESS:
        address = (profile.postal_address if profile else "").strip()
        if placeholder := _PLACEHOLDER_RE.search(address or footer):
            # A template address satisfies "a string is present" and nothing else. CAN-SPAM
            # requires a *valid* address, so an unfilled placeholder has to block the send.
            failures.append(
                GuardrailFailure(
                    code=GuardrailCode.FOOTER,
                    rule_id="R5.1",
                    detail="postal address is still a placeholder; CAN-SPAM requires a real one "
                    "(set it with `pitchline profile-set --postal-address ...`)",
                    observed=placeholder.group(0),
                    allowed="a valid physical postal address",
                )
            )
        elif address and _norm(address) not in _norm(footer):
            failures.append(
                GuardrailFailure(
                    code=GuardrailCode.FOOTER,
                    rule_id="R5.1",
                    detail="footer is missing the physical postal address",
                    observed=footer[:80] or "(empty)",
                    allowed=address[:80],
                )
            )
        elif not address and not footer.strip():
            failures.append(
                GuardrailFailure(
                    code=GuardrailCode.FOOTER,
                    rule_id="R5.1",
                    detail="no CAN-SPAM footer on a commercial message",
                    allowed="postal address + opt-out",
                )
            )
    if REQUIRE_OPTOUT_MECHANISM and not _OPTOUT_RE.search(footer):
        failures.append(
            GuardrailFailure(
                code=GuardrailCode.FOOTER,
                rule_id="R5.1",
                detail="footer has no opt-out mechanism",
                observed=footer[:80] or "(empty)",
                allowed="an explicit opt-out instruction",
            )
        )
    return failures


def _check_novelty(
    draft: Draft, report: LintReport, client: LLMClient | None
) -> list[GuardrailFailure]:
    """R2.4 — 'would a VC think I've seen ten of these this week?'"""
    report.checks_run.append(GuardrailCode.NOVELTY)
    client = client or get_client()
    verdict = client.run(
        "novelty_v1",
        NoveltyVerdict,
        {
            "subject": draft.subject,
            "body": draft.body,
            "has_personalization_hook": bool(draft.personalization_hook),
            "has_specific_problem": bool(draft.problem_variant_id),
        },
    )
    report.novelty = verdict
    draft.novelty_score = verdict.score
    draft.novelty_reason = verdict.reason
    if verdict.score < MIN_NOVELTY_SCORE:
        return [
            GuardrailFailure(
                code=GuardrailCode.NOVELTY,
                rule_id="R2.4",
                detail=f"reads as derivative: {verdict.reason}"
                + (f" (cliches: {', '.join(verdict.cliches[:4])})" if verdict.cliches else ""),
                observed=f"{verdict.score}",
                allowed=f">= {MIN_NOVELTY_SCORE}",
            )
        ]
    return []


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _variant_text(session: Session, variant_id: int | None) -> str | None:
    if variant_id is None:
        return None
    variant = session.get(PitchVariant, variant_id)
    return variant.body_text if variant else None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _persist(session: Session, draft: Draft, report: LintReport) -> None:
    attempt = (draft.retry_count or 0) + 1
    for failure in report.failures:
        session.add(
            GuardrailResult(
                draft_id=draft.id,  # type: ignore[arg-type]
                attempt=attempt,
                code=failure.code,
                rule_id=failure.rule_id,
                passed=False,
                detail=failure.detail,
                observed=failure.observed or None,
                allowed=failure.allowed or None,
            )
        )
    if report.passed:
        session.add(
            GuardrailResult(
                draft_id=draft.id,  # type: ignore[arg-type]
                attempt=attempt,
                code=GuardrailCode.LENGTH,
                rule_id="all",
                passed=True,
                detail=f"passed {len(report.checks_run)} guardrails",
            )
        )
    session.flush()
