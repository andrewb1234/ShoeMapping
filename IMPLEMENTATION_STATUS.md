# Personalized Shoe Advisor MVP: Implementation Status

## Initial Ask

The original request was to:

- read `README.md` and `PRODUCT_NEXT.md`,
- assess the product direction from a product and UX perspective,
- use current research on running shoes and biomechanics to shape the implementation,
- implement the new Personalized Shoe Advisor MVP,
- keep the existing static shoe-catalog experience,
- add a split architecture with:
  - a public stateless runtime on Vercel,
  - a persistent personalization API with database-backed state, imports, Strava integration, and background jobs,
- make any architectural changes required by the current lightweight stack,
- and set up infrastructure as needed.

## What Was Implemented

This repository now contains two application surfaces built from a shared FastAPI codebase:

- a public catalog explorer and anonymous recommendation experience,
- a separate personalization runtime with session bootstrap, owned-shoe tracking, import parsing, runner-profile computation, explainable recommendations, job processing, and Strava scaffolding.

The public experience was redesigned to remove placeholder/random behavior and “AI theater.” It now focuses on deterministic catalog recommendations, lab-backed shoe facets, and a cleaner split between anonymous exploration and future personalization.

The personalization implementation is present in code, but the persistent production infrastructure for it has not yet been provisioned. The public site degrades cleanly when that API is not configured.

## Current Architecture

### Public Runtime

- Entry point: `webapp.main:app`
- App factory: [webapp/app_factory.py](/Users/andrewbetbadal/CascadeProjects/ShoeMapping/webapp/app_factory.py)
- Deployed on Vercel
- Uses only static artifacts:
  - `data/shoes.catalog.json`
  - `data/precomputed_recommendations.json`
- Serves:
  - `/`
  - `/explore`
  - `/api/catalog/shoes`
  - `/api/catalog/recommendations`
  - `/api/catalog/shoes/{shoe_id}`
  - health endpoints

### Personalization Runtime

- Entry point: `api.personalization_main:app`
- Runs as a persistent FastAPI process
- Background worker entry point: `python -m personalization.worker`
- Uses SQLAlchemy + Alembic
- Designed for Postgres in production
- Supports:
  - guest-session bootstrap,
  - runner profile generation,
  - manual owned-shoe management,
  - CSV import,
  - GPX import,
  - job-backed recomputation,
  - explainable recommendation scoring,
  - feedback capture,
  - Strava OAuth + webhook scaffolding

### Shared Catalog Layer

- `generate_catalog.py` now enriches the catalog with derived shoe facets
- `shoe_catalog_facets.py` computes:
  - `cushion_level`
  - `stability_level`
  - `weight_class`
  - `ride_role`
  - `durability_proxy`
  - `drop_band`
- `precompute_recommendations.py` still generates the anonymous recommendation artifact used by the public runtime

## Deployment Status

- Public production deployment is live at:
  - `https://shoe-mapping.vercel.app`
- Public Vercel deployment is healthy and under bundle limits
- The public site now disables personalization CTAs unless `PERSONALIZATION_BASE_URL` is configured
- The personalization API, worker, and managed Postgres are not yet deployed in production

## Files Changed By This Implementation

### Modified Files

- `.vercelignore`
- `README.md`
- `data/shoes.catalog.json`
- `generate_catalog.py`
- `precompute_recommendations.py`
- `requirements-full.txt`
- `webapp/main.py`
- `webapp/models.py`
- `webapp/services.py`
- `webapp/static/app.js`
- `webapp/static/styles.css`

### New Files

- `.env.example`
- `.python-version`
- `IMPLEMENTATION_STATUS.md`
- `Procfile`
- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/20260409_000001_initial_personalization.py`
- `api/__init__.py`
- `api/personalization_main.py`
- `personalization/__init__.py`
- `personalization/db.py`
- `personalization/imports.py`
- `personalization/jobs.py`
- `personalization/models.py`
- `personalization/profile.py`
- `personalization/rotation.py`
- `personalization/scoring.py`
- `personalization/schemas.py`
- `personalization/security.py`
- `personalization/session.py`
- `personalization/strava.py`
- `personalization/utils.py`
- `personalization/worker.py`
- `requirements-personalization.txt`
- `shoe_catalog_facets.py`
- `tests/conftest.py`
- `tests/test_catalog_facets.py`
- `tests/test_import_parsers.py`
- `tests/test_personalization_api.py`
- `vercel.json`
- `webapp/app_factory.py`
- `webapp/config.py`
- `webapp/deps.py`
- `webapp/routers/__init__.py`
- `webapp/routers/catalog.py`
- `webapp/routers/feedback.py`
- `webapp/routers/imports.py`
- `webapp/routers/personalization.py`
- `webapp/routers/rotation.py`
- `webapp/routers/strava.py`
- `webapp/static/personalize.js`
- `webapp/templates/explore.html`
- `webapp/templates/home.html`
- `webapp/templates/personalize.html`

## Key Functional Changes

### Public UI

- New landing page with a clean split between:
  - `Explore shoes`
  - `Personalize my recommendations`
- New anonymous catalog explorer page
- Deterministic lab-data presentation
- No random metrics or fake personalized explanations
- Clean Vercel-safe behavior when personalization infrastructure is missing

### Personalization

- Signed guest-session cookie flow
- DB-backed user records
- Owned-shoe tracking with retirement targets
- Runner profile generation from recent activity history
- CSV import support
- GPX import support
- Recompute job pipeline
- Explainable recommendation output by context:
  - `easy`
  - `long`
  - `workout`
  - `trail`
  - `replace`

### Strava

- OAuth start/callback routes exist
- Webhook verification and ingestion routes exist
- Token persistence/encryption scaffolding exists
- Feature remains gated by env vars and deployment setup

## Validation Completed

The following validation has already been completed:

- `pytest -q tests`
- public runtime smoke tests
- personalization runtime smoke tests
- Vercel preview deployment
- Vercel production deployment
- production catalog API verification via `vercel curl`

Current automated test result:

- `4 passed`

## How To Run Locally

### Public Runtime

```bash
cd /Users/andrewbetbadal/CascadeProjects/ShoeMapping
source env/bin/activate
uvicorn webapp.main:app --reload --port 8000
```

Open:

- `http://127.0.0.1:8000`

### Personalization Runtime

```bash
cd /Users/andrewbetbadal/CascadeProjects/ShoeMapping
source env/bin/activate
pip install -r requirements-personalization.txt
uvicorn api.personalization_main:app --reload --port 9000
```

Open:

- `http://127.0.0.1:9000`

### Worker

```bash
cd /Users/andrewbetbadal/CascadeProjects/ShoeMapping
source env/bin/activate
python -m personalization.worker
```

### Local Database Migration

```bash
cd /Users/andrewbetbadal/CascadeProjects/ShoeMapping
source env/bin/activate
alembic upgrade head
```

## Next Steps To Get Personalization Started In Production

### 1. Provision Postgres

Create a managed Postgres database on your persistent host provider.

The application expects:

- `DATABASE_URL`

### 2. Deploy the Personalization API

Use a persistent Python host such as Render.

Build command:

```bash
pip install -r requirements-personalization.txt
```

Start command:

```bash
uvicorn api.personalization_main:app --host 0.0.0.0 --port $PORT
```

### 3. Deploy the Background Worker

Use the same repo and environment.

Build command:

```bash
pip install -r requirements-personalization.txt
```

Start command:

```bash
python -m personalization.worker
```

### 4. Set Environment Variables On The Personalization Host

Required:

```text
APP_ENV=production
DATABASE_URL=postgresql://...
SESSION_SECRET=<random-secret>
APP_BASE_URL=https://<personalization-host>
PERSONALIZATION_BASE_URL=https://<personalization-host>
PUBLIC_WEB_BASE_URL=https://shoe-mapping.vercel.app
AUTO_CREATE_DB=false
INLINE_JOB_EXECUTION=false
ENABLE_STRAVA_UI=false
```

Optional for Strava later:

```text
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
STRAVA_VERIFY_TOKEN=
STRAVA_REDIRECT_URI=https://<personalization-host>/auth/strava/callback
```

### 5. Run Migrations Against Production Postgres

```bash
cd /Users/andrewbetbadal/CascadeProjects/ShoeMapping
source env/bin/activate
export DATABASE_URL='postgresql://...'
alembic upgrade head
```

### 6. Verify The Personalization API

Check:

- `https://<personalization-host>/api/personalization/readyz`

### 7. Connect The Public Site To The Personalization API

Set this env var in the Vercel project:

```text
PERSONALIZATION_BASE_URL=https://<personalization-host>
```

Then redeploy Vercel.

### 8. Enable Strava Later

Once the personalization host is live:

- create a Strava app,
- set the callback URL to:
  - `https://<personalization-host>/auth/strava/callback`
- set the webhook URL to:
  - `https://<personalization-host>/webhooks/strava`
- add the Strava env vars,
- and flip:

```text
ENABLE_STRAVA_UI=true
```

## Recommended Immediate Follow-Up

- add a `render.yaml` so the API, worker, and Postgres can be provisioned from one blueprint
- provision the personalization host
- wire `PERSONALIZATION_BASE_URL` into Vercel
- do an end-to-end test of:
  - session bootstrap
  - owned shoe creation
  - CSV upload
  - GPX upload
  - recommendation refresh
  - worker processing

