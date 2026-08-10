# Job Hunter Agent

A daily job-hunting outreach assistant. It searches for relevant jobs
across **all companies** (not a pre-configured list), finds up to 3
people to contact at each hiring company, drafts one message per
contact, and sends everything to Telegram for you to review and
copy-paste manually.

**Nothing is ever sent automatically.** This is a human-in-the-loop
drafting tool, not an auto-sender — you always review and send the
message yourself.

## $0/month architecture

| Stage | Source | Cost |
|---|---|---|
| **Find jobs** | [JSearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) (RapidAPI free tier — searches Google Jobs, which indexes LinkedIn/Indeed/Glassdoor/thousands of boards) | Free — 200 requests/month |
| **Find contacts (Priority A)** | Your LinkedIn **Connections.csv** export, matched by company | Free — official LinkedIn data export |
| **Find contacts (Priority C/D)** | [Apollo.io](https://apollo.io) free tier, called per-company as jobs are found | Free tier — see caveat below |
| **Draft message** | One fixed template string, personalized only by first name | Free — no LLM, no API call |
| **Send alert** | Telegram bot | Free |

```
JSearch (search ALL companies by keyword)
    → for each job's company:
        LinkedIn Connections.csv → Priority A matches
        Apollo (free tier)       → Priority C/D matches
    → rank top 3 contacts per job
    → fill first-name-only message template
    → send batched Telegram alert per job
```

### Why no LLM?

The outreach message never needs to be creative — it's the same pitch
every time. A fixed f-string template costs nothing and never breaks,
rate-limits, or drifts in tone. See `modules/message_generator.py`.

### Why not scrape LinkedIn for contacts?

Automating or logging into LinkedIn's own site violates its Terms of
Service and risks your account. Instead, Priority A contacts come from
**LinkedIn's own official data export** — Settings & Privacy → Data
privacy → Get a copy of your data → Connections — which is the
ToS-compliant way to get your 1st-degree network as a CSV.

### ⚠️ Known limitation: Apollo's free tier

As of this writing, Apollo's real, documented search endpoints
(`mixed_companies/search`, `mixed_people/api_search`) return HTTP 403
`API_INACCESSIBLE` on a true Free plan — **API access itself requires a
paid Apollo plan**, even though viewing basic fields doesn't cost
credits once you have access. This was verified live against the
project's own Apollo key during development, including double-checking
that an alternate endpoint name (`organization_top_people`, sometimes
referenced in older integrations) doesn't exist at all — it 404s.

The integration in `modules/contact_finder.py` is implemented correctly
against Apollo's current documented endpoints and will start working
automatically the moment your key gains API access (e.g. if you
upgrade, or if Apollo changes its free-tier policy). Until then,
**Priority C/D contacts will simply come back empty**, and the pipeline
runs fine on Priority A (LinkedIn CSV) alone.

### ⚠️ JSearch requires a RapidAPI subscription, not just a key

A RapidAPI account key alone is **not** enough — you must visit
[the JSearch API page](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)
and click **Subscribe** on the free "Basic" plan before `RAPIDAPI_KEY`
will actually work. Without subscribing, every request returns
`{"message": "You are not subscribed to this API."}`, which the
scraper logs as a warning and treats as zero results (never crashes).

## Setup

```bash
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt

copy .env.example .env
copy config.example.py config.py
```

Then edit:

- **`.env`** — Telegram bot token/chat id, RapidAPI key (subscribe to
  JSearch first — see above), Apollo API key (optional).
- **`config.py`** — your name/degree/university and job keywords.
- **`Connections.csv`** — export from LinkedIn (Settings & Privacy →
  Data privacy → Get a copy of your data → Connections) and drop the
  file in the project root. The parser skips LinkedIn's preamble lines
  and finds the real header automatically.

All of these (`.env`, `config.py`, `Connections.csv`) are git-ignored —
they hold your personal info and secrets and are never committed.

## Running it

```bash
python main.py                    # Single run, console output only
python main.py --telegram         # Also send to Telegram
python main.py --daily            # Run once per day at 08:00
python main.py --daily --hour 9   # ...at 09:00 instead
python main.py --mock             # Use hardcoded sample jobs instead of JSearch
python main.py -v                 # Verbose/debug logging
```

`--daily` computes the exact wait until the next run and sleeps once —
it doesn't poll in a loop. Ctrl+C stops it cleanly.

If `.env`/`config.py`/`Connections.csv` are missing or incomplete, the
pipeline prints clear warnings and runs in degraded mode (console
output only, contacts limited to whatever's available) instead of
crashing.

## API budget safety

Two independent safeguards keep this project from ever going over a
free tier, or being charged if a plan ever changes:

**1. One keyword per day.** Regardless of how long `JOB_KEYWORDS` is,
`JobScraper._keywords_for_today()` queries exactly **one** keyword per
run (`day_of_year % len(keywords)` picks which one) — roughly 1 JSearch
request per daily run instead of one per keyword. The full list still
gets covered once every `len(keywords)` days. `date_posted=3days` is
used on every query so a keyword rotated back in after a few idle days
still won't miss recent postings.

**2. Hard monthly caps, enforced in code, not just by habit.**
`modules/usage_tracker.py` tracks call counts in a local
`api_usage.json` (gitignored — it's local state, not config), reset
automatically on the 1st of each month:

- JSearch: capped at **180 calls/month** (`config.MAX_MONTHLY_JSEARCH_CALLS`) — the free tier's real limit is 200; this is a backstop under the 1-keyword-per-day behavior, which alone stays far under it.
- Apollo: capped at **70 calls/month** (`config.MAX_MONTHLY_APOLLO_CALLS`) — a conservative safety margin in case Apollo's free-tier API restriction (see below) ever lifts.

Every call site checks the counter *before* making a request. Once a
cap is hit, that source is skipped for the rest of the month with a
clear log line (`Monthly JSearch limit reached — skipping.` /
`Monthly Apollo limit reached — skipping.`) — the pipeline keeps
running on whatever sources are still available instead of crashing.

## Output

- **Telegram** (if configured): one message per job, batched with all of
  that job's ranked contacts (🥇🥈🥉) — name, role, why they were picked,
  LinkedIn URL, and the ready-to-copy message.
- **Console**: the same information, always printed, so you can test
  without Telegram set up.
- **`outreach_log.jsonl`**: every alert ever sent, one JSON line per job —
  a permanent free record, useful even if Telegram is down.
- **`seen_jobs.json`**: persisted job UIDs so re-running the pipeline
  (or restarting `--daily` mode) never re-alerts on the same posting.

## Contact priority hierarchy

| Priority | Meaning | Source |
|---|---|---|
| A | 1st-degree connection | LinkedIn `Connections.csv` |
| B | University alumni | Not available from the CSV export (no university column) — kept in the code for future use |
| C | Engineering Manager / Tech Lead / Director of Engineering | Apollo (see limitation above) |
| D | HR / Technical Recruiter / Talent Acquisition | Apollo (see limitation above) |

Up to 3 contacts per job, ranked A → D. If nothing is found for a
company, it's skipped — the agent never invents placeholder people.
