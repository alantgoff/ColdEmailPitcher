"""Build the shareable review console from the live campaign database.

The Streamlit app in ``pitchline/app.py`` is the operating surface: it writes approvals
back to the database. This builds a *read-and-decide* page instead — one self-contained
HTML file with the drafts, their evidence and their scoring baked in, so it can be handed
to a co-founder or an advisor who has no checkout and no database.

Decisions made in the page export as a list of ``pitchline approve``/``reject`` commands,
which you run here. That keeps the rule intact: approval is still recorded per email
against a named human, by the engine, not by a web page.

    python scripts/build_review_console.py --campaign pad-seed --out web/console.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import select

from pitchline.analytics import funnel
from pitchline.db import get_engine, session_scope
from pitchline.guardrails import lint_draft
from pitchline.models import (
    Campaign, Draft, DraftStatus, Evidence, Firm, Investor, PitchVariant,
    StartupProfile, Target, TargetStatus, Update,
)
from pitchline.rules import MAX_PITCH_WORDS, MIN_NOVELTY_SCORE, RULES, RULES_FINGERPRINT

SHELL = Path(__file__).resolve().parent.parent / "web" / "review_console.html"


def collect(campaign_name: str) -> dict:
    with session_scope(get_engine()) as session:
        profile = session.exec(select(StartupProfile)).first()
        campaign = session.exec(select(Campaign).where(Campaign.name == campaign_name)).first()
        if campaign is None:
            raise SystemExit(f"no campaign named {campaign_name!r}")

        out: dict = {
            "profile": {
                "name": profile.name, "one_liner": profile.one_liner,
                "stage": profile.stage.value, "raising": profile.raising_usd,
                "check_min": profile.target_check_min_usd,
                "check_max": profile.target_check_max_usd,
                "geography": profile.geography, "postal": profile.postal_address,
                "deck": profile.deck_url, "cal": profile.calendar_url,
            },
            "rules": {
                "fingerprint": RULES_FINGERPRINT, "max_words": MAX_PITCH_WORDS,
                "min_novelty": MIN_NOVELTY_SCORE, "count": len(RULES),
            },
            "funnel": funnel(session, campaign.id),
            "drafts": [],
        }

        for draft in session.exec(select(Draft).where(Draft.status == DraftStatus.PENDING_APPROVAL)):
            target = session.get(Target, draft.target_id)
            if target is None or target.campaign_id != campaign.id:
                continue
            investor = session.get(Investor, target.investor_id)
            firm = session.get(Firm, investor.firm_id) if investor.firm_id else None
            report = lint_draft(session, draft, profile=profile)

            claims = []
            for claim in draft.claim_map:
                if not claim.get("investor_specific"):
                    continue
                evidence = (
                    session.get(Evidence, claim["evidence_id"]) if claim.get("evidence_id") else None
                )
                claims.append({
                    "text": claim["text"], "evidence_id": claim.get("evidence_id"),
                    "area": evidence.area.value if evidence else None,
                    "kind": evidence.kind.value if evidence else None,
                    "url": evidence.url if evidence else None,
                    "title": evidence.title if evidence else None,
                    "excerpt": (evidence.excerpt or evidence.raw_text)[:300] if evidence else None,
                })

            out["drafts"].append({
                "id": draft.id, "touch": draft.touch_number, "subject": draft.subject,
                "greeting": draft.greeting, "body": draft.body, "footer": draft.footer,
                "words": draft.word_count, "novelty": draft.novelty_score,
                "variant": draft.variant_key, "ask_type": draft.ask_type,
                "marker": draft.credibility_marker_type,
                "checks": len(report.checks_run), "passed": report.passed,
                "investor": {
                    "name": investor.full_name, "email": investor.email,
                    "role": investor.role.value, "firm": firm.name if firm else None,
                    "city": investor.city, "tz": investor.timezone,
                    "stages": investor.stages, "sectors": investor.sectors,
                    "check_min": investor.check_size_min_usd,
                    "check_max": investor.check_size_max_usd,
                },
                "fit": {
                    "composite": round(target.composite_score, 2),
                    "rationales": target.rationales, "cited": target.dimension_evidence_ids,
                    "scores": {
                        "stage": target.stage_score, "sector": target.sector_score,
                        "check_size": target.check_size_score,
                        "geography": target.geography_score,
                        "thesis_recency": target.thesis_recency_score,
                        "portfolio_conflict": target.portfolio_conflict_score,
                    },
                },
                "claims": claims,
            })

        out["drafts"].sort(key=lambda d: (-d["fit"]["composite"], d["id"]))

        out["suppressed"] = []
        for target in session.exec(
            select(Target).where(
                Target.campaign_id == campaign.id,
                Target.status == TargetStatus.SUPPRESSED_CONFLICT,
            )
        ):
            investor = session.get(Investor, target.investor_id)
            firm = session.get(Firm, investor.firm_id) if investor.firm_id else None
            out["suppressed"].append({
                "name": investor.full_name, "firm": firm.name if firm else None,
                "companies": target.conflict_companies,
                "composite": round(target.composite_score, 2),
            })
        out["suppressed"] = out["suppressed"][:8]

        out["variants"] = [
            {"slot": v.slot.value, "key": v.key, "label": v.label, "text": v.body_text,
             "marker": v.marker_type, "ask": v.ask_type}
            for v in session.exec(select(PitchVariant))
        ]
        out["updates"] = [
            {"headline": u.headline, "body": u.body_text, "category": u.category,
             "on": str(u.occurred_on)}
            for u in session.exec(select(Update))
        ]
        return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--out", type=Path, default=Path("web/console.html"))
    parser.add_argument("--shell", type=Path, default=SHELL)
    args = parser.parse_args()

    payload = json.dumps(collect(args.campaign), separators=(",", ":"))
    if "</script" in payload:
        raise SystemExit("payload contains a script terminator; refusing to build")

    shell = args.shell.read_text(encoding="utf-8")
    if "__PAYLOAD__" not in shell:
        raise SystemExit(f"{args.shell} has no __PAYLOAD__ placeholder")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(shell.replace("__PAYLOAD__", payload), encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
