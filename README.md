# Atlas

Atlas finds duplicate lines in a company's product catalogue (and, later, duplicate work in task exports). This repository is the production codebase.

**Current build: Phase 4 complete (catalogue duplicate finding).** People sign in, create or join a workspace, upload a CSV, Excel or JSON product catalogue and check what Atlas read. **Start analysis** finds duplicate groups with reasons, keeps look-alikes apart (2RS vs ZZ, A2 vs A4, 100 W vs 150 W), optionally asks a Claude model about pairs the rules can't decide, and totals the stock and money on duplicate lines. On the results screen people confirm or reject groups, choose the line to keep, take lines out, settle unclear pairs, and download their file with the results added. Every decision is kept when the analysis runs again.

## What's in the repository

| Folder | What it is |
| --- | --- |
| `backend/atlas/ingest/` | File reading: format detection, CSV / XLSX / JSON readers, column mapping (task or catalogue fields), validation report. Pure Python, fully tested. |
| `backend/atlas/catalogue/` | Catalogue analysis: normalisation (English and Arabic), matching rules, AI review, stock and value figures. Pure Python. Product knowledge (variant suffixes, brands, product words) lives in `rules.py`. |
| `backend/atlas/analysis.py`, `export.py`, `review.py` | Running an analysis, building the cleaned file, and applying people's review decisions, with results stored per workspace. |
| `backend/atlas/api/` | The API (FastAPI). |
| `backend/atlas/worker.py` | Background worker: reads uploaded files, runs analyses, builds exports, deletes files after 7 days. |
| `backend/migrations/` | Database schema, including row-level security that keeps each company's data separate. |
| `backend/tests/` | Automated tests. |
| `web/` | The web app (Next.js). |
| `docker-compose.yml` | Runs everything on your computer. |

## Run it on your computer

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) and a free [Clerk](https://clerk.com) account.

1. **Set up Clerk** (see [Clerk setup](#clerk-setup) below) and copy its development keys.
2. Copy the settings template and fill in the three Clerk values:
   ```
   cp .env.example .env
   ```
3. Start everything:
   ```
   docker compose up --build
   ```
4. Open http://localhost:3000, sign up, create a workspace and upload a file.

Local file storage runs in SeaweedFS, an S3-compatible server, at http://localhost:9000 (access key `atlas-local`, secret `change-me-local-only`). It has no web console. These local passwords are for your computer only. (MinIO was used until its images were removed from Docker Hub in September 2026.)

## Run the tests

```
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                   # file-reading tests; no database needed
```

The tenant-isolation tests need a disposable database. With `docker compose up postgres` running:

```
DATABASE_OWNER_URL=postgresql://atlas_owner:change-me@localhost:5432/atlas pytest tests/test_tenant_isolation.py
```

They check that one company can't read, change, delete or plant data in another company's workspace. **Run these before every deploy.**

The end-to-end tests (analysis, AI settings and cache, export) also need the local file storage:

```
DATABASE_OWNER_URL=postgresql://atlas_owner:change-me@localhost:5432/atlas \
STORAGE_BUCKET=atlas-uploads STORAGE_ENDPOINT_URL=http://localhost:9000 \
STORAGE_ACCESS_KEY_ID=atlas-local STORAGE_SECRET_ACCESS_KEY=change-me-local-only \
pytest
```

### Matching accuracy

`pytest -s tests/test_matching.py` prints precision (how many grouped pairs are real duplicates) and recall (how many real duplicates were found) for each labelled file in `tests/fixtures/catalogue`. The files are made up by `generate.py` in that folder; `blind.csv` is never used for tuning. Rules only, today: 100% precision on every file, recall 89% to 100%.

## AI review (optional)

Pairs the rules can't decide (for example the same item named in English on one line and in Arabic on the other) can be checked by a Claude model. Add a key from console.anthropic.com to `.env` and restart the worker:

```
ANTHROPIC_API_KEY=...
AI_REVIEW_MODEL=claude-opus-5
```

Without a key everything else works and those pairs stay under "needs review". Only the cleaned name, brand, part number, variant, kind of product and sizes are sent, never stock, cost, supplier or other columns. Answers are cached per workspace, at most 2,000 pairs are sent per analysis, and a workspace admin can turn AI review off (`PUT /v1/settings`). To measure accuracy and cost on a labelled file (this calls the API and costs money; it asks first):

```
cd backend
ANTHROPIC_API_KEY=... .venv/bin/python -m atlas.catalogue.ai_check tests/fixtures/catalogue/blind.csv
```

## Put it online

The steps use [Render](https://render.com) for hosting and [Cloudflare R2](https://developers.cloudflare.com/r2/) for file storage. Any host that runs Docker and offers managed Postgres works the same way.

### 1. Accounts

- **GitHub**: create a private repository and push this code to it.
- **Render**: create an account and connect it to GitHub.
- **Clerk**: create a production instance (see below).
- **Cloudflare**: create an account and enable R2.

### 2. Database

In Render, create a **PostgreSQL** database in an EU region (Frankfurt) or wherever your customers are. Copy its **Internal Database URL**; this is both `DATABASE_URL` and `DATABASE_OWNER_URL`.

The first migration creates a restricted database role, `atlas_app`, that the API and worker use. This needs a database user allowed to create roles. If the migration fails with `permission denied to create role`, your host doesn't allow that: stop and ask for the alternative setup rather than removing the role, because the role is what enforces company separation.

### 3. File storage

In Cloudflare R2:

1. Create a bucket (for example `atlas-uploads`) in the EU jurisdiction. Leave public access **off**.
2. Create an **R2 API token** with *Object Read & Write* on that bucket only.
3. Note the **Access Key ID**, **Secret Access Key** and the S3 endpoint `https://<account-id>.r2.cloudflarestorage.com`.

### 4. Services on Render

Create these from your GitHub repository, all in the same region as the database:

| Service | Render type | Root directory | Start command |
| --- | --- | --- | --- |
| `atlas-api` | Web Service (Docker) | `backend` | *(default in Dockerfile)* |
| `atlas-worker` | Background Worker (Docker) | `backend` | `python -m atlas.worker` |
| `atlas-web` | Web Service (Docker) | `web` | *(default in Dockerfile)* |

On `atlas-api`, set **Pre-Deploy Command** to `python -m atlas.migrate` so the database is updated before each release.

### 5. Settings

In each service's **Environment** tab, add the variables from `.env.example` with real values. The API and worker need the database, Clerk and storage settings; the web app needs the Clerk keys and `NEXT_PUBLIC_API_URL`.

| Variable | Production value |
| --- | --- |
| `ENVIRONMENT` | `production` (also hides the API docs page) |
| `WEB_ORIGINS`, `CLERK_AUTHORIZED_PARTIES` | Your web app's address, e.g. `https://app.example.com` |
| `NEXT_PUBLIC_API_URL` | Your API's address, e.g. `https://api.example.com` |
| `STORAGE_ENDPOINT_URL` | Your R2 endpoint |
| `STORAGE_SERVER_SIDE_ENCRYPTION` | empty for R2; `AES256` for Amazon S3 |

`NEXT_PUBLIC_*` values are built into the web app, so they must also be available at build time (Render passes environment variables to Docker builds).

**Keep secrets out of chat, email and git.** They belong only in the hosting platform's environment settings.

### 6. Domains

Add custom domains to `atlas-web` and `atlas-api` in Render, then update `WEB_ORIGINS`, `CLERK_AUTHORIZED_PARTIES` and `NEXT_PUBLIC_API_URL`, and add the web domain in Clerk.

## Clerk setup

1. Create an application. Turn on the sign-in methods you want (email is enough to start).
2. **Enable Organizations** (Configure → Organizations). Atlas calls these *workspaces*; every dataset belongs to one.
3. **Add claims to the session token** (Configure → Sessions → Customize session token), so names and emails appear in Atlas:
   ```json
   { "email": "{{user.primary_email_address}}", "name": "{{user.full_name}}", "org_name": "{{org.name}}" }
   ```
4. Copy the **Publishable key**, **Secret key** and **Frontend API URL** (that last one is `CLERK_ISSUER`).

## How data is protected in this build

- **Company separation is enforced by the database.** Every table holding company data has row-level security; the app runs as a role that can only see the current workspace's rows. A missing filter in code returns nothing rather than another company's data.
- **Files are treated as hostile.** Type is checked by content, not name. Old Excel files, macro workbooks and oversized archives are refused. Files are parsed in a separate process with a memory cap and a time limit. Formulas are never evaluated.
- **Uploads are private.** Stored under random keys, never behind a public URL, and deleted automatically after 7 days. Deleting a dataset removes its file and rows immediately.
- **Logs hold no task content.** IDs, counts, timings and error codes only. Users see plain-language errors with a reference code; stack traces stay in server logs.
- **Exports can't run formulas.** Cells that start with `=`, `+`, `-`, `@`, tab or carriage return are written as text. Export files are private, downloaded only through the API and deleted with the upload after 7 days.
- **AI review sends as little as possible** (see above), passes item fields as data, accepts only a fixed answer format and treats anything else as "unsure".

## Not yet built

- Analysis of task exports (catalogues only for now; the screen says so).
- Rate limiting per company and a full content-security policy for the web app come in Phase 11 (security hardening).

See the Phase 4 plan document for the milestones.
