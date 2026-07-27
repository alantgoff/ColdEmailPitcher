"""Generate a deterministic sample investor export for Phase 1.

Shaped like a real OpenVC/PitchBook export, including the parts that make ingest hard:
non-partner rows, shared inboxes, missing emails, inconsistent stage spellings, money
written five different ways, and duplicate people under slightly different firm names.

Run: python scripts/generate_sample_investors.py [output.csv]
"""

from __future__ import annotations

import argparse
import csv
import random
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
#: R1.4 includes angels — for a friends & family round they are the decision-maker.
ANGEL_TITLES = ["Angel Investor", "Angel", "Individual Investor", "Angel / Operator"]
NON_PARTNER_TITLES = [
    "Associate", "Senior Associate", "Analyst", "Investment Analyst", "Head of Platform",
    "Chief of Staff", "Talent Partner",
]

VERTICALS = {
    # Healthtech / clinical infrastructure — the reference vertical.
    "health": {
        "core_sectors": [
            "Healthtech; Digital Health; Life Sciences",
            "Health IT; Clinical Trials; B2B SaaS",
            "Healthcare; Payments; Vertical SaaS",
            "Life Sciences Tools; Healthtech; Data Infrastructure",
        ],
        "adjacent_sectors": [
            "B2B SaaS; Fintech; Payments",
            "Enterprise Software; Data Infrastructure; AI",
            "Vertical SaaS; Marketplaces; Fintech",
        ],
        "off_sectors": [
            "Consumer Gaming; Social; Creator Economy",
            "Crypto; Web3; DeFi",
            "Space; Defense; Advanced Manufacturing",
            "Climate; Energy Storage; Industrial",
        ],
        "core_theses": [
            "We back seed-stage companies rebuilding the financial plumbing of healthcare "
            "delivery, with a bias toward clinical operations and life sciences infrastructure.",
            "Our thesis is vertical software for regulated industries: healthcare, clinical "
            "research and pharma services, where workflow and payments converge.",
            "We invest in health IT founders selling into providers, CROs and sponsors, "
            "especially where the buyer has a measurable cost of delay.",
        ],
        "adjacent_theses": [
            "Seed-stage B2B software with a payments component. We like businesses where the "
            "software earns the right to touch the transaction.",
            "We fund vertical SaaS in industries that still run on spreadsheets and PDFs.",
        ],
        "off_theses": [
            "Consumer social and gaming at seed. We look for products with organic distribution.",
            "We invest in crypto protocols and the tooling around them.",
            "Hard tech at seed: space, defense and advanced manufacturing.",
        ],
        "core_portfolio": [
            "Corvus Health", "SiteLedger", "Protocol IO", "Trialbase", "Northstar Rx",
            "CareLoop", "Pathway Bio", "Verity Clinical", "Radial Health", "Cohort Systems",
        ],
        "off_portfolio": [
            "Pixelforge", "Loomstack", "Basalt", "Orbital Freight", "Ember Grid",
            "Fathom Social", "Cartwheel", "Ninefold", "Terrace", "Bluewire",
        ],
        "competitors": ["Greenphire", "Mural Health", "Paylode Health", "TrialPay Sciences"],
        "core_writing": [
            "Wrote about why site-level cost data never reaches the sponsor's finance team in time.",
            "Podcast appearance on how clinical research became a working-capital business.",
            "Blog post arguing that vertical software wins when it takes over the payment.",
            "Posted a breakdown of where trial budgets actually leak between sponsor and site.",
        ],
        "off_writing": [
            "Published notes on the consumer subscription shakeout.",
            "Wrote about validator economics and where the fees really go.",
            "Posted on why grid interconnection queues are the real climate bottleneck.",
        ],
        "cities": "us_default",
        "check_bands": [
            ("$250k", "$1M"), ("250000", "1500000"), ("$100k", "$500k"),
            ("$1M", "$5M"), ("500k", "2M"), ("$2M", "$10M"),
        ],
    },
    # Consumer / food & beverage / hospitality — Prime After Dark's actual universe.
    "food": {
        "core_sectors": [
            "Food & Beverage; Restaurant Tech; Consumer",
            "Hospitality; Consumer; Franchise",
            "Ghost Kitchens; Food Delivery; Logistics",
            "Consumer Brands; CPG; Food",
            "Restaurant Technology; Vertical SaaS; Hospitality",
        ],
        "adjacent_sectors": [
            "Consumer; DTC; Marketplaces",
            "Last Mile Logistics; Marketplaces; Consumer",
            "Consumer Fintech; Loyalty; Payments",
            "Real Estate; Hospitality; PropTech",
        ],
        "off_sectors": [
            "Enterprise SaaS; Security; DevTools",
            "Biotech; Therapeutics; Life Sciences",
            "Crypto; Web3; DeFi",
            "Space; Defense; Advanced Manufacturing",
            "Climate; Energy Storage; Industrial",
        ],
        "core_theses": [
            "We back consumer food and beverage brands at pre-seed and seed, with a strong "
            "preference for operators who have actually run kitchens.",
            "Our focus is the restaurant and hospitality stack: delivery, ghost kitchens, "
            "virtual brands and the logistics underneath them.",
            "We invest in Miami consumer companies. Nightlife, hospitality and food are the "
            "categories this city exports, and we fund founders building in them.",
            "Early-stage consumer brands with real unit economics. We care about average order "
            "value, repeat rate and contribution margin before we care about the story.",
            "We fund multi-unit and franchise-ready food concepts that can replicate a playbook "
            "across corridors without heavy capex.",
        ],
        "adjacent_theses": [
            "Consumer and marketplace businesses at seed, especially last-mile logistics and "
            "anything that moves physical goods to a doorstep.",
            "We invest in DTC and consumer brands where the founder owns the customer "
            "relationship rather than renting it from a platform.",
            "Hospitality real estate and the operating businesses inside it.",
        ],
        "off_theses": [
            "Enterprise infrastructure and developer tools at seed.",
            "We invest in therapeutics and platform biology.",
            "We invest in crypto protocols and the tooling around them.",
            "Hard tech at seed: space, defense and advanced manufacturing.",
            "Climate infrastructure, with a focus on grid-scale storage.",
        ],
        "core_portfolio": [
            "Nocturne Hospitality", "Corridor Kitchens", "Late Plate", "Brickell Provisions",
            "Sunbelt Foods", "Nightcap Brands", "Harborline Hospitality", "Vice City Eats",
            "Coral Way Kitchen", "Second Shift Foods", "Palmetto Provisions",
        ],
        "off_portfolio": [
            "Pixelforge", "Loomstack", "Basalt", "Orbital Freight", "Ember Grid",
            "Ninefold", "Terrace", "Bluewire", "Cartwheel",
        ],
        # R1.5 — funds holding one of these compete directly with Prime After Dark.
        "competitors": [
            "CloudKitchens", "REEF Technology", "Kitchen United", "Nextbite",
            "Local Kitchens", "Virtual Dining Concepts", "Wonder",
        ],
        "core_writing": [
            "Wrote about why late night is the only daypart still growing for restaurants.",
            "Podcast appearance on ghost kitchen unit economics and where they break.",
            "Blog post on why delivery-first brands beat restaurants that bolt delivery on.",
            "Posted a breakdown of Miami's nightlife spend and who actually captures it.",
            "Wrote about packaging as the real product problem in premium delivery.",
            "Posted on why multi-unit food concepts should stop signing restaurant leases.",
        ],
        "off_writing": [
            "Published notes on developer tooling consolidation.",
            "Wrote about validator economics and where the fees really go.",
            "Posted on why grid interconnection queues are the real climate bottleneck.",
        ],
        "cities": "miami_weighted",
        "check_bands": [
            ("$250k", "$1M"), ("$500k", "$2M"), ("250000", "1500000"),
            ("$1M", "$3M"), ("$100k", "$500k"), ("$50k", "$250k"),
        ],
    },
}

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
MIAMI_CITIES = [
    ("Miami", "United States", "America/New_York"),
    ("Miami Beach", "United States", "America/New_York"),
    ("Coral Gables", "United States", "America/New_York"),
    ("Fort Lauderdale", "United States", "America/New_York"),
    ("West Palm Beach", "United States", "America/New_York"),
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


def pick_city(rng: random.Random, mode: str) -> tuple[str, str, str]:
    """Miami-weighted for the food vertical: a Miami F&F round is a local round first."""
    if mode == "miami_weighted":
        roll = rng.random()
        if roll < 0.45:
            return rng.choice(MIAMI_CITIES)
        if roll < 0.88:
            return rng.choice(US_CITIES)
        return rng.choice(INTL_CITIES)
    return rng.choice(US_CITIES if rng.random() < 0.78 else INTL_CITIES)


def build_firms(rng: random.Random, v: dict) -> list[dict]:
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
                sectors, thesis = rng.choice(v["core_sectors"]), rng.choice(v["core_theses"])
                portfolio_pool, writing_pool = v["core_portfolio"], v["core_writing"]
            elif bucket < 0.68:
                sectors, thesis = rng.choice(v["adjacent_sectors"]), rng.choice(v["adjacent_theses"])
                portfolio_pool = v["core_portfolio"] + v["off_portfolio"]
                writing_pool = v["core_writing"] + v["off_writing"]
            else:
                sectors, thesis = rng.choice(v["off_sectors"]), rng.choice(v["off_theses"])
                portfolio_pool, writing_pool = v["off_portfolio"], v["off_writing"]

            portfolio = rng.sample(portfolio_pool, k=4)
            # ~6% of *funds* hold a direct competitor. R1.5 has to catch exactly these.
            if rng.random() < 0.06:
                portfolio.append(rng.choice(v["competitors"]))

            city, country, tz = pick_city(rng, v["cities"])
            check_min, check_max = rng.choice(v["check_bands"])
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


def build_rows(vertical: str = "health") -> list[dict[str, str]]:
    rng = random.Random(SEED)
    today = date(2026, 7, 27)
    v = VERTICALS[vertical]
    firms = build_firms(rng, v)
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
        # Mostly institutional partners; angels are a minority of a seed round's list.
        angel = vertical == "food" and rng.random() < 0.12
        title = rng.choice(ANGEL_TITLES if angel else PARTNER_TITLES)
        rows.append(make_row(title=title, email_style="personal"))
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vertical", choices=sorted(VERTICALS), default="health")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    output = args.out or Path(f"data/sample_investors_{args.vertical}.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = build_rows(args.vertical)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} {args.vertical}-vertical rows to {output}")


if __name__ == "__main__":
    main()
