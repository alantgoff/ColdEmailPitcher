"""Turn the researched investor universe into an ingestible CSV.

Contact resolution is deliberately left open. The CSV carries no email addresses because
none were verified, and the ``Email Confidence`` column says so on every row. Ingest will
quarantine those records (R1.4 has no email to work with), which is the correct outcome:
the list is real, the contacts are not yet.

    python scripts/build_investor_csv.py --out data/investors_real.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.investor_universe_2026 import ALL_RECORDS, SEGMENT_LABELS  # noqa: E402

FIELDNAMES = [
    "Full Name", "Firm", "Title", "Email", "Email Confidence", "Website", "City", "Country",
    "Timezone", "Investment Stages", "Sectors", "Check Size Min", "Check Size Max", "Thesis",
    "Portfolio Companies", "Recent Investments", "Recent Writing", "Segment", "Source",
]


def rows() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for record in ALL_RECORDS:
        name = record["partner_name"]
        # An angel invests their own money: there is no fund behind them. Emitting a shared
        # "Independent Angel" firm name would dedupe eleven separate people into one
        # organisation and put that phantom at the top of a fund ranking.
        firm = "" if record["segment"] == "angel" else record["firm"]
        out.append({
            # Empty where no individual is known — R1.4 will quarantine it, by design.
            "Full Name": name,
            "Firm": firm,
            "Title": record["partner_role"],
            "Email": "",
            "Email Confidence": "unknown",
            "Website": "",
            "City": record["city"],
            "Country": record["country"],
            "Timezone": record["timezone"],
            "Investment Stages": record["stages"],
            "Sectors": record["sectors"],
            "Check Size Min": record["check_min"],
            "Check Size Max": record["check_max"],
            "Thesis": record["thesis"],
            "Portfolio Companies": record["portfolio"],
            "Recent Investments": record["portfolio"],
            "Recent Writing": record["recent_activity"],
            "Segment": SEGMENT_LABELS.get(record["segment"], record["segment"]),
            "Source": "public web research, July 2026",
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/investors_real.csv"))
    parser.add_argument(
        "--worklist", type=Path, default=Path("data/contact_worklist.csv"),
        help="Rows still needing a named partner and a verified address.",
    )
    args = parser.parse_args()

    data = rows()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(data)

    # The enrichment worklist: one line of work per firm, ordered by relevance segment so
    # the highest-fit funds get resolved first.
    priority = {
        "Restaurant, hospitality & nightlife": 0,
        "Food & beverage / CPG specialist": 1,
        "Miami / Florida": 2,
        "Corporate venture arm": 3,
        "Family office": 4,
        "Latino-led / LatAm connected": 5,
        "Operator, athlete & talent-led consumer fund": 6,
        "Consumer generalist": 7,
        "Delivery, logistics & marketplace": 8,
        "Commerce & retail technology": 9,
        "Accelerator or programme": 10,
        "Named angel investor": 11,
    }
    todo = sorted(
        (r for r in data if not r["Full Name"] or not r["Email"]),
        key=lambda r: (priority.get(r["Segment"], 99), r["Firm"]),
    )
    with args.worklist.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Priority", "Firm", "Segment", "City", "Needs", "Thesis"],
        )
        writer.writeheader()
        for index, row in enumerate(todo, start=1):
            needs = []
            if not row["Full Name"]:
                needs.append("named partner")
            if not row["Email"]:
                needs.append("verified email")
            writer.writerow({
                "Priority": index,
                "Firm": row["Firm"],
                "Segment": row["Segment"],
                "City": row["City"],
                "Needs": " + ".join(needs),
                "Thesis": row["Thesis"][:160],
            })

    print(f"wrote {len(data)} investor rows to {args.out}")
    print(f"wrote {len(todo)} enrichment rows to {args.worklist}")
    print(f"  named individuals already resolved: {sum(1 for r in data if r['Full Name'])}")
    print(f"  verified emails: {sum(1 for r in data if r['Email'])}")


if __name__ == "__main__":
    main()
