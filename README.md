# Pitchline

A founder-side VC outreach engine. It takes a startup profile, builds a researched list of
relevant investors, writes a personalised cold pitch for each one, sequences follow-ups,
and handles replies — under hard deliverability and provenance constraints.

**The objective function is qualified replies per unit of sender reputation consumed.** Not
emails sent. Reputation is a depletable budget, enforced in code.

[`PITCH_RULES.md`](PITCH_RULES.md) is the normative spec. Every threshold in the system is
parsed from it at import time; no rule value is hard-coded anywhere else. Rules derive from
a field experiment that sent 50 pitches to ~28,000 investors, and each rule quotes the
source passage it comes from.

---

## Quick start

```bash
pip install -e ".[dev]"                     # core: sqlmodel, pydantic, typer
python scripts/generate_sample_investors.py # 570-row sample export
pytest                                      # 85 tests, no network, no API key

pitchline init --demo                       # database + a runnable founder setup
pitchline ingest data/sample_investors.csv  # partner-level records with provenance
pitchline target --campaign demo            # score, rank, cap, suppress conflicts
pitchline compose --campaign demo --limit 20
pitchline queue --campaign demo             # what is waiting on you
pitchline show 1                            # read it exactly as it will arrive
pitchline approve 1 --by "Your Name"        # R6.1 — one email at a time
pitchline send --campaign demo              # dry run by default
streamlit run pitchline/app.py              # the review UI
```

Nothing sends without `--live` **and** a per-email human approval.

### Running without an API key

The engine ships with a deterministic offline client that implements every LLM call
(fit scoring, variant selection, personalization hook, novelty judging, reply
classification). It is the default when `ANTHROPIC_API_KEY` is unset, so the whole
pipeline — and the whole test suite — runs with no network and no spend. Set the key, or
`PITCHLINE_LLM=anthropic`, to switch to Claude with forced structured output.

---

## What a run actually looks like

```
570 rows -> 560 new investors, 10 duplicates, 56 quarantined, 180 firms, 2240 evidence snippets
504 considered -> 119 qualified (227 low fit, 23 conflicts, 135 lacking research, 0 over cap)
12 drafts passed every gate, 0 routed to the human-fix queue
```

Every one of those numbers is a rule doing its job: 56 rows quarantined because they were
not partner-level or were shared inboxes (R1.4); 227 investors dropped because the thesis
did not match (R1.2); 23 suppressed because the fund holds a direct competitor (R1.5); 135
skipped because there was not enough evidence on file to write anything specific (R1.3).

A draft it produces:

> Hi Nadia,
>
> I spent six years running clinical operations at a CRO that paid 400 trial sites a month.
> Your stated thesis — "back seed-stage companies rebuilding the financial plumbing of
> healthcare delivery, with a bias toward clinical operations" — is why I am writing to you
> rather than mass-mailing.
>
> Clinical trial sites wait an average of 87 days to be paid for visits they have already
> completed, and roughly 1 in 5 sites leaves a study citing cash flow.
>
> We parse the executed site contract into machine-readable payment triggers, then release
> payment when the EDC records the visit.
>
> Happy to send the deck if that is easier.

86 words. Credibility marker in sentence one. The quoted clause is a verbatim extract from
a stored evidence row, and the draft records which row.

---

## Architecture

```
pitchline/
  rules.py       parses PITCH_RULES.md -> typed constants; single source of truth
  models.py      SQLModel schema (19 tables)
  schemas.py     Pydantic v2 contracts for every LLM call
  llm.py         versioned prompts, Anthropic client + offline heuristic client
  ingest/        1. CSV import, partner-level resolution, public-source scrapers
  research/      2. evidence store, TTL cache, R1.3 coverage floor
  targeting/     3. fit scoring, conflict suppression, campaign cap
  compose/       4. four-slot composition, personalization hook, follow-up sequences
  guardrails/    5. the gate: length, media, links, spam, credibility, provenance, novelty
  send/          6. reputation budget, preflight, transports, monitor, scheduler
  inbox/         7. reply classification, CRM transitions, suppression
  approval.py    the human-in-the-loop surface, built before the sender
  analytics.py   reply rate by variant/cohort vs the 4% / 13-17% benchmarks
  app.py         Streamlit approval queue
  cli.py         Typer
```

### The four design principles, made concrete

**1. Reputation is a depletable budget.** `ReputationBudget` is a database row per mailbox
per day, capped by a warmup ramp indexed by mailbox age. It raises
`ReputationBudgetExceeded` rather than silently deferring, because "we ran out of
reputation today" is information the operator needs. A process restart cannot reset it.

**2. No unsourced claims.** Every investor-specific sentence in a draft maps to an
`evidence_id` in the draft's claim map, and the linter fails a draft with any unsourced
claim, any claim citing an id that does not resolve, or any claim map that has gone stale
against the body it describes.

**3. Human-in-the-loop is structural.** `approval.approve` is the only function that can
set `approved_by`/`approved_at`. It refuses non-human actors, refuses drafts that have not
cleared the gate, and editing a draft clears its approval and re-runs every check.

**4. Every send is an experiment record.** Variant key, cohort, touch number and timestamp
on every `Send`. Analytics reports qualified reply rate by arm against the 4% baseline and
13–17% ceiling — and says "insufficient sample" rather than calling 1-of-3 a 33% reply rate.

---

## What the guardrails actually block

| Gate | Rule | Blocks |
|---|---|---|
| length | R2.1 | > 150 words; empty body; > 4 paragraphs; > 78-char subject |
| structure | R2.2 | solution stated before the problem; slot text the model rewrote |
| credibility | R2.3 | no registered marker in sentence one — including markers it cannot verify |
| novelty | R2.4 | "I've seen ten of these this week" — scored, fails below 4.0/5 |
| ask | R2.5 | "next Tuesday at 3 PM"; term-sheet asks; calendar links on touch 1 |
| provenance | R2.6 | any unsourced investor-specific claim; dangling or stale citations |
| media | R3.1 | embedded images, attachments, tracking pixels, HTML parts |
| spam | R3.4 | 60-term deny list, exclamation marks, ALL-CAPS beyond short acronyms |
| links | R3.5 | any URL on the first touch (email addresses are not URLs) |
| footer | R5.1 | missing postal address or opt-out |

A failure returns a structured code, and each code has a mechanical repair — a shorter
variant for a length failure, a different angle for a novelty failure. After two retries
the draft goes to the human-fix queue rather than being retried forever.

## What refuses to send

`UnapprovedDraftError`, `SuppressedRecipientError`, `PortfolioConflictError`,
`OutsideSendWindowError`, `UnknownTimezoneError`, `InvalidSenderError`,
`GuardrailNotPassedError`, `ReputationBudgetExceeded`, `NoMailboxAvailable`.

Each is a distinct type because "not approved yet" and "this person asked never to be
contacted again" are operationally different problems. The suppression list is checked in
preflight *and* again in the statement immediately before `transport.deliver`, because a
reply can land in between.

---

## Configuration

| Variable | Effect |
|---|---|
| `PITCHLINE_DATABASE_URL` | Postgres instead of SQLite |
| `PITCHLINE_DB` | SQLite file path (default `pitchline.db`) |
| `PITCHLINE_RULES_PATH` | Load a different rules file |
| `PITCHLINE_LLM` | `anthropic` or `offline` |
| `PITCHLINE_MODEL` | Model id (default `claude-sonnet-5`) |
| `ANTHROPIC_API_KEY` | Present -> Anthropic client; absent -> offline client |

Optional extras: `.[llm]` Anthropic, `.[research]` httpx + trafilatura,
`.[ui]` Streamlit, `.[schedule]` APScheduler, `.[gmail]` Gmail API.

## Going live

1. Register a dedicated secondary domain with SPF, DKIM and DMARC (R3.2). Never the
   company's primary domain.
2. Add mailboxes with an honest `warmup_started_on` — the ramp is indexed off it.
3. Replace the demo variant library with your own copy. The credibility markers must be
   *your* credibility; the problem and approach text must be *your* words. The model
   selects between them, it never writes them.
4. Fill `updates` with real, dated news. A follow-up with nothing new is not generated.
5. Run `pitchline send --live --transport gmail`, or drip it with
   `pitchline tick --campaign <name> --live` from cron.

## Non-goals

No autonomous sending. No open or click tracking. No scraping behind authentication. No
LinkedIn contact scraping. No purchased lists. No volume above the R1.1 cap — if the list
is too small, fix the targeting.

## Provenance of the rules

`PITCH_RULES.md` was written from the practitioner guidance published alongside the field
experiment ("What Makes a Cold Pitch Work"). Where the source is qualitative — it names the
"I've seen ten of these this week" test but no threshold, endorses persistence but no touch
count, says timing matters but names no window — the rules file takes the stricter reading
and tags it `RULE-CHECK`. Those are listed by `pitchline rules` so the author can confirm
or change each one; every number they set propagates from that file alone.
