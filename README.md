# Job Hunter Agent

A daily job-hunting outreach assistant. It finds relevant job postings,
finds up to 3 people to contact at each hiring company, drafts one
message per contact, and sends everything to Telegram for you to review
and copy-paste manually.

**Nothing is ever sent automatically.** This is a human-in-the-loop
drafting tool, not an auto-sender — you always review and send the
message yourself.

## $0/month architecture

Every piece of this pipeline is free at normal usage volumes. There is
no paid API anywhere in the stack, and no LLM call of any kind.

| Stage | Source | Cost |
|---|---|---|
| **Find jobs** | [Greenhouse's public board API](https://boards-api.greenhouse.io) (no key needed) + plain RSS feeds | Free |
| **Find contacts** | `known_connections.json` (a file you maintain by hand) + [Apollo.io](https://apollo.io) free tier | Free |
| **Draft message** | One fixed template string, personalized only by first name | Free — no LLM, no API call |
| **Send alert** | Telegram bot | Free |

```
Job Scraper → Contact Finder → Message Templater → Telegram Alerter
```

### Why no LLM?

The outreach message never needs to be creative — it's the same pitch
every time. A fixed f-string template costs nothing and never breaks,
rate-limits, or drifts in tone. See `modules/message_generator.py`.

### Why not scrape LinkedIn for contacts?

Automating or logging into LinkedIn's own site violates its Terms of
Service and risks your account. Instead:

- **Priority A/B (people you already know)** come from
  `known_connections.json`, a file *you* fill in by hand — the only
  reliable, ToS-compliant way to know your own 1st-degree network and
  alma mater overlap.
- **Priority C/D (engineering leads, recruiters you don't know yet)**
  come from Apollo's free tier, which is a legitimate people-search API,
  not a LinkedIn scraper. Apollo's free tier discloses name / title /
  company / LinkedIn URL at no cost — only *revealing* an email or phone
  number costs credits, which this project never requests.

## Setup

```bash
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt

copy .env.example .env
copy config.example.py config.py
copy known_connections.example.json known_connections.json
```

Then edit:

- **`.env`** — Telegram bot token/chat id (required for alerts), Apollo
  API key (optional, only needed for Priority C/D auto-discovery).
- **`config.py`** — your name/degree/university, job keywords, target
  locations, and the Greenhouse company slugs / RSS feeds you want to
  poll.
- **`known_connections.json`** — real people you already know at your
  target companies. See the `_readme` key inside
  `known_connections.example.json` for the exact format.

All three of these are git-ignored — they hold your personal info and
secrets and are never committed.

## Running it

```bash
python main.py                    # Single test run, console output only
python main.py --telegram         # Also send to Telegram
python main.py --daily            # Run once per day at 08:00
python main.py --daily --hour 9   # ...at 09:00 instead
python main.py -v                 # Verbose/debug logging
```

`--daily` computes the exact wait until the next run and sleeps once —
it doesn't poll in a loop. Ctrl+C stops it cleanly.

If `.env`/`config.py`/`known_connections.json` are missing or incomplete,
the pipeline prints clear warnings and runs in degraded mode (console
output only, contacts limited to whatever `known_connections.json` has)
instead of crashing.

## Output

- **Telegram** (if configured): one message per job, batched with all of
  that job's ranked contacts (🥇🥈🥉) — name, role, why they were picked,
  LinkedIn URL, and the ready-to-copy message.
- **Console**: the same information, always printed, so you can test
  without Telegram set up.
- **`outreach_log.jsonl`**: every alert ever sent, one JSON line per job —
  a permanent free record, useful even if Telegram is down.

## Contact priority hierarchy

| Priority | Meaning | Source |
|---|---|---|
| A | 1st-degree connection | `known_connections.json` |
| B | University alumni | `known_connections.json` |
| C | Engineering Manager / Tech Lead / Director of Engineering | Apollo free tier |
| D | HR / Technical Recruiter / Talent Acquisition | Apollo free tier |

Up to 3 contacts per job, ranked A → D. If nothing is found for a
company, it's skipped — the agent never invents placeholder people.
