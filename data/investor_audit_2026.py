"""Audit findings against ``investor_universe_2026``.

Each finding was checked against a public source during the audit pass. They are recorded
as data rather than applied silently, so the correction and the reason for it stay
together — a list you cannot audit is a list you cannot trust.

The mechanical checks live in ``scripts/audit_investors.py``. This file holds only what
required a human-verifiable lookup.
"""

from __future__ import annotations

# --------------------------------------------------------------------------------------
# Verified defects. Each entry: what was wrong, what is true, and how it was checked.
# --------------------------------------------------------------------------------------

VERIFIED_FINDINGS = [
    {
        "id": "F1",
        "severity": "critical",
        "record": "CAVU Consumer Partners",
        "claim_was": "Clayton Christopher is the contact at CAVU Consumer Partners.",
        "truth": (
            "Clayton Christopher left an active role at CAVU in early 2019 and is now "
            "Managing Partner at Asto Consumer Partners. The contact was seven years stale."
        ),
        "impact": (
            "This was the ONLY record that cleared the research floor and produced a draft. "
            "The single email this system generated would have gone to a person who left the "
            "firm being addressed."
        ),
        "source": "Austin Chronicle / BevNET, April 2019; astoconsumer.com team page",
        "action": "Remove as CAVU contact; add Asto Consumer Partners as a separate firm.",
    },
    {
        "id": "F2",
        "severity": "high",
        "record": "Greycroft",
        "claim_was": "Alan Patricof is the contact at Greycroft.",
        "truth": (
            "Patricof is Chairman Emeritus at Greycroft. His active fund is Primetime "
            "Partners, which this list already carries as a separate record."
        ),
        "impact": "A cold email to an emeritus chairman reaches nobody who can act on it.",
        "source": "Crunchbase person profile; primetimepartners.com team page",
        "action": "Remove as Greycroft contact.",
    },
    {
        "id": "F3",
        "severity": "high",
        "record": "GPS Hospitality",
        "claim_was": "GPS Hospitality is an investor.",
        "truth": (
            "GPS Hospitality is an Atlanta-based Burger King / Popeyes / Pizza Hut "
            "franchisee operator. It receives investment; it does not make venture "
            "investments."
        ),
        "impact": "A non-investor in an investor list is noise that inflates the count.",
        "source": "Wikipedia; PitchBook company profile; nrn.com",
        "action": "Remove from the universe.",
    },
    {
        "id": "F4",
        "severity": "medium",
        "record": "Derive Ventures",
        "claim_was": "Derive Ventures is a separate active fund.",
        "truth": (
            "Thayer Ventures and Derive Ventures combined into Thayer Investment Partners, "
            "which this list already carries. Derive is the same entity counted twice."
        ),
        "impact": "Double-counting inflates the list and would double-contact one team.",
        "source": "shorttermrentalz.com; hotelmanagement.net",
        "action": "Remove; folded into Thayer Investment Partners.",
    },
    {
        "id": "F5",
        "severity": "medium",
        "record": "Blumberg Capital",
        "claim_was": "Headquartered in Miami.",
        "truth": (
            "Headquartered in San Francisco, founded 1991, with team members in Tel Aviv, "
            "Miami and New York. The Miami presence is real but it is not the HQ."
        ),
        "impact": (
            "Geography feeds the fit score and the R4.5 send window. A wrong city is a "
            "wrong send time as well as a wrong score."
        ),
        "source": "blumbergcapital.com; Wikipedia",
        "action": "Correct city to San Francisco.",
    },
    {
        "id": "F6",
        "severity": "low",
        "record": "Chobani Incubator",
        "claim_was": "Active incubator for early-stage food and beverage companies.",
        "truth": (
            "Founded 2016, roughly 7 companies supported. No 2026 evidence found that it is "
            "still accepting applications; status could not be confirmed either way."
        ),
        "impact": "An inactive programme wastes a slot and a founder's time.",
        "source": "Tracxn profile; no current application page found",
        "action": "Flag status as unconfirmed.",
    },
    {
        "id": "F8",
        "severity": "high",
        "record": "Jaws Ventures / JAWS Estates Capital",
        "claim_was": "Two separate Miami investors, with Jaws Ventures at seed/Series A.",
        "truth": (
            "Jaws Ventures IS Barry Sternlicht's family office, headquartered in Miami "
            "Beach and founded 2014 — the same entity recorded separately as JAWS Estates "
            "Capital. It provides GROWTH capital to consumer and technology companies, not "
            "seed."
        ),
        "impact": (
            "A duplicate that would have double-contacted one team, carrying a wrong stage "
            "that put a growth-stage family office near the top of the seed prospect "
            "ranking."
        ),
        "source": "altss.com fund profile; jawsvc.com/about; Crunchbase",
        "action": "Merge into one record and correct the stage to growth (drops to Tier C).",
    },
    {
        "id": "F9",
        "severity": "low",
        "record": "SC30 / Penny Jar Capital",
        "claim_was": "Two independent funds.",
        "truth": (
            "Both are Stephen Curry vehicles — SC30 is his holding company and Penny Jar "
            "Capital is the venture fund it co-founded. Distinct entities, one principal."
        ),
        "impact": "Contacting both reaches the same team twice.",
        "source": "public fund profiles",
        "action": "Keep both, flag as related so only one is contacted.",
    },
    {
        "id": "F7",
        "severity": "medium",
        "record": "Springdale Ventures",
        "claim_was": "Genevieve Gilbreath is based in Austin.",
        "truth": (
            "Still Co-Founder and General Partner at Springdale (confirmed current), but "
            "personally based in Santa Fe, New Mexico."
        ),
        "impact": "Only affects the send window, not the fit; the firm remains Austin-based.",
        "source": "springdaleventures.com team page; Bloomberg profile",
        "action": "Keep; note the personal timezone differs from the firm's.",
    },
]

#: Partner attributions re-checked and found CURRENT during the audit.
CONFIRMED_CONTACTS = {
    "Genevieve Gilbreath": "Co-Founder and General Partner, Springdale Ventures — confirmed 2026",
    "Don Thompson": "Founder and CEO, Cleveland Avenue — confirmed 2026",
    "Tom Spier": "Founder and Managing Partner, Boulder Food Group — confirmed",
    "Steve Hughes": "Co-Founder and CEO, Sunrise Strategic Partners — confirmed",
    "Kirsten Green": "Founder, Forerunner Ventures — confirmed via Fund VII coverage",
    "Nick Brown": "Co-Founder, Imaginary Ventures — confirmed",
    "Brian Rosen": "Founder, InvestBev — confirmed via January 2026 coverage",
    "Arlene Dickinson": "Managing Partner, District Ventures Capital — confirmed",
    "Allan Karp": "Co-Founder, KarpReilly — confirmed",
}

#: Firms to remove entirely, with the finding that removed them.
REMOVE = {
    "GPS Hospitality": "F3",
    "Derive Ventures": "F4",
    # Same family office as JAWS Estates Capital, which is kept.
    "Jaws Ventures": "F8",
}

#: Distinct entities sharing one principal — contact one, not both.
RELATED_ENTITIES = {
    "SC30": "Penny Jar Capital",
    "Penny Jar Capital": "SC30",
}

#: Field-level corrections applied by the audit script.
CORRECTIONS = {
    "Blumberg Capital": {"city": "San Francisco", "timezone": "America/Los_Angeles", "finding": "F5"},
    "CAVU Consumer Partners": {"partner_name": "", "partner_role": "", "finding": "F1"},
    "Greycroft": {"partner_name": "", "partner_role": "", "finding": "F2"},
    "Chobani Incubator": {"status_note": "status unconfirmed for 2026", "finding": "F6"},
    "JAWS Estates Capital": {
        "stages": "Growth", "city": "Miami Beach",
        "thesis": "Barry Sternlicht's Miami Beach family office, founded 2014, providing "
                  "growth capital to consumer and technology companies.",
        "finding": "F8",
    },
}

#: Discovered during the audit — Clayton Christopher's actual current fund.
ADDITIONS = [
    {
        "firm": "Asto Consumer Partners", "city": "Austin", "country": "United States",
        "timezone": "America/Chicago", "stages": "Series A; Growth",
        "sectors": "Food & Beverage; Consumer; CPG",
        "check_min": "", "check_max": "",
        "thesis": "Later-stage consumer packaged goods investing, founded by the Sweet Leaf Tea "
                  "and Deep Eddy Vodka founder after leaving CAVU.",
        "portfolio": "Rebbl; High Brew Coffee; Kettle & Fire; Waterloo Sparkling Water",
        "recent_activity": "Clayton Christopher serves as Managing Partner.",
        "partner_name": "Clayton Christopher", "partner_role": "Managing Partner",
        "segment": "food_beverage",
    },
]

# --------------------------------------------------------------------------------------
# Mechanical relevance rules for a $2.5M institutional seed in Miami.
# --------------------------------------------------------------------------------------

#: Sector vocabulary that makes a fund genuinely relevant to a premium late-night
#: delivery brand. Matched against the record's declared sectors.
#: Tier A: the fund's own words put it in this company's actual business. "Consumer" is
#: deliberately NOT here — a generalist consumer fund is a real but materially weaker
#: prospect than a fund that says "restaurant", and collapsing the two inflates Tier A
#: to the point where the tiering stops being a decision aid.
CORE_SECTORS = (
    "food", "beverage", "restaurant", "hospitality", "nightlife", "foodservice",
    "ghost kitchen", "culinary", "franchise", "multi-unit",
)
#: Tier B: plausible, but the founder is arguing the category rather than matching it.
ADJACENT_SECTORS = (
    "consumer", "cpg", "commerce", "retail", "marketplace", "d2c", "dtc", "logistics",
    "last mile", "delivery", "wellness", "lifestyle", "brands",
)
#: Declared focus that makes a fund a poor use of a cold email for this company.
OFF_THESIS_SECTORS = (
    "enterprise", "b2b saas", "saas", "developer", "devtools", "security", "cyber",
    "biotech", "therapeutics", "life sciences", "crypto", "web3", "defi", "blockchain",
    "space", "defense", "agtech", "agriculture", "proptech", "real estate", "insurtech",
    "women's health", "longevity", "ai;", "deep tech",
)

#: Non-US funds are kept but flagged: they rarely lead a first US seed round.
NON_US_HINTS = ("Canada", "United Kingdom", "Germany", "Sweden", "Singapore")
