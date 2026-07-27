"""Generate a deterministic sample investor export for Phase 1.

Shaped like a real OpenVC/PitchBook export, including the parts that make ingest hard:
non-partner rows, shared inboxes, missing emails, inconsistent stage spellings, money
written five different ways, and duplicate people under slightly different firm names.

Run: python scripts/generate_sample_investors.py [output.csv]
"""

from __future__ import annotations

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

SEED = 20260727
TOTAL_PARTNER_ROWS = 500
NON_PARTNER_ROWS = 34
GENERIC_INBOX_ROWS = 14
NO_EMAIL_ROWS = 12
DUPLICATE_ROWS = 10

FIRST_NAMES = [
    "Ana", "Priya", "Wei", "Daniel", "Marcus", "Sofia", "Kenji", "Leah", "Omar", "Fatima",
    "Nils", "Grace", "Tomas", "Aisha", "Ruth", "Ivan", "Yara", "Hugo", "Mei", "Samir",
    "Elena", "Jonas", "Nadia", "Peter", "Amara", "Lucas", "Hana", "Ravi", "Clara", "Diego",
    "Iris", "Mateo", "Zoe", "Arjun", "Freya", "Noah", "Talia", "Felix", "Rosa", "Ade",
]
LAST_NAMES = [
    "Okafor", "Lindqvist", "Ramirez", "Chen", "Osei", "Brenner", "Vasquez", "Novak", "Haddad",
    "Kowalski", "Moreau", "Tanaka", "Silva", "Dubois", "Farrell", "Iqbal", "Petrov", "Nguyen",
    "Baumann", "Alvarez", "Rossi", "Andersen", "Mbeki", "Kaur", "Larsen", "Costa", "Weber",
    "Sharma", "Fontaine", "Berger",
]
FIRM_STEMS = [
    "Northaven", "Blue Meridian", "Fifth Harbor", "Grove Lane", "Cedar Point", "Lantern",
    "Rivermark", "Two Bridges", "Halcyon", "Foundry Row", "Quarry", "Windward", "Ironwood",
    "Silverline", "Copper Beach", "Longshore", "Highgate", "Pinemark", "Solstice", "Kestrel",
    "Vantage Hill", "Beacon Ridge", "Alder", "Marlow", "Tidewater", "Granite Row", "Ashford",
    "Larkspur", "Compass Rose", "Hollow Creek",
]
FIRM_SUFFIXES = ["Capital", "Ventures", "Partners", "Venture Partners", "Capital Partners", "Labs"]
PARTNER_TITLES = [
    "Partner", "General Partner", "Managing Partner", "Founding Partner", "Principal",
    "Venture Partner", "GP", "Managing Director",
]
NON_PARTNER_TITLES = [
    "Associate", "Senior Associate", "Analyst", "Investment Analyst", "Head of Platform",
    "Chief of Staff", "Talent Partner",
]

HEALTH_SECTORS = [
    "Healthtech; Digital Health; Life Sciences",
    "Health IT; Clinical Trials; B2B SaaS",
    "Healthcare; Payments; Vertical SaaS",
    "Life Sciences Tools; Healthtech; Data Infrastructure",
    "Digital Health; Fintech; Healthcare Services",
]
ADJACENT_SECTORS = [
    "B2B SaaS; Fintech; Payments",
    "Enterprise Software; Data Infrastructure; AI",
    "Vertical SaaS; Marketplaces; Fintech",
    "Fintech; Insurtech; Payments",
]
OFF_SECTORS = [
    "Consumer Gaming; Social; Creator Economy",
    "Crypto; Web3; DeFi",
    "Space; Defense; Advanced Manufacturing",
    "Climate; Energy Storage; Industrial",
    "Consumer Retail; DTC; Food",
]

HEALTH_THESES = [
    "We back seed-stage companies rebuilding the financial plumbing of healthcare delivery, "
    "with a bias toward clinical operations and life sciences infrastructure.",
    "Our thesis is vertical software for regulated industries: healthcare, clinical research and "
    "pharma services, where workflow and payments converge.",
    "We invest in health IT founders selling into providers, CROs and sponsors, especially where "
    "the buyer has a measurable cost of delay.",
    "Digital health infrastructure at seed. We look for companies that move money or data between "
    "sponsors, sites and patients.",
]
ADJACENT_THESES = [
    "Seed-stage B2B software with a payments component. We like businesses where the software "
    "earns the right to touch the transaction.",
    "We fund vertical SaaS in industries that still run on spreadsheets and PDFs.",
    "Fintech infrastructure at pre-seed and seed, with a preference for embedded payments.",
]
OFF_THESES = [
    "Consumer social and gaming at seed. We look for products with organic distribution.",
    "We invest in crypto protocols and the tooling around them.",
    "Hard tech at seed: space, defense and advanced manufacturing.",
    "Climate infrastructure, with a focus on grid-scale storage and industrial decarbonisation.",
]

HEALTH_PORTFOLIO = [
    "Corvus Health", "SiteLedger", "Protocol IO", "Trialbase", "Northstar Rx", "CareLoop",
    "Pathway Bio", "Verity Clinical", "Radial Health", "Cohort Systems",
]
OFF_PORTFOLIO = [
    "Pixelforge", "Loomstack", "Basalt", "Orbital Freight", "Ember Grid", "Fathom Social",
    "Cartwheel", "Ninefold", "Terrace", "Bluewire",
]
#: R1.5 — a handful of funds hold a direct competitor, so conflict suppression has work to do.
COMPETITOR_PORTFOLIO = ["Greenphire", "Mural Health", "Paylode Health", "TrialPay Sciences"]

RECENT_WRITING = [
    "Wrote about why site-level cost data never reaches the sponsor's finance team in time.",
    "Podcast appearance on how clinical research became a working-capital business.",
    "Blog post arguing that vertical software wins when it takes over the payment, not the record.",
    "Posted a breakdown of where trial budgets actually leak between sponsor and site.",
    "Wrote a piece on why regulated industries adopt software through the CFO, not the end user.",
    "Published notes on the consumer subscription shakeout.",
    "Wrote about validator economics and where the fees really go.",
    "Posted on why grid interconnection queues are the real climate bottleneck.",
]

STAGE_SPELLINGS = [
    "Pre-Seed; Seed", "Seed", "seed, series a", "Seed; Series A", "Pre-seed/Seed",
    "Series A; Series B", "Growth", "Early Stage",
]
CHECK_BANDS = [
    ("$250k", "$1M"), ("250000", "1500000"), ("$100k", "$500k"), ("$1M", "$5M"),
    ("500k", "2M"), ("$2M", "$10M"),
]
US_CITIES = [
    ("Boston", "United States", "America/New_York"),
    ("New York", "United States", "America/New_York"),
    ("San Francisco", "United States", "America/Los_Angeles"),
    ("Chicago", "United States", "America/Chicago"),
    ("Austin", "United States", "America/Chicago"),
    ("Seattle", "United States", "America/Los_Angeles"),
]
INTL_CITIES = [
    ("London", "United Kingdom", "Europe/London"),
    ("Berlin", "Germany", "Europe/Berlin"),
    ("Stockholm", "Sweden", "Europe/Stockholm"),
    ("Singapore", "Singapore", "Asia/Singapore"),
    ("Toronto", "Canada", "America/Toronto"),
]

FIELDNAMES = [
    "Full Name", "Firm", "Title", "Email", "Website", "City", "Country", "Timezone",
    "Investment Stages", "Sectors", "Check Size Min", "Check Size Max", "Thesis",
    "Portfolio Companies", "Recent Investments", "Recent Writing", "Recent Activity Date",
    "LinkedIn",
]


def _slug(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum() or ch == " ").replace(" ", "")


def build_firms(rng: random.Random) -> list[dict]:
    """Firm-first generation.

    A fund's thesis, portfolio and location belong to the *firm*, and every partner there
    inherits them. Generating those per-person would be a data bug that shows up
    downstream as phantom portfolio conflicts, because Pitchline correctly treats a
    portfolio holding as fund-level (R1.5).
    """
    firms: list[dict] = []
    for stem in FIRM_STEMS:
        for suffix in FIRM_SUFFIXES:
            name = f"{stem} {suffix}"
            bucket = rng.random()
            if bucket < 0.40:
                sectors, thesis = rng.choice(HEALTH_SECTORS), rng.choice(HEALTH_THESES)
                portfolio_pool, writing_pool = HEALTH_PORTFOLIO, RECENT_WRITING[:5]
            elif bucket < 0.68:
                sectors, thesis = rng.choice(ADJACENT_SECTORS), rng.choice(ADJACENT_THESES)
                portfolio_pool, writing_pool = HEALTH_PORTFOLIO + OFF_PORTFOLIO, RECENT_WRITING
            else:
                sectors, thesis = rng.choice(OFF_SECTORS), rng.choice(OFF_THESES)
                portfolio_pool, writing_pool = OFF_PORTFOLIO, RECENT_WRITING[5:]

            portfolio = rng.sample(portfolio_pool, k=4)
            # ~6% of *funds* hold a direct competitor. R1.5 has to catch exactly these.
            if rng.random() < 0.06:
                portfolio.append(rng.choice(COMPETITOR_PORTFOLIO))

            city, country, tz = rng.choice(US_CITIES if rng.random() < 0.78 else INTL_CITIES)
            check_min, check_max = rng.choice(CHECK_BANDS)
            firms.append(
                {
                    "name": name,
                    "domain": f"{_slug(stem)}.vc",
                    "sectors": sectors,
                    "thesis": thesis,
                    "portfolio": portfolio,
                    "writing_pool": writing_pool,
                    "city": city,
                    "country": country,
                    "timezone": tz,
                    "check_min": check_min,
                    "check_max": check_max,
                    "stages": rng.choice(STAGE_SPELLINGS),
                }
            )
    rng.shuffle(firms)
    return firms


def build_rows() -> list[dict[str, str]]:
    rng = random.Random(SEED)
    today = date(2026, 7, 27)
    firms = build_firms(rng)
    rows: list[dict[str, str]] = []
    used_names: set[str] = set()

    def make_name() -> str:
        for _ in range(200):
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            if name not in used_names:
                used_names.add(name)
                return name
        suffix = len(used_names)
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}-{suffix}"
        used_names.add(name)
        return name

    firm_cycle = iter(())

    def next_firm() -> dict:
        nonlocal firm_cycle
        try:
            return next(firm_cycle)
        except StopIteration:
            firm_cycle = iter(firms)
            return next(firm_cycle)

    def make_row(*, title: str, email_style: str) -> dict[str, str]:
        name = make_name()
        firm = next_firm()
        firm_domain = firm["domain"]
        local = _slug(name).replace(" ", ".")
        email = {
            "personal": f"{name.split()[0].lower()}.{name.split()[-1].lower()}@{firm_domain}",
            "generic": f"{rng.choice(['info', 'hello', 'deals', 'submissions'])}@{firm_domain}",
            "none": "",
        }[email_style]
        # Most exports carry reasonably fresh activity; a quarter are stale enough that
        # R1.3 should — correctly — refuse to score the investor on them.
        age = rng.randint(5, 170) if rng.random() < 0.75 else rng.randint(200, 520)

        return {
            "Full Name": name,
            "Firm": firm["name"],
            "Title": title,
            "Email": email,
            "Website": f"https://{firm_domain}",
            "City": firm["city"],
            "Country": firm["country"],
            "Timezone": firm["timezone"],
            "Investment Stages": firm["stages"],
            "Sectors": firm["sectors"],
            "Check Size Min": firm["check_min"],
            "Check Size Max": firm["check_max"],
            "Thesis": firm["thesis"],
            "Portfolio Companies": "; ".join(firm["portfolio"]),
            "Recent Investments": "; ".join(rng.sample(firm["portfolio"], k=2)),
            "Recent Writing": rng.choice(firm["writing_pool"]),
            "Recent Activity Date": (today - timedelta(days=age)).isoformat(),
            "LinkedIn": f"https://www.linkedin.com/in/{local}",
        }

    for _ in range(TOTAL_PARTNER_ROWS):
        rows.append(make_row(title=rng.choice(PARTNER_TITLES), email_style="personal"))
    for _ in range(NON_PARTNER_ROWS):
        rows.append(make_row(title=rng.choice(NON_PARTNER_TITLES), email_style="personal"))
    for _ in range(GENERIC_INBOX_ROWS):
        rows.append(make_row(title=rng.choice(PARTNER_TITLES), email_style="generic"))
    for _ in range(NO_EMAIL_ROWS):
        rows.append(make_row(title=rng.choice(PARTNER_TITLES), email_style="none"))

    # Duplicates under a messier firm spelling — the dedupe key has to survive this.
    for row in rng.sample(rows[:TOTAL_PARTNER_ROWS], k=DUPLICATE_ROWS):
        duplicate = dict(row)
        duplicate["Firm"] = f"{row['Firm']}, LLC"
        duplicate["Full Name"] = row["Full Name"].upper()
        rows.append(duplicate)

    rng.shuffle(rows)
    return rows


def main() -> None:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "data/sample_investors.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {output}")


if __name__ == "__main__":
    main()
