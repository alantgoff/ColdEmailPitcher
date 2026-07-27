"""Audit the researched investor universe and emit a tiered, defensible list.

The universe was assembled to a target count. That is the exact pressure under which weak
records get in, so this pass grades every record against what the round actually needs —
a fund that can write a seed cheque, into a consumer food business, in a jurisdiction that
makes sense — and drops the ones that cannot.

    python scripts/audit_investors.py                 # report
    python scripts/audit_investors.py --write-csv     # also emit the Tier A/B CSV
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.investor_audit_2026 import (  # noqa: E402
    ADDITIONS, ADJACENT_SECTORS, CONFIRMED_CONTACTS, CORE_SECTORS, CORRECTIONS,
    NON_US_HINTS, OFF_THESIS_SECTORS, RELATED_ENTITIES, REMOVE, VERIFIED_FINDINGS,
)
from data.investor_universe_2026 import ALL_RECORDS, SEGMENT_LABELS  # noqa: E402
from data.investor_universe_supplement import ALL_SUPPLEMENT, SUPPLEMENT_CONTACTS  # noqa: E402

#: Every contact re-verified or newly sourced against a public page.
VERIFIED_CONTACTS = {**CONFIRMED_CONTACTS, **SUPPLEMENT_CONTACTS}

SEED_TOKENS = ("pre-seed", "seed", "early stage")


def seed_capable(record: dict) -> bool:
    """Can this investor write into a $2.5M seed at all?

    A growth or buyout fund is a perfectly real investor and a completely wrong recipient:
    they have a mandate that starts at a cheque size this round does not have. Cold-emailing
    them costs sender reputation for a structurally impossible outcome.
    """
    stages = (record.get("stages") or "").lower()
    return any(token in stages for token in SEED_TOKENS)


def sector_class(record: dict) -> str:
    """Core = the fund's own words name this business. Adjacent = you have to argue it.

    Matched against the declared SECTORS, not the thesis prose: a thesis that mentions
    "food" in passing is not a food fund, and letting prose vote here was what pushed
    two thirds of the list into the top tier.
    """
    sectors = (record.get("sectors") or "").lower()
    if any(term in sectors for term in CORE_SECTORS):
        return "core"
    thesis = (record.get("thesis") or "").lower()
    # A thesis that names the category twice over is evidence too, just weaker.
    if sum(1 for term in CORE_SECTORS if term in thesis) >= 2:
        return "core"
    if any(term in sectors for term in ADJACENT_SECTORS):
        return "adjacent"
    return "off"


def off_thesis(record: dict) -> bool:
    sectors = (record.get("sectors") or "").lower()
    if any(term in sectors for term in CORE_SECTORS):
        return False
    return any(term in sectors for term in OFF_THESIS_SECTORS)


def non_us(record: dict) -> bool:
    """Outside the US. Reads the shared NON_US_HINTS list rather than a private literal —
    the previous version hardcoded the check and left the constant dead."""
    country = record.get("country") or ""
    return country in NON_US_HINTS


def apply_audit(records: list[dict]) -> list[dict]:
    """Remove what the audit disproved, correct what it found wrong, add what it found."""
    out: list[dict] = []
    for record in records:
        if record["firm"] in REMOVE:
            continue
        record = dict(record)
        correction = CORRECTIONS.get(record["firm"])
        if correction:
            for key, value in correction.items():
                if key == "finding":
                    continue
                record[key] = value
        out.append(record)
    out.extend(dict(a) for a in ADDITIONS)
    # Second research pass. Partner additions duplicate a firm deliberately: one record per
    # named person, which is what R1.4 wants. The "contact one" flag below stops that from
    # turning into three emails to the same fund.
    out.extend(dict(a) for a in ALL_SUPPLEMENT)
    return out


def grade(record: dict) -> tuple[str, list[str]]:
    """Return (tier, reasons). Tier C means: do not spend a send on this."""
    reasons: list[str] = []

    if not seed_capable(record):
        reasons.append("cannot write a seed cheque (growth/buyout mandate)")
        return "C", reasons
    if off_thesis(record):
        reasons.append("declared focus is outside consumer food/hospitality")
        return "C", reasons

    klass = sector_class(record)
    if klass == "off":
        reasons.append("no consumer or food signal in the stated focus")
        return "C", reasons

    if record.get("segment") == "accelerator":
        reasons.append("accelerator — apply through their programme, do not cold email")
        return "B", reasons

    if non_us(record):
        reasons.append("outside the US; unlikely to lead a first US seed")
        return "B", reasons

    if klass == "core":
        tier = "A"
    else:
        tier = "B"
        reasons.append("consumer-adjacent rather than food/hospitality specific")

    if not record.get("thesis"):
        reasons.append("no stated thesis on record")
        tier = "B"
    if not record.get("portfolio") and not record.get("recent_activity"):
        reasons.append("thin evidence — no portfolio or recent activity captured")
    if record.get("partner_name") in VERIFIED_CONTACTS:
        reasons.append("contact verified during the audit")
    elif record.get("partner_name"):
        reasons.append("contact NOT re-verified — check before sending")
    if record.get("_siblings", 0) > 1:
        reasons.append(
            f"{record['_siblings']} partners known at this firm — contact one, not all"
        )
    if record["firm"] in RELATED_ENTITIES:
        reasons.append(f"shares a principal with {RELATED_ENTITIES[record['firm']]} — contact one")

    return tier, reasons


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-csv", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("data/investors_audited.csv"))
    args = parser.parse_args()

    print("=" * 78)
    print("VERIFIED DEFECTS")
    print("=" * 78)
    for finding in VERIFIED_FINDINGS:
        print(f"\n[{finding['id']}] {finding['severity'].upper()} — {finding['record']}")
        print(f"  claimed : {finding['claim_was']}")
        print(f"  actual  : {finding['truth']}")
        print(f"  impact  : {finding['impact']}")
        print(f"  source  : {finding['source']}")
        print(f"  action  : {finding['action']}")

    audited = apply_audit(ALL_RECORDS)
    counts_by_firm = Counter(r["firm"] for r in audited if r.get("partner_name"))
    for record in audited:
        record["_siblings"] = counts_by_firm.get(record["firm"], 0)
    graded = [(r, *grade(r)) for r in audited]

    print("\n" + "=" * 78)
    print("TIERING")
    print("=" * 78)
    tiers = Counter(t for _, t, _ in graded)
    print(f"  started with        {len(ALL_RECORDS)} records")
    print(f"  removed as invalid  {len(REMOVE)}")
    print(f"  added by the audit  {len(ADDITIONS)}")
    print(f"  now grading         {len(audited)}")
    print()
    print(f"  Tier A — worth a cold email       {tiers['A']}")
    print(f"  Tier B — plausible, with caveats  {tiers['B']}")
    print(f"  Tier C — do not spend a send      {tiers['C']}")

    print("\nWhy Tier C:")
    for reason, count in Counter(
        rs[0] for _, t, rs in graded if t == "C" and rs
    ).most_common():
        print(f"  {count:>4}  {reason}")

    print("\nTier A by segment:")
    for segment, count in Counter(
        r.get("segment") for r, t, _ in graded if t == "A"
    ).most_common():
        print(f"  {count:>4}  {SEGMENT_LABELS.get(segment, segment)}")

    named = [r for r, t, _ in graded if t in ("A", "B") and r.get("partner_name")]
    verified = [r for r in named if r["partner_name"] in VERIFIED_CONTACTS]
    print(f"\nNamed contacts in Tier A/B: {len(named)}  "
          f"({len(verified)} re-verified during this audit)")
    for record in named:
        mark = "verified  " if record["partner_name"] in VERIFIED_CONTACTS else "UNCHECKED "
        print(f"  {mark}{record['partner_name']:<22} {record['firm'] or '(angel)'}")

    # The real ceiling on this list is not fit, it is evidence: R1.3 refuses to write to
    # anyone whose portfolio, thesis and recent activity are not all on file.
    draftable = [
        r for r, t, _ in graded
        if t in ("A", "B") and r.get("partner_name")
        and r.get("thesis") and r.get("portfolio") and r.get("recent_activity")
    ]
    print(f"\nCould produce a draft today (named + full R1.3 evidence): {len(draftable)}")
    for record in draftable:
        print(f"  {record['partner_name']:<22} {record['firm']}")

    print("\nTop of Tier A:")
    for record, tier, _ in [g for g in graded if g[1] == "A"][:15]:
        print(f"  {record['firm'][:40]:<40} {(record.get('city') or '-')[:16]:<16} "
              f"{(record.get('sectors') or '')[:38]}")

    if args.write_csv:
        keep = [(r, t, rs) for r, t, rs in graded if t in ("A", "B")]
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "Tier", "Full Name", "Firm", "Title", "Email", "Email Confidence",
                    "City", "Country", "Timezone", "Investment Stages", "Sectors",
                    "Check Size Min", "Check Size Max", "Thesis", "Portfolio Companies",
                    "Recent Investments", "Recent Writing", "Segment", "Audit Notes",
                ],
            )
            writer.writeheader()
            for record, tier, reasons in keep:
                writer.writerow({
                    "Tier": tier,
                    "Full Name": record.get("partner_name", ""),
                    "Firm": "" if record.get("segment") == "angel" else record["firm"],
                    "Title": record.get("partner_role", ""),
                    "Email": "",
                    "Email Confidence": "unknown",
                    "City": record.get("city", ""),
                    "Country": record.get("country", ""),
                    "Timezone": record.get("timezone", ""),
                    "Investment Stages": record.get("stages", ""),
                    "Sectors": record.get("sectors", ""),
                    "Check Size Min": record.get("check_min", ""),
                    "Check Size Max": record.get("check_max", ""),
                    "Thesis": record.get("thesis", ""),
                    "Portfolio Companies": record.get("portfolio", ""),
                    "Recent Investments": record.get("portfolio", ""),
                    "Recent Writing": record.get("recent_activity", ""),
                    "Segment": SEGMENT_LABELS.get(record.get("segment"), record.get("segment", "")),
                    "Audit Notes": "; ".join(reasons),
                })
        print(f"\nwrote {len(keep)} Tier A/B rows to {args.out}")


if __name__ == "__main__":
    main()
