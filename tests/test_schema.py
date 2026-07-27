"""Phase 0 gate: the schema migrates clean and the model invariants hold."""

from __future__ import annotations

from datetime import timedelta

from sqlmodel import SQLModel, Session, select

from pitchline.models import (
    Draft,
    DraftStatus,
    Evidence,
    Investor,
    Mailbox,
    Target,
    TargetStatus,
    utcnow,
)

REQUIRED_TABLES = {
    "firms", "investors", "evidence", "startup_profile", "pitch_variants", "updates",
    "targets", "drafts", "sends", "events", "replies", "experiments", "suppressions",
    "campaigns", "sequences", "guardrail_results", "mailboxes", "mailbox_daily_quota",
    "prompt_versions",
}


def test_every_required_table_exists(engine):
    assert REQUIRED_TABLES <= set(SQLModel.metadata.tables)


def test_schema_creates_and_recreates_cleanly(engine):
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    SQLModel.metadata.create_all(engine)  # idempotent
    with Session(engine) as session:
        assert session.exec(select(Investor)).all() == []


def test_llm_generated_rows_carry_model_and_prompt_version(session, campaign, profile, client):
    """Every LLM-generated row is traceable (BUILD_PROMPT data-model requirement)."""
    from tests.conftest import give_full_research, make_investor
    from pitchline.compose import compose_first_touch, plan_sequence
    from pitchline.targeting import score_investor

    investor = make_investor(session)
    give_full_research(session, investor)
    target = score_investor(session, campaign=campaign, investor=investor, profile=profile)
    assert target.model and target.prompt_version and target.created_at

    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=profile)
    assert draft.model and draft.prompt_version and draft.created_at
    assert draft.rules_fingerprint


def test_draft_is_approved_requires_both_fields():
    draft = Draft(target_id=1)
    assert draft.is_approved is False
    draft.approved_by = "Dana Reyes"
    assert draft.is_approved is False
    draft.approved_at = utcnow()
    assert draft.is_approved is True


def test_target_conflict_override_requires_all_three_fields():
    target = Target(campaign_id=1, investor_id=1, has_portfolio_conflict=True)
    assert target.conflict_overridden is False
    target.conflict_override_by = "Dana Reyes"
    assert target.conflict_overridden is False
    target.conflict_override_reason = "adjacent, not competitive"
    assert target.conflict_overridden is False
    target.conflict_override_at = utcnow()
    assert target.conflict_overridden is True
    assert target.is_sendable is False  # still needs a sendable status
    target.status = TargetStatus.QUALIFIED
    assert target.is_sendable is True


def test_rendered_draft_includes_the_footer_separator():
    draft = Draft(target_id=1, greeting="Hi Ana,", body="Body text.", footer="Address\nOpt out")
    rendered = draft.rendered
    assert rendered.startswith("Hi Ana,")
    assert "\n\n--\n" in rendered
    assert rendered.endswith("Opt out")


def test_mailbox_age_drives_the_warmup_ramp(session):
    from pitchline.timeutil import today_utc

    mailbox = Mailbox(
        email="a@outreach.example", domain="outreach.example",
        warmup_started_on=today_utc() - timedelta(days=3),
    )
    assert mailbox.age_days() == 3


def test_json_columns_round_trip(session):
    from pitchline.models import EvidenceArea, EvidenceKind

    evidence = Evidence(
        area=EvidenceArea.PORTFOLIO,
        kind=EvidenceKind.PORTFOLIO_COMPANY,
        raw_text="text",
        content_hash="abc",
        entities=["Corvus Health", "SiteLedger"],
    )
    session.add(evidence)
    session.commit()
    session.expire_all()

    reloaded = session.get(Evidence, evidence.id)
    assert reloaded.entities == ["Corvus Health", "SiteLedger"]
    assert reloaded.area is EvidenceArea.PORTFOLIO


def test_draft_status_enum_round_trips(session, campaign, profile):
    draft = Draft(target_id=1, status=DraftStatus.PENDING_APPROVAL, claim_map=[{"text": "x"}])
    session.add(draft)
    session.commit()
    session.expire_all()
    reloaded = session.get(Draft, draft.id)
    assert reloaded.status is DraftStatus.PENDING_APPROVAL
    assert reloaded.claim_map == [{"text": "x"}]
