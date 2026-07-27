# PITCH_RULES.md — normative spec for Pitchline

This file is the **single source of truth**. `pitchline/rules.py` parses it into typed
constants at import time; no rule value may be hard-coded anywhere else in the codebase.

Rules derive from a field experiment that sent 50 distinct pitches to ~28,000 investors,
plus the practitioner guidance published alongside it ("What Makes a Cold Pitch Work").
Every rule quotes the source passage it derives from in its `**Source:**` line. Where the
source is silent on a specific threshold, the rule states a value chosen under the
**stricter reading** and is tagged `RULE-CHECK` for the author to confirm.

Severity vocabulary:

| Severity | Meaning |
|---|---|
| `hard` | Enforced in code. Violation blocks the pipeline (draft rejected, send refused). |
| `soft` | Enforced in code as a warning + logged `Event`. Does not block. |
| `advisory` | Documented intent; enforced by review, not by code. |

```meta
spec_version = "1.0.0"
source_title = "What Makes a Cold Pitch Work"
source_kind = "field_experiment_plus_practitioner_guidance"
pitches_tested = 50
investors_contacted = 28000
adopted_on = "2026-07-27"
```

---

## §0 — Objective function

### R0.1 — Qualified replies per unit of reputation

- **Severity:** hard
- **Enforced by:** send.budget, analytics.benchmarks
- **Source:** "the unconditional probability of getting an interested reply to any single email was about 4%... The top pitches hit 13–17% response rates from VCs."

The campaign optimises qualified replies per unit of sender reputation consumed, never
emails sent. Reputation is a depletable budget (R3.3) and every send debits it. Campaign
performance is always reported against the 4% baseline and the 13–17% ceiling band, by
variant and by cohort, so the programme compounds into a benchmark rather than a volume
count.

```params
baseline_reply_rate = 0.04
ceiling_reply_rate_low = 0.13
ceiling_reply_rate_high = 0.17
min_sends_for_rate_significance = 100
```

---

## §1 — Target universe and list construction

### R1.1 — Volume ceiling; quality over blast

- **Severity:** hard
- **Enforced by:** targeting.campaign_cap
- **Source:** "Mass-blasting a generic template to thousands of investors is the wrong strategy. Crafting a strong pitch and sending it to a well-researched list of a few hundred relevant investors is the right one."

A campaign target list is capped at 400 investors and warns above 250. "A few hundred"
is the operative phrase: the cap is a ceiling, not a goal. If the list comes in short,
the correct response is to improve targeting (R1.2) or the pitch (R2.4) — never to widen
the net.

```params
max_campaign_targets = 400
warn_campaign_targets = 250
allow_cap_override = false
```

### R1.2 — Investor-to-pitch matching

- **Severity:** hard
- **Enforced by:** targeting.fit_score
- **Source:** "We didn't blast the same email to everyone. We mapped each investor's past investments and stated interests to our pitches and sent them the ones most likely to be relevant... An investor who focuses on healthcare SaaS is not going to reply to a pitch about consumer gaming."

Every target carries a `FitScore` with a 0–5 score plus a one-line rationale on each of
six dimensions: stage, sector, check size, geography, thesis recency, and portfolio
conflict. A target below the minimum composite, or below the floor on either of the two
dimensions the source calls out explicitly (stage, sector), is dropped from the campaign.
Each dimension rationale must cite at least one `evidence_id` (R2.6).

```params
score_scale_min = 0
score_scale_max = 5
dimensions = ["stage", "sector", "check_size", "geography", "thesis_recency", "portfolio_conflict"]
min_composite_score = 3.0
min_stage_score = 3
min_sector_score = 3
require_rationale_per_dimension = true
require_evidence_per_dimension = true
```

### R1.3 — Research floor ("thirty minutes of homework")

- **Severity:** hard
- **Enforced by:** research.evidence_store, targeting.fit_score
- **Source:** "Doing even thirty minutes of homework on an investor's portfolio, fund thesis, and recent activity dramatically increases your odds."

No investor may be scored or drafted to without stored evidence covering the three areas
the source names: portfolio, fund thesis, and recent activity. Evidence is retrieved once
and cached; re-fetching inside the TTL is forbidden. Evidence older than the staleness
window does not count toward the floor — "recent activity" that is two years old is not
recent activity.

> **RULE-CHECK:** the source quantifies effort ("thirty minutes"), not snippet counts or
> TTLs. Minimums below are the stricter reading: at least one snippet in each of the three
> named areas, four in total.

```params
min_evidence_snippets = 4
required_evidence_areas = ["portfolio", "thesis", "recent_activity"]
min_snippets_per_required_area = 1
cache_ttl_days = 14
max_evidence_age_days = 365
recent_activity_max_age_days = 180
forbid_refetch_inside_ttl = true
```

### R1.4 — Partner-level resolution

- **Severity:** hard
- **Enforced by:** ingest.resolve, send.preflight
- **Source:** "Research suggests they receive thousands of solicitation emails per month." (Firm-level and generic inboxes are the highest-volume, lowest-reply destinations.)

Targets resolve to a named individual with an investing role, never to a firm or a shared
inbox. Records without a resolvable partner-level role are held in the ingest quarantine,
not promoted to targets. Non-partner roles (associate, analyst, platform, chief of staff)
are outside the campaign universe.

Angels are included: the rule's purpose is to reach someone who can decide, and an angel
investing their own money is that person. Titles that do not resolve to an investing role —
"CEO", "Founder", "Operator" — stay in quarantine with their reason recorded, because a
person's operating title says nothing about whether they invest.

```params
require_named_individual = true
require_investing_role = true
partner_level_roles = ["managing_partner", "general_partner", "founding_partner", "partner", "venture_partner", "principal", "angel"]
forbid_firm_level_targets = true
forbid_generic_mailboxes = true
generic_mailbox_locals = ["info", "hello", "contact", "team", "admin", "support", "press", "careers", "ir", "deals", "submissions", "pitch", "pitches", "intros", "inbound", "office"]
dedupe_key = ["normalized_name", "normalized_firm"]
require_provenance = true
```

### R1.5 — Portfolio conflict suppression

- **Severity:** hard
- **Enforced by:** targeting.conflicts, send.preflight
- **Source:** "We mapped each investor's past investments and stated interests..." (An investor holding a direct competitor is a disclosure risk, not a prospect.)

An investor whose fund holds a direct competitor is suppressed. Suppression is the
default and applies at dispatch as well as at scoring, so a target scored before a
conflict was discovered still cannot be sent to. Override requires a named human, a
written reason, and a timestamp; it is recorded as an `Event` and never inferred by a
model.

```params
suppress_direct_conflict = true
conflict_evidence_required = true
allow_override = true
override_requires_human = true
override_requires_reason = true
override_requires_timestamp = true
model_may_override = false
enforce_at_dispatch = true
```

---

## §2 — Message construction

### R2.1 — Length ceiling

- **Severity:** hard
- **Enforced by:** guardrails.length
- **Source:** "Every one of our pitches was a single short email... VCs process information fast... You have seconds, not minutes. If your cold email requires scrolling, it's too long."

A draft body may not exceed 150 words. Words are whitespace-delimited tokens in the body
excluding the CAN-SPAM footer (R5.1), which is compliance text rather than pitch text.
Subject lines are capped separately. One email, one screen.

```params
max_words = 150
word_count_method = "whitespace_tokens"
exclude_footer_from_count = true
exclude_signature_from_count = false
max_subject_chars = 78
max_paragraphs = 4
```

### R2.2 — Problem before solution

- **Severity:** hard
- **Enforced by:** compose.slots, guardrails.structure
- **Source:** "Lead with the problem, not the solution... Investors are pattern-matchers trained to evaluate whether a market opportunity is real. Give them the 'why this matters' before the 'what we built.'"

Every pitch has exactly four slots, in this order: credibility marker (R2.3), problem
(R2.2), novel approach (R2.4), low-commitment ask (R2.5). The problem slot must precede
the approach slot in the rendered body. Problem and approach text is selected from the
founder-authored variant library — the model selects and personalises, it does not invent.

```params
slots = ["credibility", "problem", "approach", "ask"]
problem_precedes_approach = true
problem_from_variant_library = true
approach_from_variant_library = true
model_may_author_slot_text = false
max_problem_words = 60
```

### R2.3 — Credibility marker in the first sentence

- **Severity:** hard
- **Enforced by:** guardrails.credibility
- **Source:** "You may not have a Stanford affiliation, but you do have some source of credibility—a relevant technical background, a prior company, domain expertise, notable early customers or advisors. Put it in the first sentence. Investors use fast heuristics to filter pitches, and your credibility marker is the first filter you need to pass."

The first sentence of the body must contain a credibility marker drawn from the founder's
registered marker set. "First sentence" means sentence index 0 of the body, after any
greeting line. A marker appearing later in the email does not satisfy this rule.

```params
required_sentence_index = 0
greeting_line_exempt = true
marker_types = ["academic_affiliation", "technical_background", "prior_company", "prior_exit", "domain_expertise", "named_customer", "notable_advisor", "institutional_backing", "traction_metric"]
marker_must_be_registered = true
min_markers = 1
```

### R2.4 — Specific and novel

- **Severity:** hard
- **Enforced by:** guardrails.novelty
- **Source:** "Generic, vague, or derivative pitches got ignored. The startups that stood out offered something genuinely different. If an investor reads your email and thinks 'I've seen ten of these this week,' you've already lost."

An LLM judge scores the draft 0–5 on the source's own test: would a VC reading this think
"I've seen ten of these this week"? Drafts below the threshold are rejected back to
compose. The judge returns a structured verdict with a reason; free-text-only verdicts are
not accepted.

> **RULE-CHECK:** the source states the test qualitatively but sets no numeric threshold.
> 4.0 on a 0–5 scale is the stricter reading of "genuinely different".

```params
novelty_scale_min = 0
novelty_scale_max = 5
min_novelty_score = 4.0
judge_prompt_key = "novelty_v1"
require_structured_verdict = true
max_compose_retries = 2
route_to_human_after_retries = true
```

### R2.5 — Low-commitment ask

- **Severity:** hard
- **Enforced by:** guardrails.ask, inbox.routing
- **Source:** "Our pitches ended with a simple, low-commitment request... Many investors replied by requesting a pitch deck—the lowest-friction next step. Don't ask for a meeting at their office next Tuesday at 3 PM. Don't ask them to commit to a term sheet."

The ask slot must be one of the registered low-commitment forms. Hard-scheduled meeting
requests, calendar links on first touch, and any funding ask are forbidden. `deck_request`
is the expected modal positive reply and routes to a one-click deck-plus-calendar
response.

```params
allowed_ask_types = ["offer_to_share_more", "deck_offer", "quick_call_in_next_week_or_two", "brief_reply_question"]
forbid_specific_time_request = true
forbid_calendar_link_first_touch = true
forbid_funding_ask = true
forbid_term_sheet_ask = true
modal_positive_reply = "deck_request"
max_ask_sentences = 2
```

### R2.6 — Provenance: no unsourced claims

- **Severity:** hard
- **Enforced by:** guardrails.provenance
- **Source:** "By making each cold pitch investor specific increases the odds further by a lot." (Investor-specific text is only defensible if it is verifiable.)

Every investor-specific sentence in a draft must map to a stored `evidence_id` in the
draft's claim map. Zero unsourced investor-specific claims may reach the approval queue.
Personalisation is one hook per draft — the model's job is selection plus a single
verifiable hook, not invention.

```params
max_unsourced_claims = 0
require_claim_map = true
min_personalization_hooks = 1
max_personalization_hooks = 1
hook_requires_evidence_id = true
evidence_must_be_stored = true
forbid_model_asserted_facts = true
```

---

## §3 — Deliverability and infrastructure

### R3.1 — Text only; no embedded images

- **Severity:** hard
- **Enforced by:** guardrails.media, send.mime
- **Source:** "keep your emails text-only (our data showed that emails with embedded images were disproportionately blocked by spam filters)."

Plain-text MIME only. Zero embedded images, zero attachments on any touch, zero tracking
pixels anywhere in the programme. HTML multipart is not permitted.

```params
max_embedded_images = 0
max_attachments = 0
allow_html_part = false
mime_type = "text/plain"
forbid_tracking_pixel = true
forbid_open_tracking = true
forbid_click_tracking = true
```

### R3.2 — Dedicated professional sending domain

- **Severity:** hard
- **Enforced by:** send.preflight
- **Source:** "make sure your email infrastructure is solid: use a professional domain, warm up your sending reputation..."

Sending runs on a dedicated secondary domain with SPF, DKIM and DMARC in place, never on
the founder's primary corporate domain — a burned reputation must not take company mail
down with it. Free-provider addresses are not permitted as sending identities.

```params
require_dedicated_domain = true
forbid_primary_domain = true
require_spf = true
require_dkim = true
require_dmarc = true
forbid_freemail_senders = true
freemail_domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com", "proton.me"]
```

### R3.3 — Warmup ramp and per-mailbox daily cap

- **Severity:** hard
- **Enforced by:** send.budget
- **Source:** "we observed a meaningful decline in response rates as our email campaign progressed, largely because spam filters caught an increasing fraction of our messages. We estimate that roughly a quarter of our emails were blocked."

Each mailbox has a daily send cap that ramps over a warmup schedule indexed by mailbox
age in days, reaching a steady-state ceiling. The cap is a `ReputationBudget` decremented
per send; a send attempt against an exhausted budget raises `ReputationBudgetExceeded`
rather than silently deferring. Mailboxes rotate, and sends are spaced.

> **RULE-CHECK:** the source establishes that campaign-scale sending degrades
> deliverability but gives no ramp table. The schedule below is a conservative standard
> warmup; steady state is 40/day/mailbox.

```params
steady_state_daily_cap = 40
warmup_daily_caps = [5, 5, 8, 8, 12, 12, 16, 20, 24, 28, 32, 36, 40]
warmup_index_basis = "mailbox_age_days"
min_seconds_between_sends = 90
require_mailbox_rotation = true
max_consecutive_sends_per_mailbox = 5
cap_override_allowed = false
```

### R3.4 — Spam-term deny list

- **Severity:** hard
- **Enforced by:** guardrails.spam
- **Source:** "avoid spam trigger words"

A draft containing any denied term is rejected. Matching is case-insensitive on word
boundaries. Formatting tells that filters weight alongside vocabulary — shouted words,
exclamation pile-ups, currency-and-urgency constructions — are capped in the same check.

```params
max_spam_term_hits = 0
case_insensitive = true
word_boundary_match = true
deny_terms = ["act now", "apply now", "amazing", "billion dollar", "buy now", "cash bonus", "cheap", "click here", "congratulations", "credit card", "dear friend", "discount", "don't delete", "double your", "earn money", "exclusive deal", "extra income", "fast cash", "free access", "free consultation", "free gift", "free money", "free trial", "get paid", "get rich", "giveaway", "guarantee", "guaranteed returns", "incredible", "instant", "limited time", "lowest price", "make money", "miracle", "money back", "no catch", "no cost", "no credit check", "no obligation", "no risk", "not spam", "once in a lifetime", "only today", "opportunity of a lifetime", "order now", "pre-approved", "presented to you", "prize", "risk free", "risk-free", "satisfaction guaranteed", "special promotion", "this isn't spam", "unlimited", "urgent", "while supplies last", "winner", "work from home", "100% free", "$$$"]
max_exclamation_marks = 0
max_all_caps_words = 0
allow_caps_acronyms = true
max_caps_acronym_length = 5
```

### R3.5 — No links on first touch

- **Severity:** hard
- **Enforced by:** guardrails.links
- **Source:** "make sure your email infrastructure is solid... The best pitch in the world doesn't work if it lands in a spam folder." (Link count is a primary filter signal on unestablished sender-recipient pairs.)

The first touch carries zero URLs of any form — no deck link, no site link, no calendar
link, no tracked redirect. The deck goes out on reply (R2.5), which is the point of the
low-commitment ask. Later touches permit at most one link.

```params
max_links_first_touch = 0
max_links_followup = 1
forbid_url_shorteners = true
forbid_redirect_domains = true
forbid_bare_domains_first_touch = true
```

### R3.6 — Rolling reply-rate and deliverability monitor

- **Severity:** hard
- **Enforced by:** send.monitor
- **Source:** "we observed a meaningful decline in response rates as our email campaign progressed, largely because spam filters caught an increasing fraction of our messages. We estimate that roughly a quarter of our emails were blocked before reaching the intended recipient."

A rolling window monitors reply rate and bounce rate. Sustained decline — the source's own
failure mode — raises a deliverability alarm and pauses the campaign for human review
rather than continuing to burn domain reputation. Bounces feed the same monitor.

```params
rolling_window_sends = 100
min_window_reply_rate = 0.02
max_window_bounce_rate = 0.03
decline_ratio_vs_baseline = 0.5
consecutive_bad_windows_to_alarm = 2
pause_campaign_on_alarm = true
require_human_resume = true
```

---

## §4 — Cadence and follow-ups

### R4.1 — Sequence length

- **Severity:** hard
- **Enforced by:** compose.sequence, send.preflight
- **Source:** "don't send one email and give up... across multiple well-targeted pitches, the odds compound."

The odds compound across *investors*, not across repeated touches to one investor. A
target receives the first touch plus at most two follow-ups. The full sequence is planned
as one object at compose time so cadence is visible before the first send.

> **RULE-CHECK:** the source endorses persistence without specifying a touch count. Two
> follow-ups (three touches total) is the stricter reading.

```params
max_followups_per_target = 2
max_total_touches_per_target = 3
plan_sequence_at_first_compose = true
```

### R4.2 — Spacing between touches

- **Severity:** hard
- **Enforced by:** compose.sequence, send.scheduler
- **Source:** "VCs process information fast. Research suggests they receive thousands of solicitation emails per month."

Follow-ups are spaced in business days, never sent same-week as the prior touch, and are
subject to the same send windows as the first touch (R4.5).

```params
followup_gap_business_days = [7, 14]
min_gap_business_days = 5
gap_basis = "days_since_previous_touch"
```

### R4.3 — New information required

- **Severity:** hard
- **Enforced by:** compose.sequence
- **Source:** "Give them an easy, low-cost way to express interest... your task at this stage is not to get money from the investor but get investor hooked enough to want to learn more."

Every follow-up must carry a distinct, previously unused payload from the founder-maintained
`updates` table. A bare bump ("just floating this to the top of your inbox") is not a
follow-up. If no unused update exists, **the follow-up is not generated** — the sequence
simply ends.

```params
require_new_information = true
allow_bump_only = false
allow_update_reuse = false
update_consumed_on_draft = true
generate_without_update = false
max_update_age_days = 90
```

### R4.4 — Stop conditions

- **Severity:** hard
- **Enforced by:** inbox.crm, send.preflight
- **Source:** "Many investors replied by requesting a pitch deck—the lowest-friction next step." (Once a reply arrives, the cold sequence has done its job.)

Any reply ends the cold sequence. A `pass` reply is a permanent global suppression across
all present and future campaigns. Hard bounces and complaints suppress immediately.
Out-of-office reschedules rather than cancels.

```params
stop_on_any_reply = true
stop_on_pass = true
pass_suppression_permanent = true
pass_suppression_scope = "global"
stop_on_hard_bounce = true
stop_on_complaint = true
stop_on_unsubscribe = true
ooo_reschedules = true
ooo_reschedule_days = 14
auto_reply_continues_sequence = true
```

### R4.5 — Send windows

- **Severity:** hard
- **Enforced by:** send.scheduler
- **Source:** "Timing and deliverability are real."

Sends occur Tuesday through Thursday, 07:00–10:00 in the **recipient's** local time. If
the recipient's timezone is unknown the send is deferred, not guessed — a mistimed send
spends reputation for nothing.

> **RULE-CHECK:** the source asserts that timing matters without naming a window. The
> Tue–Thu 07:00–10:00 recipient-local window is specified by BUILD_PROMPT.md and adopted
> here; deferring on unknown timezone is the stricter reading.

```params
allowed_weekdays_iso = [2, 3, 4]
window_start_hour = 7
window_end_hour = 10
timezone_basis = "recipient_local"
defer_on_unknown_timezone = true
forbid_send_outside_window = true
respect_recipient_holidays = false
```

---

## §5 — Legal, consent, and data provenance

### R5.1 — CAN-SPAM footer

- **Severity:** hard
- **Enforced by:** guardrails.footer, send.mime
- **Source:** Statutory (15 U.S.C. §7704). Not derived from the field experiment.

Every commercial message carries an accurate `From` header, a non-deceptive subject, a
valid physical postal address, and a working opt-out. The footer is exempt from the R2.1
word count so compliance text never competes with pitch text. Opt-outs are honoured
immediately, not within the statutory ten business days.

```params
require_physical_postal_address = true
require_optout_mechanism = true
require_accurate_from_header = true
forbid_deceptive_subject = true
optout_honored_immediately = true
statutory_optout_days = 10
footer_exempt_from_word_count = true
```

### R5.2 — Suppression list precedence

- **Severity:** hard
- **Enforced by:** send.preflight
- **Source:** Statutory + R4.4.

The global suppression list is checked immediately before every dispatch, after all
scheduling and queueing. A suppressed recipient is never dispatched to regardless of
queue state, approval state, or campaign. Suppression checks apply at email, domain, and
firm scope.

```params
check_before_every_send = true
check_at_dispatch_time = true
scopes = ["email", "domain", "firm", "investor"]
queue_state_cannot_bypass = true
approval_cannot_bypass = true
```

### R5.3 — Data provenance and collection limits

- **Severity:** hard
- **Enforced by:** ingest.sources, research.fetch
- **Source:** BUILD_PROMPT.md non-goals; consistent with the experiment's use of public investor data.

Every investor and evidence record stores its source and ingestion date. Collection is
limited to public sources: published exports, fund websites, SEC filings, and public
writing. No scraping behind authentication, no LinkedIn contact scraping, no purchased
contact lists.

```params
require_source_on_every_record = true
require_ingested_at = true
forbid_authenticated_scraping = true
forbid_linkedin_contact_scraping = true
forbid_purchased_lists = true
respect_robots_txt = true
allowed_source_types = ["csv_import", "fund_site", "sec_form_d", "public_writing", "manual_entry"]
```

---

## §6 — Human-in-the-loop

### R6.1 — Per-email approval

- **Severity:** hard
- **Enforced by:** app.approval_queue, send.preflight
- **Source:** BUILD_PROMPT.md core design principle 3.

No message is dispatched without explicit per-email human approval recorded as
`approved_by` and `approved_at` on the draft. Approval is per draft, never per campaign or
per batch, and cannot be granted by a model. A draft edited after approval loses its
approval and must be re-approved.

```params
require_per_email_approval = true
require_approved_by = true
require_approved_at = true
allow_batch_approval = false
allow_campaign_level_approval = false
model_may_approve = false
edit_invalidates_approval = true
dry_run_exempt = true
```
