"""Second research pass — additions that clear the audit rather than pad the count.

The first pass optimised for a target number and 31% of it was unsendable. This pass
optimised for the thing that actually converts: funds whose own words name this business,
that can write a seed cheque, and — most importantly — that have a *named partner*, because
a fund without one can be ranked but never written to.

Two kinds of record:

``SUPPLEMENT_FIRMS``
    Genuinely new funds.

``PARTNER_ADDITIONS``
    Named partners at firms already in the universe. These are worth more than new firms:
    they turn a record that could only ever be a prospect into one that can produce a draft.

Sourced from public web research, July 2026. Same rule as the main universe — a field is
populated only where a source stated it, and no email address is invented.
"""

from __future__ import annotations

from data.investor_universe_2026 import LA, MIA, NY, R, SF, UNK

# --------------------------------------------------------------------------------------
# New funds
# --------------------------------------------------------------------------------------

SUPPLEMENT_FIRMS = [
    R("Supply Change Capital", LA, "Pre-Seed; Seed", "Food; Food Tech; Culture; Consumer",
      thesis="Invests at the intersection of food, culture and technology, on the thesis that "
             "the food investment opportunity over the next two decades exceeds $100B.",
      recent="Closed a $40M debut fund; roughly 80% of the portfolio is Latinx, Black or "
             "female-led; took equity investment from Bank of America.",
      partner=("Noramay Cadena", "Co-Founder and Managing Partner"), segment="food_beverage"),
    R("Supply Change Capital", LA, "Pre-Seed; Seed", "Food; Food Tech; Culture; Consumer",
      thesis="Invests at the intersection of food, culture and technology, on the thesis that "
             "the food investment opportunity over the next two decades exceeds $100B.",
      recent="Co-founder previously architected supply chain at Mars and built Farmer's Fridge.",
      partner=("Shayna Harris", "Co-Founder and Managing Partner"), segment="food_beverage"),
    R("Convivialite Ventures", SF, "Seed; Series A", "Beverage; Food & Beverage; Consumer",
      thesis="Pernod Ricard's venture arm, created 2017, investing beyond the group's "
             "traditional wine and spirits offering.",
      portfolio="AF Drinks; Ghia",
      recent="Offices in San Francisco, Paris, Mumbai and Shanghai.", segment="corporate_vc"),
    R("Constellation Brands Ventures", ("Rochester", "United States", "America/New_York"),
      "Seed; Series A", "Beverage; Food & Beverage; Consumer",
      thesis="Constellation Brands' venture arm, investing in emerging beverage and consumer "
             "brands.", segment="corporate_vc"),
    R("True Ventures", SF, "Seed; Series A", "Consumer; Technology; Restaurant Tech",
      thesis="Seed and Series A investor with more than $3.8B under management, active in "
             "restaurant and consumer technology.", segment="consumer"),
    R("General Catalyst", ("Cambridge", "United States", "America/New_York"),
      "Seed; Series A; Growth", "Consumer; Restaurant Tech; Technology",
      thesis="Multi-stage firm named among the most active venture investors in restaurants "
             "and restaurant technology.", segment="restaurant_hospitality"),
]

# --------------------------------------------------------------------------------------
# Named partners at firms already in the universe
# --------------------------------------------------------------------------------------

PARTNER_ADDITIONS = [
    R("Branded Hospitality Ventures", NY, "Pre-Seed; Seed; Series A",
      "Hospitality; Food & Beverage; Restaurant Tech; Foodservice",
      thesis="Investment, advisory and media platform driving growth in foodservice and "
             "hospitality, investing in technology-driven food and beverage concepts.",
      portfolio="Blanket; Brizo FoodMetrics; Copia; Cut+Dry; Incentivio; Minnow; Ovation; "
                "Simple Marketplace; Spendgo; TapRm; Targetable; Usual Wines",
      recent="Managing partner sits on the boards of a dozen portfolio companies across "
             "restaurant technology and beverage.",
      partner=("Jimmy Frischling", "Co-Founder and Managing Partner"),
      segment="restaurant_hospitality"),
    R("Siddhi Capital", UNK, "Seed; Series A; Growth", "Food & Beverage; CPG; Food Tech",
      thesis="Growth-stage CPG brands providing restaurant-quality foods and beverages, plus "
             "food-tech; roughly two-thirds CPG and one-third food-tech.",
      recent="Raised $135M for Fund II.",
      partner=("Melissa Facchina", "Co-Founder and General Partner"), segment="food_beverage"),
    R("Kitchen Fund", NY, "Seed; Series A", "Restaurants; Food & Beverage; Restaurant Tech",
      thesis="Early-stage specialist investing exclusively in restaurant innovation.",
      portfolio="Curry Up Now; The Pie Hole; Gregorys Coffee; JUICER",
      recent="Invested in Gregorys Coffee (2025) and JUICER's $5.3M seed round (2024).",
      partner=("Greg Golkin", "Managing Partner"), segment="restaurant_hospitality"),
    R("Kitchen Fund", NY, "Seed; Series A", "Restaurants; Food & Beverage; Restaurant Tech",
      thesis="Early-stage specialist investing exclusively in restaurant innovation.",
      portfolio="Curry Up Now; The Pie Hole; Gregorys Coffee; JUICER",
      recent="Partner focused on growth equity and sustainable restaurant businesses.",
      partner=("Dan Rowe", "Managing Partner"), segment="restaurant_hospitality"),
    R("Kitchen Fund", NY, "Seed; Series A", "Restaurants; Food & Beverage; Restaurant Tech",
      thesis="Early-stage specialist investing exclusively in restaurant innovation.",
      portfolio="Curry Up Now; The Pie Hole; Gregorys Coffee; JUICER",
      recent="Partner specialising in financial analysis and market selection.",
      partner=("Akash Mirchandani", "Partner"), segment="restaurant_hospitality"),
    R("Savory Fund", ("Salt Lake City", "United States", "America/Denver"), "Growth",
      "Restaurants; Food & Beverage; Multi-Unit",
      thesis="Invests in emerging restaurant concepts, providing capital and operating "
             "expertise to scale them into multi-unit brands.",
      portfolio="Mo' Bettahs; Via 313; Hash Kitchen; South Block",
      recent="More than 70 restaurant operators and finance staff who have run 170+ "
             "restaurants over twelve years.",
      partner=("Andrew K. Smith", "Co-Founder and Managing Partner"),
      segment="restaurant_hospitality"),
]

#: Contacts added in this pass, each checked against a public source when found.
SUPPLEMENT_CONTACTS = {
    "Noramay Cadena": "Co-Founder and Managing Partner, Supply Change Capital — TechCrunch, fund site",
    "Shayna Harris": "Co-Founder and Managing Partner, Supply Change Capital — TechCrunch, fund site",
    "Jimmy Frischling": "Co-Founder and Managing Partner, Branded Hospitality — brandedstrategic.com, Vator",
    "Melissa Facchina": "Co-Founder and General Partner, Siddhi Capital — LinkedIn, fund profile",
    "Greg Golkin": "Managing Partner, Kitchen Fund — fund profile",
    "Dan Rowe": "Managing Partner, Kitchen Fund — fund profile",
    "Akash Mirchandani": "Partner, Kitchen Fund — fund profile",
    "Andrew K. Smith": "Co-Founder and Managing Partner, Savory Fund — savoryfund.com",
}

ALL_SUPPLEMENT = SUPPLEMENT_FIRMS + PARTNER_ADDITIONS
