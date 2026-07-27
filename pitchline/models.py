"""SQLModel schema for Pitchline.

Design notes:

* SQLite by default, Postgres-swappable — no dialect-specific column types, no raw SQL.
* Every externally-sourced row carries ``source``/``source_url``/``ingested_at`` (R5.3).
* Every LLM-generated row carries ``model``, ``prompt_version`` and ``created_at``.
* Enums are stored by name; changing a member's *value* is safe, renaming one is a
  migration.
* Anything a rule constrains is a real column, so the constraint is testable in SQL rather
  than living only in a prompt string.
"""

# NB: SQLModel resolves Relationship targets from real annotations, so this module
# deliberately does *not* use `from __future__ import annotations`.
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import JSON, Column, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

__all__ = [
    "utcnow",
    "InvestorRole",
    "Stage",
    "SourceType",
    "EvidenceArea",
    "EvidenceKind",
    "SlotKind",
    "DraftStatus",
    "GuardrailCode",
    "SendStatus",
    "ReplyClass",
    "TargetStatus",
    "SuppressionScope",
    "SuppressionReason",
    "EventKind",
    "CampaignStatus",
    "Firm",
    "Investor",
    "Evidence",
    "StartupProfile",
    "PitchVariant",
    "Update",
    "Campaign",
    "Target",
    "Sequence",
    "Draft",
    "GuardrailResult",
    "Mailbox",
    "MailboxDailyQuota",
    "Send",
    "Reply",
    "Suppression",
    "Event",
    "Experiment",
    "PromptVersion",
]


def utcnow() -> datetime:
    """Timezone-aware UTC now. Every timestamp in the schema uses this."""
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------------------


class InvestorRole(str, Enum):
    """R1.4 — which of these count as partner-level is decided by the rules file."""

    MANAGING_PARTNER = "managing_partner"
    GENERAL_PARTNER = "general_partner"
    FOUNDING_PARTNER = "founding_partner"
    PARTNER = "partner"
    VENTURE_PARTNER = "venture_partner"
    PRINCIPAL = "principal"
    ASSOCIATE = "associate"
    ANALYST = "analyst"
    PLATFORM = "platform"
    SCOUT = "scout"
    ANGEL = "angel"
    UNKNOWN = "unknown"


class Stage(str, Enum):
    PRE_SEED = "pre_seed"
    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    GROWTH = "growth"
    UNKNOWN = "unknown"


class SourceType(str, Enum):
    """R5.3 — public sources only."""

    CSV_IMPORT = "csv_import"
    FUND_SITE = "fund_site"
    SEC_FORM_D = "sec_form_d"
    PUBLIC_WRITING = "public_writing"
    MANUAL_ENTRY = "manual_entry"


class EvidenceArea(str, Enum):
    """R1.3 — the three areas the source names as "thirty minutes of homework"."""

    PORTFOLIO = "portfolio"
    THESIS = "thesis"
    RECENT_ACTIVITY = "recent_activity"
    OTHER = "other"


class EvidenceKind(str, Enum):
    INVESTMENT = "investment"
    PORTFOLIO_COMPANY = "portfolio_company"
    THESIS_STATEMENT = "thesis_statement"
    FUND_ANNOUNCEMENT = "fund_announcement"
    BLOG_POST = "blog_post"
    PODCAST = "podcast"
    SOCIAL_POST = "social_post"
    INTERVIEW = "interview"
    FORM_D = "form_d"
    OTHER = "other"


class SlotKind(str, Enum):
    """R2.2 — the four slots, in render order."""

    CREDIBILITY = "credibility"
    PROBLEM = "problem"
    APPROACH = "approach"
    ASK = "ask"


class DraftStatus(str, Enum):
    COMPOSING = "composing"
    GUARDRAIL_FAILED = "guardrail_failed"
    NEEDS_HUMAN_FIX = "needs_human_fix"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SCHEDULED = "scheduled"
    SENT = "sent"
    CANCELLED = "cancelled"


class GuardrailCode(str, Enum):
    """One per gate in §5 of BUILD_PROMPT; each maps to a rule ID."""

    LENGTH = "length"
    SUBJECT_LENGTH = "subject_length"
    PARAGRAPHS = "paragraphs"
    STRUCTURE = "structure"
    CREDIBILITY_MARKER = "credibility_marker"
    NOVELTY = "novelty"
    ASK_TYPE = "ask_type"
    PROVENANCE = "provenance"
    PERSONALIZATION_HOOKS = "personalization_hooks"
    IMAGES = "images"
    ATTACHMENTS = "attachments"
    LINKS = "links"
    SPAM_TERMS = "spam_terms"
    SHOUTING = "shouting"
    FOOTER = "footer"
    TRACKING = "tracking"


class SendStatus(str, Enum):
    SCHEDULED = "scheduled"
    DRY_RUN = "dry_run"
    SENT = "sent"
    FAILED = "failed"
    BOUNCED = "bounced"
    REPLIED = "replied"


class ReplyClass(str, Enum):
    INTERESTED = "interested"
    DECK_REQUEST = "deck_request"
    NOT_NOW = "not_now"
    PASS = "pass"
    AUTO_REPLY = "auto_reply"
    OOO = "ooo"
    BOUNCE = "bounce"
    UNSUBSCRIBE = "unsubscribe"
    UNKNOWN = "unknown"


class TargetStatus(str, Enum):
    SCORED = "scored"
    QUALIFIED = "qualified"
    DROPPED_LOW_FIT = "dropped_low_fit"
    SUPPRESSED_CONFLICT = "suppressed_conflict"
    SUPPRESSED_LIST = "suppressed_list"
    IN_SEQUENCE = "in_sequence"
    REPLIED = "replied"
    CLOSED = "closed"


class SuppressionScope(str, Enum):
    EMAIL = "email"
    DOMAIN = "domain"
    FIRM = "firm"
    INVESTOR = "investor"


class SuppressionReason(str, Enum):
    PASS_REPLY = "pass_reply"
    UNSUBSCRIBE = "unsubscribe"
    HARD_BOUNCE = "hard_bounce"
    COMPLAINT = "complaint"
    PORTFOLIO_CONFLICT = "portfolio_conflict"
    MANUAL = "manual"
    DO_NOT_CONTACT = "do_not_contact"


class EventKind(str, Enum):
    """Append-only audit trail — the experiment record from design principle 4."""

    INGESTED = "ingested"
    QUARANTINED = "quarantined"
    EVIDENCE_STORED = "evidence_stored"
    EVIDENCE_CACHE_HIT = "evidence_cache_hit"
    SCORED = "scored"
    SUPPRESSED = "suppressed"
    CONFLICT_OVERRIDDEN = "conflict_overridden"
    DRAFTED = "drafted"
    GUARDRAIL_FAILED = "guardrail_failed"
    ROUTED_TO_HUMAN = "routed_to_human"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    SCHEDULED = "scheduled"
    SENT = "sent"
    SEND_REFUSED = "send_refused"
    BUDGET_EXHAUSTED = "budget_exhausted"
    REPLIED = "replied"
    BOUNCED = "bounced"
    SEQUENCE_ENDED = "sequence_ended"
    ALARM_RAISED = "alarm_raised"
    CAMPAIGN_PAUSED = "campaign_paused"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


# --------------------------------------------------------------------------------------
# Mixins
# --------------------------------------------------------------------------------------


class ProvenanceMixin(SQLModel):
    """R5.3 — where a record came from and when it arrived."""

    source: SourceType = Field(default=SourceType.MANUAL_ENTRY, index=True)
    source_url: Optional[str] = None
    source_detail: Optional[str] = None
    ingested_at: datetime = Field(default_factory=utcnow, index=True)


class LLMProvenanceMixin(SQLModel):
    """Every LLM-generated row is traceable to a model and a versioned prompt."""

    model: Optional[str] = Field(default=None, index=True)
    prompt_version: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


# --------------------------------------------------------------------------------------
# 1. Investor universe
# --------------------------------------------------------------------------------------


class Firm(ProvenanceMixin, table=True):
    __tablename__ = "firms"
    __table_args__ = (UniqueConstraint("name_normalized", name="uq_firm_name_normalized"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    name_normalized: str = Field(index=True)
    website: Optional[str] = None
    domain: Optional[str] = Field(default=None, index=True)
    hq_city: Optional[str] = None
    hq_country: Optional[str] = Field(default=None, index=True)
    aum_usd: Optional[float] = None
    stages: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    sectors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    check_size_min_usd: Optional[float] = None
    check_size_max_usd: Optional[float] = None
    thesis_summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    portfolio_companies: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    notes: Optional[str] = None

    investors: list["Investor"] = Relationship(back_populates="firm")


class Investor(ProvenanceMixin, table=True):
    """R1.4 — a named individual with an investing role, never a firm or shared inbox."""

    __tablename__ = "investors"
    __table_args__ = (
        UniqueConstraint("name_normalized", "firm_id", name="uq_investor_name_firm"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    firm_id: Optional[int] = Field(default=None, foreign_key="firms.id", index=True)
    full_name: str = Field(index=True)
    name_normalized: str = Field(index=True)
    role: InvestorRole = Field(default=InvestorRole.UNKNOWN, index=True)
    role_raw: Optional[str] = None
    is_partner_level: bool = Field(default=False, index=True)
    email: Optional[str] = Field(default=None, index=True)
    email_domain: Optional[str] = Field(default=None, index=True)
    personal_site: Optional[str] = None
    blog_url: Optional[str] = None
    x_handle: Optional[str] = None
    timezone: Optional[str] = Field(default=None, index=True)
    country: Optional[str] = None
    city: Optional[str] = None
    stages: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    sectors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    check_size_min_usd: Optional[float] = None
    check_size_max_usd: Optional[float] = None
    thesis_summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    quarantined: bool = Field(default=False, index=True)
    quarantine_reason: Optional[str] = None
    active: bool = Field(default=True, index=True)

    firm: Optional[Firm] = Relationship(back_populates="investors")
    evidence: list["Evidence"] = Relationship(back_populates="investor")


# --------------------------------------------------------------------------------------
# 2. Evidence store — the compressed "thirty minutes of homework" (R1.3)
# --------------------------------------------------------------------------------------


class Evidence(ProvenanceMixin, table=True):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("investor_id", "content_hash", name="uq_evidence_investor_hash"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    investor_id: Optional[int] = Field(default=None, foreign_key="investors.id", index=True)
    firm_id: Optional[int] = Field(default=None, foreign_key="firms.id", index=True)
    area: EvidenceArea = Field(default=EvidenceArea.OTHER, index=True)
    kind: EvidenceKind = Field(default=EvidenceKind.OTHER, index=True)
    title: Optional[str] = None
    url: Optional[str] = Field(default=None, index=True)
    raw_text: str = Field(sa_column=Column(Text))
    excerpt: Optional[str] = Field(default=None, sa_column=Column(Text))
    content_hash: str = Field(index=True)
    published_at: Optional[datetime] = Field(default=None, index=True)
    fetched_at: datetime = Field(default_factory=utcnow, index=True)
    ttl_days: int = Field(default=14)
    retrieval_query: Optional[str] = None
    entities: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    investor: Optional[Investor] = Relationship(back_populates="evidence")


# --------------------------------------------------------------------------------------
# 3. Founder-authored material
# --------------------------------------------------------------------------------------


class StartupProfile(SQLModel, table=True):
    __tablename__ = "startup_profile"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    version: int = Field(default=1)
    one_liner: str
    stage: Stage = Field(default=Stage.SEED, index=True)
    sectors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    geography: Optional[str] = None
    raising_usd: Optional[float] = None
    target_check_min_usd: Optional[float] = None
    target_check_max_usd: Optional[float] = None
    #: R1.5 — names matched against investor portfolios to detect direct conflicts.
    competitors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    #: R2.3 — the founder's registered credibility markers.
    credibility_markers: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    founder_name: str = ""
    founder_email: str = ""
    reply_to_email: Optional[str] = None
    deck_url: Optional[str] = None
    calendar_url: Optional[str] = None
    #: R5.1 — CAN-SPAM requires a real postal address in every commercial message.
    postal_address: str = ""
    optout_instruction: str = "Reply 'unsubscribe' and I won't contact you again."
    created_at: datetime = Field(default_factory=utcnow)


class PitchVariant(SQLModel, table=True):
    """R2.2 — founder-authored slot text. The model selects; it does not invent."""

    __tablename__ = "pitch_variants"
    __table_args__ = (UniqueConstraint("slot", "key", name="uq_variant_slot_key"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    startup_profile_id: Optional[int] = Field(
        default=None, foreign_key="startup_profile.id", index=True
    )
    slot: SlotKind = Field(index=True)
    key: str = Field(index=True)
    label: str = ""
    body_text: str = Field(sa_column=Column(Text))
    #: For credibility variants: which marker type this asserts (R2.3).
    marker_type: Optional[str] = Field(default=None, index=True)
    #: For ask variants: which allowed ask type this is (R2.5).
    ask_type: Optional[str] = Field(default=None, index=True)
    sectors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    stages: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    author: str = "founder"
    active: bool = Field(default=True, index=True)
    version: int = Field(default=1)
    created_at: datetime = Field(default_factory=utcnow)


class Update(SQLModel, table=True):
    """R4.3 — the new-information payload a follow-up must carry. Consumed once."""

    __tablename__ = "updates"

    id: Optional[int] = Field(default=None, primary_key=True)
    startup_profile_id: Optional[int] = Field(
        default=None, foreign_key="startup_profile.id", index=True
    )
    headline: str
    body_text: str = Field(sa_column=Column(Text))
    category: str = "traction"
    occurred_on: date = Field(default_factory=lambda: utcnow().date(), index=True)
    #: Set when a follow-up draft consumes this update; never reused (R4.3).
    consumed_by_draft_id: Optional[int] = Field(default=None, index=True)
    consumed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)

    @property
    def is_available(self) -> bool:
        return self.consumed_by_draft_id is None


# --------------------------------------------------------------------------------------
# 4. Campaign and targeting
# --------------------------------------------------------------------------------------


class Campaign(SQLModel, table=True):
    __tablename__ = "campaigns"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    startup_profile_id: int = Field(foreign_key="startup_profile.id", index=True)
    status: CampaignStatus = Field(default=CampaignStatus.DRAFT, index=True)
    #: R1.1 — a ceiling, not a goal. Never exceeds MAX_CAMPAIGN_TARGETS.
    max_targets: int = Field(default=400)
    rules_fingerprint: Optional[str] = None
    paused_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class Target(LLMProvenanceMixin, table=True):
    """R1.2 — an investor scored against the startup profile, with cited rationale."""

    __tablename__ = "targets"
    __table_args__ = (
        UniqueConstraint("campaign_id", "investor_id", name="uq_target_campaign_investor"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaigns.id", index=True)
    investor_id: int = Field(foreign_key="investors.id", index=True)
    status: TargetStatus = Field(default=TargetStatus.SCORED, index=True)

    # FitScore — 0-5 per dimension (R1.2)
    stage_score: int = 0
    sector_score: int = 0
    check_size_score: int = 0
    geography_score: int = 0
    thesis_recency_score: int = 0
    portfolio_conflict_score: int = 0
    composite_score: float = Field(default=0.0, index=True)
    #: dimension -> one-line rationale
    rationales: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    #: dimension -> [evidence_id, ...]
    dimension_evidence_ids: dict[str, list[int]] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    evidence_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON))

    # R1.5 — portfolio conflict
    has_portfolio_conflict: bool = Field(default=False, index=True)
    conflict_companies: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    conflict_evidence_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    conflict_override_by: Optional[str] = None
    conflict_override_at: Optional[datetime] = None
    conflict_override_reason: Optional[str] = None

    cohort: Optional[str] = Field(default=None, index=True)
    suppressed_reason: Optional[str] = None

    @property
    def conflict_overridden(self) -> bool:
        """R1.5 — an override needs a named human, a written reason, and a timestamp."""
        return bool(
            self.conflict_override_by
            and self.conflict_override_reason
            and self.conflict_override_at
        )

    @property
    def is_sendable(self) -> bool:
        if self.has_portfolio_conflict and not self.conflict_overridden:
            return False
        return self.status in {
            TargetStatus.QUALIFIED,
            TargetStatus.IN_SEQUENCE,
        }


# --------------------------------------------------------------------------------------
# 5. Composition
# --------------------------------------------------------------------------------------


class Sequence(SQLModel, table=True):
    """R4.1 — the whole cadence is planned as one object at first compose."""

    __tablename__ = "sequences"

    id: Optional[int] = Field(default=None, primary_key=True)
    target_id: int = Field(foreign_key="targets.id", index=True, unique=True)
    planned_touches: int = Field(default=1)
    generated_touches: int = Field(default=0)
    ended: bool = Field(default=False, index=True)
    ended_reason: Optional[str] = None
    ended_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class Draft(LLMProvenanceMixin, table=True):
    __tablename__ = "drafts"
    __table_args__ = (
        UniqueConstraint("target_id", "touch_number", name="uq_draft_target_touch"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    target_id: int = Field(foreign_key="targets.id", index=True)
    sequence_id: Optional[int] = Field(default=None, foreign_key="sequences.id", index=True)
    touch_number: int = Field(default=1, index=True)
    status: DraftStatus = Field(default=DraftStatus.COMPOSING, index=True)

    subject: str = ""
    greeting: str = ""
    body: str = Field(default="", sa_column=Column(Text))
    #: R5.1 — compliance text, excluded from the R2.1 word count.
    footer: str = Field(default="", sa_column=Column(Text))
    word_count: int = Field(default=0, index=True)

    # Slot provenance (R2.2)
    credibility_variant_id: Optional[int] = Field(
        default=None, foreign_key="pitch_variants.id"
    )
    problem_variant_id: Optional[int] = Field(default=None, foreign_key="pitch_variants.id")
    approach_variant_id: Optional[int] = Field(default=None, foreign_key="pitch_variants.id")
    ask_variant_id: Optional[int] = Field(default=None, foreign_key="pitch_variants.id")
    credibility_marker_type: Optional[str] = None
    ask_type: Optional[str] = Field(default=None, index=True)

    # R2.6 — every investor-specific sentence maps to stored evidence.
    #: [{"text": str, "evidence_id": int | None, "investor_specific": bool}]
    claim_map: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    personalization_hook: Optional[str] = Field(default=None, sa_column=Column(Text))
    hook_evidence_id: Optional[int] = Field(default=None, foreign_key="evidence.id")
    evidence_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON))

    # R4.3 — the follow-up's new-information payload.
    update_id: Optional[int] = Field(default=None, foreign_key="updates.id", index=True)

    # R2.4
    novelty_score: Optional[float] = None
    novelty_reason: Optional[str] = None

    # R6.1 — human in the loop
    approved_by: Optional[str] = Field(default=None, index=True)
    approved_at: Optional[datetime] = Field(default=None, index=True)
    rejected_by: Optional[str] = None
    rejected_at: Optional[datetime] = None
    reject_reason: Optional[str] = None
    edited_by: Optional[str] = None
    edited_at: Optional[datetime] = None

    retry_count: int = Field(default=0)
    rules_fingerprint: Optional[str] = None
    variant_key: Optional[str] = Field(default=None, index=True)
    experiment_id: Optional[int] = Field(default=None, foreign_key="experiments.id", index=True)
    scheduled_for: Optional[datetime] = Field(default=None, index=True)

    @property
    def is_approved(self) -> bool:
        """R6.1 — both fields, always. One without the other is not an approval."""
        return self.approved_by is not None and self.approved_at is not None

    @property
    def rendered(self) -> str:
        parts = [p for p in (self.greeting, self.body) if p]
        message = "\n\n".join(parts)
        if self.footer:
            message = f"{message}\n\n--\n{self.footer}"
        return message


class GuardrailResult(SQLModel, table=True):
    """Structured failure reasons — what routes a draft back to compose."""

    __tablename__ = "guardrail_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    draft_id: int = Field(foreign_key="drafts.id", index=True)
    attempt: int = Field(default=1)
    code: GuardrailCode = Field(index=True)
    rule_id: str = Field(index=True)
    passed: bool = Field(index=True)
    detail: str = ""
    observed: Optional[str] = None
    allowed: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------------------
# 6. Sending
# --------------------------------------------------------------------------------------


class Mailbox(SQLModel, table=True):
    """R3.2/R3.3 — a sending identity on the dedicated domain, with a warmup age."""

    __tablename__ = "mailboxes"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    display_name: str = ""
    domain: str = Field(index=True)
    warmup_started_on: date = Field(default_factory=lambda: utcnow().date())
    active: bool = Field(default=True, index=True)
    spf_verified: bool = False
    dkim_verified: bool = False
    dmarc_verified: bool = False
    last_send_at: Optional[datetime] = Field(default=None, index=True)
    consecutive_sends: int = Field(default=0)
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

    def age_days(self, on: date | None = None) -> int:
        return max(0, ((on or utcnow().date()) - self.warmup_started_on).days)


class MailboxDailyQuota(SQLModel, table=True):
    """R3.3 — the persisted ReputationBudget ledger. One row per mailbox per day."""

    __tablename__ = "mailbox_daily_quota"
    __table_args__ = (UniqueConstraint("mailbox_id", "day", name="uq_quota_mailbox_day"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    mailbox_id: int = Field(foreign_key="mailboxes.id", index=True)
    day: date = Field(index=True)
    cap: int
    used: int = Field(default=0)

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.used)


class Send(SQLModel, table=True):
    """Every send is an experiment record (design principle 4)."""

    __tablename__ = "sends"

    id: Optional[int] = Field(default=None, primary_key=True)
    draft_id: int = Field(foreign_key="drafts.id", index=True)
    target_id: int = Field(foreign_key="targets.id", index=True)
    mailbox_id: Optional[int] = Field(default=None, foreign_key="mailboxes.id", index=True)
    to_email: str = Field(index=True)
    subject: str = ""
    body_snapshot: str = Field(default="", sa_column=Column(Text))
    status: SendStatus = Field(default=SendStatus.SCHEDULED, index=True)
    dry_run: bool = Field(default=True, index=True)
    touch_number: int = Field(default=1, index=True)
    scheduled_for: Optional[datetime] = Field(default=None, index=True)
    sent_at: Optional[datetime] = Field(default=None, index=True)
    recipient_timezone: Optional[str] = None
    provider_message_id: Optional[str] = Field(default=None, index=True)
    thread_id: Optional[str] = Field(default=None, index=True)
    error: Optional[str] = None
    reputation_cost: int = Field(default=1)

    # Experiment dimensions
    experiment_id: Optional[int] = Field(default=None, foreign_key="experiments.id", index=True)
    variant_key: Optional[str] = Field(default=None, index=True)
    cohort: Optional[str] = Field(default=None, index=True)

    replied: bool = Field(default=False, index=True)
    replied_at: Optional[datetime] = None
    bounced: bool = Field(default=False, index=True)


class Reply(LLMProvenanceMixin, table=True):
    __tablename__ = "replies"

    id: Optional[int] = Field(default=None, primary_key=True)
    send_id: Optional[int] = Field(default=None, foreign_key="sends.id", index=True)
    target_id: Optional[int] = Field(default=None, foreign_key="targets.id", index=True)
    from_email: str = Field(index=True)
    subject: str = ""
    body_text: str = Field(default="", sa_column=Column(Text))
    received_at: datetime = Field(default_factory=utcnow, index=True)
    classification: ReplyClass = Field(default=ReplyClass.UNKNOWN, index=True)
    confidence: float = 0.0
    reason: Optional[str] = None
    handled_at: Optional[datetime] = None
    handler_action: Optional[str] = None
    provider_message_id: Optional[str] = Field(default=None, index=True)


class Suppression(SQLModel, table=True):
    """R5.2 — checked immediately before every dispatch. Nothing bypasses it."""

    __tablename__ = "suppressions"
    __table_args__ = (UniqueConstraint("scope", "value", name="uq_suppression_scope_value"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    scope: SuppressionScope = Field(default=SuppressionScope.EMAIL, index=True)
    #: Normalized: lowercased email, domain, firm name or investor id as text.
    value: str = Field(index=True)
    reason: SuppressionReason = Field(default=SuppressionReason.MANUAL, index=True)
    permanent: bool = Field(default=True, index=True)
    investor_id: Optional[int] = Field(default=None, foreign_key="investors.id", index=True)
    firm_id: Optional[int] = Field(default=None, foreign_key="firms.id", index=True)
    source: str = "system"
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow, index=True)


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: Optional[int] = Field(default=None, primary_key=True)
    kind: EventKind = Field(index=True)
    entity_type: str = Field(index=True)
    entity_id: Optional[int] = Field(default=None, index=True)
    campaign_id: Optional[int] = Field(default=None, foreign_key="campaigns.id", index=True)
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    actor: str = "system"
    created_at: datetime = Field(default_factory=utcnow, index=True)


class Experiment(SQLModel, table=True):
    """R0.1 — the campaign compounds into a benchmark, not a send count."""

    __tablename__ = "experiments"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    campaign_id: Optional[int] = Field(default=None, foreign_key="campaigns.id", index=True)
    hypothesis: str = ""
    arms: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    baseline_reply_rate: float = 0.04
    ceiling_low: float = 0.13
    ceiling_high: float = 0.17
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: Optional[datetime] = None
    notes: Optional[str] = None


class PromptVersion(SQLModel, table=True):
    """Versioned prompt objects, as in Scout."""

    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("key", "version", name="uq_prompt_key_version"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True)
    version: str = Field(index=True)
    model: str = ""
    template_hash: str = ""
    template_text: str = Field(default="", sa_column=Column(Text))
    output_schema: str = ""
    created_at: datetime = Field(default_factory=utcnow)
