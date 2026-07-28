"""Third research pass — resolving the named partner for every Tier A firm.

A firm with no named partner can be scored, ranked and admired, but never emailed. After
the second audit 63 of 80 Tier A firms were in exactly that state, so this pass went
firm-by-firm through public sources to find the person a founder would actually write to.

It also fixes the largest structural gap in the list: Prime After Dark operates in Miami,
geography carries weight in R1.2, and the universe contained almost no South Florida funds.

``FIT`` on each record is this pass's own read of how well the firm matches a *Miami
late-night premium delivery and ghost-kitchen operator raising a seed* — not a generic
"is this a good fund" score:

``strong``   restaurant/hospitality operators, late-night and nightlife, Miami regional,
             delivery and consumer marketplaces
``moderate`` food & beverage funds that buy packaged brands rather than operators
``weak``     agtech, plant-based protein, fintech and generalists with no line to this

Sourced from public web research, July 2026. A field is populated only where a source
stated it. No email address is invented — see EMAIL_NOTES at the bottom.
"""

from __future__ import annotations

from data.investor_universe_2026 import LA, MIA, NY, R as _R, SF, UNK

CHI = ("Chicago", "United States", "America/Chicago")
FTL = ("Fort Lauderdale", "United States", "America/New_York")
RWC = ("Redwood City", "United States", "America/Los_Angeles")


def R(*args, fit="", **kwargs):
    """The universe's record helper, plus this pass's fit read."""
    record = _R(*args, **kwargs)
    record["fit"] = fit
    return record

# --------------------------------------------------------------------------------------
# Restaurant, hospitality and late-night — the closest comparables to this business
# --------------------------------------------------------------------------------------

HOSPITALITY = [
    # No source stated a city for this fund, so it stays blank rather than inheriting
    # Mast-Jaegermeister's German HQ on an assumption.
    R("Best Nights VC", UNK, "Pre-Seed; Seed; Series A",
      "Nightlife; Hospitality Tech; Consumer Experience; Food & Beverage",
      thesis="Backs nightlife, hospitality-tech and consumer-experience startups reimagining "
             "how people gather socially; describes itself as an impact fund for nightlife.",
      recent="Rebranded at the end of 2021 to focus purely on venture investment, writing "
             "cheques from pre-seed up to Series A.",
      partner=("Lorrain de Silva", "Managing Director"), segment="restaurant_hospitality",
      fit="strong"),
    R("Barrel Ventures", UNK, "Seed", "Food; Restaurants; Food Tech",
      thesis="Seed-stage fund investing across the food ecosystem.",
      recent="Founder was a founding partner of L3 Hospitality Group, owner of LYFE Kitchen, "
             "and later founded Wise Apple.",
      partner=("Nate Cooper", "Founder and Managing Partner"),
      segment="restaurant_hospitality", fit="strong"),
    R("Dom Capital Group", CHI, "Seed; Series A",
      "Hospitality; Food; Grocery; Food Tech",
      thesis="Chicago investment and private capital group focused on hospitality, food and "
             "grocery, and food technology.",
      recent="Founded 2007 by the family behind the Dominick's grocery chain.",
      partner=("Jay Owen", "Co-Founder and Managing Partner"),
      segment="restaurant_hospitality", fit="strong"),
    R("Dom Capital Group", CHI, "Seed; Series A",
      "Hospitality; Food; Grocery; Food Tech",
      thesis="Chicago investment and private capital group focused on hospitality, food and "
             "grocery, and food technology.",
      recent="Founded 2007 by the family behind the Dominick's grocery chain.",
      partner=("Anthony Owen", "Co-Founder and Managing Partner"),
      segment="restaurant_hospitality", fit="strong"),
    R("1st Course Capital", RWC, "Pre-Seed; Seed",
      "Restaurant Tech; Food Tech; Supply Chain; Consumer",
      thesis="Invests in restaurant technology, food technology and supply chain across "
             "North America.",
      recent="Founded 2019; general partner sits on the Menus of Change advisory work.",
      partner=("Peter Herz", "Founding General Partner"),
      segment="restaurant_hospitality", fit="strong"),
    R("1st Course Capital", RWC, "Pre-Seed; Seed",
      "Restaurant Tech; Food Tech; Supply Chain; Consumer",
      thesis="Invests in restaurant technology, food technology and supply chain across "
             "North America.",
      recent="Founded 2019, headquartered in Redwood City.",
      partner=("Renske Lynde", "Founding General Partner"),
      segment="restaurant_hospitality", fit="strong"),
]

# --------------------------------------------------------------------------------------
# Miami and South Florida — geography carries weight in R1.2 and this was the biggest hole
# --------------------------------------------------------------------------------------

SOUTH_FLORIDA = [
    R("Secocha Ventures", MIA, "Pre-Seed; Seed; Series A",
      "Consumer; Consumer Products; Health & Wellness; Fintech",
      thesis="Early-stage B2C investor in consumer products and services, health and wellness, "
             "and fintech.",
      recent="Founded 2013 and headquartered in Miami; invests across the US, India, Israel "
             "and France.",
      partner=("Sanket Parekh", "Founder and Managing Partner"),
      segment="regional_miami", fit="strong"),
    R("Pareto Holdings", MIA, "Pre-Seed; Seed",
      "Consumer; Consumer Products; Technology; Digital Media",
      thesis="Early-stage investment vehicle and venture studio backing consumer products, "
             "technology and digital media.",
      portfolio="Cameo; Ramp",
      recent="Miami-based fund writing six-figure cheques into pre-seed founders, deploying "
             "the founder's own capital rather than LP money.",
      partner=("Edward Lando", "Co-Founder and Managing Partner"),
      segment="regional_miami", fit="strong"),
    R("Fuel Venture Capital", MIA, "Seed; Series A; Growth",
      "Consumer; Technology; Marketplaces",
      thesis="Miami-based founder-focused investor backing consumer and technology companies.",
      recent="Founded 2017 in Coconut Grove; core team has 80+ years combined experience "
             "across investment banking, wealth management and entrepreneurship.",
      partner=("Jeff Ransdell", "Founding Partner and Managing Director"),
      segment="regional_miami", fit="strong"),
    R("Fuel Venture Capital", MIA, "Seed; Series A; Growth",
      "Consumer; Technology; Marketplaces",
      thesis="Miami-based founder-focused investor backing consumer and technology companies.",
      recent="Managing General Partner and CIO was named a Top VC by Insider.",
      partner=("Maggie Vo", "Managing General Partner and Chief Investment Officer"),
      segment="regional_miami", fit="strong"),
    R("TheVentureCity", MIA, "Pre-Seed; Seed; Series A",
      "Consumer; Product-Led Growth; Technology; Marketplaces",
      thesis="Global early-stage fund offering founders investment plus data insights, "
             "designed for product-led growth.",
      recent="Headquartered in Miami with hubs in Madrid, San Francisco and Sao Paulo.",
      partner=("Laura Gonzalez-Estefani", "Founder and General Partner"),
      segment="regional_miami", fit="strong"),
    R("TheVentureCity", MIA, "Pre-Seed; Seed; Series A",
      "Consumer; Product-Led Growth; Technology; Marketplaces",
      thesis="Global early-stage fund offering founders investment plus data insights, "
             "designed for product-led growth.",
      recent="General partner based in the Miami office.",
      partner=("Andres Dancausa", "General Partner"),
      segment="regional_miami", fit="strong"),
    R("Ocean Azul Partners", MIA, "Seed; Series A", "Technology; Consumer; Software",
      thesis="Miami-based fund founded by operators with deep South Florida roots, helping "
             "companies from Israel and Latin America enter the US market.",
      partner=("David Zinn", "Co-Founder and Managing Partner"),
      segment="regional_miami", fit="moderate"),
    R("Las Olas Venture Capital", FTL, "Seed; Series A", "Technology; Software; Consumer",
      thesis="South Florida early-stage fund led by operators who scaled HigherOne from "
             "zero to IPO.",
      recent="Founded 2015 in Fort Lauderdale.",
      partner=("Mark Volchek", "Founding and Co-Managing Partner"),
      segment="regional_miami", fit="moderate"),
    R("Krillion Ventures", MIA, "Seed", "Technology; Healthcare; Fintech; Real Estate",
      thesis="Miami-based fund investing in early-stage technology companies across "
             "healthcare, financial services and real estate.",
      partner=("Melissa Krinzman", "Managing Partner"),
      segment="regional_miami", fit="weak"),
]

# --------------------------------------------------------------------------------------
# Consumer and food & beverage funds
# --------------------------------------------------------------------------------------

CONSUMER_FB = [
    R("CAVU Consumer Partners", NY, "Seed; Series A; Growth",
      "Food & Beverage; Consumer; Wellness",
      thesis="Consumer-brand builders investing with a hands-on style that emphasises close "
             "collaboration with founders.",
      recent="Co-founder previously Partner and Chief Marketing Officer at Glaceau.",
      partner=("Brett Thomas", "Co-Founder and Managing Partner"),
      segment="food_beverage", fit="moderate"),
    R("Coefficient Capital", NY, "Series A; Growth",
      "Food & Beverage; Consumer; Beauty; Wellness",
      thesis="Consumer growth investor backing branded consumer and retail companies.",
      recent="Raised over $500M across funds in March 2026, bringing assets under management "
             "above $800M; has backed more than 20 consumer companies since 2018.",
      partner=("Franklin Isacson", "Co-Founder and Managing Partner"),
      segment="food_beverage", fit="moderate"),
    R("Listen Ventures", CHI, "Seed; Series A", "Consumer; Consumer Brands; Food & Beverage",
      thesis="Consumer-obsessed venture firm that invests beyond capital to become a partner "
             "in building the brand.",
      portfolio="Calm; Catch Co; Dame; Factor; Interior Define",
      recent="Raised $92M across two new funds.",
      partner=("Jeff Cantalupo", "Co-Founder and Managing Partner"),
      segment="food_beverage", fit="moderate"),
    R("Listen Ventures", CHI, "Seed; Series A", "Consumer; Consumer Brands; Food & Beverage",
      thesis="Consumer-obsessed venture firm that invests beyond capital to become a partner "
             "in building the brand.",
      portfolio="Calm; Catch Co; Dame; Factor; Interior Define",
      recent="Co-founder co-leads the investment committee.",
      partner=("Rick Desai", "Co-Founder and Managing Partner"),
      segment="food_beverage", fit="moderate"),
    R("Silas Capital", NY, "Seed; Series A; Growth",
      "Consumer; Consumer Brands; Food & Beverage",
      thesis="Venture and growth equity firm growing the next generation of consumer brands.",
      recent="Closed Fund II at a $150M hard cap.",
      partner=("Frank T. Lin", "Co-Founder and Managing Partner"),
      segment="food_beverage", fit="moderate"),
    R("Rocana Venture Partners", LA, "Pre-Seed; Seed",
      "Food & Beverage; CPG; Wellness; Beauty",
      thesis="Invests in early-stage consumer packaged goods brands, primarily food and "
             "beverage, with secondary focus on beauty, wellness, pet and fitness.",
      recent="Founded February 2018; co-founder spent 17 years in investment banking M&A "
             "across North America and Asia.",
      partner=("Gurdeep Prewal", "Co-Founder and General Partner"),
      segment="food_beverage", fit="moderate"),
    R("VMG Partners", SF, "Growth", "Food & Beverage; Consumer; Beauty; Personal Care",
      thesis="Private equity firm specialising in building iconic consumer brands.",
      recent="Founded 2005; team of roughly 50 professionals.",
      partner=("Wayne Wu", "General Partner"), segment="food_beverage", fit="weak"),
]

# --------------------------------------------------------------------------------------
# Found by walking the cap tables of comparable companies
# --------------------------------------------------------------------------------------
#
# The sharpest way to find an investor for a late-night premium delivery and ghost-kitchen
# operator is not to search for "food VC" — it is to ask who already wrote a cheque to
# CookUnity, Local Kitchens, Wonder, Sweetgreen, CAVA or REEF, and read their names off the
# round announcements. A fund that has already underwritten this business model does not
# need to be persuaded the category exists.

COMPARABLE_INVESTORS = [
    R("Pear VC", SF, "Pre-Seed; Seed",
      "Consumer; Marketplaces; Consumer Technology; E-commerce",
      check=("$250k", "$6M"),
      thesis="Pre-seed and seed specialists investing in consumer technology including "
             "marketplaces, subscription and e-commerce.",
      portfolio="Local Kitchens",
      recent="Backed Local Kitchens through its seed and Series A alongside General Catalyst.",
      partner=("Pejman Nozad", "Founding Managing Partner"),
      segment="comparable_investor", fit="strong"),
    R("Penny Jar Capital", SF, "Seed; Series A", "Consumer; Consumer Brands; Technology",
      thesis="Early-stage firm backing consumer and technology companies.",
      portfolio="Local Kitchens",
      recent="Invested in Local Kitchens' Series A; founded 2021 with Stephen Curry as "
             "anchor investor and special advisor.",
      partner=("Bryant Barr", "Founding Partner"),
      segment="comparable_investor", fit="strong"),
    R("RevTech Ventures", ("Dallas", "United States", "America/Chicago"), "Pre-Seed; Seed",
      "Restaurant Tech; Retail Tech; Hospitality Tech",
      thesis="Dallas-based venture accelerator and seed fund working exclusively with "
             "retail, restaurant and hospitality technology startups.",
      recent="Runs an accelerator with 100+ mentors drawn from restaurant, retail and "
             "venture backgrounds.",
      partner=("David Matthews", "Managing Partner"),
      segment="restaurant_hospitality", fit="strong"),
    R("Branch Venture Group", ("Boston", "United States", "America/New_York"), "Seed",
      "Food & Beverage; Food Tech; Hospitality Tech; Consumer",
      check=("$500k", "$3M"),
      thesis="The largest US angel network investing exclusively in food-related startups, "
             "spanning food and beverage, hospitality technology and marketplaces.",
      recent="Has invested over $3.7M across 18 portfolio companies since 2017, backing "
             "founders raising between $500K and $3M.",
      partner=("Lauren Abda", "Co-Founder"), segment="food_beverage", fit="strong"),
    R("Enlightened Hospitality Investments", NY, "Series A; Growth",
      "Restaurants; Hospitality; Food & Beverage",
      thesis="Growth equity firm affiliated with Danny Meyer's Union Square Hospitality "
             "Group, leveraging USHG's brands and operating team to back hospitality "
             "businesses.",
      portfolio="Joe Coffee; Salt & Straw; Goldbelly; Dig; Tacombi; Slutty Vegan; 7shifts",
      recent="Closed a second fund at $332M, above its $300M target; led Slutty Vegan's "
             "$25M Series A and 7shifts' $21.5M Series B.",
      partner=("Danny Meyer", "Co-Founder and Managing Partner"),
      segment="restaurant_hospitality", fit="moderate"),
    R("Act III Holdings", ("Boston", "United States", "America/New_York"), "Growth",
      "Restaurants; Consumer",
      thesis="Evergreen investment vehicle backing public and private restaurant and "
             "consumer companies with potential to dominate their niches.",
      portfolio="CAVA; Tatte; Life Alive; Clover Food Lab; Level99; BJ's Restaurants",
      recent="Grew from a $300M fund to a $1B+ evergreen vehicle; committed $100M to "
             "Level99 in 2026.",
      partner=("Ron Shaich", "Managing Partner"),
      segment="restaurant_hospitality", fit="moderate"),
    R("Revolution", ("Washington", "United States", "America/New_York"), "Seed; Series A",
      "Consumer; Restaurants; Technology; Marketplaces",
      check=("$250k", "$1M"),
      thesis="Backs entrepreneurs upending traditional industries, explicitly outside the "
             "coastal venture hubs; the Rise of the Rest Seed Fund writes $250K-$1M cheques.",
      portfolio="Sweetgreen; CAVA",
      recent="Rise of the Rest has invested in 200+ startups across 80+ US cities; "
             "Revolution was an early backer of both Sweetgreen and CAVA.",
      partner=("Steve Case", "Founder and Chairman"),
      segment="comparable_investor", fit="strong"),
    R("Bread and Butter Ventures", ("Minneapolis", "United States", "America/Chicago"),
      "Seed; Series A", "Food Tech; Food & Ag; Consumer",
      thesis="Invests in founders across food and ag tech, health tech and enterprise SaaS, "
             "leveraging Minnesota's corporate food industry connections.",
      recent="Raised $27M for its third fund; managing partner formerly ran the Techstars "
             "Farm to Fork accelerator with Cargill and Ecolab.",
      partner=("Brett Brohl", "Founder and Managing Partner"),
      segment="food_beverage", fit="moderate"),
    # Mandate mismatch, kept visible rather than silently dropped: NVF invests in companies
    # owned and managed by women of colour. It led Slutty Vegan's Series A, so it belongs in
    # the research trail, but Prime After Dark does not meet the stated mandate.
    R("New Voices Fund", NY, "Seed; Series A", "Consumer; Consumer Brands; Food & Beverage",
      thesis="Invests in companies owned and managed by women of colour.",
      portfolio="Slutty Vegan; The Honey Pot Company",
      recent="Manages a $100M fund across 27+ portfolio companies; co-led Slutty Vegan's "
             "$25M Series A with Enlightened Hospitality Investments.",
      partner=("Richelieu Dennis", "Managing Partner"),
      segment="comparable_investor", fit="weak"),
]

ALL_ROUND3 = HOSPITALITY + SOUTH_FLORIDA + CONSUMER_FB + COMPARABLE_INVESTORS

#: Firm -> the comparable company it already funded.
#:
#: This is the highest-value evidence in the whole list. "You led CookUnity's Series A" is a
#: first sentence no other founder's template produces, and it is verifiable, which is what
#: separates a specific opening from a flattering one.
COMPARABLE_CAP_TABLE = {
    "Fuel Venture Capital": (
        "Led CookUnity's $15.5M Series A — chef-prepared meal delivery, from a Miami fund."
    ),
    "General Catalyst": (
        "Led Local Kitchens' $25M Series A and its $40M follow-on, and committed up to "
        "$250M to CookUnity in 2025."
    ),
    "Pear VC": "Backed Local Kitchens from seed through its Series A.",
    "Penny Jar Capital": "Invested in Local Kitchens' Series A.",
    "Forerunner Ventures": "Participated in Wonder's $700M and $600M rounds.",
    "True Ventures": "An investor in Sweetgreen.",
    "Revolution": "An early backer of both Sweetgreen and CAVA.",
    "Kitchen Fund": "Backed CAVA, and was an early institutional investor in Sweetgreen.",
    "Enlightened Hospitality Investments": (
        "Led Slutty Vegan's $25M Series A and 7shifts' $21.5M Series B."
    ),
    "Act III Holdings": "Lead investor and board chair at CAVA; funded its Zoe's take-private.",
    "New Voices Fund": "Co-led Slutty Vegan's $25M Series A.",
}

#: Contacts resolved in this pass, each with the public source that named them.
ROUND3_CONTACTS = {
    "Lorrain de Silva": "Managing Director, Best Nights VC — Global Venturing, Crack Magazine, 032c",
    "Nate Cooper": "Founder and Managing Partner, Barrel Ventures — Crunchbase, adVentures Academy",
    "Jay Owen": "Co-Founder and Managing Partner, Dom Capital Group — CB Insights, RocketReach",
    "Anthony Owen": "Co-Founder and Managing Partner, Dom Capital Group — CB Insights",
    "Peter Herz": "Founding General Partner, 1st Course Capital — Menus of Change, Crunchbase",
    "Renske Lynde": "Founding General Partner, 1st Course Capital — Crunchbase, ImpactAssets",
    "Sanket Parekh": "Founder and Managing Partner, Secocha Ventures — Refresh Miami",
    "Edward Lando": "Co-Founder, Pareto Holdings — Crunchbase, fund site",
    "Jeff Ransdell": "Founding Partner and Managing Director, Fuel Venture Capital — fund site",
    "Maggie Vo": "Managing General Partner and CIO, Fuel Venture Capital — fund site",
    "Laura Gonzalez-Estefani": "Founder and General Partner, TheVentureCity — vcsheet, fund site",
    "Andres Dancausa": "General Partner, TheVentureCity — fund site",
    "David Zinn": "Co-Founder and Managing Partner, Ocean Azul Partners — Coral Gables Magazine",
    "Mark Volchek": "Founding and Co-Managing Partner, Las Olas VC — Crunchbase, fund profile",
    "Melissa Krinzman": "Managing Partner, Krillion Ventures — Refresh Miami, The Org",
    "Brett Thomas": "Co-Founder and Managing Partner, CAVU — Crunchbase, fund site",
    "Franklin Isacson": "Co-Founder and Managing Partner, Coefficient — Crunchbase, BusinessWire",
    "Jeff Cantalupo": "Co-Founder and Managing Partner, Listen Ventures — PR Newswire, Crain's",
    "Rick Desai": "Co-Founder and Managing Partner, Listen Ventures — PR Newswire",
    "Frank T. Lin": "Co-Founder and Managing Partner, Silas Capital — PR Newswire, fund site",
    "Gurdeep Prewal": "Co-Founder and General Partner, Rocana — Investor Connect, fund site",
    "Wayne Wu": "General Partner, VMG Partners — fund site, The Org",
    "Pejman Nozad": "Founding Managing Partner, Pear VC — fund site",
    "Bryant Barr": "Founding Partner, Penny Jar Capital — Crunchbase, TechCrunch",
    "David Matthews": "Managing Partner, RevTech Ventures — fund site, Datanyze",
    "Lauren Abda": "Co-Founder, Branch Venture Group — Edible Boston, VC Include",
    "Danny Meyer": "Co-Founder and Managing Partner, EHI — ehi.fund, FSR Magazine",
    "Ron Shaich": "Managing Partner, Act III Holdings — act3holdings.com, NRN, Fortune",
    "Steve Case": "Founder and Chairman, Revolution — revolution.com, Crunchbase",
    "Brett Brohl": "Founder and Managing Partner, Bread and Butter — Crunchbase, Star Tribune",
    "Richelieu Dennis": "Managing Partner, New Voices Fund — newvoicesfund.com, Forbes",
}

#: Firm -> the stated mandate that rules this company out, whatever the sector fit.
#:
#: Fit scoring reads stage, sector, cheque size and geography. It cannot read a fund's
#: eligibility criteria, so a fund can score well and still be one whose own published
#: mandate excludes this founder. Emailing anyway wastes the send and, worse, tells the
#: recipient the sender did not read the first line of their website.
MANDATE_EXCLUSIONS = {
    "New Voices Fund": (
        "invests only in companies owned and managed by women of colour — Prime After "
        "Dark does not meet the stated mandate"
    ),
}

#: Firms that turned out to be the same entity under two names.
MERGE_AS_DUPLICATE = {
    # Best Nights VC *is* the venture unit of Mast-Jaegermeister SE. Carrying both names
    # would have put two records, and potentially two emails, on one fund.
    "Mast-Jagermeister Ventures": "Best Nights VC",
}

EMAIL_NOTES = """
No email address is recorded in this pass.

Partner names came from search-result summaries, which state names and titles but do not
publish inboxes. Reading a fund's own team or contact page requires fetching it, and every
outbound page fetch from this environment is refused by the network policy (403 at the
proxy on every host tried, checked three times).

Guessing is the one option that looks like progress and is not. A wrong address bounces,
bounces are the single strongest negative signal a receiving domain has, and the reputation
they burn belongs to the sending domain this whole system exists to protect. So the addresses
stay empty and EmailConfidence stays UNKNOWN, which is what makes the send preflight refuse
to dispatch. Filling the column is a human step: fund contact pages, a warm intro, or a
verification service run against the pattern.
"""
