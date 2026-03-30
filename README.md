# ShoeMapping: RunRepeat Crawler (Phase 1)

This repository contains the first data collection step for the shoe recommendation engine: a crawler that discovers running shoe pages on `https://runrepeat.com/` and extracts shoe-specific **Lab Test Results** and **Audience Verdict** scores.

## Data Storage

Data is stored in a SQLite database optimized for ML workflows:

### Schema
- `shoe_id` (TEXT PRIMARY KEY) - Format: `"<brand>::<full_shoe_name>"`
- `brand` (TEXT) - Extracted brand name
- `shoe_name` (TEXT) - Full shoe name
- `source_url` (TEXT) - Original RunRepeat URL
- `audience_verdict` (INTEGER) - 0-100 score (nullable)
- `lab_test_results` (JSON) - Dynamic metrics as JSON string
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

# Flatten JSON metrics for modeling
metrics_df = json_normalize(df['lab_test_results'])
final_df = pd.concat([df.drop('lab_test_results', axis=1), metrics_df], axis=1)
```

## Features

- **Running shoes focus**: Crawls only `/sitemap/running-shoes` category
- **Cloudflare bypass**: Uses `cloudscraper` for reliable access
- **Incremental updates**: Skips already crawled shoes automatically
- **Dynamic metrics**: Handles varying lab test configurations per shoe
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

## RunRepeat Shoe Clustering

The new K-means helper looks up a shoe by human-readable name and returns the shoe's cluster label plus nearest cluster neighbors.

### Example
```python
from shoe_clustering import recommend_similar_shoes

result = recommend_similar_shoes("Adidas Adistar")
print(result["cluster_label"])
print(result["matched_shoe"])
print(result["nearest_shoes"])
```

### CLI
```bash
python3 shoe_clustering.py "Adidas Adistar"
```

### Features used by K-means
- Drop
- Heel stack
- Forefoot stack
- Energy return heel
- Weight
- Midsole softness (old method)
- Torsional rigidity

*Features with >30% missing values are automatically excluded*

### Notes
- Install dependencies with `pip install -r requirements.txt`
- The helper reads from `data/runrepeat_lab_tests.sqlite`
- Shoe lookup accepts human-readable names and resolves them against the dataset

## Notes

- URL discovery: Sitemap → Catalog pages → Individual shoe pages
- Lab Test Results: Extracts shoe-specific column (left of "Average")
- Re-runs are efficient: Only crawls new/updated shoes
- Database schema supports flexible metric addition over time
- Activity preprocessor ready for clustering algorithms
