# ShoeMapping: Intelligent Running Shoe Recommendation System

This repository contains a complete shoe recommendation engine that crawls running shoe data from `https://runrepeat.com/`, trains supervised learning models, and serves recommendations via a web API. The system extracts shoe-specific **Lab Test Results**, **Specs**, and **Audience Verdict** scores, then uses advanced ML algorithms to find similar shoes.

## Key Features
- **Web crawler** for RunRepeat shoe data with lab test metrics
- **Supervised XGBoost model** with 83% improvement over K-means baseline
- **Pre-computed recommendations** for fast web deployment
- **FastAPI web app** with live demo
- **Vercel deployment** with serverless functions

## Data Storage

Data is stored in a SQLite database optimized for ML workflows:

### Schema
- `shoe_id` (TEXT PRIMARY KEY) - Format: `"<brand>::<full_shoe_name>"`
- `brand` (TEXT) - Extracted brand name
- `shoe_name` (TEXT) - Full shoe name
- `source_url` (TEXT) - Original RunRepeat URL
- `audience_verdict` (INTEGER) - 0-100 score (nullable)
- `lab_test_results` (JSON) - Dynamic metrics and Specs fields as JSON string
- `crawled_at` (TEXT) - ISO timestamp

### Output
Default database: `data/runrepeat_lab_tests.sqlite`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Crawling Data
Quick test crawl:
```bash
python3 -m crawler.runrepeat_crawler --max-shoes 20 --workers 4
```

Full crawl (running shoes only):
```bash
python3 -m crawler.runrepeat_crawler --workers 8
```

Fresh rebuild with a clean database:
```bash
python3 -m crawler.runrepeat_crawler --workers 8 --rebuild-db
```

Custom output location:
```bash
python3 -m crawler.runrepeat_crawler --output data/custom_shoes.sqlite
```

### ML Data Access
```python
import sqlite3
import pandas as pd
from pandas import json_normalize

# Load data for ML
conn = sqlite3.connect('data/runrepeat_lab_tests.sqlite')
df = pd.read_sql_query("SELECT * FROM shoes", conn)

# Flatten JSON metrics and Specs fields for modeling
metrics_df = json_normalize(df['lab_test_results'])
final_df = pd.concat([df.drop('lab_test_results', axis=1), metrics_df], axis=1)
```

## Features

- **Running shoes focus**: Crawls only `/sitemap/running-shoes` category
- **Cloudflare bypass**: Uses `cloudscraper` for reliable access
- **Incremental updates**: Skips already crawled shoes automatically
- **Dynamic metrics**: Handles varying lab test configurations per shoe
- **Specs extraction**: Captures `Terrain`, `Arch Support`, `Pronation`, `Arch Type`, `Use`, `Strike Pattern`, and `Pace`
- **ML-ready**: Direct Pandas integration with JSON normalization
- **Audience Verdict**: Captures user rating scores (0-100)

## Activity Data Processing

For clustering analysis, use the built-in data preprocessor:

```python
from data_preprocessor import ActivityDataProcessor

# Initialize processor
processor = ActivityDataProcessor()

# Process your activity CSV
processed_data = processor.process("your_activities.csv")

# Save for clustering
processor.save_processed_data(processed_data, "running_activities.csv")
```

### Command Line Usage
```bash
python3 data_preprocessor.py input_activities.csv processed_running_activities.csv --summary
```

### Extracted Features
- Activity ID, Date, Type, Gear
- Distance, Moving Time, Average Speed
- Grade Adjusted Pace, Elevation Gain
- Cadence, Heart Rate, Training Load
- Relative Effort, Perceived Exertion
- Weather Temperature

### Data Quality
- Filters to "Run" activities only
- Handles missing values gracefully
- Converts to proper data types
- Provides summary statistics

## Shoe Recommendation Algorithms

This project now includes **two** recommendation approaches: a classic K-means clustering baseline and a state-of-the-art supervised learning model.

### 1. K-means Clustering (Baseline)
The K-means helper looks up a shoe by human-readable name and returns the shoe's cluster label plus nearest cluster neighbors.

#### Example
```python
from shoe_clustering import recommend_similar_shoes

result = recommend_similar_shoes("Adidas Adistar")
print(result["cluster_label"])
print(result["matched_shoe"])
print(result["nearest_shoes"])
```

#### CLI
```bash
python3 shoe_clustering.py "Adidas Adistar"
```

#### Features used by K-means
- Drop
- Heel stack
- Forefoot stack
- Energy return heel
- Weight
- Midsole softness (old method)
- Torsional rigidity

*Features with >30% missing values are automatically excluded*

### 2. Supervised Learning Model (Production)
The supervised XGBoost model learns similarity patterns from synthetic training data and significantly outperforms the K-means baseline.

#### Performance Metrics
- **MAE**: 5.23 (vs K-means: 30.70) - **83% improvement**
- **RMSE**: 8.56 (vs K-means: 34.29) - **75% improvement**
- **Correlation**: 0.939
- **Within 10 points**: 84.8%
- **NDCG@5**: 0.985 (excellent ranking quality)

#### Training
```bash
# Generate synthetic training data
python synthetic_dataset_generator.py

# Train supervised model
python supervised_shoe_matcher.py

# Evaluate model performance
python evaluate_supervised_model.py
```

#### Features
- Uses comprehensive lab test metrics and specs
- Handles missing values with median imputation
- Learns non-linear similarity patterns
- Optimized for ranking quality (NDCG)

### Model Comparison
| Metric | K-means | Supervised | Improvement |
|--------|---------|------------|-------------|
| MAE | 30.70 | 5.23 | **83%** |
| RMSE | 34.29 | 8.56 | **75%** |
| Correlation | ~0.4 | 0.939 | **135%** |

The supervised model is now the **production algorithm** used for all recommendations.

## Shoe Matcher Web App

This repository now includes a small FastAPI web app for trying the matcher in a browser.

### Run locally
```bash
source env/bin/activate
pip install -r requirements.txt
uvicorn webapp.main:app --reload
```

Open `http://127.0.0.1:8000` in your browser.

### API endpoints
- `GET /api/shoes` — returns the shoe list for the dropdown. Supports `?terrain=Road`, `?terrain=Trail`, or no terrain filter for Both.
- `POST /api/recommendations` — takes a shoe selection and returns the matched shoe plus similar recommendations.

### Terrain behavior
- `Road` and `Trail` filter both the dropdown and the clustering dataset.
- `Both` means no terrain filter is sent to clustering.

## Vercel Deployment

The web app is deployed on Vercel as a serverless function. To keep the Lambda
under the 500 MB size limit, **all shoe recommendations are pre-computed** into
a static JSON file. The heavy ML libraries (scikit-learn, xgboost, pandas, etc.)
are **not** installed at runtime on Vercel.

### How it works
1. `data/shoes.catalog.json` - compact shoe metadata (generated from SQLite).
2. `data/precomputed_recommendations.json` - top-15 similar shoes per shoe,
   pre-computed with the **supervised XGBoost model** (~2.5 MB).
3. The FastAPI app reads both JSON files at startup - no ML inference at runtime.
4. All recommendations use the production supervised algorithm with 83% MAE improvement.

### Regenerating pre-computed data

After crawling new shoes or retraining the model, regenerate the deployment data:

```bash
source env/bin/activate
pip install -r requirements-full.txt   # full ML deps needed for generation

# 1. Regenerate the shoe catalog from SQLite
python generate_catalog.py

# 2. Train/retrain the supervised model (if needed)
python synthetic_dataset_generator.py  # Generate training data
python supervised_shoe_matcher.py      # Train model
python evaluate_supervised_model.py   # Verify performance

# 3. Re-compute recommendations with supervised model (~10 min for 641 shoes)
python precompute_recommendations.py

# 4. Commit and push to trigger Vercel redeploy
git add data/shoes.catalog.json data/precomputed_recommendations.json data/supervised_shoe_matcher.pkl
git commit -m "Update supervised model recommendations"
git push
```

### Dependency files
- `requirements.txt` — slim runtime deps for Vercel (fastapi, jinja2, uvicorn).
- `requirements-full.txt` — all dependencies including ML libraries for local
  development, training, and pre-computation.

## Notes

- URL discovery: Sitemap → Catalog pages → Individual shoe pages
- Lab Test Results: Extracts shoe-specific column (left of "Average")
- Re-runs are efficient: Only crawls new/updated shoes
- Database schema supports flexible metric addition over time
- Activity preprocessor ready for clustering algorithms
- Use `--rebuild-db` when you want a fresh crawl with new extracted fields
