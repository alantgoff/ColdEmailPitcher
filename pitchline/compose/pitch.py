"""First-touch composition.

The loop is: select variants -> write one hook -> render -> lint. A failure comes back as
a structured code, and each code has a *mechanical* repair (shorter variant for a length
failure, a different angle for a novelty failure). After ``MAX_COMPOSE_RETRIES`` the draft
goes to the human-fix queue rather than being retried forever — a draft the machine cannot
fix is a signal about the copy, not a reason to keep spending tokens.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from pitchline import events
from pitchline.compose import library
from pitchline.guardrails import LintReport, lint_draft
from pitchline.llm import LLMClient, get_client, stamp
from pitchline.models import (
    Draft,
    DraftStatus,
    Evidence,
    EventKind,
    GuardrailCode,
    Investor,
    PitchVariant,
    SlotKind,
    StartupProfile,
    Target,
)
from pitchline.research.store import evidence_payload
from pitchline.rules import MAX_COMPOSE_RETRIES, RULES_FINGERPRINT
from pitchline.schemas import HookProposal, VariantSelection
from pitchline.targeting.score import investor_payload, profile_payload
from pitchline.timeutil import utcnow


class ComposeError(RuntimeError):
    """Composition could not produce a draft at all."""


class HumanFixRequired(ComposeError):
    """The gate rejected every mechanical repair. A person needs to look at this."""

    def __init__(self, draft: Draft, report: LintReport) -> None:
        super().__init__(report.describe())
        self.draft = draft
        self.report = report


@dataclass
class Slots:
    credibility: PitchVariant
    problem: PitchVariant
    approach: PitchVariant
    ask: PitchVariant

    @property
    def variant_key(self) -> str:
        return "|".join([self.credibility.key, self.problem.key, self.approach.key, self.ask.key])


def render_body(slots: Slots, hook: str) -> str:
    """Assemble the four slots in R2.2 order.

    Sentence one is the credibility marker (R2.3); the hook follows it in the same
    paragraph so the personalization lands before the pitch, but never *before* the
    credibility filter.
    """
    opening = f"{slots.credibility.body_text.strip()} {hook.strip()}".strip()
    return "\n\n".join(
        [
            opening,
            slots.problem.body_text.strip(),
            slots.approach.body_text.strip(),
            slots.ask.body_text.strip(),
        ]
    )


def render_footer(profile: StartupProfile) -> str:
    """R5.1 — postal address and a working opt-out. No links (R3.5)."""
    lines = [
        f"{profile.founder_name}, {profile.name}".strip(", "),
        profile.postal_address.strip(),
        profile.optout_instruction.strip(),
    ]
    return "\n".join(line for line in lines if line)


def render_greeting(investor: Investor) -> str:
    first = (investor.full_name or "").split()[0] if investor.full_name else "there"
    return f"Hi {first},"


def render_subject(profile: StartupProfile, slots: Slots) -> str:
    subject = f"{profile.name} — {slots.problem.label}".strip(" —")
    return subject[:78]


def compose_first_touch(
    session: Session,
    *,
    target: Target,
    profile: StartupProfile,
    client: LLMClient | None = None,
    experiment_id: int | None = None,
    max_retries: int = MAX_COMPOSE_RETRIES,
) -> Draft:
    """Compose touch 1 for a target and run it through the gate."""
    client = client or get_client()
    investor = session.get(Investor, target.investor_id)
    if investor is None:
        raise ComposeError(f"target {target.id} has no investor")

    evidence = evidence_payload(session, investor.id)  # type: ignore[arg-type]
    if not evidence:
        raise ComposeError(
            f"{investor.full_name}: no evidence on file; personalization would be unsourced (R2.6)"
        )

    slots = _select_slots(session, client, investor, profile)
    hook = _write_hook(session, client, investor, profile, evidence)

    draft = session.exec(
        select(Draft).where(Draft.target_id == target.id, Draft.touch_number == 1)
    ).first() or Draft(target_id=target.id, touch_number=1)  # type: ignore[arg-type]

    tried_problem: list[str] = []
    tried_approach: list[str] = []
    report: LintReport | None = None

    for attempt in range(max_retries + 1):
        _apply(draft, slots, hook, investor, profile, client, experiment_id)
        session.add(draft)
        session.flush()

        report = lint_draft(session, draft, profile=profile, client=client, persist=True)
        if report.passed:
            draft.status = DraftStatus.PENDING_APPROVAL
            draft.retry_count = attempt
            session.add(draft)
            session.flush()
            events.record(
                session,
                EventKind.DRAFTED,
                entity_type="draft",
                entity_id=draft.id,
                campaign_id=target.campaign_id,
                summary=f"touch 1 for {investor.full_name} passed {len(report.checks_run)} gates",
                payload={"variant_key": draft.variant_key, "attempt": attempt + 1},
                flush=False,
            )
            return draft

        draft.status = DraftStatus.GUARDRAIL_FAILED
        draft.retry_count = attempt + 1
        session.add(draft)
        session.flush()
        events.record(
            session,
            EventKind.GUARDRAIL_FAILED,
            entity_type="draft",
            entity_id=draft.id,
            campaign_id=target.campaign_id,
            summary=f"attempt {attempt + 1}: " + ", ".join(c.value for c in report.codes),
            payload={"failures": report.as_dicts()},
            flush=False,
        )

        if attempt == max_retries:
            break
        slots, hook = _repair(
            session, client, report, slots, hook, investor, profile, evidence,
            tried_problem, tried_approach,
        )

    assert report is not None
    draft.status = DraftStatus.NEEDS_HUMAN_FIX
    session.add(draft)
    session.flush()
    events.record(
        session,
        EventKind.ROUTED_TO_HUMAN,
        entity_type="draft",
        entity_id=draft.id,
        campaign_id=target.campaign_id,
        summary="guardrails could not be satisfied mechanically",
        payload={"failures": report.as_dicts()},
        flush=False,
    )
    raise HumanFixRequired(draft, report)


# --------------------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------------------


def _select_slots(
    session: Session, client: LLMClient, investor: Investor, profile: StartupProfile
) -> Slots:
    payload = library.variants_payload(session, profile_id=profile.id)
    selection: VariantSelection = client.run(
        "variant_select_v1",
        VariantSelection,
        {
            "investor": investor_payload(session, investor),
            "profile": profile_payload(profile),
            "variants": payload,
        },
    )
    try:
        return Slots(
            credibility=library.by_key(session, SlotKind.CREDIBILITY, selection.credibility_key),
            problem=library.by_key(session, SlotKind.PROBLEM, selection.problem_key),
            approach=library.by_key(session, SlotKind.APPROACH, selection.approach_key),
            ask=library.by_key(session, SlotKind.ASK, selection.ask_key),
        )
    except library.VariantLibraryError as exc:
        # The model invented a key. Fall back to the library rather than to invented copy.
        raise ComposeError(f"variant selection returned an unknown key: {exc}") from exc


def _write_hook(
    session: Session,
    client: LLMClient,
    investor: Investor,
    profile: StartupProfile,
    evidence: list[dict],
) -> HookProposal:
    proposal: HookProposal = client.run(
        "hook_v1",
        HookProposal,
        {
            "investor": investor_payload(session, investor),
            "profile": profile_payload(profile),
            "evidence": evidence,
        },
    )
    if session.get(Evidence, proposal.evidence_id) is None:
        raise ComposeError(
            f"hook cites evidence {proposal.evidence_id}, which is not in the store (R2.6)"
        )
    return proposal


def _apply(
    draft: Draft,
    slots: Slots,
    hook: HookProposal,
    investor: Investor,
    profile: StartupProfile,
    client: LLMClient,
    experiment_id: int | None,
) -> None:
    body = render_body(slots, hook.hook_text)
    draft.greeting = render_greeting(investor)
    draft.body = body
    draft.footer = render_footer(profile)
    draft.subject = render_subject(profile, slots)
    draft.word_count = len(f"{draft.greeting} {body}".split())
    draft.credibility_variant_id = slots.credibility.id
    draft.problem_variant_id = slots.problem.id
    draft.approach_variant_id = slots.approach.id
    draft.ask_variant_id = slots.ask.id
    draft.credibility_marker_type = slots.credibility.marker_type
    draft.ask_type = slots.ask.ask_type
    draft.personalization_hook = hook.hook_text
    draft.hook_evidence_id = hook.evidence_id
    draft.evidence_ids = [hook.evidence_id]
    draft.claim_map = [
        {"text": hook.hook_text, "evidence_id": hook.evidence_id, "investor_specific": True},
        {"text": slots.problem.body_text, "evidence_id": None, "investor_specific": False},
        {"text": slots.approach.body_text, "evidence_id": None, "investor_specific": False},
        {"text": slots.credibility.body_text, "evidence_id": None, "investor_specific": False},
    ]
    draft.variant_key = slots.variant_key
    draft.experiment_id = experiment_id
    draft.rules_fingerprint = RULES_FINGERPRINT
    draft.status = DraftStatus.COMPOSING
    for key, value in stamp(client, "variant_select_v1").items():
        setattr(draft, key, value)


def _repair(
    session: Session,
    client: LLMClient,
    report: LintReport,
    slots: Slots,
    hook: HookProposal,
    investor: Investor,
    profile: StartupProfile,
    evidence: list[dict],
    tried_problem: list[str],
    tried_approach: list[str],
) -> tuple[Slots, HookProposal]:
    """Map structured failures to mechanical fixes. Unknown codes are not repairable."""
    if report.has(GuardrailCode.LENGTH) or report.has(GuardrailCode.PARAGRAPHS):
        tried_problem.append(slots.problem.key)
        tried_approach.append(slots.approach.key)
        slots = Slots(
            credibility=library.shortest(session, SlotKind.CREDIBILITY),
            problem=library.shortest(session, SlotKind.PROBLEM, exclude=tried_problem),
            approach=library.shortest(session, SlotKind.APPROACH, exclude=tried_approach),
            ask=library.shortest(session, SlotKind.ASK),
        )
    elif report.has(GuardrailCode.NOVELTY) or report.has(GuardrailCode.SPAM_TERMS):
        tried_problem.append(slots.problem.key)
        tried_approach.append(slots.approach.key)
        slots = Slots(
            credibility=slots.credibility,
            problem=library.next_alternative(session, SlotKind.PROBLEM, exclude=tried_problem),
            approach=library.next_alternative(session, SlotKind.APPROACH, exclude=tried_approach),
            ask=slots.ask,
        )
    elif report.has(GuardrailCode.ASK_TYPE):
        slots = Slots(
            credibility=slots.credibility,
            problem=slots.problem,
            approach=slots.approach,
            ask=library.next_alternative(session, SlotKind.ASK, exclude=[slots.ask.key]),
        )
    elif report.has(GuardrailCode.PERSONALIZATION_HOOKS) or report.has(GuardrailCode.PROVENANCE):
        hook = _write_hook(session, client, investor, profile, evidence)
    return slots, hook
