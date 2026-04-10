# ShoeMapping: Shoe Explorer + Personalized Shoe Advisor

ShoeMapping now has two runtime surfaces built on the same offline shoe-intelligence layer:

- A **public shoe explorer** on Vercel that serves anonymous shoe-to-shoe recommendations from static JSON artifacts.
- A **personalization API** for runner profiles, CSV/GPX imports, owned-shoe tracking, explainable scoring, and optional Strava sync.

The shared shoe data still comes from [RunRepeat](https://runrepeat.com/) lab-test/spec crawls and offline metric-learning pipelines.

## Architecture Overview

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────────┐
│  RunRepeat   │────▶│  SQLite Database │────▶│  ML Training Pipeline │
│  Crawler     │     │  (lab test data) │     │  (ITML + K-Means)    │
└─────────────┘     └──────────────────┘     └──────────┬───────────┘
                                                        │
                    ┌──────────────────┐                │
                    │  Gemini API      │────────────────┘
                    │  (pairwise       │   similarity constraints
                    │   similarity)    │
                    └──────────────────┘
                                                        │
                    ┌──────────────────┐     ┌──────────────────────┐
                    │  shoes.catalog   │────▶│  public-web          │
                    │  .json + facets  │     │  (Vercel, stateless) │
                    └────────┬─────────┘     └──────────────────────┘
                             │
                    ┌────────▼─────────┐     ┌──────────────────────┐
                    │ precomputed_recs │────▶│ personalization-api  │
                    │ .json            │     │ + worker + Postgres   │
                    └──────────────────┘     └──────────────────────┘
```

The public runtime still consumes **only** static JSON artifacts: `shoes.catalog.json` (now including derived shoe facets) and `precomputed_recommendations.json`. The personalization runtime layers user-owned shoes, imported activities, runner profiles, and explanation caches on top of the same catalog.

## Setup

```bash
python3 -m venv env
source env/bin/activate

# Public Vercel runtime
pip install -r requirements.txt

# Personalized API + worker runtime
pip install -r requirements-personalization.txt

# Full local development stack (ML + personalization + tests)
pip install -r requirements-full.txt
```

Copy `.env.example` to `.env` and fill in the values you need. A `GOOGLE_GEMINI_API_KEY` is only required for generating synthetic training data.

## Data Collection

A web crawler discovers running shoe pages from RunRepeat's sitemap and extracts lab-test metrics, specs, and audience verdict scores into a SQLite database.

```bash
# Quick test crawl
python3 -m crawler.runrepeat_crawler --max-shoes 20 --workers 4

# Full crawl (running shoes only)
python3 -m crawler.runrepeat_crawler --workers 8

# Fresh rebuild with clean database
python3 -m crawler.runrepeat_crawler --workers 8 --rebuild-db
```

### Database Schema

| Column | Type | Description |
|--------|------|-------------|
| `shoe_id` | TEXT PK | Format: `"<brand>::<shoe_name>"` |
| `brand` | TEXT | Extracted brand name |
| `shoe_name` | TEXT | Full shoe name |
| `source_url` | TEXT | RunRepeat URL |
| `audience_verdict` | INTEGER | User rating 0–100 (nullable) |
| `lab_test_results` | JSON | Dynamic metrics and specs |
| `crawled_at` | TEXT | ISO timestamp |

Default path: `data/runrepeat_lab_tests.sqlite`

### ML Data Access

```python
import sqlite3, pandas as pd
from pandas import json_normalize

conn = sqlite3.connect('data/runrepeat_lab_tests.sqlite')
df = pd.read_sql_query("SELECT * FROM shoes", conn)
metrics_df = json_normalize(df['lab_test_results'].apply(json.loads))
final_df = pd.concat([df.drop('lab_test_results', axis=1), metrics_df], axis=1)
```

### Crawler Features

- **Running shoes only** — crawls `/sitemap/running-shoes`
- **Cloudflare bypass** — uses `cloudscraper`
- **Incremental updates** — skips already-crawled shoes
- **Dynamic metrics** — handles varying lab test configurations per shoe
- **Specs extraction** — Terrain, Arch Support, Pronation, Arch Type, Use, Strike Pattern, Pace

## Recommendation Algorithms

Three recommendation approaches are implemented, each building on the previous:

### 1. K-Means Clustering (Baseline)

Standard K-Means on scaled lab-test features. Assigns shoes to clusters and returns in-cluster neighbors ranked by Euclidean distance.

```python
from ml.shoe_clustering import recommend_similar_shoes
result = recommend_similar_shoes("Adidas Adistar")
```

```bash
python3 -m ml.shoe_clustering "Adidas Adistar"
```

**Features:** Drop, Heel stack, Forefoot stack, Energy return heel, Weight, Midsole softness, Torsional rigidity, Pace (one-hot encoded). Features with >30% missing values are automatically excluded.

**Limitation:** Hard cluster boundaries — a shoe on the edge of Cluster A cannot be recommended shoes just across the border in Cluster B.

### 2. Supervised XGBoost (Gemini-Trained)

Trains an XGBoost regressor on pairwise feature differences (Δ drop, Δ weight, etc.) with similarity labels generated by the Gemini LLM. Scores every shoe pair on a 0–100 scale.

```bash
python scripts/synthetic_dataset_generator.py   # ~50K pairs via Gemini API
python scripts/supervised_shoe_matcher.py        # Train XGBoost (uses ml.supervised_shoe_matcher)
python scripts/evaluate_supervised_model.py      # Evaluate
```

**Performance vs K-Means baseline:**

| Metric | K-Means | XGBoost | Improvement |
|--------|---------|---------|-------------|
| MAE | 30.70 | 5.23 | **83%** |
| RMSE | 34.29 | 8.56 | **75%** |
| Correlation | ~0.4 | 0.939 | — |
| NDCG@5 | — | 0.985 | — |

### 3. Hybrid ITML + K-Means (Production)

The production algorithm combines metric learning with clustering:

1. **Feature Engineering** — extract and scale lab-test features (via `ShoeKMeansClusterer`)
2. **Pairwise Constraints** — convert Gemini similarity scores into Must-Link (≥60) and Cannot-Link (≤15) pairs
3. **ITML Metric Learning** — learn a Mahalanobis distance that warps the feature space so similar shoes (per Gemini) are closer together
4. **Recommendation** — compute distances in the ITML-transformed space to ALL shoes, convert to 0–100 similarity via Gaussian kernel

This approach avoids both the hard-boundary problem of pure K-Means and the O(n²) inference cost of XGBoost (ITML distances are simple vector operations).

```bash
python -m ml.hybrid_kmeans_pipeline "Nike Pegasus 41"
```

**Current recommendation statistics (641 shoes):**

| Stat | Value |
|------|-------|
| Mean similarity score | 71.19 |
| Score range | 48.73 – 95.82 |
| Avg brand diversity | 7.5 brands per shoe |
| Recs per shoe | 15 |

## Runtime Surfaces

### Public Web

The public FastAPI app serves:

- `/` — home page with Explore vs Personalize entry points
- `/explore` — anonymous catalog explorer
- `/api/catalog/shoes`
- `/api/catalog/recommendations`
- `/api/catalog/shoes/{shoe_id}`

Run it locally:

```bash
source env/bin/activate
pip install -r requirements.txt
uvicorn webapp.main:app --reload
```

Open `http://127.0.0.1:8000`.

### Personalization API

The personalization FastAPI app serves:

- `POST /api/personalization/session/bootstrap`
- `POST /api/imports`
- `GET /api/imports/{job_id}`
- `GET /api/profile`
- `PATCH /api/profile`
- `GET /api/rotation`
- `POST /api/rotation/shoes`
- `PATCH /api/rotation/shoes/{shoe_id}`
- `GET /api/recommendations/personalized?context=easy|long|workout|trail|replace`
- `POST /api/feedback`
- `GET /auth/strava/start`
- `GET /auth/strava/callback`
- `GET /webhooks/strava`
- `POST /webhooks/strava`

Run it locally:

```bash
source env/bin/activate
pip install -r requirements-personalization.txt
alembic upgrade head
uvicorn api.personalization_main:app --reload --port 9000
```

In a second terminal, start the worker if you disable inline jobs:

```bash
source env/bin/activate
python -m personalization.worker
```

### Personalization Product Model

The personalized runtime is intentionally a **runner-context recommender**, not a biomechanics oracle. It uses:

- manual rotation input,
- CSV or GPX imports,
- runner-profile aggregation,
- transparent scoring,
- explanation-first recommendation cards,
- soft retirement alerts,
- optional Strava sync behind env flags.

It does **not** try to infer foot strike from cadence or make injury-risk claims.

## Deployment

### Public Web on Vercel

The public app continues to deploy to Vercel as a serverless function. Because Vercel Lambda functions have a **250 MB uncompressed / 500 MB total size limit**, all ML computation happens offline. The deployed app reads only:

- `data/shoes.catalog.json` — compact shoe metadata
- `data/precomputed_recommendations.json` — top-15 recommendations per shoe (~2.5 MB)

Runtime dependencies are minimal: `fastapi`, `jinja2`, `uvicorn` (see `requirements.txt`).

The Vercel project also needs `PERSONALIZATION_BASE_URL` if you want the public site to link into the personalization flow. When that env var is not set, the public UI now disables those CTAs instead of sending users to a localhost URL.

### Personalization API + Worker

The personalization runtime is designed for a persistent host with Postgres and two process types:

```bash
web: uvicorn api.personalization_main:app --host 0.0.0.0 --port ${PORT:-8000}
worker: python -m personalization.worker
```

The required runtime secrets are:

- `DATABASE_URL`
- `SESSION_SECRET`
- `APP_BASE_URL`
- `PUBLIC_WEB_BASE_URL`
- `PERSONALIZATION_BASE_URL`
- `ENABLE_STRAVA_UI`
- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_VERIFY_TOKEN`
- `STRAVA_REDIRECT_URI`

### Regenerating Recommendations

After crawling new shoes or retraining, regenerate the deployment data:

```bash
source env/bin/activate
pip install -r requirements-full.txt

# 1. Regenerate shoe catalog from SQLite
python generate_catalog.py

# 2. (Optional) Retrain — only needed if the model or training data changes
python scripts/synthetic_dataset_generator.py   # Generate Gemini similarity labels
python -m ml.supervised_shoe_matcher              # Train XGBoost model
python scripts/evaluate_supervised_model.py      # Verify performance

# 3. Re-compute recommendations (default: hybrid ITML backend)
python precompute_recommendations.py --backend hybrid

# 4. Deploy
git add data/shoes.catalog.json data/precomputed_recommendations.json
git commit -m "Regenerate recommendations"
git push
```

The `--backend` flag selects the algorithm:
- `hybrid` (default) — ITML + K-Means in transformed space
- `supervised` — XGBoost pairwise regression

### Dependency Files

| File | Purpose |
|------|---------|
| `requirements.txt` | Slim runtime deps for Vercel |
| `requirements-personalization.txt` | Persistent API + worker deps |
| `requirements-full.txt` | All ML libraries for local training |
| `.vercelignore` | Excludes ML scripts, SQLite, CSV, PKL from deploy |
| `vercel.json` | Public runtime rewrite configuration |
| `alembic.ini` + `alembic/` | DB migrations for personalization runtime |
| `Procfile` | Persistent web + worker process definitions |

## Project Structure

```
ShoeMapping/
├── ml/                              # ML pipeline package
│   ├── shoe_clustering.py           # K-Means baseline
│   ├── supervised_shoe_matcher.py   # XGBoost pairwise model
│   ├── hybrid_kmeans_pipeline.py    # ITML + K-Means pipeline
│   ├── hybrid_matching_service.py   # Service wrapper for hybrid pipeline
│   └── supervised_matching_service.py # Service wrapper for XGBoost
├── scripts/                         # One-off & training scripts
│   ├── synthetic_dataset_generator.py # Gemini API → training labels
│   ├── evaluate_supervised_model.py   # Model evaluation metrics
│   ├── elbow_plot.py                # Cluster count analysis
│   ├── data_preprocessor.py         # Legacy activity CSV preprocessor
│   ├── check_gemini_models.py       # Gemini model listing
│   ├── example_usage.py             # Data processor usage example
│   └── test_kmeans_integration.py   # K-Means + XGBoost integration test
├── crawler/                         # RunRepeat web crawler
│   ├── runrepeat_crawler.py
│   └── database.py                  # SQLite database operations
├── personalization/                 # DB models, imports, profile, scoring, jobs, Strava
├── api/
│   └── personalization_main.py      # Persistent API entrypoint
├── alembic/                         # Personalization DB migrations
├── webapp/
│   ├── main.py                      # Public Vercel app entrypoint
│   ├── app_factory.py               # Public vs personalization app builders
│   ├── routers/                     # Catalog + personalization route modules
│   ├── models.py                    # Catalog API schemas
│   ├── services.py                  # Catalog + static recommendation services
│   ├── templates/                   # Home, explore, personalize templates
│   └── static/                      # Shared CSS + browser JS
├── data/
│   ├── runrepeat_lab_tests.sqlite   # Raw crawled data (not deployed)
│   ├── shoes.catalog.json           # Compact metadata + derived facets
│   ├── precomputed_recommendations.json  # Recommendations (deployed)
│   ├── supervised_shoe_matcher.pkl  # Trained model (not deployed)
│   └── synthetic_similarity_dataset.csv  # Training data (not deployed)
├── shoe_catalog_facets.py           # Facet derivation for shared shoe catalog
├── precompute_recommendations.py    # Generate deployment JSON
├── generate_catalog.py              # SQLite → catalog JSON
├── main.py                          # Vercel entrypoint
├── Procfile                         # Persistent runtime process types
├── render.yaml                      # Render blueprint (API + Postgres)
└── requirements*.txt                # Dependency files (pinned)
```

## Validation

The implemented smoke and unit tests live in `tests/`:

```bash
source env/bin/activate
pytest -q tests
```
