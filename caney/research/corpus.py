"""
The seeded research corpus — Tier B fisheries evidence that ships with the build. §22.

WHY THIS EXISTS AS A FILE. The research provider (OpenAI web search) is optional: no key,
no live research. But the Carthage striper case is the regression fixture that proves the
zone model works, so its evidence has to exist offline. These are transcribed from public
TWRA pages, each with the URL it came from, retrieved on the date recorded.

WHAT THIS IS NOT. Not eternal truth (§22). Every entry carries valid_months and a
published/retrieved date; the scorer decays them, the freshness strip shows their age, and
the live provider replaces them with fresher claims of the same claim_type when it runs.

NOTHING HERE IS SAFETY-SENSITIVE. Not one entry carries a flow, a stage, a generation time
or a wade cutoff — those may only come from instruments, via SafetyClaim (§20).
"""
from ..domain.claim import ResearchClaim, SourceTier

RETRIEVED = "2026-09-09"

# Source documents, named once so a claim cannot drift from its citation.
S_OLD_HICKORY = ("https://www.tn.gov/twra/fishing/where-to-fish/middle-tennessee-r2/"
                 "old-hickory-reservoir.html")
T_OLD_HICKORY = "TWRA — Old Hickory Reservoir, Where to Fish"
S_CORDELL = ("https://www.tn.gov/twra/fishing/where-to-fish/cumberland-plateau-r3/"
             "cordell-hull-reservoir.html")
T_CORDELL = "TWRA — Cordell Hull Reservoir, Where to Fish"
S_COA = ("https://www.tn.gov/content/dam/tn/twra/documents/swap/coa/"
         "CordellHullTailwaterCOA2015TNSWAP.pdf")
T_COA = "TWRA — Cordell Hull Tailwater Conservation Opportunity Area (TN SWAP 2015)"
S_TROUT_MGMT = ("https://www.tn.gov/content/dam/tn/twra/documents/fishing/"
                "Tennessee-Trout-Management-Plan-2017-2027.pdf")
T_TROUT_MGMT = "TWRA Fisheries Report 17-10 — Trout Management Plan for Tennessee 2017–2027"
S_TROUT_STOCK = "https://www.tn.gov/twra/fishing/trout-information-stockings.html"
T_TROUT_STOCK = "TWRA — Trout Fishing & Stockings in Tennessee"
S_TROUT_REGS = "https://www.tn.gov/twra/fishing-regs/trout-regulations.html"
T_TROUT_REGS = "TWRA — Tennessee Trout Regulations"
S_DUCK = ("https://www.tn.gov/twra/fishing/where-to-fish/middle-tennessee-r2/"
          "duck-river.html")
T_DUCK = "TWRA — Duck River, Where to Fish"
S_BUFFALO = ("https://www.tn.gov/environment/program-areas/na-natural-areas/"
             "tn-scenic-rivers/buffalo.html")
T_BUFFALO = "TDEC — Buffalo State Scenic River"
S_ADVISORY = ("https://www.tn.gov/environment/news/2026/8/21/"
              "tdec-issues-precautionary-fish-consumption-advisory.html")
T_ADVISORY = "TDEC — Precautionary Fish Consumption Advisories"
S_PRIEST = ("https://www.tn.gov/twra/fishing/where-to-fish/middle-tennessee-r2/"
            "percy-priest-reservoir.html")
T_PRIEST = "TWRA — J. Percy Priest Reservoir, Where to Fish"
S_CENTERHILL = ("https://www.tn.gov/twra/fishing/where-to-fish/cumberland-plateau-r3/"
                "center-hill-reservoir.html")
T_CENTERHILL = "TWRA — Center Hill Reservoir, Where to Fish"

ALL_MONTHS = list(range(1, 13))


def _c(**kw):
    kw.setdefault("published_at", None)
    return ResearchClaim(source_tier=SourceTier.B, **kw)


def seed_claims():
    """Constructed fresh each call — ResearchClaim.score() mutates match fields."""
    return [

        # ── §22: the Carthage striper case ──────────────────────────────────
        _c(species="striped_bass", claim_type="seasonal_location",
           location_ids=["carthage_confluence", "cordell_tailwater"],
           geographic_description="Cordell Hull Dam downstream to the mouth of the Caney Fork River",
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TWRA: “Striped bass are concentrated from Cordell Hull Dam "
                       "downstream to the mouth of the Caney Fork River.”"),
           source_url=S_OLD_HICKORY, source_title=T_OLD_HICKORY, retrieved_at=None),

        _c(species="striped_bass", claim_type="species_presence",
           location_ids=["carthage_confluence", "caney_lower"],
           geographic_description="Caney Fork River within about 2 river miles of the Cumberland confluence",
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TWRA: “They are also abundant in the Caney Fork River and are "
                       "usually found within 2 river miles from its confluence to the "
                       "Cumberland River.”"),
           source_url=S_OLD_HICKORY, source_title=T_OLD_HICKORY),

        _c(species="striped_bass", claim_type="seasonal_location",
           location_ids=["carthage_confluence", "cordell_tailwater"],
           geographic_description="upper Old Hickory Reservoir near Carthage",
           valid_months=[5], season="spring",
           claim_text=("TWRA: “May is a great month to catch a trophy Striped Bass from "
                       "the upper end of Old Hickory Reservoir near Carthage, Tennessee.” "
                       "Fish move upstream to spawn during May and are drawn to Cordell Hull "
                       "Dam, which provides an upstream barrier."),
           source_url=S_OLD_HICKORY, source_title=T_OLD_HICKORY),

        _c(species="striped_bass", claim_type="current_response",
           location_ids=["carthage_confluence", "cordell_tailwater"],
           geographic_description="Cumberland River at Cordell Hull Dam",
           valid_months=[4, 5, 6], season="spring",
           claim_text=("TWRA: water temperatures in the lower to middle 60s F, photoperiod "
                       "and WATER CURRENT are the natural spawning cues for striped bass in "
                       "this system."),
           source_url=S_OLD_HICKORY, source_title=T_OLD_HICKORY),

        _c(species="striped_bass", claim_type="forage",
           location_ids=["carthage_confluence", "cordell_tailwater", "caney_lower"],
           geographic_description="Cordell Hull system",
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TWRA: “Great numbers of gizzard shad, threadfin shad, and "
                       "skipjack herring continue to provide a forage base very conducive "
                       "to a trophy-striped bass fishery.”"),
           source_url=S_CORDELL, source_title=T_CORDELL),

        _c(species="striped_bass", claim_type="stocking",
           location_ids=["cordell_tailwater", "carthage_confluence"],
           geographic_description="Cordell Hull Reservoir",
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TWRA: “TWRA continues to stock striped bass annually in Cordell "
                       "Hull Reservoir, depending on hatchery success.” The state record "
                       "striped bass, 65 lb 6 oz, came from Cordell Hull Reservoir in 2000."),
           source_url=S_CORDELL, source_title=T_CORDELL),

        _c(species="striped_bass", claim_type="thermal_refuge",
           location_ids=["cordell_tailwater", "carthage_confluence", "caney_lower"],
           geographic_description="Cordell Hull tailwater and the cool Caney Fork discharge",
           valid_months=[6, 7, 8, 9], season="summer",
           claim_text=("Cool, oxygenated bottom-release water below the dams is the summer "
                       "thermal refuge that holds striped bass through the hottest months; "
                       "the Cordell Hull tailwater is managed as a Conservation Opportunity "
                       "Area for exactly this cold-tailwater habitat."),
           source_url=S_COA, source_title=T_COA),

        _c(species="striped_bass", claim_type="time_of_day",
           location_ids=["carthage_confluence", "cordell_tailwater", "caney_lower"],
           geographic_description="Cordell Hull tailwater / Caney Fork confluence",
           valid_months=[6, 7, 8, 9], season="summer",
           claim_text=("Under summer thermal-refuge conditions the early and low-light "
                       "windows produce best, with the fish holding on current when the "
                       "dam is running."),
           source_url=S_COA, source_title=T_COA),

        # ── Cordell Hull black bass ─────────────────────────────────────────
        _c(species="smallmouth", claim_type="seasonal_location",
           location_ids=["cordell_tailwater"],
           geographic_description="lower end of Cordell Hull Reservoir, Defeated Creek to the dam",
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TWRA: “Concentrate on the lower end of the reservoir from "
                       "Defeated Creek to the dam. Some tributary streams also offer good "
                       "smallmouth bass habitat.” Peak spawning at 59–60 F; consistently "
                       "sampled on rocky banks in spring electrofishing surveys."),
           source_url=S_CORDELL, source_title=T_CORDELL),

        _c(species="largemouth", claim_type="habitat",
           location_ids=["cordell_tailwater", "carthage_confluence"],
           geographic_description="Cordell Hull Reservoir creeks and flats",
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TWRA: largemouth bass hold in creeks, stump beds and fallen trees on "
                       "flats in 2–8 feet of water, with success year round; “a good "
                       "forage base of gizzard and threadfin shad has helped sustain this "
                       "LMB fishery through the years.” Spawn at 68–72 F."),
           source_url=S_CORDELL, source_title=T_CORDELL),

        # ── §35 · stillwater largemouth, and §34 · stripers beyond Carthage ─
        _c(species="largemouth", claim_type="habitat",
           location_ids=["oldhickory_creek_arms", "oldhickory_embayments"],
           geographic_description=("Bledsoe, Spencer, Station Camp, Drakes Creek and "
                                   "Shutes Branch embayments, Old Hickory Reservoir"),
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TWRA: Old Hickory is a 22,500-acre Cumberland impoundment; Bledsoe, "
                       "Spencer and Station Camp Creek embayments sit in the middle section "
                       "near Gallatin, Drakes Creek and Shutes Branch downstream. As the "
                       "level drops, the matted tops of the grass patches reappear in the "
                       "3-5 ft zone around the bank and in the pockets — target hard "
                       "structure mixed into the grass, or the hard grass lines. TWRA "
                       "maintains forty fish-attractor sites on the reservoir. Largemouth "
                       "carry a 14-inch minimum here."),
           source_url=S_OLD_HICKORY, source_title=T_OLD_HICKORY),

        _c(species="striped_bass", claim_type="seasonal_distribution",
           location_ids=["oldhickory_embayments"],
           geographic_description="lower Old Hickory Reservoir embayments",
           valid_months=[12, 1, 2, 3], season="winter",
           claim_text=("TWRA: striped bass concentrate in the lower-reservoir embayments "
                       "starting in December and through the winter months."),
           source_url=S_OLD_HICKORY, source_title=T_OLD_HICKORY),

        _c(species="largemouth", claim_type="habitat",
           location_ids=["priest_creek_arms"],
           geographic_description=("Spring, Fall, Stewart and Suggs Creek embayments, "
                                   "J. Percy Priest Reservoir"),
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TWRA: the productive largemouth areas on J. Percy Priest are the "
                       "Spring and Fall Creek embayments in the upper reservoir, Stewart "
                       "Creek near mid-lake and Suggs Creek in the lower reservoir. April "
                       "is a peak month, with fish shallow to spawn and catchable lake-wide "
                       "on gently sloping banks. Largemouth use the roughly 132 TWRA fish "
                       "attractors year round, hardest from late November through April in "
                       "6-15 ft."),
           source_url=S_PRIEST, source_title=T_PRIEST),

        _c(species="smallmouth", claim_type="habitat",
           location_ids=["centerhill_shoreline"],
           geographic_description="Center Hill Reservoir main lake",
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TWRA: Center Hill hosts great smallmouth habitat — miles of rocky "
                       "shoreline, points and bluff areas — and largemouth fishing "
                       "opportunities exist year round."),
           source_url=S_CENTERHILL, source_title=T_CENTERHILL),

        _c(species="largemouth", claim_type="habitat",
           location_ids=["centerhill_shoreline"],
           geographic_description="Center Hill Reservoir main lake",
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TWRA: fishing opportunities for largemouth bass exist year round at "
                       "Center Hill Reservoir."),
           source_url=S_CENTERHILL, source_title=T_CENTERHILL),

        _c(species="striped_bass", claim_type="seasonal_distribution",
           location_ids=["cordell_granville_reach"],
           geographic_description=("major creeks from Granville to Gainesboro, Cordell Hull "
                                   "Reservoir; and around Celina in summer"),
           valid_months=[3, 4, 5, 6], season="spring",
           claim_text=("TWRA: striped bass use the major creeks from Granville to Gainesboro "
                       "during spring, and concentrate around Celina because of the cooler "
                       "water temperatures."),
           source_url=S_CORDELL, source_title=T_CORDELL),

        # ── Caney Fork trout ────────────────────────────────────────────────
        _c(species="trout", claim_type="stocking",
           location_ids=["caney_upper", "caney_middle"],
           geographic_description="Caney Fork River below Center Hill Dam",
           valid_months=[3, 4, 5, 6, 7, 8, 9, 10, 11, 12], season="all",
           claim_text=("TWRA stocks fingerling and adult trout into cold-water tailwaters "
                       "below dams; the Caney Fork below Center Hill Dam carries special "
                       "trout regulations for rainbow, brook, brown and cutthroat trout "
                       "March through December."),
           source_url=S_TROUT_STOCK, source_title=T_TROUT_STOCK),

        _c(species="trout", claim_type="regulation",
           location_ids=["caney_upper", "caney_middle", "caney_lower"],
           geographic_description="Caney Fork River, Center Hill Dam to the Cumberland River",
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TWRA: Caney Fork River from Center Hill Dam to the Cumberland River — "
                       "total daily creel of all trout in combination is five. Rainbow, brook "
                       "and cutthroat 5/day with a 14–20 inch protected length range and only "
                       "one over 20 inches; brown trout one per day, 24-inch minimum."),
           source_url=S_TROUT_REGS, source_title=T_TROUT_REGS),

        _c(species="trout", claim_type="survey",
           location_ids=["caney_upper", "caney_middle"],
           geographic_description="Tennessee tailwater trout fisheries",
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TWRA biologists survey tailwater trout populations annually to "
                       "evaluate regulations and stocking rates (Trout Management Plan "
                       "2017–2027). Always check the dam discharge and generation schedule "
                       "before fishing a tailwater."),
           source_url=S_TROUT_MGMT, source_title=T_TROUT_MGMT),

        # ── Duck / Buffalo smallmouth ───────────────────────────────────────
        _c(species="smallmouth", claim_type="species_presence",
           location_ids=["duck_upper", "duck_middle", "duck_lower"],
           geographic_description="Duck River, Middle Tennessee",
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TWRA: the Duck River offers excellent fishing for smallmouth bass, "
                       "spotted bass, rock bass and panfish, with 30 free public access "
                       "sites ranging from concrete ramps to canoe/kayak accesses and bank "
                       "fishing. Creel limit 5/day for largemouth, smallmouth and spotted "
                       "bass in combination, no length restrictions."),
           source_url=S_DUCK, source_title=T_DUCK),

        _c(species="smallmouth", claim_type="habitat",
           location_ids=["duck_upper"],
           geographic_description="upper Duck River gorge at Old Stone Fort",
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TWRA: the upper Duck through Old Stone Fort is a series of deep "
                       "limestone pools with repeating runs and short pools; the pool below "
                       "Big Falls has long held smallmouth to four pounds and better."),
           source_url=S_DUCK, source_title=T_DUCK),

        _c(species="smallmouth", claim_type="species_presence",
           location_ids=["buffalo_river"],
           geographic_description="Buffalo River, the longest un-impounded river in Middle Tennessee",
           valid_months=ALL_MONTHS, season="all",
           claim_text=("TDEC: the Buffalo is the longest un-impounded river in Middle "
                       "Tennessee, over 125 miles supporting nearly 85 fish species; "
                       "canoeing and kayaking are popular through the middle and lower "
                       "reaches for the fishing."),
           source_url=S_BUFFALO, source_title=T_BUFFALO),

        _c(species="smallmouth", claim_type="regulation",
           location_ids=["duck_lower", "duck_middle", "buffalo_river"],
           geographic_description="Duck River from the Buffalo River to Interstate 40",
           valid_months=ALL_MONTHS, season="all", published_at="2026-08-21",
           claim_text=("TDEC precautionary fish consumption advisory for black bass on the "
                       "Duck River from the Buffalo River to Interstate 40 (mercury). "
                       "Catch-and-release is unaffected; the advisory is about eating them."),
           source_url=S_ADVISORY, source_title=T_ADVISORY),
    ]


def claims_for(species, month=None, zone_ids=(), extra=()):
    """Seed claims plus any live-research claims, scored and sorted best first."""
    out = []
    for c in list(seed_claims()) + list(extra):
        if c.species and c.species != species:
            continue
        c.score(month=month, zone_ids=zone_ids)
        out.append(c)
    out.sort(key=lambda c: -c.confidence)
    return out
