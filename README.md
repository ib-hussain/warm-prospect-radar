# Warm Prospect Radar

Warm Prospect Radar is a central business-acquisition, prospect-scoring, outreach and review workspace. It crawls public sources, prioritises high-value pages such as About and Contact, extracts structured company facts, preserves immutable evidence, calculates explainable prospect signals, and provides governed outreach and a grounded data assistant.

The application has **no application users, logins, per-user ownership or tenant separation**. Every browser connected to the same Supabase project sees the same records, drafts, assistant history and feature controls.

## Current capabilities

- About-first, bounded same-domain crawling with URL validation, redirects revalidation, retries, robots rules and optional Playwright rendering.
- Wikipedia infobox, JSON-LD and deterministic extraction before optional LLM enrichment.
- Official social API adapters where credentials are available, with a bounded public-page fallback.
- Ollama `gemma3:1b` first and Together AI second, with deterministic fallbacks when neither is available.
- Central Supabase records or a local atomic JSON backend for development.
- Immutable versioned snapshots, soft archive, run diagnostics and explainable scores.
- Drafts for email, direct message, comment, social post, picture and other channels.
- Draft → pending approval → approved/rejected → delivered/failed state controls.
- Safe dry-run delivery; optional live SMTP email and authorised webhook delivery.
- Manual recording of sent actions and replies, followed by immediate score recalculation.
- Grounded data assistant with shared question history.
- Optional once-daily refresh worker and a manual full-workspace refresh control.
- Global feature switches for acquisition, social acquisition, LLMs, outreach, assistant, scheduled refresh and delivery.
- Flask/HTML/CSS/JavaScript interface using the supplied pastel glass visual direction.
- Native Windows, Arch/WSL and Docker workflows.

## Security boundary

This build deliberately does not implement application users or Row Level Security. Treat it as one shared workspace.

- Run it only on a trusted computer or private network.
- If it must be internet-accessible, protect the Flask service at the network or reverse-proxy layer.
- Never place a Supabase service-role key, SMTP password or API token in browser JavaScript.
- The scraper never imports browser cookies, automates login, solves CAPTCHAs or bypasses platform access controls.
- Live non-email delivery goes through a user-configured webhook whose receiving system must use authorised platform APIs.
- `OUTREACH_DELIVERY_MODE=dry_run` is the default. It exercises the workflow without sending anything externally.

See `SECURITY.md` for the operational checklist.

## 1. Local setup

Python 3.11 or newer is required; Python 3.12 is recommended.

### Arch Linux or WSL

```bash
cp .env.example .env
python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
./run.sh
```

If Playwright cannot provide system packages on Arch, install Chromium through `pacman`, set `PLAYWRIGHT_EXECUTABLE_PATH=/usr/bin/chromium` in `.env`, and keep `SCRAPER_JS_FALLBACK=true`.

### Windows PowerShell

```powershell
Copy-Item .env.example .env
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m playwright install chromium
.\run.ps1
```

Open `http://127.0.0.1:5000`.

## 2. Docker setup

The image contains Python, the Flask application, Gunicorn, the refresh worker and Playwright Chromium. Supabase, Together AI and Ollama remain external providers.

```bash
cp .env.example .env
docker compose build
docker compose up -d
docker compose ps
```

Open `http://127.0.0.1:5000`. Stop with:

```bash
docker compose down
```

Local JSON and snapshots persist in the named `radar-storage` volume. To remove that data deliberately, use `docker compose down -v`.

Docker uses one Gunicorn worker with four threads because the once-daily scheduler lives inside the application container. A single worker prevents duplicate scheduler loops. Chromium receives a 1 GiB shared-memory allocation and an init process.

### Ollama from Docker

If Ollama runs on Windows/WSL or the Docker host, Compose uses:

```dotenv
DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434
```

Make sure Ollama is listening on an interface reachable from Docker. Otherwise configure `TOGETHER_API_KEY`; deterministic extraction, drafting and assistant answers remain available without either model provider.

## 3. Supabase setup

Create a new Supabase project, open its SQL editor, and run these files in order:

1. `db/schema_v1.sql`
2. `db/functions_v2.sql`

Then configure:

```dotenv
DATA_BACKEND=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SECRET_KEY=your-server-side-secret-key
SUPABASE_BUCKET=business-snapshots
SUPABASE_UPLOAD_RAW=false
```

`SUPABASE_UPLOAD_RAW=false` keeps full raw snapshots locally while structured, searchable records remain central. Set it to `true` only when the server-side key or storage policies can write to the private bucket.

The schema revokes table and RPC access from Supabase `anon` and `authenticated` roles, then grants it to `service_role`. Use a new `sb_secret_...` key or the legacy server-side `service_role` key. A publishable/anon key is intentionally rejected by the application. Keep the secret only in the server/container environment.

### Upgrade an earlier scraper-first database

If the earlier schema is already installed, run:

1. `db/migrate_v1_to_v2.sql`
2. `db/functions_v2.sql`

The migration removes `app_users` and every user foreign key, then adds central feature flags, outreach drafts and assistant history. Back up a real database before any migration.

## 4. Central feature controls

The Settings page contains global switches:

| Switch | Effect when disabled |
| --- | --- |
| Acquisition | Blocks manual, API and scheduled scraping. |
| Social acquisition | Keeps website crawling but skips social-profile acquisition. |
| LLM enrichment | Uses deterministic extraction, drafting and assistant fallbacks. |
| Outreach workflow | Blocks draft, approval, delivery and interaction routes. |
| Data assistant | Blocks the assistant page and API. |
| Daily refresh | Stops scheduled cycles and blocks manual full cycles. |
| External delivery | Keeps drafting/approval available but blocks delivery. |

The initial values come from `ENABLE_*` variables in `.env`. Once the data store is created, changes made in the Settings page become the central values shared by everyone.

## 5. Acquisition and refresh

Enter a public website or Wikipedia page under Acquire. Each synchronous run:

1. validates the target and every redirect against private or unsafe network destinations;
2. reads crawl policy when enabled;
3. prioritises About, company, contact, team, product and service pages;
4. retries transient failures and optionally renders sparse JavaScript pages;
5. extracts deterministic data and then optionally asks the configured LLM;
6. discovers and acquires a bounded number of public social profiles;
7. recalculates the prospect score;
8. writes the canonical record and immutable snapshot.

Manual refresh remains available on each business page. The daily worker uses the same pipeline and continues when one business fails.

Scheduler variables:

```dotenv
ENABLE_SCHEDULED_REFRESH=true
SCHEDULER_INTERVAL_HOURS=24
SCHEDULER_INITIAL_DELAY_SECONDS=60
SCHEDULER_MAX_BUSINESSES_PER_RUN=100
SCHEDULER_RUN_IN_WEB=false
```

Docker overrides `SCHEDULER_RUN_IN_WEB=true`. For local development, either enable it or run one cycle explicitly:

```bash
.venv/bin/python -m src.scheduler --once
```

For a dedicated local loop:

```bash
.venv/bin/python -m src.scheduler
```

Do not run both a dedicated loop and the in-web loop against the same workspace.

## 6. Outreach and approval

The outreach desk supports six channel types. A blank body invokes LLM drafting when enabled and falls back to a deterministic template. Every generated statement is constrained to stored facts.

State transitions are explicit:

```text
draft → pending approval → approved → delivered
                         ↘ rejected → draft
approved → failed → draft after editing
```

Editing any non-delivered item returns it to `draft`. A delivered item is terminal, which prevents accidental duplicate sends.

### Dry-run delivery

```dotenv
OUTREACH_DELIVERY_MODE=dry_run
```

Approval and delivery states are exercised, a simulated interaction is stored, and nothing leaves the application. Simulated actions do not count as response-scoring attempts.

### Live email

```dotenv
OUTREACH_DELIVERY_MODE=live
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=account@example.com
SMTP_PASSWORD=secret
SMTP_FROM_ADDRESS=account@example.com
SMTP_USE_TLS=true
```

Only an approved email draft can reach SMTP.

### Live social or custom delivery

```dotenv
OUTREACH_DELIVERY_MODE=live
OUTREACH_WEBHOOK_URL=https://your-authorised-integration.example/hooks/outreach
OUTREACH_WEBHOOK_SECRET=replace-with-a-random-secret
```

The app sends a JSON payload with an `X-Warm-Prospect-Signature: sha256=...` HMAC header when a secret is configured. The receiving integration is responsible for authorised Facebook, Instagram, LinkedIn, X, comment, post, media or other delivery.

## 7. Data assistant

The Assistant page selects relevant businesses, passes only bounded structured context to Ollama/Together AI, and stores the question and answer centrally. Source fields are explicitly treated as untrusted data to reduce prompt-injection risk.

If no LLM is reachable, deterministic answers still support:

- active business counts;
- top prospects by score;
- single-company summaries;
- relevant record lists.

Control its prompt size with:

```dotenv
ASSISTANT_MAX_BUSINESSES=20
ASSISTANT_CONTEXT_CHARACTERS=24000
```

## 8. Scoring

Reply likelihood is intentionally inversely related to company size and then adjusted by contactability. The prospect score is:

- response strength: 65%;
- difficulty value: 25%;
- data completeness: 10%.

The business detail page exposes every component. Live delivered actions and manually recorded interactions update the attempt/reply summary. Dry-run delivery does not inflate it.

## 9. Social acquisition

Optional official credentials:

```dotenv
META_ACCESS_TOKEN=
X_BEARER_TOKEN=
LINKEDIN_ACCESS_TOKEN=
LINKEDIN_ORGANIZATION_ID=
LINKEDIN_API_VERSION=202501
GITHUB_TOKEN=
```

When an official adapter or credential is unavailable, the application may read a public profile page if `ALLOW_PUBLIC_SOCIAL_FALLBACK=true`. A blocked page becomes a warning and does not fail the complete business run.

## 10. API

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Backend, feature and delivery readiness. |
| `GET` | `/api/businesses` | Searchable central business records. |
| `POST` | `/api/scrape` | Synchronous acquisition. |
| `POST` | `/api/assistant` | Grounded assistant answer. |
| `GET` | `/api/outreach/drafts` | Central outreach draft list. |

Example:

```bash
curl -X POST http://127.0.0.1:5000/api/assistant -H "Content-Type: application/json" -d '{"question":"Which prospects have the highest score?"}'
```

## 11. Tests and quality checks

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/python -m compileall -q app.py src tests
```

Docker configuration can be resolved without starting the application:

```bash
docker compose config
```

## Project layout

```text
db/                   Supabase clean schema, migration, functions and sample loader
fileStorage/          Local snapshots and optional media
src/frontend/         Flask routes, templates, CSS and JavaScript
src/outreach/         Drafting, approval and guarded delivery adapters
src/scraper/          Crawl, extraction, LLM, social and pipeline modules
src/chatbot.py        Grounded central data assistant
src/scheduler.py      Manual and once-daily refresh worker
src/database.py       Local and Supabase repositories
tests/                Unit and Flask integration tests
Dockerfile            Single application image with Chromium
docker-compose.yml    Persistent one-container runtime
```

`src/scraper/webpape.py` remains as a compatibility wrapper for the original filename; new code uses `webpage.py`.

## Troubleshooting

- **Supabase table error after upgrading:** run `db/migrate_v1_to_v2.sql`, then rerun `db/functions_v2.sql`.
- **Assistant or drafts page returns 403:** enable the feature under Settings.
- **Ollama unavailable in Docker:** set `DOCKER_OLLAMA_BASE_URL` to a host-reachable address or configure Together AI.
- **Chromium crashes in Docker:** keep `init: true` and `shm_size: 1gb`; increase shared memory for heavy crawls.
- **Live delivery fails:** confirm the item is approved, External delivery is enabled, `OUTREACH_DELIVERY_MODE=live`, and the relevant SMTP/webhook settings are present.
- **Duplicate scheduler work:** run only one Gunicorn worker when `SCHEDULER_RUN_IN_WEB=true`, or disable the in-web scheduler and use a single dedicated scheduler process.
- **Local JSON contention:** do not run Windows and WSL processes against the same local JSON file; use Supabase for concurrent access.
