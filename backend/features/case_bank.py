"""Practice cases (made-up companies, real Indian business patterns). Seeded at startup; Admin picks the live one.

Model answers follow Akshat's Strategic Thinking Framework, the same six steps the current hub's
"Strategy Thinking Framework" GPT uses (backend/gpts/prompts/strategy-thinking-framework.md):

  Phase 1 · Define the Problem   Step 1 Understand Scope (region · product · channel · time)
                                 Step 2 Identify Objective (from → to → in by when; success; failure)
  Phase 2 · Craft the Strategy   Step 3 Identify Framework · Step 4 Generate Options · Step 5 Prioritize (do first)
  Phase 3 · Execute              Step 6 Implementation Charter (owner · leading metric weekly · lagging metric monthly)

Figures are illustrative of a typical case, not cited statistics. The weekly case from real news (stage 2)
uses the same shape plus `source` {title, url}.
"""
from __future__ import annotations


def _ma(scope_before, scope_after, frm, to, by, success, failure, framework, why, finding, options, do_first, owner,
        leading, lagging) -> dict:
    return {"scope_before": scope_before, "scope_after": scope_after,
            "objective": {"from": frm, "to": to, "by": by}, "success": success, "failure": failure,
            "framework": framework, "framework_why": why, "finding": finding,
            "options": [{"source": s, "option": o} for s, o in options], "do_first": do_first,
            "charter": {"owner": owner, "leading": leading, "lagging": lagging}}


CASES: list[dict] = [
    {
        "_id": "retail-chain-margins", "title": "Selling more, earning less", "company": "Sharma Fresh Mart",
        "industry": "Retail · grocery", "city": "Pune",
        "situation": "Sharma Fresh Mart runs 14 grocery stores. Sales are up 18% this year, but profit fell from 4% "
                     "of sales to 1.5%. The owner opened 5 new stores in the last 12 months and has been running "
                     "heavy weekend discounts to pull people in.",
        "facts": ["Discounts doubled as a share of sales in a year", "30% of products sell less than one unit a week",
                  "Fresh fruit and vegetable wastage is 9% (well-run stores manage 4–5%)",
                  "The 5 new stores are not yet breaking even"],
        "question": "The owner says: \"We're selling more than ever. Why is there less money?\" "
                    "Take him through the framework: scope, objective, your framework and options, and how you'd run it.",
        "framework_hint": "Where does each ₹100 of sales leak before it becomes profit?",
        "model_answer": _ma(
            "We're selling more than ever, but there's less money.",
            "Profit at our 14 Pune stores fell from 4% to 1.5% of sales over the last 12 months, mostly in fresh produce and at the 5 new stores.",
            "1.5% profit on sales", "3% profit on sales", "90 days",
            "Profit back to 3% of sales while sales hold steady.", "Profit still under 2% at the 45-day check.",
            "Margin leak check: Profit = Sales − Cost of goods − Wastage − Discounts − Store costs",
            "It shows exactly where each rupee of sales leaks before it becomes profit.",
            "Discounts doubled, fresh wastage is about twice what well-run stores manage, and 30% of products barely sell. Growth was bought with margin.",
            [("Same industry", "Order fresh produce by daily sell-through and mark down before it spoils"),
             ("Adjacent industry", "Cut the slowest 30% of products, the way quick-commerce stores keep tight ranges"),
             ("Similar geography", "Swap blanket weekend discounts for targeted offers on high-margin baskets"),
             ("Customer research", "Ask 50 regulars why they come; keep only the offers that matter to them"),
             ("Out of the box", "Pause new openings until the 5 new stores break even")],
            "Fresh produce ordering and markdowns: the biggest leak, and it can start this week.",
            "Head of store operations", "Wastage % per store, every week", "Profit as % of sales, every month"),
    },
    {
        "_id": "d2c-skincare-cac", "title": "Ads cost more every month", "company": "GlowRoot",
        "industry": "D2C · skincare", "city": "Mumbai",
        "situation": "GlowRoot sells skincare online and makes ₹12 crore a year. The cost of winning one new "
                     "customer through Instagram ads went from ₹450 to ₹1,100 in a year. The founder wants to "
                     "double the ad budget to get growth back.",
        "facts": ["Average order is ₹799", "Only 18% of customers buy a second time",
                  "No email or WhatsApp follow-up after the first order", "Three best-sellers make 70% of sales"],
        "question": "Should the founder double the ad budget? Scope the real problem, set the objective, and show your options and plan.",
        "framework_hint": "What does one customer cost you, and what is one customer worth?",
        "model_answer": _ma(
            "Growth has stalled. We need more ads.",
            "The cost of winning a new online customer rose from ₹450 to ₹1,100 over 12 months, and only 18% of customers buy again.",
            "18% of customers buy again", "28% buy again", "6 months",
            "Each new customer earns back their ad cost within 6 months.", "Repeat rate still under 20% at the 2-month check.",
            "Unit economics: customer value (order × repeat orders) against cost to win a customer",
            "It shows whether more ad spend creates profit or just bigger losses.",
            "At ₹1,100 to win a customer who spends ₹799 and rarely returns, every new customer loses money. The gap is repeat orders, not ads.",
            [("Same industry", "Refill reminders and a refill subscription for the three best-sellers"),
             ("Adjacent industry", "Bundles that lift order value, the way meal-kit brands sell weekly boxes"),
             ("Similar geography", "List best-sellers on Indian marketplaces to cut dependence on one ad channel"),
             ("Customer research", "Call 30 one-time buyers and ask why they didn't come back"),
             ("Out of the box", "A free sample of a second product in every first order")],
            "A WhatsApp refill reminder for the top 3 products: cheap, fast, and it attacks the real gap.",
            "Founder, with one person owning retention", "Repeat orders per week", "Repeat rate and cost per customer, every month"),
    },
    {
        "_id": "auto-parts-delivery", "title": "Late deliveries, angry buyers", "company": "Patel Auto Components",
        "industry": "Manufacturing · auto parts", "city": "Rajkot",
        "situation": "Patel Auto Components supplies two-wheeler makers. Only 71% of orders reach on time; the "
                     "buyers need 95% and have started charging penalties. The factory is running heavy overtime "
                     "and still missing dates.",
        "facts": ["Machines are down 14% of planned time", "Planning is done on a spreadsheet by one person",
                  "Raw material sometimes arrives late from two suppliers", "Penalties cost ₹18 lakh last quarter"],
        "question": "The owner thinks he needs more machines. Do you agree? Work it through the framework.",
        "framework_hint": "Which one step limits everything else?",
        "model_answer": _ma(
            "We're always late. We need more machines.",
            "On-time delivery to two-wheeler makers from the Rajkot plant is 71% against the 95% they require, over the last two quarters.",
            "71% on time", "90% on time", "12 weeks",
            "90% on time and penalties halved.", "Still under 80% at the 6-week check.",
            "Bottleneck thinking: the factory's output is set by its slowest step",
            "Fixing the one step that limits everything recovers capacity before buying any.",
            "14% downtime on the bottleneck machine, spreadsheet planning and late material lose more capacity than a new machine would add.",
            [("Same industry", "Preventive maintenance on the bottleneck machine first"),
             ("Adjacent industry", "Weekly plan built from buyer schedules with material checked before release, as process plants do"),
             ("Similar geography", "Agree delivery dates and buffer stock with the two late Rajkot suppliers"),
             ("Customer research", "Ask each buyer which parts and dates matter most"),
             ("Out of the box", "Keep the bottleneck machine running through breaks with a relief operator")],
            "A downtime log and maintenance on the bottleneck machine: no capital needed.",
            "Plant head", "Bottleneck machine downtime %, every shift", "On-time delivery % and penalties, every month"),
    },
    {
        "_id": "hospital-claims", "title": "Insurance money stuck", "company": "CareWell Hospital",
        "industry": "Healthcare · hospital", "city": "Nagpur",
        "situation": "CareWell is a 120-bed hospital. Beds are full, but cash is always short. 22% of insurance "
                     "claims are rejected or cut, and the hospital waits 68 days on average to be paid.",
        "facts": ["Most rejections cite missing documents or wrong codes", "Billing staff are trained on the job",
                  "Doctors write discharge notes late", "Two insurers make up 60% of claims"],
        "question": "The CEO asks for a plan to bring cash in faster. Scope it, set the objective and show how you'd run it.",
        "framework_hint": "Follow one claim from admission to payment and find where it breaks.",
        "model_answer": _ma(
            "We're full every day and still short of cash.",
            "22% of insurance claims at our 120-bed Nagpur hospital are rejected or cut, and payment takes 68 days, mostly with two insurers.",
            "22% rejected, 68 days to payment", "10% rejected, 45 days", "4 months",
            "Rejections at 10% and payment in 45 days.", "Rejections still above 15% at the 6-week check.",
            "Process map of one claim: admission → treatment → discharge → file → payment",
            "It shows the exact step where claims break, instead of blaming everyone.",
            "Most rejections are paperwork: missing documents, wrong codes and late discharge notes.",
            [("Same industry", "A pre-send checklist per insurer for every claim file"),
             ("Adjacent industry", "Code training for billing staff, the way banks train KYC teams"),
             ("Similar geography", "A monthly review meeting with the two main insurers"),
             ("Customer research", "Ask the insurer desks which errors they reject most"),
             ("Out of the box", "A rule that discharge notes are finished within 4 hours")],
            "The pre-send file check: it stops most rejections at the source.",
            "Head of billing", "Files sent with zero gaps, every week", "Rejection rate and days to payment, every month"),
    },
    {
        "_id": "it-attrition", "title": "People keep leaving", "company": "Nexa Softech",
        "industry": "IT services", "city": "Bengaluru",
        "situation": "Nexa Softech has 400 people. 31% of staff left last year. Projects are slipping, and two "
                     "large clients have complained about new people on their teams every few months.",
        "facts": ["Most leavers have 2–4 years' experience", "Exit interviews mention pay and no growth path",
                  "Managers were promoted for technical skill, with no people training",
                  "Hiring a replacement takes 70 days"],
        "question": "The founder wants to give everyone a raise. Is that the fix? Work it through the framework.",
        "framework_hint": "Separate why people join, why they stay and why they leave.",
        "model_answer": _ma(
            "Attrition is killing us. Let's raise salaries.",
            "31% of our 400 staff left last year, mostly people with 2–4 years' experience, and it is hurting two large client accounts.",
            "31% attrition", "20% attrition", "12 months",
            "Under 20% a year and no more complaints from the two large clients.", "No drop in monthly exits at the 3-month check.",
            "Employee turnover drivers: pay · growth path · manager · the work itself",
            "It separates why people leave, so the fix targets the real reason.",
            "Mid-level people leave for a growth path and better managers as much as for pay. A blanket raise is costly and fixes neither.",
            [("Same industry", "A published career path for each role, with what it takes to move up"),
             ("Adjacent industry", "Train every manager on one-to-ones, the way good sales teams do"),
             ("Similar geography", "Fix pay only for roles clearly below the Bengaluru market"),
             ("Customer research", "Stay interviews with the top 50 people"),
             ("Out of the box", "Stable named teams on the two unhappy clients, with an account bonus")],
            "Stay interviews and manager one-to-ones: they show who is at risk before they resign.",
            "Head of HR with the delivery heads", "One-to-ones held per manager, every week", "Attrition %, every month"),
    },
    {
        "_id": "restaurant-aggregators", "title": "Busy kitchens, thin profit", "company": "Tandoor Tales",
        "industry": "Restaurants", "city": "Delhi NCR",
        "situation": "Tandoor Tales has 6 outlets. Online orders are now 45% of sales, almost all through food apps "
                     "that take 25–30% commission. The outlets are busy, but profit has nearly halved in two years.",
        "facts": ["Menu prices are the same online and in the outlet", "Food cost is 34% of sales",
                  "Dine-in customers come back often; app customers mostly don't", "No own ordering channel"],
        "question": "The owner asks: should we leave the food apps? Scope it and take it through the framework.",
        "framework_hint": "What is left from ₹100 of sales on each channel?",
        "model_answer": _ma(
            "We're busier than ever and making less.",
            "Profit at our 6 Delhi NCR outlets nearly halved over 2 years as app orders grew to 45% of sales at 25–30% commission.",
            "Profit about half of 2 years ago", "Back to two-thirds of it", "6 months",
            "Two-thirds of the old profit without losing app volume.", "No change in profit per app order at the 6-week check.",
            "Profit by channel: what is left from ₹100 of sales on dine-in, apps and takeaway",
            "It shows which channel makes money and which only makes noise.",
            "Every app order pays 25–30% commission on top of 34% food cost, at the dine-in price. Very little is left.",
            [("Same industry", "An app-only menu with prices that cover the commission"),
             ("Adjacent industry", "Direct ordering for regulars on WhatsApp, as cloud kitchens do"),
             ("Similar geography", "Weekday lunch offers for nearby offices to grow dine-in"),
             ("Customer research", "Ask 30 app customers why they don't visit the outlet"),
             ("Out of the box", "A shorter app menu of high-margin dishes that travel well")],
            "App pricing on the top 20 dishes: it changes profit on almost half of sales at once.",
            "Operations head", "Profit per app order, every week", "Outlet profit, every month"),
    },
    {
        "_id": "coaching-conversions", "title": "More enquiries, fewer students", "company": "Bright Path Academy",
        "industry": "Education · coaching", "city": "Jaipur",
        "situation": "Bright Path Academy coaches students for entrance exams. Enquiries are up 40% thanks to online "
                     "ads, but only 18% of students who attend a demo class now join, down from 35%.",
        "facts": ["Demo classes are taken by different teachers each time", "Follow-up calls happen days later",
                  "Fees went up 15% this year", "Parents ask most about results and batch size"],
        "question": "The director wants to spend more on ads. What would you look at first? Use the framework.",
        "framework_hint": "Enquiry → demo → follow-up → admission. Where is the biggest drop?",
        "model_answer": _ma(
            "We need more ads. Admissions are down.",
            "At our Jaipur centre, the share of demo students who join fell from 35% to 18% this year while enquiries rose 40%.",
            "18% of demo students join", "30% join", "8 weeks",
            "30% of demo students join.", "Still below 22% at the 4-week check.",
            "Funnel analysis: enquiry → demo → follow-up → admission",
            "It finds the step where interested families drop out.",
            "The leak is after the demo: uneven demo classes, slow follow-up and a higher fee without clear proof of results.",
            [("Same industry", "The two best teachers take every demo class"),
             ("Adjacent industry", "Same-day follow-up, the way car dealers call back after a test drive"),
             ("Similar geography", "Show last year's Jaipur results and batch sizes in every demo"),
             ("Customer research", "Call 20 families who didn't join and ask why"),
             ("Out of the box", "A refundable first month if the family isn't satisfied")],
            "Same-day follow-up with results and batch details: it costs nothing and starts tomorrow.",
            "Admissions head", "Families followed up the same day, every week", "Demo-to-admission %, every month"),
    },
    {
        "_id": "exporter-concentration", "title": "One buyer holds all the power", "company": "Tiruppur Knit Works",
        "industry": "Textiles · export", "city": "Tiruppur",
        "situation": "Tiruppur Knit Works makes knitwear for export. One European buyer gives 62% of all orders "
                     "and is now asking for a 7% price cut for next season.",
        "facts": ["The next biggest buyer is 11% of sales", "The factory has spare capacity in two months of the year",
                  "No one works full-time on finding new buyers", "Profit is 6% of sales"],
        "question": "The owner asks: do we accept the 7% cut? Advise him for this season and the next two years, using the framework.",
        "framework_hint": "When one client is too big, every decision is theirs.",
        "model_answer": _ma(
            "Our biggest buyer wants 7% off. We can't lose them.",
            "One European buyer is 62% of our knitwear export sales and wants 7% off next season, on a 6% profit.",
            "Main buyer is 62% of sales", "Under 40% of sales", "2 years",
            "No loss-making orders this season and two new buyers above 5% of sales each within a year.",
            "No new buyer above 5% of sales by the 12-month check.",
            "Concentration risk: no single client above 25–30% of sales",
            "It explains why the buyer can dictate price, and what changes that.",
            "A 7% cut on a 6% profit makes this buyer's orders loss-making. One buyer at 62% of sales removes all bargaining power.",
            [("Same industry", "Offer a smaller cut tied to volume or longer lead times"),
             ("Adjacent industry", "Private-label work for Indian D2C apparel brands in the spare months"),
             ("Similar geography", "Two trade fairs with samples aimed at new markets"),
             ("Customer research", "Ask the main buyer what else they value: speed, compliance, small batches"),
             ("Out of the box", "Hire one person whose only job is winning new buyers")],
            "A buyer-by-buyer profit sheet before replying, then a counter-offer on volume.",
            "Owner with the export manager", "New buyer meetings, every week", "Main buyer's share of sales, every month"),
    },
]

CRITERIA = [
    ("scope", "Scope: pinned down where, what and since when"),
    ("objective", "Objective: from → to → by when"),
    ("strategy", "Strategy: a framework, options and what to do first"),
    ("execution", "Execution: who owns it and what to measure"),
]


def model_answer_text(m: dict) -> str:
    """Plain-text model answer for the scoring prompt and printing."""
    o = m["objective"]
    opts = "; ".join(f"{x['source']}: {x['option']}" for x in m["options"])
    return (f"Scope — before: {m['scope_before']} After: {m['scope_after']}\n"
            f"Objective — from {o['from']} to {o['to']} in {o['by']}. Success: {m['success']} Failure: {m['failure']}\n"
            f"Framework — {m['framework']} ({m['framework_why']}) Finding: {m['finding']}\n"
            f"Options — {opts}\nDo first — {m['do_first']}\n"
            f"Charter — owner: {m['charter']['owner']}; leading: {m['charter']['leading']}; lagging: {m['charter']['lagging']}")
