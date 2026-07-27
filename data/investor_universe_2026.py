"""Researched investor universe for Prime After Dark's seed round (July 2026).

Every firm below was surfaced by a public web search during this research session. Fields
are populated ONLY where the source actually stated them; unknown fields stay empty rather
than being guessed, because a fabricated check size or thesis would corrupt the fit scoring
that this list exists to feed.

**There are no email addresses in this file, and that is deliberate.** Contact details were
not reachable from this environment, and inventing them would be actively harmful: an
invented address bounces, bounces burn sender reputation, and sender reputation is the
budget the entire engine is built to conserve (R0.1, R3.6). Every record therefore carries
``email_confidence = unknown`` and is quarantined by R1.4 at ingest until a human resolves
a named partner and a verified address.

Segment tags map roughly to how relevant the firm is to a Miami premium late-night delivery
brand raising an institutional seed. The tags are *not* the fit score — the engine computes
that from thesis and portfolio evidence. They only describe why the firm entered the list.

Sources are the public directories, fund profiles and trade press surfaced in search:
openvc.app, failory.com, rho.co, ellty.com, shizune.co, signal.nfx.com, vcsheet.com,
f4.fund, emerging.com, aaronallen.com, crunchbase.com, pitchbook.com, forbes.com,
foodnavigator.com, agfundernews.com, techcrunch.com, fintrx.com, confluence.vc and the
funds' own published descriptions.
"""

from __future__ import annotations

# Field order:
#   firm, city, country, timezone, stages, sectors, check_min, check_max,
#   thesis, portfolio, recent_activity, partner_name, partner_role, segment
#
# Empty string means "not established by the source". It is not a default.

FIELDS = (
    "firm", "city", "country", "timezone", "stages", "sectors", "check_min", "check_max",
    "thesis", "portfolio", "recent_activity", "partner_name", "partner_role", "segment",
)

NY = ("New York", "United States", "America/New_York")
SF = ("San Francisco", "United States", "America/Los_Angeles")
LA = ("Los Angeles", "United States", "America/Los_Angeles")
MIA = ("Miami", "United States", "America/New_York")
CHI = ("Chicago", "United States", "America/Chicago")
AUS = ("Austin", "United States", "America/Chicago")
BOS = ("Boston", "United States", "America/New_York")
BOU = ("Boulder", "United States", "America/Denver")
TOR = ("Toronto", "Canada", "America/Toronto")
UNK = ("", "", "")


def R(firm, loc, stages, sectors, check=("", ""), thesis="", portfolio="", recent="",
      partner=("", ""), segment=""):
    city, country, tz = loc
    return {
        "firm": firm, "city": city, "country": country, "timezone": tz,
        "stages": stages, "sectors": sectors,
        "check_min": check[0], "check_max": check[1],
        "thesis": thesis, "portfolio": portfolio, "recent_activity": recent,
        "partner_name": partner[0], "partner_role": partner[1], "segment": segment,
    }


# --------------------------------------------------------------------------------------
# Tier 1 — food, beverage and CPG specialists
# --------------------------------------------------------------------------------------

FOOD_BEVERAGE = [
    R("Rocana Venture Partners", UNK, "Seed; Series A", "Food & Beverage; CPG; Wellness",
      thesis="Early-stage food and beverage with an emphasis on wellness-oriented products, "
             "functional beverages and plant-based categories.",
      portfolio="Olipop; Poppi", recent="Backed Olipop and Poppi before gut-health drinks hit the mainstream.",
      segment="food_beverage"),
    R("CAVU Consumer Partners", AUS, "Seed; Series A; Growth", "Food & Beverage; Wellness; Consumer",
      thesis="Invests in the better-for-you consumer sector across food, beverage and wellness, "
             "from seed to late stage, with hands-on marketing and operating support.",
      portfolio="Beyond Meat; Oatly; The Farmer's Dog",
      recent="Co-founded by Clayton Christopher, who built and sold Sweet Leaf Tea and Deep Eddy Vodka.",
      partner=("Clayton Christopher", "Co-Founder"), segment="food_beverage"),
    R("VMG Partners", SF, "Seed; Series A; Growth", "Food & Beverage; Beauty; Personal Care",
      thesis="Invests seed through private equity in food, beverage, beauty and personal care brands.",
      portfolio="Drunk Elephant; Quest Nutrition", recent="Fund VI reported at $1B.",
      segment="food_beverage"),
    R("Coefficient Capital", NY, "Pre-Seed; Seed; Series A", "Food & Beverage; Beauty; Wellness; Consumer",
      thesis="Consumer sector specialist targeting innovative brands across food and beverage, "
             "beauty and wellness, engaging from pre-seed through Series A.",
      recent="Closed oversubscribed Fund II at $290M in March 2026.", segment="food_beverage"),
    R("Springdale Ventures", AUS, "Seed; Series A", "Food & Beverage; CPG; Pet; Health & Beauty",
      check=("$1M", "$1M"),
      thesis="Emerging consumer brands across food, beverage, pet, health and beauty at seed "
             "through Series A.",
      recent="Raised $40M for Fund II targeting early-stage CPG brands.",
      partner=("Genevieve Gilbreath", "Co-Founder"), segment="food_beverage"),
    R("Selva Ventures", SF, "Seed; Series A", "Consumer; Health & Wellness; CPG",
      thesis="Backs emerging consumer brands improving health and wellness, prioritising clean "
             "ingredients, typically before $10M in annual sales.", segment="food_beverage"),
    R("Boulder Food Group", BOU, "Seed; Series A", "Food & Beverage; CPG",
      thesis="Partners with early-stage food and beverage consumer product companies.",
      recent="Raised a $100M fund for early-stage food and beverage.",
      partner=("Tom Spier", "Founder"), segment="food_beverage"),
    R("PowerPlant Partners", LA, "Series A; Growth", "Food & Beverage; Foodservice; Food Tech; Wellness",
      thesis="Growth equity for emerging consumer food, beverage, foodservice, food-tech and "
             "personal wellness brands, founded by the creators of ZICO coconut water.",
      portfolio="Beyond Meat; Thrive Market; Rebbl", recent="Closed third fund at $330M.",
      segment="food_beverage"),
    R("Sunrise Strategic Partners", BOU, "Growth", "Food & Beverage; Healthy Living",
      thesis="Growth capital and operating expertise for emerging food and beverage brands in "
             "the healthy, active and sustainable living space.",
      partner=("Steve Hughes", "Founder"), segment="food_beverage"),
    R("Siddhi Capital", UNK, "Seed; Series A; Growth", "Food & Beverage; CPG; Food Tech",
      thesis="Growth-stage CPG brands providing restaurant-quality foods and beverages, plus "
             "food-tech; roughly two-thirds CPG and one-third food-tech.",
      recent="Raised $135M for Fund II.", segment="food_beverage"),
    R("Sonoma Brands Capital", ("Sonoma", "United States", "America/Los_Angeles"),
      "Growth", "Food & Beverage; Consumer",
      thesis="Minority and control investments in growth-stage consumer businesses, typically "
             "above $5M in sales.", recent="Founded 2015 in California wine country; team of 10 including 5 partners.",
      segment="food_beverage"),
    R("Manna Tree Partners", UNK, "Growth", "Food; Health & Wellness",
      thesis="Invests in companies that empower consumers to live better, longer lives through "
             "improved health and wellness.", segment="food_beverage"),
    R("Big Idea Ventures", NY, "Pre-Seed; Seed", "Food Tech; Plant-Based; CPG",
      thesis="Venture fund focused on the plant-based and alternative protein food sector.",
      recent="45 companies invested as of March 2026.", segment="food_beverage"),
    R("Stray Dog Capital", ("Kansas City", "United States", "America/Chicago"),
      "Seed; Series A", "Food Tech; Plant-Based; CPG",
      thesis="Emerging plant-based brands and alternative protein.",
      portfolio="Kite Hill; Beyond Meat; Miyoko's; Good Catch", segment="food_beverage"),
    R("Clear Current Capital", UNK, "Seed", "Food Tech; Plant-Based",
      thesis="Invests in plant-based and alternative protein startups.", segment="food_beverage"),
    R("S2G Investments", CHI, "Seed; Series A; Growth", "Food; Agriculture; Oceans; Energy",
      thesis="Multi-stage investor across food and agriculture, oceans and energy, backing "
             "healthier and more sustainable systems from seed to post-IPO.",
      recent="$2.5B in committed capital.", segment="food_beverage"),
    R("Astanor Ventures", UNK, "Seed; Series A; Growth", "Food; Agriculture; Impact",
      thesis="Backs entrepreneurs regenerating the food, blue ocean economy and agriculture sectors.",
      segment="food_beverage"),
    R("AgFunder", SF, "Seed", "Food Tech; AgTech",
      thesis="Global venture firm backing deeptech across food and agriculture, AI, biotech and robotics.",
      segment="food_beverage"),
    R("Blue Horizon", UNK, "Series A; Growth", "Food Tech; Alternative Protein",
      thesis="Supports later rounds for scaling production and global expansion in sustainable food.",
      segment="food_beverage"),
    R("InvestBev", CHI, "Seed; Growth", "Beverage; Adult Beverage; Beverage Tech",
      thesis="Private equity dedicated to the adult beverage industry: brands, raw distillate, "
             "beverage technology and cannabis beverage.",
      recent="$300M AUM and $100M in private credit; announced a $14M strategic investment in January 2026.",
      partner=("Brian Rosen", "Founder"), segment="food_beverage"),
    R("BeliV", UNK, "Seed; Series A", "Beverage; Food & Beverage",
      thesis="Beverage-focused investor.", recent="Co-led Bulletproof's $13M raise.", segment="food_beverage"),
    R("Prelude Growth Partners", NY, "Growth", "Consumer; Beauty; Food & Beverage",
      thesis="Growth investor in high-growth consumer brands.", segment="food_beverage"),
    R("Alliance Consumer Growth", NY, "Series A; Growth", "Consumer; Food & Beverage; Retail",
      thesis="Invests in emerging consumer, food and beverage and retail brands.",
      recent="Frequently follows Sonoma Brands into consumer rounds.", segment="food_beverage"),
    R("KarpReilly", ("Greenwich", "United States", "America/New_York"), "Growth",
      "Consumer; Restaurants; Retail; Food & Beverage",
      thesis="Growth-stage investor across retail, direct-to-consumer, e-commerce, restaurants, "
             "apparel and branded consumer products.",
      partner=("Allan Karp", "Co-Founder"), segment="restaurant_hospitality"),
    R("301 INC", ("Minneapolis", "United States", "America/Chicago"), "Seed; Series A",
      "Food & Beverage; CPG",
      thesis="General Mills' venture arm, investing in emerging food and beverage brands.",
      portfolio="Kite Hill; Good Culture; Tio Gazpacho; Rhythm Superfoods", segment="corporate_vc"),
    R("SnackFutures Ventures", CHI, "Seed; Series A", "Food & Beverage; Snacking; CPG",
      thesis="Mondelez International's corporate venture arm, pushing the boundaries of snacking.",
      segment="corporate_vc"),
    R("Tyson Ventures", ("Springdale", "United States", "America/Chicago"), "Series A; Growth",
      "Food; Protein; Food Tech",
      thesis="Tyson Foods' venture arm, investing in breakthrough technologies, business models "
             "and products across food.", portfolio="Beyond Meat; Tovala; Memphis Meats",
      segment="corporate_vc"),
    R("Danone Manifesto Ventures", NY, "Seed; Series A", "Food & Beverage; Health",
      thesis="Danone's venture arm supporting companies that promote healthier, more sustainable "
             "eating practices.", segment="corporate_vc"),
    R("Cultivate Ventures", UNK, "Seed; Series A", "Food & Beverage; CPG",
      thesis="Hain Celestial's platform investing in lifestyle brands and emerging concepts.",
      segment="corporate_vc"),
    R("Evolv Ventures", CHI, "Seed; Series A", "Food Tech; Consumer; Commerce",
      thesis="Kraft Heinz-backed venture fund investing in technology across the food ecosystem.",
      segment="corporate_vc"),
    R("Unilever Ventures", UNK, "Seed; Series A", "Consumer; Beauty; Personal Care",
      thesis="Unilever's venture arm, a strategic CPG partner to consumer brands.", segment="corporate_vc"),
    R("Companion Fund", UNK, "Seed; Series A", "Consumer; Pet; CPG",
      thesis="Mars-backed fund investing alongside consumer brands.", segment="corporate_vc"),
    R("Shopify Ventures", TOR, "Seed; Series A", "Commerce; Retail Tech",
      thesis="Strategic capital into startups that enhance the commerce ecosystem.", segment="corporate_vc"),
    R("Almanac Investments", UNK, "Seed", "Food & Beverage; CPG",
      thesis="Supports innovative food and beverage startups.", segment="food_beverage"),
    R("Ridgeline Ventures", UNK, "Seed; Series A", "Food & Beverage; Consumer",
      thesis="Backs emerging food and beverage and consumer companies.", segment="food_beverage"),
    R("Revolution Growth", ("Washington", "United States", "America/New_York"), "Series A; Growth",
      "Consumer; Food & Beverage; Technology",
      thesis="Growth investor backing companies outside traditional coastal hubs.", segment="consumer"),
    R("Silas Capital", NY, "Seed; Series A; Growth", "Consumer; Food & Beverage; Beauty",
      thesis="Venture and growth equity investing in emerging consumer brands from early stage "
             "through growth.", segment="consumer"),
    R("AF Ventures", NY, "Seed; Series A", "Food & Beverage; CPG; Consumer",
      thesis="Active food and beverage investor backing emerging consumer brands.", segment="food_beverage"),
    R("Barrel Ventures", UNK, "Seed", "Food & Beverage; CPG",
      thesis="Early-stage food and beverage investor.", segment="food_beverage"),
    R("Bread and Butter Ventures", ("Minneapolis", "United States", "America/Chicago"), "Seed",
      "Food & Beverage; AgTech; Health",
      thesis="Seed investor across food, agriculture and health.", segment="food_beverage"),
    R("Five Seasons Ventures", UNK, "Seed; Series A", "Food & Beverage; Food Tech",
      thesis="European food and agriculture technology venture fund.", segment="food_beverage"),
    R("Melitas Ventures", UNK, "Seed; Series A", "Food & Beverage; CPG",
      thesis="Invests in emerging food and beverage brands.", segment="food_beverage"),
    R("Sandbox Industries", CHI, "Seed; Series A", "Food & Beverage; AgTech; Insurance",
      thesis="Invests across food, agriculture and adjacent sectors.", segment="food_beverage"),
    R("Better Food Ventures", SF, "Pre-Seed; Seed", "Food Tech; Restaurant Tech",
      thesis="Early-stage investor funding concept-to-market food technology startups.", segment="food_beverage"),
    R("1st Course Capital", SF, "Pre-Seed; Seed", "Food Tech; AgTech",
      thesis="Early-stage investor in food and agriculture technology.", segment="food_beverage"),
    R("FoodLabs", UNK, "Pre-Seed; Seed", "Food Tech; Food & Beverage",
      thesis="Early-stage food technology and sustainability investor.", segment="food_beverage"),
    R("PeakBridge", UNK, "Seed; Series A; Series B", "Food Tech; Food & Beverage",
      thesis="Global impact venture fund connecting the people, technology and processes shaping "
             "the future of food, from early stage to Series A-B.", segment="food_beverage"),
    R("Anterra Capital", UNK, "Series A; Growth", "Food; AgTech; Health",
      thesis="Backs startups and entrepreneurs building a healthier food system.", segment="food_beverage"),
    R("Branch Venture Group", BOS, "Pre-Seed; Seed", "Food & Beverage; CPG; Food Tech; AgTech",
      thesis="Boston investment network providing funding and advice to early-stage food companies "
             "across food and beverage CPG, foodtech and agtech.", segment="food_beverage"),
    R("Fresh Source Capital", BOS, "Seed; Series A", "Food; Food Tech",
      thesis="Funds companies whose products, services and technologies provide better food to "
             "consumers and institutions.", segment="food_beverage"),
    R("Sherbrooke Capital", BOS, "Growth", "Consumer; Health & Wellness; Food & Beverage",
      thesis="Growth capital exclusively for emerging consumer companies in the healthy, active "
             "and sustainable living market.", segment="food_beverage"),
    R("Castanea Partners", BOS, "Growth", "Consumer; Food & Beverage; Beauty",
      thesis="Consumer-focused growth investor.", portfolio="Pirate Brands; Dave's Killer Bread",
      segment="food_beverage"),
    R("Breakaway Ventures", BOS, "Seed", "Consumer; Food & Beverage",
      thesis="Consumer-focused venture capital firm.", segment="consumer"),
    R("Trailhead Capital", BOU, "Seed", "Food; AgTech; Regenerative",
      thesis="Seed and early-stage investor in regenerative food and agriculture.", segment="food_beverage"),
    R("District Ventures Capital", ("Calgary", "Canada", "America/Edmonton"), "Seed; Series A",
      "Food & Beverage; Health; CPG",
      thesis="Invests in innovative food and health sector companies.",
      partner=("Arlene Dickinson", "Managing Partner"), segment="food_beverage"),
    R("Ankur Capital", UNK, "Seed; Series A", "Food; AgTech",
      thesis="Early-stage investor across food and agriculture.", segment="food_beverage"),
    R("Winklevoss Capital", NY, "Seed", "Consumer; Food & Beverage; Crypto",
      thesis="Backs early-stage consumer and food and beverage companies.", segment="consumer"),
    R("Lattice Ventures", NY, "Seed", "Consumer; Food & Beverage",
      thesis="Seed investor across consumer and food categories.", segment="consumer"),
    R("Math Venture Partners", CHI, "Seed; Series A", "Consumer; Marketplaces; Food & Beverage",
      thesis="Backs companies with distribution advantage.", segment="consumer"),
    R("Sugar Capital", SF, "Seed", "Consumer; CPG; Commerce",
      thesis="Seed-stage consumer and commerce investor.", segment="consumer"),
    R("True Beauty Ventures", NY, "Seed; Series A", "Beauty; Consumer; CPG",
      thesis="Beauty and personal care consumer brands.", segment="consumer"),
    R("Crush Ventures", NY, "Seed", "Consumer; Food & Beverage; Music",
      thesis="Seed-stage consumer investor with brand-building support.", segment="consumer"),
]

# --------------------------------------------------------------------------------------
# Tier 1 — restaurant, hospitality and nightlife
# --------------------------------------------------------------------------------------

RESTAURANT_HOSPITALITY = [
    R("Branded Hospitality Ventures", NY, "Pre-Seed; Seed; Series A",
      "Hospitality; Food & Beverage; Restaurant Tech; Foodservice",
      thesis="Investment and advisory platform for hospitality and foodservice, focused on "
             "technology-driven and innovative food and beverage concepts that improve guest "
             "experience and operating efficiency.",
      portfolio="Ottonomy IO; Mr Bing", recent="Founded 2017; invests pre-seed to Series A across "
             "food and beverage, software, proptech, fintech and robotics touching hospitality.",
      segment="restaurant_hospitality"),
    R("Enlightened Hospitality Investments", NY, "Series A; Growth",
      "Restaurant Tech; Hospitality; Food & Beverage",
      thesis="Union Square Hospitality Group's fund, investing with 30+ years of restaurant "
             "operating experience behind it.",
      portfolio="Goldbelly; BentoBox; Resy; Salt & Straw; Dig; Joe Coffee",
      segment="restaurant_hospitality"),
    R("Kitchen Fund", NY, "Seed; Series A", "Restaurants; Food & Beverage; Restaurant Tech",
      thesis="Early-stage specialist investing exclusively in restaurant innovation.",
      portfolio="Curry Up Now; The Pie Hole; Gregorys Coffee; JUICER",
      recent="Invested in Gregorys Coffee (2025) and JUICER's $5.3M seed round (2024).",
      segment="restaurant_hospitality"),
    R("Best Nights VC", NY, "Pre-Seed; Seed", "Nightlife; Hospitality Tech; Consumer Experience",
      thesis="Boutique early-stage fund backing nightlife, hospitality-tech and consumer "
             "experience startups reimagining how people gather socially.",
      segment="restaurant_hospitality"),
    R("Mast-Jagermeister Ventures", UNK, "Pre-Seed; Seed; Series A",
      "Nightlife; Hospitality; Consumer",
      check=("$300k", "$1M"),
      thesis="Jagermeister's venture arm investing in nightlife technology, social platforms and "
             "community-driven hospitality.", segment="restaurant_hospitality"),
    R("Savory Fund", ("Salt Lake City", "United States", "America/Denver"), "Growth",
      "Restaurants; Food & Beverage; Multi-Unit",
      thesis="Invests in emerging restaurant concepts, providing capital and operating expertise "
             "to scale them into multi-unit brands beyond their founding region.",
      portfolio="Mo' Bettahs; Via 313; Hash Kitchen; South Block",
      recent="$20M growth partnership with Hash Kitchen targeting ~30 new locations over four years.",
      segment="restaurant_hospitality"),
    R("Rosser Capital Partners", UNK, "Growth", "Restaurants; Hospitality",
      thesis="Restaurant-focused investor with flexible targets, backing emerging concepts.",
      portfolio="BarTaco; Barcelona Wine Bar; Skillets", segment="restaurant_hospitality"),
    R("10 Point Capital", ("Atlanta", "United States", "America/New_York"), "Growth",
      "Restaurants; Franchise; Multi-Unit",
      thesis="Partners with founders and operating executives of multi-unit and franchise businesses.",
      segment="restaurant_hospitality"),
    R("Thayer Investment Partners", SF, "Seed; Series A", "Hospitality; Travel; Restaurant Tech",
      thesis="Early-stage travel and hospitality technology; formed by the combination of Thayer "
             "Ventures and Derive Ventures.",
      portfolio="Sonder; Mews; Duetto; Canary Technologies; NoiseAware; HyperGuest; Operto",
      recent="Four active vehicles, over $300M deployed and 30+ active portfolio companies.",
      segment="restaurant_hospitality"),
    R("Derive Ventures", UNK, "Seed", "Hospitality; Travel",
      thesis="Early-stage travel and hospitality investor, founded 2022.", segment="restaurant_hospitality"),
    R("Jaws Ventures", MIA, "Seed; Series A", "Hospitality; Consumer; Real Estate",
      thesis="Barry Sternlicht-affiliated vehicle investing across hospitality and consumer.",
      segment="restaurant_hospitality"),
    R("JAWS Estates Capital", MIA, "Growth", "Hospitality; Food & Beverage; Real Estate",
      thesis="Family office with keen interest in food and beverage and hospitality.",
      recent="Acquired Miami Beach's Standard Hotel in January 2022.", segment="family_office"),
    R("Elysium Management", NY, "Growth", "Restaurants; Hospitality; Food & Beverage; Franchise",
      thesis="Private equity and direct investments in retail, food and beverage, restaurants, "
             "hospitality and franchises.", portfolio="Huddle House", segment="family_office"),
    R("Cleveland Avenue", CHI, "Seed; Series A; Growth",
      "Restaurants; Food Tech; Beverage; Consumer",
      thesis="Chicago venture firm investing in restaurant, food tech and beverage companies "
             "across North America, founded by the former CEO of McDonald's.",
      portfolio="Beyond Meat; Bhakti; Farmwise Foods; Bright Cellars",
      recent="Runs a $70M CAST US fund mandated to deploy 75% into Black- and Hispanic-owned companies.",
      partner=("Don Thompson", "Founder"), segment="restaurant_hospitality"),
    R("Listen Ventures", CHI, "Seed; Series A", "Consumer Brands; D2C; Wellness; Food & Beverage",
      thesis="Consumer-focused firm backing brands with potential to capture consumer attention "
             "and disrupt established markets.", portfolio="Go Brewing; Good Bacteria",
      segment="consumer"),
    R("Trive Capital", ("Dallas", "United States", "America/Chicago"), "Growth",
      "Restaurants; Consumer; Industrials",
      thesis="Equity and debt in middle-market companies with transformational upside through "
             "operational improvement.", portfolio="Mo' Bettahs", segment="restaurant_hospitality"),
    R("Sun Capital Partners", ("Boca Raton", "United States", "America/New_York"), "Growth",
      "Restaurants; Consumer; Retail",
      thesis="Named among the top private equity investors for the restaurant industry.",
      portfolio="Johnny Rockets; Friendly's; Boston Market; Bar Louie",
      recent="Over $13B in capital commitments.", segment="restaurant_hospitality"),
    R("KKR", NY, "Growth", "Restaurants; Consumer; Multi-Sector",
      thesis="Global private equity active in restaurant buyouts.", portfolio="Lemonade Restaurant Group",
      segment="restaurant_hospitality"),
    R("NBK Capital Partners", UNK, "Growth", "Restaurants; Consumer",
      thesis="Regional private equity active in restaurant deals, $875M in commitments.",
      segment="restaurant_hospitality"),
    R("GPS Hospitality", ("Atlanta", "United States", "America/New_York"), "Growth",
      "Restaurants; Franchise",
      thesis="Large multi-brand franchisee operation approaching 500 units.",
      portfolio="Burger King; Popeyes; Pizza Hut", segment="restaurant_hospitality"),
    R("Lamont Companies", UNK, "Growth", "Hospitality; Restaurants; Hotels",
      thesis="Single-family office developing franchised hotels and restaurants across the US.",
      segment="family_office"),
    R("Dom Capital Group", CHI, "Seed; Growth", "Food; Restaurants; Consumer",
      thesis="Single-family office with roots in a 1918 family deli and food store.",
      portfolio="Junzi Kitchen", segment="family_office"),
    R("The Losa Group", UNK, "Growth", "Food & Beverage; Hospitality; Agriculture; Entertainment",
      thesis="Family office targeting food and beverage, agriculture, entertainment and hospitality.",
      segment="family_office"),
]

# --------------------------------------------------------------------------------------
# Tier 2 — delivery, marketplace and commerce infrastructure
# --------------------------------------------------------------------------------------

DELIVERY_COMMERCE = [
    R("Sequoia Capital", SF, "Seed; Series A; Growth", "Delivery; Marketplaces; Technology",
      check=("$1M", "$200M"),
      thesis="Deep logistics and delivery portfolio, technology-first delivery solutions from "
             "seed to growth.", portfolio="DoorDash", segment="delivery"),
    R("Andreessen Horowitz", ("Menlo Park", "United States", "America/Los_Angeles"),
      "Seed; Series A; Growth", "Food Tech; Ghost Kitchens; Consumer; Technology",
      thesis="Multi-stage fund backing commerce infrastructure, logistics and food technology.",
      portfolio="Virtual Kitchen Co; All Day Kitchens; Foodology",
      recent="Backed Virtual Kitchen Co's $15M Series A and All Day Kitchens.", segment="delivery"),
    R("Founders Fund", SF, "Seed; Series A; Growth", "Food Tech; Ghost Kitchens; Delivery",
      thesis="Backs contrarian technology companies including ghost kitchen infrastructure.",
      portfolio="Virtual Kitchen Co; Ritual; Postmates", segment="delivery"),
    R("SoftBank Vision Fund", UNK, "Growth", "Delivery; Ghost Kitchens; Technology",
      thesis="Late-stage technology investor.", portfolio="CloudKitchens",
      recent="Led CloudKitchens' $400M round at a $5B valuation.", segment="delivery"),
    R("Tiger Global Management", NY, "Growth", "Delivery; Marketplaces; Technology",
      check=("$50M", "$500M"),
      thesis="Growth investor active in delivery technology and marketplaces.",
      portfolio="Instacart; EatClub", segment="delivery"),
    R("Prologis Ventures", SF, "Series A; Growth", "Logistics; Supply Chain; Last Mile",
      check=("$5M", "$50M"),
      thesis="Corporate venture arm of the logistics real estate group, focused on supply chain "
             "and last-mile solutions.", segment="delivery"),
    R("Maersk Growth", UNK, "Series A; Growth", "Logistics; Supply Chain; Last Mile",
      check=("$10M", "$50M"),
      thesis="Corporate venture arm focused on supply chain innovation and last-mile technology.",
      portfolio="Huboo; Forto; Afresh", segment="delivery"),
    R("Y Combinator", SF, "Pre-Seed; Seed", "Technology; Delivery; Consumer",
      thesis="Accelerator that has launched over 200 notable companies including DoorDash.",
      portfolio="DoorDash; Coinbase; Reddit", segment="delivery"),
    R("Commerce Ventures", SF, "Seed; Series A; Series B", "Retail Tech; Commerce; Fintech",
      thesis="Retail and commerce technology investor across seed through later stages.",
      portfolio="Bill.com; Marqeta; Forter", segment="commerce"),
    R("Silicon Road Ventures", ("Atlanta", "United States", "America/New_York"), "Seed",
      "Retail Tech; Commerce", thesis="Seed-stage retail technology investor.", segment="commerce"),
    R("RevTech Ventures", ("Dallas", "United States", "America/Chicago"), "Seed",
      "Retail Tech; Restaurant Tech; Commerce",
      thesis="Seed-stage retail and restaurant technology accelerator and fund.", segment="commerce"),
    R("Mu Ventures", UNK, "Seed", "Retail Tech; Commerce",
      thesis="Seed-stage retail technology investor.", segment="commerce"),
    R("FJ Labs", NY, "Seed; Series A", "Marketplaces; Commerce; Consumer",
      thesis="Marketplace and network-effect specialist.", segment="commerce"),
    R("Index Ventures", SF, "Seed; Series A; Growth", "Commerce; Marketplaces; Technology",
      thesis="Invested in Shopify and marketplace leaders across Europe and the US.", segment="commerce"),
    R("Accel", ("Palo Alto", "United States", "America/Los_Angeles"), "Seed; Series A; Growth",
      "Commerce; SaaS; Consumer",
      thesis="Focused on SaaS tools powering commerce growth.", segment="commerce"),
    R("Bessemer Venture Partners", SF, "Series A; Growth", "Consumer Commerce; SaaS; Fintech",
      thesis="Series A through late stage across SaaS, cloud, consumer commerce and fintech.",
      segment="commerce"),
    R("Lightspeed Venture Partners", ("Menlo Park", "United States", "America/Los_Angeles"),
      "Seed; Series A; Growth", "Retail Tech; D2C; Consumer",
      thesis="Early-stage retail technology and direct-to-consumer.", segment="commerce"),
    R("Greylock Partners", ("Menlo Park", "United States", "America/Los_Angeles"),
      "Seed; Series A", "B2B Commerce; Logistics",
      thesis="B2B commerce and logistics innovation.", segment="commerce"),
    R("Bain Capital Ventures", BOS, "Seed; Series A; Growth", "Payments; Retail Tech; Fintech",
      thesis="Payments and enterprise retail technology.", segment="commerce"),
    R("14W", NY, "Seed; Series A", "Consumer Internet; Marketplaces; CPG; Media",
      thesis="Consumer internet, marketplace, e-commerce, CPG and media specialist.", segment="consumer"),
    R("Ascend Venture Capital", ("Seattle", "United States", "America/Los_Angeles"), "Pre-Seed",
      "Marketplaces; Consumer Brands; E-commerce",
      thesis="Most active pre-seed fund in the Pacific Northwest, investing in marketplaces, "
             "consumer brands and e-commerce.", segment="consumer"),
    R("Camber Creek", ("Washington", "United States", "America/New_York"), "Seed; Series A",
      "PropTech; Real Estate Tech", thesis="Real estate technology investor.", segment="commerce"),
]

# --------------------------------------------------------------------------------------
# Tier 1 — Miami and Florida (geography is a real signal for this company)
# --------------------------------------------------------------------------------------

MIAMI_FLORIDA = [
    R("Fuel Venture Capital", MIA, "Seed; Series A; Growth", "Consumer Tech; AI; Financial Markets",
      thesis="Partners with founders from seed to growth across technology, with a Latin America "
             "connection.", portfolio="Replit; CookUnity; Betr",
      recent="Manages roughly $150M across two funds; 40+ portfolio companies.", segment="miami"),
    R("Secocha Ventures", MIA, "Pre-Seed; Seed", "Consumer Products; Consumer Services; FinTech; Digital Health",
      thesis="Early-stage B2C investor, predominantly fintech, digital health and consumer "
             "products and services.", segment="miami"),
    R("Krillion Ventures", MIA, "Seed", "Consumer Tech; Health; Finance",
      thesis="Miami-focused firm investing in early-stage health, finance and consumer technology.",
      segment="miami"),
    R("Ocean Azul Partners", MIA, "Seed; Early Stage", "Technology; Consumer",
      check=("$200k", "$3M"), thesis="Early-stage and seed investor writing $200K-$3M.", segment="miami"),
    R("ANIMO Ventures", MIA, "Seed; Series A", "Technology; Consumer",
      thesis="Miami-based early-stage venture firm.", segment="miami"),
    R("TheVentureCity", MIA, "Pre-Seed; Seed", "Technology; Consumer; Data",
      check=("$500k", "$2M"),
      thesis="Combines capital with operational support; 40+ Miami-based portfolio companies.",
      segment="miami"),
    R("Miami Angels", MIA, "Seed", "Consumer; SaaS; FinTech; Climate",
      check=("$200k", "$500k"),
      thesis="Angel network whose members collectively invest $200K-$500K in seed companies, "
             "often co-investing with institutional funds.",
      recent="Over 150 angel investors in the network.", segment="miami"),
    R("Atomic", MIA, "Pre-Seed; Seed", "Consumer; Technology",
      thesis="Venture studio combining ideas, talent and capital to build companies in parallel.",
      portfolio="Hims & Hers; Bungalow; OpenStore", segment="miami"),
    R("Rokk3r", MIA, "Pre-Seed; Seed", "Technology; Consumer",
      thesis="Venture builder creating companies from scratch.", segment="miami"),
    R("Pareto Holdings", MIA, "Pre-Seed; Seed", "Technology; Consumer; FinTech",
      thesis="Miami-based early-stage investor and ecosystem builder.", segment="miami"),
    R("Alpaca VC", MIA, "Seed; Series A", "PropTech; Consumer; Commerce",
      thesis="Invests across proptech, consumer and commerce.", segment="miami"),
    R("305 Ventures", MIA, "Pre-Seed; Seed", "Technology; Consumer",
      thesis="Miami early-stage fund.", segment="miami"),
    R("Exceptional Capital", MIA, "Pre-Seed; Seed", "Enterprise SaaS",
      thesis="Miami firm founded 2022 focused on pre-seed and seed Enterprise SaaS.", segment="miami"),
    R("Las Olas Venture Capital", ("Fort Lauderdale", "United States", "America/New_York"),
      "Seed; Series A", "B2B SaaS; Enterprise Software",
      thesis="Early-stage investor primarily in B2B software.", segment="miami"),
    R("Florida Funders", ("Tampa", "United States", "America/New_York"), "Pre-Seed; Seed; Series B",
      "B2B SaaS; FinTech; AI; E-commerce",
      thesis="Southeast venture firm investing in early-stage B2B technology from pre-seed "
             "through Series B.", segment="miami"),
    R("Valhalla Ventures", MIA, "Seed", "Technology; Consumer", thesis="Miami-based seed investor.",
      segment="miami"),
    R("Blumberg Capital", MIA, "Seed; Series A", "FinTech; SaaS; Consumer",
      thesis="Early-stage investor with Miami presence.",
      partner=("David Blumberg", "Managing Partner"), segment="miami"),
    R("Crew VC", MIA, "Pre-Seed; Seed", "Technology; Consumer", thesis="Miami early-stage fund.",
      segment="miami"),
    R("Thundermark Capital", MIA, "Seed", "AI; Technology", thesis="Seed investor in AI and technology.",
      segment="miami"),
    R("Duna Ventures", MIA, "Pre-Seed; Seed", "Technology; Consumer", thesis="Miami early-stage fund.",
      segment="miami"),
    R("Clerisy", MIA, "Seed; Series A", "Consumer; Technology", thesis="Consumer-oriented venture firm.",
      segment="miami"),
    R("Lightship Capital", MIA, "Pre-Seed; Seed", "Consumer; CPG; Health",
      thesis="Invests in underrepresented founders across consumer and healthcare.", segment="miami"),
    R("Acronym Venture Capital", MIA, "Seed", "Technology; Consumer", thesis="Miami seed investor.",
      segment="miami"),
    R("Future Perfect Ventures", MIA, "Seed", "Technology; Consumer", thesis="Early-stage investor.",
      segment="miami"),
    R("Seven Seven Six", MIA, "Seed; Series A", "Consumer; Technology; Web3",
      thesis="Early-stage firm with Miami roots.", segment="miami"),
    R("Harlem Capital", NY, "Seed", "Consumer; Technology",
      thesis="Backs diverse founders across consumer and technology.", segment="miami"),
    R("Form Capital", MIA, "Pre-Seed; Seed", "Technology; Consumer", thesis="Miami early-stage fund.",
      segment="miami"),
    R("Focal VC", MIA, "Pre-Seed; Seed", "Technology; Consumer", thesis="Miami early-stage fund.",
      segment="miami"),
    R("Guild Capital", MIA, "Seed; Early Stage", "Consumer; SaaS; FinTech",
      check=("$500k", "$4M"),
      thesis="Contrarian thesis backing early-growth founders before conventional metrics catch up.",
      segment="miami"),
    R("Zenda Capital", MIA, "Seed", "Technology; Consumer", thesis="Miami seed investor.", segment="miami"),
    R("Bling Capital", MIA, "Pre-Seed; Seed", "Consumer; Technology", thesis="Early-stage investor.",
      segment="miami"),
    R("Reign Ventures", MIA, "Seed", "Consumer; Technology", thesis="Early-stage investor.", segment="miami"),
    R("Beni VC", MIA, "Pre-Seed; Seed", "Consumer; Technology", thesis="Miami early-stage fund.",
      segment="miami"),
    R("Beresford Ventures", MIA, "Seed", "Technology; Consumer", thesis="Miami seed investor.",
      segment="miami"),
    R("Medina Capital", MIA, "Growth", "Technology; Cybersecurity",
      thesis="Miami growth investor.", partner=("Manny Medina", "Managing Partner"), segment="miami"),
    R("Zelkova Ventures", MIA, "Seed", "Consumer; Technology", thesis="Early-stage generalist.",
      segment="miami"),
    R("Starlight Ventures", MIA, "Seed; Series A", "Deep Tech; Climate",
      thesis="Miami-based investor in foundational technologies.", segment="miami"),
    R("Motivate Venture Capital", CHI, "Pre-Seed; Seed", "Consumer; Technology",
      thesis="Pre-seed and seed investor active across the Midwest and Southeast.", segment="miami"),
    R("Axioma Ventures", ("Tampa", "United States", "America/New_York"), "Seed",
      "Consumer; Technology", thesis="Tampa-area firm whose team includes the former CEO of Publix.",
      segment="miami"),
    R("Embarc Collective", ("Tampa", "United States", "America/New_York"), "Pre-Seed; Seed",
      "Technology; Consumer",
      thesis="Tampa accelerator supporting early-stage companies with space, mentorship and "
             "investor connections.", segment="miami"),
    R("DeepWork Capital", ("Orlando", "United States", "America/New_York"), "Seed; Series A",
      "Technology; Health", thesis="Florida early-stage venture firm.", segment="miami"),
    R("New World Angels", ("Boca Raton", "United States", "America/New_York"), "Seed",
      "Technology; Consumer", thesis="Florida angel investor group.", segment="miami"),
    R("Gold Coast Angel Investors", ("Fort Lauderdale", "United States", "America/New_York"), "Seed",
      "Technology; Consumer", thesis="South Florida angel group.", segment="miami"),
    R("Black Angels Miami", MIA, "Seed", "Consumer; Technology",
      thesis="Miami angel group backing founders across sectors.", segment="miami"),
    R("Accelerated Growth Partners", MIA, "Seed", "Technology; Consumer",
      thesis="Florida angel and early-stage investment group.", segment="miami"),
    R("Alpha Wave Global", MIA, "Growth", "Technology; Consumer",
      thesis="Global investment firm with Miami presence.", segment="miami"),
    R("Blue Cloud Ventures", MIA, "Growth", "Software", thesis="Growth-stage software investor.",
      segment="miami"),
    R("SaaS Ventures", MIA, "Seed", "B2B SaaS", thesis="Seed investor in B2B software.", segment="miami"),
    R("Original Capital", MIA, "Seed", "Consumer; Technology", thesis="Miami early-stage investor.",
      segment="miami"),
    R("GTM Capital", MIA, "Seed", "Technology", thesis="Miami-based seed fund.", segment="miami"),
]

# --------------------------------------------------------------------------------------
# Tier 2 — Latino-led and Latin America connected (Miami-relevant)
# --------------------------------------------------------------------------------------

LATINO_LED = [
    R("L'ATTITUDE Ventures", ("San Diego", "United States", "America/Los_Angeles"),
      "Pre-Seed; Seed; Series A", "Consumer; Technology; Latino Founders",
      thesis="Purpose-driven firm investing in early-stage businesses led by US Latinos.",
      recent="$100M+ platform; hosts its Match-Up competition at the L'ATTITUDE conference in Miami.",
      segment="latino_led"),
    R("Vamos Ventures", LA, "Seed; Series A", "Health; Financial; Future of Work; Sustainability",
      thesis="Invests at seed and Series A in Latino- and diverse-led companies across four sectors.",
      segment="latino_led"),
    R("Chingona Ventures", CHI, "Pre-Seed; Seed", "FinTech; Software; Consumer",
      thesis="Invests at the earliest stages in founders building scalable companies from the ground up.",
      segment="latino_led"),
    R("Mendoza Ventures", BOS, "Seed", "FinTech; AI; Consumer",
      thesis="Latino-led fund investing in fintech, AI and cybersecurity.", segment="latino_led"),
    R("Leap Global Partners", SF, "Seed", "Technology; Consumer; Cross-Border",
      thesis="Invests in US Latino and Latin America cross-border founders.", segment="latino_led"),
]

# --------------------------------------------------------------------------------------
# Tier 2 — consumer generalists and pre-seed
# --------------------------------------------------------------------------------------

CONSUMER_GENERALIST = [
    R("Forerunner Ventures", SF, "Seed; Series A", "Consumer; Commerce; CPG",
      check=("$1M", "$20M"),
      thesis="Consumer specialist; early investor in Warby Parker, Away and Glossier.",
      portfolio="Warby Parker; Away; Glossier; Allbirds",
      recent="Raised $500M Fund VII; nearly $3B AUM.",
      partner=("Kirsten Green", "Founder"), segment="consumer"),
    R("Lerer Hippeau", NY, "Pre-Seed; Seed", "Consumer; Enterprise; CPG",
      thesis="Seed first, New York first generalist that has backed culture-defining consumer brands.",
      portfolio="Allbirds; Glossier; Warby Parker",
      recent="Closed $200M for its ninth seed fund; over 400 companies invested; $1.2B AUM.",
      segment="consumer"),
    R("Greycroft", NY, "Seed; Series A; Growth", "Consumer; AI; Sustainability",
      thesis="Combines AI-driven software, sustainability and consumer brands; also a growth "
             "investor in food delivery infrastructure.",
      recent="461 portfolio companies; average seed $4.62M and Series A $11.5M.",
      partner=("Alan Patricof", "Founder"), segment="consumer"),
    R("Imaginary Ventures", NY, "Seed; Series A", "Consumer; Retail; Commerce",
      thesis="Identifies, invests in and scales iconic consumer businesses at the intersection of "
             "retail and technology.",
      recent="Founded 2018; roughly 50% of Fund I backed women founders.",
      partner=("Nick Brown", "Co-Founder"), segment="consumer"),
    R("Bullish", NY, "Pre-Seed; Seed; Series A", "Consumer; CPG; Brand",
      check=("$500k", "$3M"),
      thesis="Early-stage investment firm that doubles as a brand strategy agency, providing "
             "capital and hands-on brand support to consumer companies.", segment="consumer"),
    R("XRC Ventures", NY, "Pre-Seed; Seed; Series A", "Retail Tech; Consumer; Commerce; CPG",
      thesis="Invests in the future of retail, consumer and commerce technology across an "
             "Accelerator Fund, Technology Fund and Brand Capital Fund.", segment="consumer"),
    R("Elizabeth Street Ventures", NY, "Seed", "Consumer; Consumer FinTech",
      thesis="Funds digital consumer and consumer fintech businesses transforming verticals.",
      segment="consumer"),
    R("Maveron", ("Seattle", "United States", "America/Los_Angeles"), "Seed; Series A", "Consumer",
      thesis="Consumer-only venture firm.", segment="consumer"),
    R("L Catterton", ("Greenwich", "United States", "America/New_York"), "Growth",
      "Consumer; Food & Beverage; Retail; Hospitality",
      thesis="Consumer-focused private equity, among the largest by AUM.",
      recent="Reported $37-40B AUM.", segment="consumer"),
    R("Spark Capital", BOS, "Series A; Growth", "Consumer; Technology",
      thesis="Consumer and technology investor.", recent="$12B AUM.", segment="consumer"),
    R("Primary Venture Partners", NY, "Seed", "Consumer; B2B",
      check=("$1M", "$3M"),
      thesis="NYC seed fund that led Allbirds and Harry's at seed.", portfolio="Jet.com; Mirror",
      segment="consumer"),
    R("Homebrew", SF, "Seed", "Consumer Marketplaces; D2C",
      check=("$500k", "$2M"),
      thesis="Seed fund for the bottom-up economy, consumer marketplaces and D2C brands.",
      portfolio="The Farmer's Dog; Plaid", segment="consumer"),
    R("Brand Foundry Ventures", AUS, "Seed; Series A", "Consumer Brands; E-commerce; Retail",
      thesis="Builds the next generation of consumer brands for digitally native audiences; leads "
             "seed and Series A.", segment="consumer"),
    R("Silverton Partners", AUS, "Seed; Series A", "Software; Consumer; CPG",
      thesis="Austin early-stage firm investing in software, tech-enabled services and CPG brands.",
      segment="consumer"),
    R("NEXT VENTURES", AUS, "Seed; Series A", "Sports; Fitness; Nutrition; Wellness",
      thesis="Invests in the sports, fitness, nutrition and wellness markets.", segment="consumer"),
    R("Cowboy Ventures", SF, "Seed", "Consumer Internet; Technology",
      thesis="Seed-stage consumer internet investor.", segment="consumer"),
    R("NFX", SF, "Pre-Seed; Seed", "Marketplaces; Network Effects; Consumer",
      thesis="Seed fund focused on network-effect businesses and marketplaces.", segment="consumer"),
    R("Precursor Ventures", SF, "Pre-Seed", "Consumer; Technology",
      thesis="Pre-seed generalist backing founders at the earliest stage.", segment="consumer"),
    R("Headline", SF, "Seed; Series A; Growth", "Marketplaces; Consumer; Network Effects",
      thesis="Formerly e.ventures; focused on marketplaces and network-effect businesses.",
      segment="consumer"),
    R("Science Inc", ("Santa Monica", "United States", "America/Los_Angeles"), "Seed; Series A",
      "Consumer; D2C; Commerce",
      thesis="Studio and fund that built and backed Dollar Shave Club at seed.", segment="consumer"),
    R("Crosscut Ventures", LA, "Seed", "Consumer; Technology",
      thesis="One of the largest seed-stage firms in Los Angeles.", segment="consumer"),
    R("Mucker Capital", LA, "Pre-Seed; Seed", "Consumer; Software",
      thesis="Hands-on early-stage investor in Southern California software and internet companies.",
      segment="consumer"),
    R("BAM Ventures", LA, "Seed", "E-commerce; Consumer",
      thesis="Consumer and e-commerce focused seed fund.", segment="consumer"),
    R("Amplify.LA", LA, "Pre-Seed; Seed", "Consumer; Technology",
      thesis="Seed capital plus a collaborative community for LA founders.", segment="consumer"),
    R("Wavemaker Partners", LA, "Seed; Series A", "Enterprise; Deep Tech; Consumer",
      thesis="Early-stage investor across enterprise and deep tech.", segment="consumer"),
    R("GTMfund", AUS, "Seed", "Go-to-Market; B2B; Consumer",
      thesis="Early-stage fund with a network of go-to-market executives.", segment="consumer"),
    R("Hyde Park Venture Partners", CHI, "Seed; Series A", "B2B Software; Consumer Marketplaces",
      thesis="Midwest and Toronto early-stage firm focused on first and second rounds.",
      recent="Raised $100M for its third fund.", segment="consumer"),
    R("Golden Ventures", TOR, "Seed", "Consumer; Technology",
      thesis="Leading Toronto seed fund investing across North America.", segment="consumer"),
    R("BrandProject", TOR, "Seed; Series A", "Consumer Products; Consumer Services; Technology",
      thesis="Early-stage fund investing in and building consumer brands.",
      portfolio="Daily Harvest; Freshly; Ritual; Chefs Plate; Pet Plate; Awake Chocolate",
      segment="consumer"),
    R("GCI Capital", TOR, "Early Stage", "Consumer; Food",
      thesis="Toronto early-stage private equity firm.", segment="consumer"),
    R("SOSV", ("Princeton", "United States", "America/New_York"), "Pre-Seed; Seed",
      "Deep Tech; Food Tech; Biotech",
      check=("$500k", "$500k"),
      thesis="Global deep tech fund investing $500K at inception through HAX and IndieBio.",
      segment="consumer"),
    R("Preface Ventures", NY, "Pre-Seed; Seed", "Restaurant Tech; Software",
      thesis="Technology-focused firm evaluating software margins and customer acquisition cost.",
      segment="restaurant_hospitality"),
    R("Pathbreaker Ventures", SF, "Pre-Seed; Seed", "Technology; Consumer",
      thesis="Pre-seed and seed investor across emerging technology.", segment="consumer"),
    R("Serendipity Investments", UNK, "Seed", "Food; Consumer",
      thesis="Backs food and consumer companies.", segment="consumer"),
    R("Heartland Ventures", ("Columbus", "United States", "America/New_York"), "Seed; Series A",
      "Supply Chain; Consumer; Industrials",
      thesis="Connects coastal startups with Midwest corporate customers.", segment="consumer"),
    R("Glasswing Ventures", BOS, "Seed; Series A", "AI; Consumer; Enterprise",
      thesis="Early-stage AI and frontier technology investor.", segment="consumer"),
    R("Fernbrook", UNK, "Seed", "Consumer", thesis="Early-stage consumer investor.", segment="consumer"),
    R("Outlander VC", ("Atlanta", "United States", "America/New_York"), "Pre-Seed; Seed",
      "Health; Wellness; Consumer",
      check=("$500k", "$2.5M"),
      thesis="Writes early checks for transformative healthcare and wellness technology.",
      segment="consumer"),
    R("Primetime Partners", NY, "Seed", "Longevity; Consumer; Health",
      thesis="Focused on longevity and quality of life for aging populations.", segment="consumer"),
    R("Amboy Street Ventures", NY, "Seed; Series A", "Women's Health; Consumer Health",
      thesis="Specialises in women's health and sexual health startups.", segment="consumer"),
    R("Speedinvest", UNK, "Pre-Seed; Seed", "Consumer; Technology",
      thesis="Pre-seed and seed investor with sector-focused teams.", segment="consumer"),
    R("Sound Ventures", LA, "Seed; Series A; Growth", "Consumer; Technology; AI",
      thesis="Founded by Ashton Kutcher and Guy Oseary; invests across consumer and technology.",
      partner=("Guy Oseary", "Co-Founder"), segment="celebrity_consumer"),
    R("Serena Ventures", SF, "Seed", "Consumer; Technology; CPG",
      thesis="Backs early-stage companies with a focus on founders from diverse backgrounds.",
      recent="Invested in more than 60 brands.",
      partner=("Serena Williams", "Founder"), segment="celebrity_consumer"),
    R("Skky Partners", LA, "Growth", "Consumer Products; Media; Hospitality; Luxury",
      thesis="Private equity investing in consumer products, media and entertainment, hospitality "
             "and luxury.", partner=("Kim Kardashian", "Co-Founder"), segment="celebrity_consumer"),
    R("Marcy Venture Partners", NY, "Seed; Series A", "Consumer; Media; CPG",
      thesis="Consumer-focused fund co-founded by Shawn Carter.", segment="celebrity_consumer"),
    R("Casa Verde Capital", LA, "Seed; Series A", "Cannabis; Consumer",
      thesis="Consumer and cannabis-adjacent investor.", partner=("Snoop Dogg", "Co-Founder"),
      segment="celebrity_consumer"),
    R("SC30", SF, "Seed; Series A", "Consumer; Sports; Media",
      thesis="Investment vehicle spanning consumer, sports and media.",
      partner=("Stephen Curry", "Founder"), segment="celebrity_consumer"),
    R("Penny Jar Capital", SF, "Seed; Series A", "Consumer; Technology",
      thesis="Early-stage fund investing across consumer and technology.", segment="celebrity_consumer"),
    R("Liquid 2 Ventures", SF, "Pre-Seed; Seed", "Consumer; Technology",
      thesis="Seed fund with a large portfolio across technology and consumer.",
      partner=("Joe Montana", "Founder"), segment="celebrity_consumer"),
    R("Rx3 Ventures", LA, "Seed; Series A", "Consumer; Brands",
      thesis="Consumer-market fund launched with a $50M debut vehicle.",
      partner=("Aaron Rodgers", "Co-Founder"), segment="celebrity_consumer"),
    R("HartBeat Ventures", LA, "Seed; Series A", "Consumer; Media; Lifestyle",
      thesis="Consumer and lifestyle fund.", partner=("Kevin Hart", "Founder"),
      segment="celebrity_consumer"),
]

# --------------------------------------------------------------------------------------
# Tier 3 — accelerators and programmes with capital
# --------------------------------------------------------------------------------------

ACCELERATORS = [
    R("Techstars Future of Food", ("Minneapolis", "United States", "America/Chicago"),
      "Pre-Seed", "Food; AgTech; Food Tech",
      check=("$20k", "$120k"),
      thesis="Accelerator with Ecolab for startups across the food supply chain; up to $120K "
             "per company.", recent="Formerly Techstars Farm to Fork; portfolio has raised $154M.",
      segment="accelerator"),
    R("Terra Food and Ag Tech Accelerator", SF, "Pre-Seed", "Food Tech; AgTech",
      thesis="Food and agriculture technology accelerator.", segment="accelerator"),
    R("Good Food Accelerator", CHI, "Pre-Seed", "Food; CPG",
      thesis="Runs Go To Market, Accelerate For Growth and Market Access programmes for food "
             "entrepreneurs.", segment="accelerator"),
    R("Chobani Incubator", NY, "Pre-Seed", "Food & Beverage; CPG",
      thesis="Incubator for early-stage food and beverage companies.", segment="accelerator"),
    R("SKU", AUS, "Pre-Seed", "CPG; Food & Beverage",
      thesis="The first CPG accelerator in the US; twelve weeks of coaching across branding, "
             "supply chain and distribution.", segment="accelerator"),
    R("Union Kitchen", ("Washington", "United States", "America/New_York"), "Pre-Seed; Seed",
      "Food & Beverage; CPG",
      thesis="Food business accelerator with kitchen, distribution and retail infrastructure.",
      segment="accelerator"),
]

# --------------------------------------------------------------------------------------
# Tier 2 — named angels (individuals who invest their own capital)
# --------------------------------------------------------------------------------------

ANGELS = [
    R("Independent Angel", MIA, "Seed", "Real Estate Tech; Consumer",
      thesis="Miami angel with 20+ local portfolio companies since 2020.",
      partner=("Mike Cardenas", "Angel Investor"), segment="angel"),
    R("Independent Angel", MIA, "Seed", "PropTech; FinTech",
      thesis="Miami-based angel investing in proptech and fintech.",
      partner=("Ana Paula Pessoa", "Angel Investor"), segment="angel"),
    R("Independent Angel", MIA, "Seed", "FinTech; Marketplaces",
      check=("$500k", "$500k"),
      thesis="Backed multiple Miami companies with $500K+ checks into fintech and marketplaces.",
      partner=("Marcelo Claure", "Angel Investor"), segment="angel"),
    R("Independent Angel", MIA, "Seed", "Healthcare; Consumer",
      thesis="Miami angel investing across healthcare and consumer.",
      partner=("Jorge Mas", "Angel Investor"), segment="angel"),
    R("Independent Angel", MIA, "Seed", "FinTech; Payments",
      thesis="Miami angel specialising in payments and lending.",
      partner=("Carlos Garcia", "Angel Investor"), segment="angel"),
    R("Independent Angel", SF, "Pre-Seed; Seed", "Consumer; D2C; Food & Beverage",
      thesis="Consumer and D2C operator-angel active in food and beverage.",
      partner=("Brian Spaly", "Angel Investor"), segment="angel"),
    R("Independent Angel", NY, "Pre-Seed; Seed", "Consumer; Food & Beverage",
      thesis="Pre-seed angel active in food and beverage.",
      partner=("Ramanan Raghavendran", "Angel Investor"), segment="angel"),
    R("Independent Angel", BOU, "Seed", "Consumer; Food & Beverage",
      thesis="Seed angel active in food and beverage.",
      partner=("Seth Levine", "Angel Investor"), segment="angel"),
    R("Independent Angel", SF, "Pre-Seed; Seed", "Consumer; Food & Beverage",
      thesis="Seed angel active in food and beverage.",
      partner=("Marvin Liao", "Angel Investor"), segment="angel"),
    R("Independent Angel", NY, "Seed", "Consumer; Food & Beverage",
      thesis="Seed angel active in food and beverage.",
      partner=("Lauren Loktev", "Angel Investor"), segment="angel"),
    R("Independent Angel", UNK, "Pre-Seed", "Consumer; Food & Beverage",
      thesis="Pre-seed angel active in food and beverage.",
      partner=("Jeff Pomeranz", "Angel Investor"), segment="angel"),
]


# --------------------------------------------------------------------------------------
# Tier 2 — restaurant technology backers and restaurant private equity
# --------------------------------------------------------------------------------------

RESTAURANT_TECH_AND_PE = [
    R("Roark Capital", ("Atlanta", "United States", "America/New_York"), "Growth",
      "Restaurants; Franchise; Consumer",
      thesis="The largest restaurant-focused private equity platform, built around franchised "
             "multi-unit brands.",
      portfolio="Subway; Inspire Brands; Dunkin'; Jimmy John's; Cinnabon; Auntie Anne's; Jamba",
      segment="restaurant_hospitality"),
    R("Blackstone", NY, "Growth", "Restaurants; Franchise; Consumer",
      thesis="Global private equity with an active restaurant franchise portfolio.",
      portfolio="Jersey Mike's; Tropical Smoothie Cafe", segment="restaurant_hospitality"),
    R("Bain Capital", BOS, "Growth", "Restaurants; Consumer; Franchise",
      thesis="Has owned major restaurant platforms and holds current restaurant positions.",
      portfolio="Domino's; Dunkin'", segment="restaurant_hospitality"),
    R("Thoma Bravo", CHI, "Growth", "Restaurant Tech; Software",
      thesis="Software-focused private equity active in restaurant technology.",
      portfolio="Olo", recent="Acquired Olo for $2 billion.", segment="restaurant_hospitality"),
    R("Insight Partners", NY, "Growth", "Restaurant Tech; Software; Commerce",
      thesis="Growth investor across software including restaurant technology.",
      portfolio="Olo", segment="restaurant_hospitality"),
    R("Redpoint Ventures", ("Menlo Park", "United States", "America/Los_Angeles"),
      "Seed; Series A", "Restaurant Tech; Software; Consumer",
      thesis="Early-stage investor; Series A investor in Olo before its IPO.", portfolio="Olo",
      segment="restaurant_hospitality"),
    R("TCV", ("Menlo Park", "United States", "America/Los_Angeles"), "Growth",
      "Restaurant Tech; Technology",
      thesis="Growth-stage technology investor.", portfolio="Toast",
      recent="Led Toast's Series E.", segment="restaurant_hospitality"),
    R("Base10 Partners", SF, "Seed; Series A", "Restaurant Tech; Automation; Consumer",
      thesis="Invests in the automation of the real economy, including restaurant technology.",
      segment="restaurant_hospitality"),
    R("Craft Ventures", SF, "Seed; Series A", "Restaurant Tech; SaaS; Marketplaces",
      thesis="Early-stage fund active in restaurant and hospitality software.", segment="restaurant_hospitality"),
    R("Menlo Ventures", SF, "Seed; Series A; Growth", "Restaurant Tech; Consumer; Technology",
      thesis="Multi-stage investor active in restaurant technology.", segment="restaurant_hospitality"),
    R("Union Square Ventures", NY, "Seed; Series A", "Marketplaces; Restaurant Tech; Consumer",
      thesis="Thesis-driven early-stage investor active in restaurant and marketplace software.",
      segment="restaurant_hospitality"),
    R("Left Lane Capital", NY, "Series A; Growth", "Consumer Internet; Restaurant Tech",
      thesis="Growth investor in consumer internet businesses.", segment="restaurant_hospitality"),
    R("HighSage Ventures", BOS, "Series A; Growth", "Restaurant Tech; Technology",
      thesis="Investor active in restaurant technology.", segment="restaurant_hospitality"),
    R("QED Investors", ("Alexandria", "United States", "America/New_York"), "Seed; Series A",
      "FinTech; Embedded Payments; Restaurant Tech",
      thesis="Fintech specialist focused on embedded payments; backed Toast.", portfolio="Toast",
      segment="restaurant_hospitality"),
    R("NYCA Partners", NY, "Seed; Series A", "FinTech; Payments; Restaurant Tech",
      thesis="Fintech and payments investor active in restaurant technology.", segment="restaurant_hospitality"),
    R("Fin Capital", MIA, "Seed; Series A", "FinTech; B2B SaaS",
      thesis="Fintech-focused firm with Miami presence.", segment="miami"),
    R("DST Global", UNK, "Growth", "Consumer Internet; Delivery",
      thesis="Late-stage consumer internet investor.", segment="delivery"),
    R("Valor Equity Partners", CHI, "Series A; Growth", "Consumer; Technology; Operations",
      thesis="Operations-focused growth investor, active in Miami.", segment="miami"),
    R("Costanoa Ventures", SF, "Seed; Series A", "B2B SaaS; Data",
      thesis="Early-stage enterprise investor listed among firms active in Miami.", segment="miami"),
    R("RRE Ventures", NY, "Seed; Series A", "Consumer; Technology",
      thesis="Early-stage generalist listed among firms active in Miami.", segment="miami"),
    R("Boldstart Ventures", NY, "Pre-Seed; Seed", "Enterprise; Developer Tools",
      thesis="Pre-seed enterprise investor listed among firms active in Miami.", segment="miami"),
    R("Arrington Capital", MIA, "Seed; Growth", "Crypto; Technology",
      thesis="Digital asset investor with Miami activity.", segment="miami"),
    R("Point72 Ventures", NY, "Seed; Series A", "FinTech; Technology",
      thesis="Multi-stage venture arm listed among firms active in Miami.", segment="miami"),
]


ALL_RECORDS = (
    FOOD_BEVERAGE
    + RESTAURANT_HOSPITALITY
    + DELIVERY_COMMERCE
    + MIAMI_FLORIDA
    + LATINO_LED
    + CONSUMER_GENERALIST
    + ACCELERATORS
    + ANGELS
    + RESTAURANT_TECH_AND_PE
)

SEGMENT_LABELS = {
    "food_beverage": "Food & beverage / CPG specialist",
    "restaurant_hospitality": "Restaurant, hospitality & nightlife",
    "corporate_vc": "Corporate venture arm",
    "delivery": "Delivery, logistics & marketplace",
    "commerce": "Commerce & retail technology",
    "miami": "Miami / Florida",
    "latino_led": "Latino-led / LatAm connected",
    "consumer": "Consumer generalist",
    "celebrity_consumer": "Operator, athlete & talent-led consumer fund",
    "accelerator": "Accelerator or programme",
    "angel": "Named angel investor",
    "family_office": "Family office",
}
