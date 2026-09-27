# Atlas

**Find the duplicate products hiding in a catalogue.** Upload a spreadsheet of parts or products, and Atlas shows which lines are the same item, keeps look-alikes apart, and totals the stock tied up in duplicates. People review every match before downloading a clean file.

**Live:** [atlasmatch.co.uk](https://atlasmatch.co.uk) (free hosting: the first visit after a quiet spell can take up to a minute to wake up)

![Atlas landing page](docs/images/landing.png)

![Results screen with duplicate groups, reasons and review actions](docs/images/results.png)

## Why it exists

The same part is often listed several times: `SKF 6205-2RS Deep Groove Ball Bearing`, `6205 2RS SKF bearing`, `Bearing 6205-2RS (SKF)`. Each copy keeps its own stock count, so businesses reorder parts they already have and staff pick the wrong line. Exact-match tools miss these, and naive fuzzy matching merges parts that only look alike (a 2RS bearing has rubber seals, a ZZ bearing has metal shields: different products).

## Highlights

- **Matching you can trust.** Hard rules first (variant, brand, part number, size, thread, power, current, poles, material, colour, grade), text similarity second, and anything doubtful goes to a person. On labelled test catalogues: **100% precision** (no wrong merges) and 89% to 100% recall with rules alone; on a real bilingual sample, 100% precision and 97% recall.
- **English and Arabic.** Arabic-Indic digits, brands and suffixes spelled in Arabic letters (`اس كي اف` = SKF, `زد زد` = ZZ), and Arabizi (`sha7m` = grease) are normalised before matching.
- **Look-alikes are explained, not merged.** "Different seal type: 2RS has rubber seals on both sides, ZZ has metal shields on both sides." Conflicting rows can never end up in one group, even through a chain of similar pairs.
- **Stock and money on duplicate lines.** Pack sizes are converted to single units; mixed currencies or units that can't be converted give no total rather than a guess.
- **People stay in charge.** Confirm or reject groups, choose the line to keep, settle unclear pairs. Every decision is re-applied when the analysis runs again.
- **Optional AI review.** Pairs the rules can't decide can go to a Claude model, with data minimisation (never stock, cost or supplier), structured output, a per-workspace cache and a spending cap.
- **Company data separated by the database itself.** PostgreSQL row-level security on every tenant table; a missing filter in code returns nothing rather than another company's data. Tests prove one company can't read, change or plant data in another's workspace.
- **Hostile files handled safely.** Type checked by content, parsing in a separate process with memory and time limits, formulas never evaluated, and exports protected against spreadsheet formula injection.
- **Fast enough for real catalogues.** 20,000 lines analysed in about 20 seconds.

## How it works

```mermaid
flowchart LR
    A[Upload CSV, Excel or JSON] --> B[Read safely in a sandbox]
    B --> C[Match columns: name, part number, brand, stock, cost]
    C --> D[Normalise each line: brand, part, variant, sizes, type]
    D --> E[Compare plausible pairs: rules first, then similarity]
    E --> F{Sure?}
    F -- yes --> G[Duplicate groups and look-alikes]
    F -- no --> H[Needs review, or AI review if enabled]
    H --> G
    G --> I[People review]
    I --> J[Download the file with results added]
```

| Part | Technology |
| --- | --- |
| Web app | Next.js 15, React 19, TypeScript |
| API and worker | Python 3.12, FastAPI, psycopg 3, a Postgres job queue |
| Database | PostgreSQL 16 with row-level security |
| Sign-in and workspaces | Clerk (organisations) |
| File storage | S3-compatible: Cloudflare R2 in production, SeaweedFS locally |
| AI review (optional) | Anthropic Claude API with structured output |
| Hosting | Docker on Render, DNS on Cloudflare; one `render.yaml` blueprint |
| Tests | 181 automated tests: matching accuracy, company separation, full pipeline, exports |

## What's in the repository

| Folder | What it is |
| --- | --- |
| `backend/atlas/ingest/` | File reading: format detection, CSV, Excel and JSON readers, column mapping, validation report. |
| `backend/atlas/catalogue/` | Normalisation (English and Arabic), matching rules, AI review, stock and value figures. Product knowledge (variant suffixes, brands, product words) lives in `rules.py`. |
| `backend/atlas/analysis.py`, `export.py`, `review.py` | Running an analysis, building the cleaned file and applying people's decisions. |
| `backend/atlas/api/` | The API (FastAPI). |
| `backend/atlas/worker.py` | Background worker: reads uploads, runs analyses, builds exports, deletes files after 7 days. |
| `backend/migrations/` | Database schema, including the row-level security policies. |
| `backend/tests/` | Automated tests, with labelled test catalogues in `tests/fixtures/catalogue`. |
| `web/` | The web app. |
| `docker-compose.yml`, `render.yaml` | Run everything locally; deploy everything to Render. |

## Run it on your computer

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) and a free [Clerk](https://clerk.com) account.

1. Set up Clerk (see [Clerk setup](#clerk-setup)) and copy its development keys.
2. Copy the settings template and fill in the three Clerk values:
   ```
   cp .env.example .env
   ```
3. Start everything:
   ```
   docker compose up --build
   ```
4. Open http://localhost:3000, sign up, create a workspace and upload a catalogue. `backend/tests/fixtures/catalogue/stores.csv` is a good first file.

Local file storage runs in SeaweedFS at http://localhost:9000 (access key `atlas-local`, secret `change-me-local-only`). These local passwords are for your computer only.

## Run the tests

```
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                   # no database needed for most tests
```

The company-separation and end-to-end tests need the local database and storage (`docker compose up postgres storage storage-setup`):

```
DATABASE_OWNER_URL=postgresql://atlas_owner:change-me@localhost:5432/atlas \
STORAGE_BUCKET=atlas-uploads STORAGE_ENDPOINT_URL=http://localhost:9000 \
STORAGE_ACCESS_KEY_ID=atlas-local STORAGE_SECRET_ACCESS_KEY=change-me-local-only \
pytest
```

Run the company-separation tests (`tests/test_tenant_isolation.py`) before every deploy.

`pytest -s tests/test_matching.py` prints precision and recall for every labelled catalogue. The files are generated by `tests/fixtures/catalogue/generate.py`; `blind.csv` is never used for tuning.

| Labelled file | Precision | Recall |
| --- | --- | --- |
| bearings.csv | 100% | 100% |
| fasteners.csv | 100% | 100% |
| stores.csv (mixed, English and Arabic) | 100% | 88.7% |
| blind.csv (never tuned on) | 100% | 95.3% |

Rules only, no AI. Most remaining misses are English and Arabic descriptions of the same item, which go to Needs review (or AI review).

## AI review (optional)

Add a key from console.anthropic.com to `.env` (locally) or the API service's settings (in production):

```
ANTHROPIC_API_KEY=...
AI_REVIEW_MODEL=claude-opus-5
```

Without a key everything else works and unclear pairs stay under Needs review. Only the cleaned name, brand, part number, variant, kind of product and sizes are sent. Answers are cached per workspace, at most 2,000 pairs are sent per analysis, and workspace admins can turn it off in Settings. To measure accuracy and cost on a labelled file (this calls the API and asks first):

```
cd backend
ANTHROPIC_API_KEY=... .venv/bin/python -m atlas.catalogue.ai_check tests/fixtures/catalogue/blind.csv
```

## Deploy

`render.yaml` describes the whole setup: a Postgres database, the API (which on the free plan also runs migrations and the background worker) and the web app, in Frankfurt, with custom domains.

1. Push the repository to GitHub.
2. Create an R2 bucket (EU jurisdiction, public access off) and an Account API token with Object Read & Write on that bucket only.
3. Create a Clerk production instance for your domain and add the DNS records it lists (DNS only, not proxied). Turn off social sign-in providers until you add your own credentials for them.
4. In Render, choose **New > Blueprint**, pick the repository, and paste the secrets it asks for (R2 endpoint and keys, Clerk production keys; leave `ANTHROPIC_API_KEY` empty to keep AI review off).
5. Point your domain at the two Render services with CNAME records (DNS only).

Change the domain names in `render.yaml` before deploying your own copy. Secrets never go in the repository; they live only in Render's settings.

## Clerk setup

1. Create an application with email sign-in.
2. Enable **Organizations** (Configure > Organizations). Atlas calls them workspaces.
3. Add claims to the session token (Configure > Sessions > Customize session token):
   ```json
   { "email": "{{user.primary_email_address}}", "name": "{{user.full_name}}", "org_name": "{{org.name}}" }
   ```
4. Copy the Publishable key, Secret key and Frontend API URL (`CLERK_ISSUER`).

## Security and privacy

- **Company separation is enforced by the database**, not only the application, and tested.
- **Files are treated as hostile**: checked by content, parsed in a sandboxed process, macro workbooks and oversized archives refused, formulas never evaluated.
- **Uploads and exports are private**: random keys, no public URLs, deleted after 7 days or when the dataset is deleted.
- **Exports can't run formulas**: risky cells are written as text.
- **Logs hold no customer content**: IDs, counts, timings and error codes only.
- **AI review sends as little as possible**, passes item fields as data, accepts only a fixed answer format and treats anything else as "unsure".

## Roadmap

- Duplicate work in task exports (Jira, Asana and similar); the upload and column mapping already support them.
- Per-company rate limiting and a content-security policy.
- Cross-brand equivalents (stock one brand instead of three) and a check for new items before they're added.
