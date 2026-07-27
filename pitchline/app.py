"""Streamlit approval queue — the human-in-the-loop surface (R6.1).

Run with: ``streamlit run pitchline/app.py``

The page shows the email exactly as it will arrive, and next to it the evidence behind
every investor-specific sentence. That pairing is the point: a founder cannot meaningfully
approve a claim without seeing what it rests on. Approve is per email; editing re-runs the
guardrails and clears the approval.
"""

from __future__ import annotations

import streamlit as st
from sqlmodel import Session, select

from pitchline import analytics as analytics_mod
from pitchline import approval as approval_mod
from pitchline.db import get_engine, init_db
from pitchline.guardrails import lint_draft
from pitchline.models import (
    Campaign,
    Draft,
    DraftStatus,
    Evidence,
    Firm,
    Investor,
    Mailbox,
    StartupProfile,
    Target,
)
from pitchline.rules import MAX_PITCH_WORDS, MIN_NOVELTY_SCORE, RULES_FINGERPRINT
from pitchline.send.budget import ReputationBudget

st.set_page_config(page_title="Pitchline — approval queue", layout="wide")


@st.cache_resource
def _engine():
    engine = get_engine()
    init_db(engine)
    return engine


def _session() -> Session:
    return Session(_engine())


def _profile(session: Session) -> StartupProfile | None:
    return session.exec(select(StartupProfile)).first()


def _md(text: str) -> str:
    """Escape `$` so Streamlit does not read "$500k-$2M" as LaTeX math."""
    return (text or "").replace("$", "\\$")


def _who() -> str:
    """R6.1 — approvals are attributable, so the reviewer names themselves once."""
    return st.sidebar.text_input("Reviewing as", value=st.session_state.get("reviewer", ""))


def sidebar(session: Session) -> tuple[str | None, str]:
    st.sidebar.title("Pitchline")
    st.sidebar.caption(f"rules {RULES_FINGERPRINT}")

    campaigns = list(session.exec(select(Campaign)))
    names = [c.name for c in campaigns]
    selected = st.sidebar.selectbox("Campaign", names) if names else None

    reviewer = _who()
    st.session_state["reviewer"] = reviewer

    st.sidebar.divider()
    st.sidebar.subheader("Reputation today")
    for mailbox in session.exec(select(Mailbox).where(Mailbox.active == True)):  # noqa: E712
        budget = ReputationBudget(session, mailbox)
        st.sidebar.progress(
            min(1.0, budget.used / budget.cap if budget.cap else 1.0),
            text=f"{mailbox.email} — {budget.used}/{budget.cap}",
        )
    return selected, reviewer


def draft_card(session: Session, draft: Draft, profile: StartupProfile | None, reviewer: str) -> None:
    target = session.get(Target, draft.target_id)
    investor = session.get(Investor, target.investor_id) if target else None
    firm = session.get(Firm, investor.firm_id) if investor and investor.firm_id else None

    header = f"#{draft.id} · touch {draft.touch_number} · {investor.full_name if investor else '?'}"
    if firm:
        header += f" ({firm.name})"

    with st.expander(header, expanded=False):
        left, right = st.columns([3, 2])

        with left:
            st.caption(f"To: {investor.email if investor else '—'}")
            subject = st.text_input("Subject", draft.subject, key=f"subject_{draft.id}")
            body = st.text_area("Body", draft.body, height=260, key=f"body_{draft.id}")
            st.caption(f"Footer (CAN-SPAM, excluded from the {MAX_PITCH_WORDS}-word count)")
            st.code(draft.footer or "(none)", language=None)

            words = len(f"{draft.greeting} {body}".split())
            metrics = st.columns(3)
            metrics[0].metric("Words", words, delta=words - MAX_PITCH_WORDS)
            metrics[1].metric("Novelty", draft.novelty_score or 0.0, delta=round((draft.novelty_score or 0) - MIN_NOVELTY_SCORE, 2))
            metrics[2].metric("Fit", round(target.composite_score, 2) if target else 0.0)

            actions = st.columns(4)
            if actions[0].button("Approve", key=f"approve_{draft.id}", type="primary"):
                try:
                    approval_mod.approve(session, draft, approved_by=reviewer)
                    session.commit()
                    st.success(f"approved by {reviewer}")
                    st.rerun()
                except approval_mod.ApprovalError as exc:
                    st.error(str(exc))

            if actions[1].button("Save edit & re-lint", key=f"edit_{draft.id}"):
                try:
                    _, report = approval_mod.edit(
                        session, draft, edited_by=reviewer, body=body, subject=subject,
                        profile=profile,
                    )
                    session.commit()
                    if report.passed:
                        st.success("edit saved; guardrails pass. Approval cleared — approve again.")
                    else:
                        st.error(_md(report.describe()))
                    st.rerun()
                except approval_mod.ApprovalError as exc:
                    st.error(str(exc))

            reason = actions[2].text_input("Reject reason", key=f"reason_{draft.id}", label_visibility="collapsed", placeholder="reason")
            if actions[3].button("Reject", key=f"reject_{draft.id}"):
                try:
                    approval_mod.reject(session, draft, rejected_by=reviewer, reason=reason or "no reason given")
                    session.commit()
                    st.rerun()
                except approval_mod.ApprovalError as exc:
                    st.error(str(exc))

        with right:
            st.markdown("**Evidence behind this email** (R2.6)")
            for claim in draft.claim_map:
                if not claim.get("investor_specific"):
                    continue
                evidence = session.get(Evidence, claim.get("evidence_id")) if claim.get("evidence_id") else None
                st.markdown(f"> {_md(str(claim.get('text', '')))}")
                if evidence is None:
                    st.error("unsourced claim — this draft cannot be approved")
                else:
                    st.caption(f"evidence #{evidence.id} · {evidence.area.value} · {evidence.url or 'no url'}")
                    st.text(evidence.excerpt or evidence.raw_text[:400])  # st.text is literal; no escaping needed

            if target and target.rationales:
                st.markdown("**Why this investor** (R1.2)")
                for dimension, rationale in target.rationales.items():
                    st.caption(_md(f"{dimension}: {rationale}"))

            report = lint_draft(session, draft, profile=profile, include_novelty=False)
            st.markdown("**Guardrails**")
            if report.passed:
                st.success(f"{len(report.checks_run)} checks passed")
            else:
                for failure in report.failures:
                    st.error(_md(failure.describe()))


def main() -> None:
    with _session() as session:
        campaign_name, reviewer = sidebar(session)
        profile = _profile(session)

        st.title("Approval queue")
        st.caption(
            "Nothing sends without an explicit approval on this page (R6.1). "
            "Editing a draft clears its approval and re-runs every guardrail."
        )

        campaign = (
            session.exec(select(Campaign).where(Campaign.name == campaign_name)).first()
            if campaign_name
            else None
        )

        tabs = st.tabs(["Pending", "Needs human fix", "Approved", "Analytics"])

        with tabs[0]:
            drafts = approval_mod.queue(
                session, campaign_id=campaign.id if campaign else None
            )
            if not reviewer:
                st.warning("Enter your name in the sidebar before approving anything.")
            st.write(f"{len(drafts)} drafts waiting")
            for draft in drafts:
                draft_card(session, draft, profile, reviewer)

        with tabs[1]:
            broken = approval_mod.queue(
                session,
                campaign_id=campaign.id if campaign else None,
                statuses=(DraftStatus.NEEDS_HUMAN_FIX,),
            )
            st.write(f"{len(broken)} drafts the machine could not fix")
            for draft in broken:
                draft_card(session, draft, profile, reviewer)

        with tabs[2]:
            approved = approval_mod.queue(
                session,
                campaign_id=campaign.id if campaign else None,
                statuses=(DraftStatus.APPROVED,),
            )
            st.write(f"{len(approved)} approved and awaiting dispatch")
            for draft in approved:
                target = session.get(Target, draft.target_id)
                investor = session.get(Investor, target.investor_id) if target else None
                st.write(
                    f"#{draft.id} · {investor.full_name if investor else '?'} · "
                    f"approved by {draft.approved_by} at {draft.approved_at}"
                )
            st.info("Dispatch from the CLI: `pitchline send --campaign <name>` (add --live to send).")

        with tabs[3]:
            result = analytics_mod.campaign_analytics(session, campaign.id if campaign else None)
            st.metric("Qualified reply rate", f"{result.overall.qualified_rate:.1%}")
            st.caption(result.overall.verdict)
            st.metric(
                "Qualified replies per 100 units of reputation",
                result.qualified_per_100_reputation,
            )
            if result.by_variant:
                st.dataframe([block.row() for block in result.by_variant.values()])


if __name__ == "__main__":
    # `streamlit run pitchline/app.py` executes this file as __main__.
    main()
