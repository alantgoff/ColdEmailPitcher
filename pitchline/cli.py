"""Typer CLI — the whole pipeline, one phase per command.

Every command that costs money or reputation says what it is about to do and defaults to
the safe option: ``send`` is a dry run unless ``--live`` is passed, and ``--live`` still
refuses any draft without a human approval.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from sqlmodel import Session, select

from pitchline import analytics as analytics_mod
from pitchline import approval as approval_mod
from pitchline import demo as demo_mod
from pitchline import llm, suppression
from pitchline.compose import (
    HumanFixRequired,
    NoUnusedUpdateError,
    compose_first_touch,
    due_followups,
    generate_followup,
    plan_sequence,
)
from pitchline.db import get_engine, init_db, reset_db, session_scope
from pitchline.guardrails import lint_draft
from pitchline.ingest import import_investors_csv
from pitchline.models import (
    Campaign,
    Draft,
    DraftStatus,
    Investor,
    Mailbox,
    StartupProfile,
    Target,
    TargetStatus,
)
from pitchline.research import enrich_campaign
from pitchline.research.store import research_coverage
from pitchline.rules import RULES, RULES_FINGERPRINT
from pitchline.send import Sender, check_deliverability
from pitchline.send.sender import approved_queue
from pitchline.send.transport import DryRunTransport, FileTransport, transport_by_name
from pitchline.targeting import build_campaign, override_conflict, ranked_targets

app = typer.Typer(
    help="Pitchline — founder-side VC outreach. Qualified replies per unit of reputation.",
    no_args_is_help=True,
    add_completion=False,
)


def _echo(message: str = "") -> None:
    typer.echo(message)


def _profile(session: Session, name: Optional[str] = None) -> StartupProfile:
    statement = select(StartupProfile)
    if name:
        statement = statement.where(StartupProfile.name == name)
    profile = session.exec(statement).first()
    if profile is None:
        raise typer.BadParameter("no startup profile found — run `pitchline init --demo` first")
    return profile


def _campaign(session: Session, name: str, *, create_for: StartupProfile | None = None) -> Campaign:
    campaign = session.exec(select(Campaign).where(Campaign.name == name)).first()
    if campaign is None:
        if create_for is None:
            raise typer.BadParameter(f"no campaign named {name!r}")
        campaign = Campaign(
            name=name,
            startup_profile_id=create_for.id,  # type: ignore[arg-type]
            rules_fingerprint=RULES_FINGERPRINT,
        )
        session.add(campaign)
        session.flush()
    return campaign


# --------------------------------------------------------------------------------------
# Setup and inspection
# --------------------------------------------------------------------------------------


@app.command()
def init(
    demo: bool = typer.Option(False, "--demo", help="Seed the demo founder profile and library."),
    reset: bool = typer.Option(False, "--reset", help="Drop and recreate every table."),
) -> None:
    """Create the database (and optionally seed a runnable founder setup)."""
    engine = get_engine()
    reset_db(engine) if reset else init_db(engine)
    _echo(f"database ready ({engine.url})")
    if demo:
        with session_scope(engine) as session:
            profile = demo_mod.seed_all(session)
            _echo(f"seeded profile {profile.name!r}, variant library, updates and mailboxes")


@app.command()
def rules(
    show_checks: bool = typer.Option(True, "--checks/--no-checks", help="List open RULE-CHECKs."),
) -> None:
    """Show the parsed rules file — the single source of truth."""
    _echo(f"{RULES.path}")
    _echo(f"spec {RULES.spec_version}  fingerprint {RULES.fingerprint}  rules {len(RULES)}")
    _echo("")
    section = None
    for rule in RULES:
        if rule.section != section:
            section = rule.section
            _echo(f"§{section} — {rule.section_title}")
        _echo(f"  {rule.id:<6} {rule.severity.value:<9} {rule.title}")
    if show_checks and (checks := RULES.rule_checks()):
        _echo("\nOpen RULE-CHECKs (author review queue):")
        for rule_id, note in checks:
            _echo(f"  {rule_id}: {note[:150]}")


@app.command()
def ingest(
    path: Path = typer.Argument(..., exists=True, help="CSV export to import."),
    limit: Optional[int] = typer.Option(None, help="Import at most N rows."),
) -> None:
    """Import an investor export, resolving to partner-level records with provenance."""
    with session_scope() as session:
        report = import_investors_csv(session, path, limit=limit)
    _echo(report.summary())
    if report.quarantine_reasons:
        _echo("quarantined:")
        for reason, count in sorted(report.quarantine_reasons.items(), key=lambda kv: -kv[1]):
            _echo(f"  {count:>4}  {reason}")
    for error in report.errors[:10]:
        _echo(f"  error: {error}")


@app.command()
def research(
    limit: Optional[int] = typer.Option(None, help="Enrich at most N investors."),
    form_d: bool = typer.Option(False, "--form-d", help="Also query SEC Form D filings."),
) -> None:
    """Fetch and cache public evidence for shortlisted investors (R1.3)."""
    with session_scope() as session:
        report = enrich_campaign(session, limit=limit, include_form_d=form_d)
    _echo(report.summary())
    for error in report.fetch_errors[:10]:
        _echo(f"  {error}")


@app.command()
def coverage(limit: int = typer.Option(10, help="Investors to show.")) -> None:
    """Show R1.3 research coverage — who is ready to be scored, and what is missing."""
    with session_scope() as session:
        investors = list(session.exec(select(Investor).where(Investor.quarantined == False)))  # noqa: E712
        ready = 0
        shown = 0
        for investor in investors:
            report = research_coverage(session, investor.id)  # type: ignore[arg-type]
            if report.meets_floor:
                ready += 1
            elif shown < limit:
                shown += 1
                _echo(f"  {investor.full_name:<28} {report.reason()}")
        _echo(f"{ready}/{len(investors)} investors meet the R1.3 research floor")


# --------------------------------------------------------------------------------------
# Targeting and composition
# --------------------------------------------------------------------------------------


@app.command()
def target(
    campaign: str = typer.Option(..., "--campaign", "-c"),
    limit: Optional[int] = typer.Option(None, help="Score at most N investors."),
    max_targets: Optional[int] = typer.Option(None, help="Campaign cap (R1.1 ceiling applies)."),
) -> None:
    """Score investors into a capped, ranked campaign list (R1.1, R1.2, R1.5)."""
    with session_scope() as session:
        profile = _profile(session)
        camp = _campaign(session, campaign, create_for=profile)
        investor_ids = None
        if limit:
            investor_ids = [
                i.id
                for i in session.exec(
                    select(Investor).where(Investor.quarantined == False)  # noqa: E712
                )
            ][:limit]
        report = build_campaign(
            session,
            campaign=camp,
            profile=profile,
            investor_ids=investor_ids,
            max_targets=max_targets,
        )
    _echo(report.summary())
    for warning in report.warnings:
        _echo(f"  ! {warning}")
    for error in report.errors[:10]:
        _echo(f"  error: {error}")


@app.command("targets")
def list_targets(
    campaign: str = typer.Option(..., "--campaign", "-c"),
    limit: int = typer.Option(20),
    status: Optional[str] = typer.Option(None, help="Filter by target status."),
) -> None:
    """List the ranked target list with per-dimension rationale."""
    with session_scope() as session:
        camp = _campaign(session, campaign)
        statuses = (TargetStatus(status),) if status else (TargetStatus.QUALIFIED, TargetStatus.IN_SEQUENCE)
        for target_row in ranked_targets(session, camp.id, statuses=statuses, limit=limit):  # type: ignore[arg-type]
            investor = session.get(Investor, target_row.investor_id)
            _echo(
                f"{target_row.composite_score:>5.2f}  {investor.full_name:<26} "
                f"{target_row.status.value:<20} evidence={len(target_row.evidence_ids)}"
            )
            for dimension, rationale in target_row.rationales.items():
                cited = target_row.dimension_evidence_ids.get(dimension, [])
                _echo(f"         {dimension:<18} {rationale} {('[e' + ','.join(map(str, cited)) + ']') if cited else ''}")


@app.command()
def compose(
    campaign: str = typer.Option(..., "--campaign", "-c"),
    limit: int = typer.Option(20, help="Compose at most N first touches."),
) -> None:
    """Compose first touches and run them through the guardrail gate."""
    composed = failed = 0
    with session_scope() as session:
        profile = _profile(session)
        camp = _campaign(session, campaign)
        for target_row in ranked_targets(session, camp.id, limit=limit):  # type: ignore[arg-type]
            plan_sequence(session, target_row)
            try:
                compose_first_touch(session, target=target_row, profile=profile)
                composed += 1
            except HumanFixRequired as exc:
                failed += 1
                _echo(f"  needs human fix: draft {exc.draft.id} — {', '.join(c.value for c in exc.report.codes)}")
            except Exception as exc:
                failed += 1
                _echo(f"  compose error: {exc}")
    _echo(f"{composed} drafts passed every gate, {failed} routed to the human-fix queue")


@app.command()
def followups(
    campaign: str = typer.Option(..., "--campaign", "-c"),
    limit: int = typer.Option(20),
) -> None:
    """Generate due follow-ups. A follow-up with no unused update is not generated (R4.3)."""
    generated = skipped = 0
    with session_scope() as session:
        profile = _profile(session)
        camp = _campaign(session, campaign)
        for due in due_followups(session, campaign_id=camp.id)[:limit]:  # type: ignore[arg-type]
            try:
                draft = generate_followup(
                    session, target=due.target, profile=profile, touch_number=due.touch_number
                )
                generated += 1
                _echo(f"  touch {draft.touch_number} drafted for target {due.target.id}")
            except NoUnusedUpdateError as exc:
                skipped += 1
                _echo(f"  target {due.target.id}: {exc}")
            except HumanFixRequired as exc:
                skipped += 1
                _echo(f"  target {due.target.id}: draft {exc.draft.id} needs a human")
    _echo(f"{generated} follow-ups generated, {skipped} sequences ended or skipped")


# --------------------------------------------------------------------------------------
# Approval queue (R6.1)
# --------------------------------------------------------------------------------------


@app.command()
def queue(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c"),
    include_failed: bool = typer.Option(False, "--include-failed"),
) -> None:
    """List drafts awaiting human approval."""
    statuses = (DraftStatus.PENDING_APPROVAL,)
    if include_failed:
        statuses = (DraftStatus.PENDING_APPROVAL, DraftStatus.NEEDS_HUMAN_FIX)
    with session_scope() as session:
        campaign_id = _campaign(session, campaign).id if campaign else None
        drafts = approval_mod.queue(session, campaign_id=campaign_id, statuses=statuses)
        for draft in drafts:
            target_row = session.get(Target, draft.target_id)
            investor = session.get(Investor, target_row.investor_id) if target_row else None
            _echo(
                f"#{draft.id:<4} touch {draft.touch_number}  {draft.status.value:<18} "
                f"{(investor.full_name if investor else '?'):<26} {draft.word_count:>3}w  "
                f"novelty {draft.novelty_score}"
            )
        _echo(f"{len(drafts)} drafts in the queue")


@app.command()
def show(draft_id: int = typer.Argument(...)) -> None:
    """Print a draft exactly as it would be sent, with its provenance."""
    with session_scope() as session:
        draft = session.get(Draft, draft_id)
        if draft is None:
            raise typer.BadParameter(f"no draft {draft_id}")
        target_row = session.get(Target, draft.target_id)
        investor = session.get(Investor, target_row.investor_id) if target_row else None
        _echo(f"To: {investor.email if investor else '?'}")
        _echo(f"Subject: {draft.subject}")
        _echo("-" * 72)
        _echo(draft.rendered)
        _echo("-" * 72)
        _echo(f"status={draft.status.value} words={draft.word_count} novelty={draft.novelty_score}")
        _echo(f"variant={draft.variant_key} rules={draft.rules_fingerprint}")
        for claim in draft.claim_map:
            if claim.get("investor_specific"):
                _echo(f"  sourced claim -> evidence {claim.get('evidence_id')}: {claim.get('text', '')[:90]}")


@app.command()
def approve(
    draft_id: int = typer.Argument(...),
    by: str = typer.Option(..., "--by", help="Your name. R6.1 requires a human."),
) -> None:
    """Approve one email. There is no batch approval."""
    with session_scope() as session:
        draft = session.get(Draft, draft_id)
        if draft is None:
            raise typer.BadParameter(f"no draft {draft_id}")
        approval_mod.approve(session, draft, approved_by=by)
    _echo(f"draft {draft_id} approved by {by}")


@app.command()
def reject(
    draft_id: int = typer.Argument(...),
    by: str = typer.Option(..., "--by"),
    reason: str = typer.Option(..., "--reason"),
) -> None:
    """Reject a draft."""
    with session_scope() as session:
        draft = session.get(Draft, draft_id)
        if draft is None:
            raise typer.BadParameter(f"no draft {draft_id}")
        approval_mod.reject(session, draft, rejected_by=by, reason=reason)
    _echo(f"draft {draft_id} rejected")


@app.command()
def lint(draft_id: int = typer.Argument(...)) -> None:
    """Re-run every guardrail against a draft and print the structured result."""
    with session_scope() as session:
        draft = session.get(Draft, draft_id)
        if draft is None:
            raise typer.BadParameter(f"no draft {draft_id}")
        report = lint_draft(session, draft, profile=_profile(session))
    _echo(report.describe())


@app.command("override-conflict")
def override_conflict_cmd(
    target_id: int = typer.Argument(...),
    by: str = typer.Option(..., "--by"),
    reason: str = typer.Option(..., "--reason"),
) -> None:
    """Explicitly override a portfolio-conflict suppression (R1.5). Human only."""
    with session_scope() as session:
        target_row = session.get(Target, target_id)
        if target_row is None:
            raise typer.BadParameter(f"no target {target_id}")
        override_conflict(session, target_row, approved_by=by, reason=reason)
    _echo(f"target {target_id} conflict overridden by {by}")


# --------------------------------------------------------------------------------------
# Sending
# --------------------------------------------------------------------------------------


@app.command()
def mailboxes() -> None:
    """Show each mailbox's warmup age and today's remaining reputation budget."""
    from pitchline.send.budget import ReputationBudget

    with session_scope() as session:
        for mailbox in session.exec(select(Mailbox)):
            budget = ReputationBudget(session, mailbox)
            _echo(
                f"{mailbox.email:<38} age {mailbox.age_days():>3}d  "
                f"{budget.used}/{budget.cap} used today  {budget.remaining} left"
            )


@app.command()
def send(
    campaign: str = typer.Option(..., "--campaign", "-c"),
    live: bool = typer.Option(False, "--live", help="Actually dispatch. Requires a live transport."),
    transport: str = typer.Option("dry_run", help="dry_run | file | smtp | gmail"),
    outbox: Path = typer.Option(Path("outbox"), help="Directory for the file transport."),
    limit: int = typer.Option(50),
    ignore_window: bool = typer.Option(
        False, "--ignore-window", help="Skip the R4.5 send-window check (testing only)."
    ),
    pace: bool = typer.Option(
        False, "--pace", help="Wait out the R3.3 spacing instead of stopping the run."
    ),
) -> None:
    """Dispatch approved drafts under the reputation budget."""
    kwargs = {"directory": outbox} if transport == "file" else {}
    engine = get_engine()
    with session_scope(engine) as session:
        camp = _campaign(session, campaign)
        drafts = approved_queue(session, campaign_id=camp.id)[:limit]
        if not drafts:
            _echo("nothing approved to send — approve drafts first (R6.1)")
            return
        sender = Sender(
            session,
            transport=transport_by_name(transport, **kwargs) if transport != "dry_run" else DryRunTransport(),
            dry_run=not live,
        )
        report = sender.send_batch(drafts, enforce_window=not ignore_window, pace=pace)
    _echo(report.summary())
    if report.paced_waits:
        _echo(f"  paced {report.paced_waits} sends to respect the R3.3 gap")
    for error in report.errors[:12]:
        _echo(f"  {error}")


@app.command()
def tick(
    campaign: str = typer.Option(..., "--campaign", "-c"),
    live: bool = typer.Option(False, "--live"),
    batch: int = typer.Option(5, help="Sends per tick."),
) -> None:
    """Run one scheduler tick: follow-ups, then a small batch, inside every rule."""
    from pitchline.send.scheduler import run_once

    report = run_once(campaign_name=campaign, dry_run=not live, batch_size=batch)
    _echo(report.describe())
    for error in report.errors[:10]:
        _echo(f"  {error}")


@app.command()
def monitor(campaign: Optional[str] = typer.Option(None, "--campaign", "-c")) -> None:
    """Check the rolling deliverability monitor (R3.6)."""
    with session_scope() as session:
        campaign_id = _campaign(session, campaign).id if campaign else None
        alarm = check_deliverability(session, campaign_id=campaign_id)
    _echo(alarm.describe())


@app.command()
def suppress(
    email: str = typer.Argument(...),
    reason: str = typer.Option("manual", help="pass_reply | unsubscribe | hard_bounce | manual"),
) -> None:
    """Add an address to the global suppression list."""
    from pitchline.models import SuppressionReason

    with session_scope() as session:
        suppression.add(session, value=email, reason=SuppressionReason(reason), source="cli")
    _echo(f"{email} suppressed ({reason})")


# --------------------------------------------------------------------------------------
# Inbox and analytics
# --------------------------------------------------------------------------------------


@app.command()
def inbox(
    directory: Optional[Path] = typer.Option(None, "--dir", help="Maildir of .eml files."),
    imap_host: Optional[str] = typer.Option(None, "--imap-host"),
    imap_user: Optional[str] = typer.Option(None, "--imap-user"),
    imap_password: Optional[str] = typer.Option(None, "--imap-password"),
    limit: int = typer.Option(100),
) -> None:
    """Poll replies, classify them, and apply CRM transitions."""
    from pitchline.inbox import IMAPPoller, MaildirPoller, poll_and_process

    if imap_host:
        poller = IMAPPoller(host=imap_host, username=imap_user or "", password=imap_password or "")
    else:
        poller = MaildirPoller(directory=directory or Path("inbox"))

    with session_scope() as session:
        outcomes = poll_and_process(session, poller, profile=_profile(session), limit=limit)
    for outcome in outcomes:
        _echo(f"  reply {outcome.reply_id}: {outcome.describe()}")
        if outcome.suggested_response:
            _echo("    suggested reply drafted (deck + calendar)")
    _echo(f"{len(outcomes)} replies processed")


@app.command()
def stats(campaign: Optional[str] = typer.Option(None, "--campaign", "-c")) -> None:
    """Reply rates by variant and cohort against the 4% / 13-17% benchmarks."""
    with session_scope() as session:
        campaign_id = _campaign(session, campaign).id if campaign else None
        result = analytics_mod.campaign_analytics(session, campaign_id)
        _echo(result.describe())
        if campaign_id:
            _echo("\nFunnel:")
            for key, value in analytics_mod.funnel(session, campaign_id).items():
                _echo(f"  {key:<32} {value}")


@app.command()
def demo(
    csv_path: Path = typer.Option(Path("data/sample_investors.csv"), "--csv"),
    campaign: str = typer.Option("demo", "--campaign", "-c"),
    investors: int = typer.Option(60, help="How many investors to score."),
    drafts: int = typer.Option(10, help="How many drafts to compose."),
) -> None:
    """Run the whole pipeline end to end in dry-run mode."""
    _echo("1. init + seed")
    init(demo=True, reset=True)
    _echo("\n2. ingest")
    ingest(csv_path, limit=None)
    _echo("\n3. target")
    target(campaign=campaign, limit=investors, max_targets=None)
    _echo("\n4. compose")
    compose(campaign=campaign, limit=drafts)
    _echo("\n5. approval queue")
    queue(campaign=campaign, include_failed=False)
    _echo("\n(approve with: pitchline approve <id> --by 'Your Name')")
    _echo("\n6. mailboxes")
    mailboxes()
    _echo("\n7. stats")
    stats(campaign=campaign)


if __name__ == "__main__":
    app()
